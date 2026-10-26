#!/usr/bin/env python3
"""Bounded, manual, candidate-only public source discovery; stdlib, no credentials."""
import argparse
import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from ingest import AGENT, MAX_BYTES, Pipeline, NoRedirect, Title, canonical

ADAPTERS = {'rss','atom','html','github_readme','github_contents','sitemap'}
MIME = {'github_contents': {'application/json','application/vnd.github+json'},
        'sitemap': {'application/xml','text/xml'},
        'rss': {'application/atom+xml','application/rss+xml','application/xml','text/xml'},
        'atom': {'application/rss+xml','application/atom+xml','application/xml','text/xml'},
        'html': {'text/html','application/xhtml+xml'},
        'github_readme': {'text/plain','text/markdown','application/octet-stream'}}

def managed_transport(url):
    """Use configured managed egress, not direct DNS/proxy bypass. No target auth.

    Called only after Collector's reviewed source policy and robots gate. The
    managed proxy performs DNS/egress enforcement; never disable its protections.
    Redirects, cookies and credential-bearing target URLs remain disabled.
    """
    url=canonical(url)
    if not urllib.request.getproxies().get('https') or urllib.request.proxy_bypass(urllib.parse.urlsplit(url).hostname):
        raise ValueError('A managed HTTPS proxy is required; direct network is disabled')
    opener=urllib.request.build_opener(NoRedirect())
    req=urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'application/json,application/rss+xml,application/atom+xml,text/html,text/plain','Accept-Encoding':'identity'})
    try: response=opener.open(req,timeout=15)
    except urllib.error.HTTPError as exc:response=exc
    with response:
        body=response.read(MAX_BYTES+1)
        return response.status,response.headers.get('Content-Type',''),body

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def source_id(url):
    p=urllib.parse.urlsplit(url); parts=p.path.strip('/').split('/')
    if p.hostname in {'github.com','raw.githubusercontent.com'} and len(parts)>=2:
        return 'github:'+('/'.join(parts[:2]).removesuffix('.git')).lower()
    return url

class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.links=[];self.link=None;self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.link=dict(attrs).get('href');self.text=[]
    def handle_data(self,data):
        if self.link:self.text.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.link:
            self.links.append((self.link,' '.join(self.text),None));self.link=None

def discover(adapter,body,url,limit):
    text=body.decode('utf-8','replace');items=[]
    if adapter in {'rss','atom','sitemap'}:
        # Do not resolve entities or fetch enclosures, article bodies, or pagination.
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('DTD not accepted')
        root=ET.fromstring(text)
        for entry in root.iter():
            if adapter=='sitemap':
                if entry.tag.split('}')[-1] in {'url','sitemap'}:
                    fields={child.tag.split('}')[-1]:child.text for child in entry}
                    if fields.get('loc'):items.append((fields['loc'],'',None,{'sitemap_entry_kind':entry.tag.split('}')[-1],'last_modified_claim':fields.get('lastmod')}))
                continue
            if entry.tag.split('}')[-1] not in {'item','entry'}:continue
            fields={};link=None
            for child in entry:
                name=child.tag.split('}')[-1]
                if name=='link' and child.get('rel','alternate')=='alternate':link=child.get('href') or child.text
                if name in {'title','pubDate','published','updated'}:fields[name]=''.join(child.itertext())
            if link:items.append((link,fields.get('title',''),fields.get('published') or fields.get('pubDate') or fields.get('updated')))
    elif adapter=='github_contents':
        payload=json.loads(text)
        entries=payload if isinstance(payload,list) else payload.get('entries',[payload]) if isinstance(payload,dict) else []
        parts=urllib.parse.urlsplit(url).path.strip('/').split('/')
        if len(parts)<4 or parts[0]!='repos' or parts[3]!='contents':raise ValueError('Expected exact repository contents endpoint')
        expected='github:'+('/'.join(parts[1:3])).lower()
        for entry in entries:
            if not isinstance(entry,dict) or entry.get('type') not in {'file','dir'}:continue
            target=entry.get('html_url')
            if not isinstance(target,str):continue
            try:target=canonical(target)
            except ValueError:continue
            if urllib.parse.urlsplit(target).hostname!='github.com' or source_id(target)!=expected:continue
            items.append((target,str(entry.get('name',''))[:300],None,{'github_entry_type':entry['type']}))
    elif adapter=='html':
        parser=Links();parser.feed(text);items=parser.links
    elif adapter=='github_readme':
        items=[(u,t,None) for t,u in re.findall(r'\[([^\]\n]{0,300})\]\((https://[^\s)]+)\)',text)]
    out=[];seen=set()
    for item in items:
        link,title,date=item[:3];metadata=item[3:]
        try:target=canonical(urllib.parse.urljoin(url,link.strip()))
        except ValueError:continue
        if target in seen:continue
        seen.add(target);out.append((target,' '.join(title.split())[:300],date,*metadata))
        if len(out)>=limit:break
    return out

