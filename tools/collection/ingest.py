#!/usr/bin/env python3
"""Public-source candidate ledger. Stdlib only; no recursive crawling or credentials."""
import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path

AGENT = 'AlgoTopResearch/1.0'
MAX_BYTES = 512_000
TRACKING = {'fbclid', 'gclid', 'sourceSSR'}
SENSITIVE = {'token','access_token','xsec_token','auth','authorization','cookie','password','key','api_key','signature'}

def canonical(url):
    p = urllib.parse.urlsplit(url.strip())
    if p.scheme.lower() != 'https' or not p.hostname or p.username or p.password or p.port or '\\' in url or any(ord(c)<32 for c in url):
        raise ValueError('Only credential-free HTTPS domain URLs with default port are accepted')
    host = p.hostname.lower().encode('idna').decode('ascii')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('IP literals are not public-source candidates')
    if '.' not in host or host.endswith(('.local','.internal','.localhost')) or host.endswith('.'):
        raise ValueError('Nonpublic hostname')
    query = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    if any(k.lower() in SENSITIVE for k,v in query):
        raise ValueError('Credential-like query parameter')
    query = [(k,v) for k,v in query if not k.lower().startswith('utm_') and k not in TRACKING]
    return urllib.parse.urlunsplit(('https',host,p.path or '/',urllib.parse.urlencode(query),''))