class StopFetch(Exception):
    pass

class Collector:
    def __init__(self,policy,checkpoint,http=managed_transport,today=None,sleeper=time.sleep,max_requests=20,max_seconds=120,max_candidates=100):
        self.policy=policy;self.path=Path(checkpoint);self.http=http;self.today=today or dt.date.today().isoformat();self.sleep=sleeper
        self.max_requests=max(0,min(max_requests,100));self.max_seconds=max(0,min(max_seconds,600));self.max_candidates=max(1,min(max_candidates,1000))
        self.requests=0;self.started=time.monotonic();self.robots={};self.paused=set()
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {'schema_version':1,'sources':{}}
        # Reuse the established fail-closed terms/date/path validator without its cache.
        self.gate=object.__new__(Pipeline);self.gate.policy=policy;self.gate.today=self.today
    def request(self,url,delay=2):
        if self.requests>=self.max_requests or time.monotonic()-self.started+delay>=self.max_seconds:raise StopFetch('budget_exhausted')
        self.sleep(delay);self.requests+=1
        code,ctype,body=self.http(url)
        if len(body)>MAX_BYTES:raise StopFetch('response_too_large')
        return code,ctype,body
    def fetch(self,url):
        host=urllib.parse.urlsplit(url).hostname
        if not self.gate.permitted(url):raise StopFetch('policy_blocked')
        if host in self.paused:raise StopFetch('host_paused')
        if host not in self.robots:
            code,ctype,body=self.request(f'https://{host}/robots.txt')
            if code not in {200,404,410} or (code==200 and ('html' in ctype or body.lstrip().startswith(b'<'))):
                self.paused.add(host);raise StopFetch('robots_unavailable')
            p=urllib.robotparser.RobotFileParser();p.parse(body.decode('utf-8','replace').splitlines() if code==200 else [])
            self.robots[host]=p
        p=self.robots[host]
        if not p.can_fetch(AGENT,url):raise StopFetch('robots_blocked')
        rate=p.request_rate(AGENT);delay=max(2,p.crawl_delay(AGENT) or 0,rate.seconds/rate.requests if rate and rate.requests else 0)
        code,ctype,body=self.request(url,delay)
        if code in {401,403,429}:self.paused.add(host)
        if code!=200:raise StopFetch('http_'+str(code))
        return ctype.split(';')[0].strip().lower(),body
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(self.path.suffix+'.tmp');temp.write_text(json.dumps(self.state,ensure_ascii=False,indent=2)+'\n');temp.replace(self.path)
    def run(self,sources,network=False):
        runs=[];candidates={}
        for source in sources[:100]:
            run={'source_id':source['id'],'platform':source['platform'],'checked_at':self.today}
            rows=[]
            try:
                if not source.get('enabled'):raise StopFetch('pending')
                if source.get('adapter') not in ADAPTERS:raise StopFetch('unsupported_adapter')
                url=canonical(source['url']);run['url']=url
                if not network:raise StopFetch('dry_run')
                if not self.gate.permitted(url):raise StopFetch('policy_blocked')
                key=digest('collector-v4.1.1|'+json.dumps(source,sort_keys=True)+json.dumps(self.policy,sort_keys=True)+self.today)
                prior=self.state['sources'].get(key)
                if prior:
                    rows=prior['candidates'][:self.max_candidates];run.update(prior['run'],status='checkpoint_reused',candidates=len(rows))
                else:
                    ctype,body=self.fetch(url)
                    if ctype not in MIME[source['adapter']]:raise StopFetch('unsupported_content')
                    content_hash=hashlib.sha256(body).hexdigest()
                    discovered=discover(source['adapter'],body,url,self.max_candidates)
                    keywords=[k.casefold() for k in source.get('candidate_keywords',[]) if isinstance(k,str) and k]
                    if keywords:
                        if source['adapter']=='html':
                            page_title=Title();page_title.feed(body.decode('utf-8','replace'))
                            discovered.insert(0,(url,' '.join(page_title.parts)[:300],None))
                            discovered=[item for item in discovered if not urllib.parse.urlsplit(item[0]).path.startswith(('/tags/','/categories/','/archives/','/about/'))]
                        discovered=[item for item in discovered if any(k in item[1].casefold() for k in keywords)][:self.max_candidates]
                    for item in discovered:
                        target,title,date=item[:3];metadata=item[3] if len(item)>3 else {}
                        rows.append({'id':digest(target)[:20],'url':target,'title':title,'canonical_source_id':source_id(target),
                            'candidate_kind':('sitemap_index_link' if metadata.get('sitemap_entry_kind')=='sitemap' else 'sitemap_url') if source['adapter']=='sitemap' else ('repository_directory' if metadata.get('github_entry_type')=='dir' else 'repository_file') if source['adapter']=='github_contents' else 'source_link',
                            'verification_status':'candidate_unverified','access_status':'fetched_source_page_unverified' if target==url else 'discovered_link_not_fetched',
                            'common_question_status':'needs_human_review','occurrence_count':0,'publication_date_claim':date,**metadata,
                            'provenance':[{'source_id':source['id'],'discovered_at':self.today,'discovery_url':url,'adapter':source['adapter'],'content_sha256':content_hash}]})
                    run.update(status='fetched_unverified',http_status=200,content_sha256=content_hash,bytes=len(body),candidates=len(rows))
                    self.state['sources'][key]={'run':run.copy(),'candidates':rows};self.save()
            except StopFetch as exc:run['status']=str(exc)
            except (ValueError,OSError,ET.ParseError) as exc:run.update(status='fetch_error',error=type(exc).__name__+': '+str(exc)[:160])
            runs.append(run)
            for row in rows:
                if row['url'] not in candidates:candidates[row['url']]=json.loads(json.dumps(row))
                else:
                    for p in row['provenance']:
                        if p not in candidates[row['url']]['provenance']:candidates[row['url']]['provenance'].append(p)
        return {'schema_version':1,'mode':'network' if network else 'dry_run','runs':runs,'requests':self.requests,
            'independent_interview_count':0,'count_policy':'Candidates never count as interviews. GitHub question sources count by canonical owner/repo only after human approval.',
            'review_required':['2022+ interview date and algorithm role','original/repost provenance','explicit generic question; exclude personal project specifics','map to existing taxonomy; deduplicate per interview or repository'],
            'source_candidates':sorted(candidates.values(),key=lambda r:r['url']),
            'question_candidates':[], 'metrics':{'discovered_source_candidates':len(candidates),'verified_common_questions':0},
            'candidates':sorted(candidates.values(),key=lambda r:r['url'])}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registry',type=Path,default=Path(__file__).with_name('sources.json'))
    p.add_argument('--policy',type=Path,default=Path(__file__).with_name('policy.json'))
    p.add_argument('--checkpoint',type=Path,default=Path('.collection/checkpoint.json'))
    p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--network',action='store_true');mode.add_argument('--dry-run',action='store_true')
    p.add_argument('--max-requests',type=int,default=20);p.add_argument('--max-seconds',type=float,default=120);p.add_argument('--max-candidates',type=int,default=100)
    args=p.parse_args();sources=json.loads(args.registry.read_text())['sources']
    result=Collector(json.loads(args.policy.read_text()),args.checkpoint,max_requests=args.max_requests,max_seconds=args.max_seconds,max_candidates=args.max_candidates).run(sources,network=args.network)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'mode':result['mode'],'requests':result['requests'],'candidates':len(result['candidates']),'statuses':{r['source_id']:r['status'] for r in result['runs']}},ensure_ascii=False))

if __name__=='__main__':main()