def import_rows(rows, origin):
    ledger = {}
    for index,row in enumerate(rows):
        url = canonical(row['url'])
        published = row.get('publishedOrEditedDate') or row.get('publishedDate')
        interview = row.get('interviewDate')
        date = interview or published
        status = 'unknown'
        if date and re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            try:
                parsed = dt.date.fromisoformat(date)
                status = 'before_2022' if parsed.year < 2022 else 'date_claim_needs_review'
            except ValueError:
                status = 'invalid_date_claim'
        if url not in ledger:
            ledger[url] = {'id':hashlib.sha256(url.encode()).hexdigest()[:20], 'url':url,
                'verification_status':'candidate_unverified', 'date_status':status,
                'interview_date':interview, 'publication_date_claim':published, 'discoveries':[]}
        ledger[url]['discoveries'].append({'input_file':origin,'input_index':index,'record':row})
    return sorted(ledger.values(),key=lambda r:r['url'])

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def transport(url):
    """Managed HTTPS egress required; no cookies, target auth or redirects."""
    url = canonical(url)
    if not urllib.request.getproxies().get('https') or urllib.request.proxy_bypass(urllib.parse.urlsplit(url).hostname):
        raise ValueError('A managed HTTPS proxy is required; direct network is disabled')
    opener = urllib.request.build_opener(NoRedirect())
    req = urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'text/html,text/plain','Accept-Encoding':'identity'})
    try:
        response = opener.open(req,timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES:
            raise ValueError('Response exceeds 512 KB limit')
        return response.status,response.headers.get('Content-Type',''),body

class Title(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.inside=False;self.parts=[]
    def handle_starttag(self, tag, attrs):
        if tag=='title':self.inside=True
    def handle_endtag(self, tag):
        if tag=='title':self.inside=False
    def handle_data(self,data):
        if self.inside:self.parts.append(data)

class Pipeline:
    def __init__(self, cache, policy, transport=transport, today=None, sleeper=time.sleep):
        self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True)
        self.policy=policy;self.transport=transport;self.today=today or dt.date.today().isoformat()
        self.sleep=sleeper;self.robots={};self.paused=set();self.delay=2.0
    def permitted(self,url):
        p=urllib.parse.urlsplit(url);rule=self.policy.get(p.hostname,{})
        try:
            age=(dt.date.fromisoformat(self.today)-dt.date.fromisoformat(rule['reviewed_at'])).days
            # Disallow ambiguous decoded paths so allowlist prefixes cannot be escaped.
            decoded=urllib.parse.unquote(p.path)
            safe_path='..' not in decoded.split('/') and '\\' not in decoded and '%' not in decoded
            return (rule.get('terms_status')=='permitted' and bool(rule.get('terms_url')) and 0<=age<=30 and safe_path
                and (any(p.path.startswith(prefix) for prefix in rule.get('allowed_paths',[]) if prefix.startswith('/') and prefix.endswith('/'))
                     or (not p.query and p.path in rule.get('allowed_exact_paths',[]))))
        except (KeyError,ValueError,TypeError):return False
    def request(self,url):
        for attempt in range(2):
            self.sleep(self.delay)
            reply=self.transport(url)
            if reply[0] not in {500,502,503,504} or attempt==1:return reply
            self.sleep(2**attempt)
    def fetch(self,raw_url):
        record={'url':raw_url,'checked_at':self.today,'verification_status':'candidate_unverified'}
        try:
            url=canonical(raw_url);record['url']=url
            if not self.permitted(url):return dict(record,status='policy_blocked')
            host=urllib.parse.urlsplit(url).hostname
            if host in self.paused:return dict(record,status='host_paused')
            robots_url=f'https://{host}/robots.txt';record['robots_url']=robots_url
            if host not in self.robots:
                code,ctype,body=self.request(robots_url)
                if code not in {200,404,410} or (code==200 and ('html' in ctype or body.lstrip().startswith(b'<'))):
                    self.paused.add(host)
                    return dict(record,status='robots_unavailable',robots_http=code)
                parser=urllib.robotparser.RobotFileParser()
                parser.parse(body.decode('utf-8','replace').splitlines() if code==200 else [])
                self.robots[host]=parser
            parser=self.robots[host]
            if not parser.can_fetch(AGENT,url):return dict(record,status='robots_blocked')
            delay=parser.crawl_delay(AGENT) or 0
            rate=parser.request_rate(AGENT)
            self.delay=max(2.0,delay,rate.seconds/rate.requests if rate and rate.requests else 0)
            key=hashlib.sha256(url.encode()).hexdigest();cached=self.cache/(key+'.json')
            if cached.exists():
                old=json.loads(cached.read_text())
                if old.get('url')==url and old.get('checked_at')==self.today:
                    return dict(old,status='cached_unverified')
            code,ctype,body=self.request(url);record['http_status']=code
            if code in {401,403,429}:self.paused.add(host)
            if code!=200:return dict(record,status=f'http_{code}')
            if ctype.split(';')[0].strip().lower() not in {'text/html','application/xhtml+xml','text/plain'}:
                return dict(record,status='unsupported_content')
            html=body.decode('utf-8','replace');title=Title();title.feed(html)
            record.update(status='fetched_unverified',title=' '.join(title.parts).strip()[:300],
                content_sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),content_type=ctype)
            # Metadata cache deliberately excludes full third-party page text.
            cached.write_text(json.dumps(record,ensure_ascii=False,indent=2))
            return record
        except (ValueError,OSError,urllib.error.URLError) as exc:
            return dict(record,status='fetch_error',error=type(exc).__name__+': '+str(exc)[:200])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs',nargs='+',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fetch',action='store_true',help='Optional policy-gated fetch; default is offline')
    parser.add_argument('--policy',type=Path)
    parser.add_argument('--cache',type=Path,default=Path('.cache'))
    parser.add_argument('--limit',type=int,default=10,help='Max fetch candidates, hard cap 100, serial concurrency 1')
    args=parser.parse_args()
    ledger={}
    for file in args.inputs:
        data=json.loads(file.read_text());rows=data if isinstance(data,list) else data['sources']
        for row in import_rows(rows,str(file)):
            if row['url'] in ledger:ledger[row['url']]['discoveries'].extend(row['discoveries'])
            else:ledger[row['url']]=row
    rows=sorted(ledger.values(),key=lambda r:r['url'])
    if args.fetch:
        if not args.policy:parser.error('--fetch requires --policy with reviewed terms and allowlisted paths')
        pipeline=Pipeline(args.cache,json.loads(args.policy.read_text()))
        for row in rows[:max(0,min(args.limit,100))]:row['fetch']=pipeline.fetch(row['url'])
    result={'schema_version':1,'scope':'2022-present public algorithm interview candidates; not exhaustive',
        'count_policy':'URLs are candidates, not verified interviews or independent people',
        'unique_urls':len(rows),'input_records':sum(len(r['discoveries']) for r in rows),'sources':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='sources'},ensure_ascii=False))

if __name__=='__main__':main()
