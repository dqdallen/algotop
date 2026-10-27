#!/usr/bin/env python3
"""Offline, explicit-human-review transactions on a private local working copy only.

No API, network, publication, scheduler or answer-file writes. A transaction changes
one data.json via atomic replace; journals/backups are durable before that replace.
"""
import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from ingest import canonical

ROOT=Path(__file__).resolve().parents[2]
class ReviewError(ValueError): pass

def fail(code): raise ReviewError(code)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def packed(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def obj(value, allowed, required=()):
    if not isinstance(value,dict) or set(value)-set(allowed) or set(required)-set(value): fail('invalid_schema')
def string(value,limit=500):
    if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value): fail('invalid_text')
    return value

def identity(raw):
    try:
        url=canonical(string(raw,2000));p=urlsplit(url);host=p.hostname
        parts=p.path.strip('/').split('/')
        if host in {'github.com','www.github.com','raw.githubusercontent.com'} and len(parts)>=2:
            if not all(re.fullmatch(r'[A-Za-z0-9_.-]+',v) and v not in {'.','..'} for v in parts[:2]): fail('invalid_repository')
            return 'github:'+('/'.join(parts[:2]).removesuffix('.git')).lower()
        query=sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k not in {'spm','from'})
        return urlunsplit(('https',host,p.path.rstrip('/') or '/',urlencode(query),''))
    except (TypeError,ValueError,AttributeError): fail('invalid_source_url')

def strict_load(raw):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out: fail('duplicate_json_key')
            out[k]=v
        return out
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:fail('invalid_number'))
    except (ValueError,UnicodeError,RecursionError):fail('invalid_json')

def validate_database(data):
    """Run the existing complete runtime schema audit, not just changed fields."""
    if not isinstance(data,dict):fail('invalid_baseline')
    with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
        tmp.write(packed(data));tmp.flush()
        try:
            result=subprocess.run(['node',str(ROOT/'scripts/data-pipeline.js'),'--data',tmp.name,
                '--answers',str(ROOT/'answers.json'),'--answers',str(ROOT/'answers-extra.json')],cwd=ROOT,capture_output=True,timeout=20)
            report=json.loads(result.stdout)
        except (OSError,ValueError,subprocess.TimeoutExpired):fail('schema_validator_unavailable')
        if result.returncode or report.get('errors'):fail('baseline_schema_invalid')
    return data

DOC_FIELDS={'schema_version','stage','question_candidates','excluded','approved_questions','occurrences_added','published','extraction_version','input_kind','text_sha256','model','used_parser','parser_version','parser_fallback_reason','access_status','demo','document_id','manual_excluded_count'}
CANDIDATE_FIELDS={'id','question','canonical_question_id','canonical_source_id','disposition','verification_status','countEligible','occurrence_count','already_in_baseline','proposed_action','evidence','open_checks'}
EVIDENCE_FIELDS={'url','locator','reviewer','interview_date_claim','provenance_claim','quote','start','end'}

def candidates(documents):
    if isinstance(documents,dict):documents=[documents]
    if not isinstance(documents,list) or not documents or len(documents)>50:fail('invalid_candidates')
    rows={};is_demo=False
    for doc in documents:
        obj(doc,DOC_FIELDS,{'schema_version','stage','question_candidates','excluded','approved_questions','occurrences_added','published'})
        if doc['schema_version']!=1 or type(doc['schema_version'])!=int or doc['stage']!='review_proposals_only' or doc['approved_questions']!=0 or doc['occurrences_added']!=0 or doc['published'] is not False:fail('candidate_not_pending')
        if any(type(doc[k])!=int for k in ['approved_questions','occurrences_added']):fail('invalid_candidate_counts')
        if 'demo' in doc and type(doc['demo'])!=bool:fail('invalid_demo_flag')
        if 'text_sha256' in doc and (not isinstance(doc['text_sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}',doc['text_sha256'])):fail('invalid_provenance_hash')
        for field in ['input_kind','model','used_parser','parser_version','parser_fallback_reason','access_status','document_id']:
            if field in doc and doc[field] is not None:string(doc[field],500)
        for field in ['extraction_version','manual_excluded_count']:
            if field in doc and (type(doc[field])!=int or doc[field]<0):fail('invalid_provenance_metadata')
        is_demo|=doc.get('demo',False) or str(doc.get('model','')).startswith('demo-')
        if not isinstance(doc['question_candidates'],list) or len(doc['question_candidates'])>500 or not isinstance(doc['excluded'],list):fail('invalid_candidates')
        for excluded in doc['excluded']:
            obj(excluded,{'input_index','reason'},{'input_index','reason'})
            if type(excluded['input_index'])!=int or excluded['input_index']<0:fail('invalid_excluded_metadata')
            string(excluded['reason'],500)
        for row in doc['question_candidates']:
            obj(row,CANDIDATE_FIELDS,CANDIDATE_FIELDS)
            cid=string(row['id'],100);string(row['question'],200)
            if cid in rows:fail('duplicate_candidate_id')
            if row['canonical_question_id'] is not None:string(row['canonical_question_id'],100)
            if row['disposition']!='common' or row['verification_status']!='pending_human_approval' or row['countEligible'] is not False or type(row['occurrence_count'])!=int or row['occurrence_count']!=0:fail('candidate_not_pending_common')
            if type(row['already_in_baseline'])!=bool or row['proposed_action'] not in {'duplicate_no_add','review_merge','review_new_card'} or not isinstance(row['open_checks'],list) or any(not isinstance(x,str) for x in row['open_checks']):fail('invalid_candidate_metadata')
            if not isinstance(row['evidence'],list) or not 1<=len(row['evidence'])<=100:fail('invalid_evidence')
            for ev in row['evidence']:
                obj(ev,EVIDENCE_FIELDS,{'url','locator','reviewer','interview_date_claim','provenance_claim'})
                for key in ['locator','reviewer','provenance_claim']:string(ev[key],500)
                supplied=string(row['canonical_source_id'],2000)
                normalized=supplied.lower() if supplied.startswith('github:') else identity(supplied)
                if identity(ev['url'])!=normalized:fail('source_identity_mismatch')
                if ev['interview_date_claim'] is not None:
                    try:dt.date.fromisoformat(ev['interview_date_claim'])
                    except (TypeError,ValueError):fail('invalid_date_claim')
                if any(k in ev for k in ['quote','start','end']):
                    if not all(k in ev for k in ['quote','start','end']):fail('invalid_evidence_offsets')
                    string(ev['quote'],500)
                    if type(ev['start'])!=int or type(ev['end'])!=int or not 0<=ev['start']<ev['end'] or ev['end']-ev['start']!=len(ev['quote']) or row['question'] not in ev['quote']:fail('invalid_evidence_offsets')
                is_demo |= 'algotop-synthetic-demo' in ev['url']
            rows[cid]=copy.deepcopy(row)
            rows[cid]['canonical_source_id']=normalized
            rows[cid]['_provenance']={k:copy.deepcopy(doc[k]) for k in ['text_sha256','input_kind','model','used_parser','parser_version','parser_fallback_reason','access_status','extraction_version'] if k in doc}
    return rows,is_demo

def decisions(value,rows):
    obj(value,{'schema_version','reviewer','decisions'},{'schema_version','reviewer','decisions'})
    if type(value['schema_version'])!=int or value['schema_version']!=1:fail('invalid_decisions')
    string(value['reviewer'],100)
    if not isinstance(value['decisions'],list):fail('invalid_decisions')
    out={}
    for d in value['decisions']:
        obj(d,{'candidate_id','action','target_question_id','common_question','source_reviewed','reason'},{'candidate_id','action'})
        cid=string(d['candidate_id'],100)
        if cid not in rows or cid in out:fail('invalid_decision_candidate')
        if d['action'] not in {'add','merge','exclude'}:fail('invalid_action')
        for key in ['common_question','source_reviewed']:
            if key in d and type(d[key])!=bool:fail('invalid_decision_confirmation')
        if 'reason' in d:string(d['reason'],500)
        if d['action']=='exclude':string(d.get('reason'),500)
        elif d.get('common_question') is not True:fail('human_common_question_confirmation_required')
        elif d.get('source_reviewed') is not True:fail('human_source_review_confirmation_required')
        if d['action']=='merge':string(d.get('target_question_id'),100)
        elif d.get('target_question_id') is not None:fail('unexpected_merge_target')
        out[cid]=copy.deepcopy(d)
    if set(out)!=set(rows):fail('missing_decisions')
    return out

def grounding(rows, trusted_document=None):
    status={}
    for cid,row in rows.items():
        verified=False
        if trusted_document is not None:
            if not isinstance(trusted_document,dict) or not isinstance(trusted_document.get('text'),str):fail('invalid_trusted_document')
            text=trusted_document['text'];key=identity(trusted_document.get('source_url'))
            if key!=row['canonical_source_id']:fail('trusted_source_mismatch')
            text_hash=sha(text.encode())
            if row['_provenance'].get('text_sha256')!=text_hash:fail('trusted_source_hash_mismatch')
            for ev in row['evidence']:
                if not all(k in ev for k in ['quote','start','end']):fail('trusted_source_evidence_incomplete')
                if ev['end']>len(text) or text[ev['start']:ev['end']]!=ev['quote'] or row['question'] not in ev['quote']:fail('trusted_source_evidence_mismatch')
            verified=True
        status[cid]='matched_supplied_text' if verified else 'human_attested_not_independently_verified'
    return status

def normalize(title):return ' '.join(title.split()).casefold().rstrip('?？。!！')
def source_key(s):return identity(s.get('canonicalUrl') or s['url'])

def plan(data,rows,choices,reviewer):
    result=copy.deepcopy(data);sources={};qmap={q['id']:q for q in result['questions']};changes=[]
    for s in result['sources']:
        key=source_key(s)
        if key in sources and sources[key]['id']!=s['id']:fail('ambiguous_source_identity')
        sources[key]=s
    source_ids={s['id'] for s in result['sources']}
    counts=dict(new_questions=0,new_sources=0,new_question_source_pairs=0,evidence_added=0,excluded=0)
    for cid in sorted(rows):
        row=rows[cid];decision=choices[cid];action=decision['action'];key=row['canonical_source_id']
        change=dict(candidate_id=cid,action=action,question_id=None,canonical_source_id=key,source_added=False,pair_added=False,evidence_added=0)
        if action=='exclude':counts['excluded']+=1;changes.append(change);continue
        if action=='merge':
            qid=decision['target_question_id']
            if qid not in qmap:fail('unknown_merge_target')
            q=qmap[qid]
        else:
            if any(normalize(q['title'])==normalize(row['question']) for q in qmap.values()):fail('existing_title_requires_merge')
            qid='q-review-'+sha(normalize(row['question']).encode())[:20]
            if qid in qmap or qid in result.get('questionAliases',{}):fail('question_id_collision')
            q=dict(id=qid,canonicalQuestionId=qid,title=row['question'],tag='待分类',tracks=['待分类'],studyTopics=['待分类'],mergeReason='人工审核新增通用问题；未推断主题或岗位',answerStatus='待专业审核',evidenceStatus='人工确认通用题；来源真实性未独立核验',answer={},records=[])
            qmap[qid]=q;result['questions'].append(q);counts['new_questions']+=1
        source=sources.get(key)
        if source is None:
            sid='s-review-'+sha(key.encode())[:20]
            if sid in source_ids or sid in result.get('sourceAliases',{}):fail('source_id_collision')
            url=('https://github.com/'+key[7:]) if key.startswith('github:') else key
            source=dict(id=sid,canonicalSourceId=key,url=url,canonicalUrl=url,title='人工审核导入来源',company='未知',kind='人工审核题目来源；非独立面试次数',date=None,qualification='secondary_compilation',accessStatus='reviewer_supplied_evidence',countEligible=True,companyEvidence={'text':'未提供明确公司归属证据','location':'unknown','certainty':'unknown'},jobDirections=[{'id':'unknown','evidence':'未提供明确岗位证据；不按题目推断','certainty':'unknown'}],dateEvidence={'value':None,'precision':'unknown','basis':'unknown','evidence':'候选日期仅作为声明保留，未独立核验'},collectionPartition='unknown',authenticity='人工审核通用题；未独立验证来源真实性')
            result['sources'].append(source);sources[key]=source;source_ids.add(sid);counts['new_sources']+=1;change['source_added']=True
        matching=[r for r in q['records'] if source_key(sources[key])==identity(next(s for s in result['sources'] if s['id']==r['source']).get('canonicalUrl') or next(s for s in result['sources'] if s['id']==r['source'])['url'])]
        if matching:record=matching[0]
        else:
            record=dict(event=source['id'],source=source['id'],canonicalSourceId=key,eventUnit='source_document',company=source['company'],companyEvidence=copy.deepcopy(source['companyEvidence']),jobDirections=copy.deepcopy(source['jobDirections']),wording=row['question'],evidenceLevel=source.get('qualification','secondary_compilation'),countEligible=True,date=None,round=None)
            q['records'].append(record);counts['new_question_source_pairs']+=1;change['pair_added']=True
        evs=record.setdefault('reviewEvidence',[])
        for ev in row['evidence']:
            # Immutable evidence; keep candidate/source provenance without raw documents.
            entry=dict(candidateId=cid,question=row['question'],evidence=copy.deepcopy(ev),reviewer=reviewer,provenance=copy.deepcopy(row['_provenance']))
            # Same evidence replay cannot increase source or evidence counts.
            if not any(e.get('question')==entry['question'] and e.get('evidence')==entry['evidence'] for e in evs):
                evs.append(entry);counts['evidence_added']+=1;change['evidence_added']+=1
        change['question_id']=qid;changes.append(change)
    validate_database(result)
    return result,counts,changes

def totals(data):
    source_ids={s['id']:source_key(s) for s in data['sources']}
    records=[r for q in data['questions'] for r in q['records']]
    pairs={(q['id'],source_ids[r['source']]) for q in data['questions'] for r in q['records'] if r.get('countEligible') is not False}
    return dict(question_count=len(data['questions']),source_count=len(set(source_ids.values())),
        question_source_pairs=len(pairs),record_count=len(records),
        review_evidence_count=sum(len(r.get('reviewEvidence',[])) for r in records))

class ReviewStore:
    def __init__(self,workspace_dir,baseline_path,*,demo=False):
        self.root=Path(workspace_dir).resolve();self.baseline=Path(baseline_path).resolve();self.data=self.root/'data.json';self.demo=demo
        if type(demo)!=bool or self.data==self.baseline or self.root==ROOT or self.root==ROOT/'_site':fail('working_copy_must_be_isolated')
        self.private=self.root/'.review';self.private.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self._lock():
            marker=self.private/'workspace.json'
            if marker.exists():
                meta=strict_load(marker.read_bytes())
                if meta.get('baseline_path')!=str(self.baseline) or meta.get('demo')!=demo:fail('workspace_mode_mismatch')
            else:
                if self.data.exists():fail('uninitialized_existing_working_copy')
                raw=self.baseline.read_bytes();validate_database(strict_load(raw))
                self._write(self.data,raw)
                self._write(marker,packed(dict(baseline_path=str(self.baseline),baseline_sha256=sha(raw),demo=demo)))
            for name in ('previews','transactions'): (self.private/name).mkdir(exist_ok=True,mode=0o700)
    @contextmanager
    def _lock(self):
        with open(self.private/'lock','a+b') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(handle,fcntl.LOCK_UN)
    def _write(self,path,raw):
        fd,name=tempfile.mkstemp(prefix='.write-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
            os.replace(name,path)
            directory=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            if os.path.exists(name):os.unlink(name)
    def _id(self,value):
        if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value):fail('invalid_id')
        return value
    def preview(self,documents,decision_file,*,trusted_document=None):
        try:
            rows,demo=candidates(documents);choices=decisions(decision_file,rows)
            grounds=grounding(rows,trusted_document)
            for cid,row in rows.items():row['_provenance']['grounding']=grounds[cid]
            with self._lock():
                raw=self.data.read_bytes();data=validate_database(strict_load(raw))
                result,counts,changes=plan(data,rows,choices,decision_file['reviewer'])
                new=raw if result==data else packed(result)
                binding=dict(baseline_sha256=sha(raw),result_sha256=sha(new),decisions=decision_file,candidates=documents,demo=demo,grounding=grounds)
                pid=sha(packed(binding))
                summary=dict(preview_id=pid,baseline_sha256=sha(raw),result_sha256=sha(new),demo=demo,counts=counts,totals={'before':totals(data),'after':totals(result)},changes=changes,count_policy='Distinct canonical source per question; repositories once across files. Not interview frequency.',requires_confirmation=True)
                payload=dict(summary=summary,binding=binding,result=result,unchanged=result==data)
                self._write(self.private/'previews'/(pid+'.json'),packed(payload))
                return summary
        except ReviewError:raise
        except (KeyError,TypeError,ValueError,OverflowError,RecursionError):fail('invalid_review_input')
    def apply(self,preview_id,*,confirmed=False):
        if confirmed is not True:fail('explicit_confirmation_required')
        pid=self._id(preview_id)
        with self._lock():
            p=self.private/'previews'/(pid+'.json')
            if not p.exists():fail('unknown_preview')
            payload=strict_load(p.read_bytes());binding=payload['binding'];summary=payload['summary']
            if sha(packed(binding))!=pid:fail('preview_integrity_failed')
            if binding['demo'] and not self.demo:fail('demo_requires_isolated_demo_workspace')
            txdir=self.private/'transactions'/pid;manifest=txdir/'manifest.json'
            current=self.data.read_bytes()
            if manifest.exists():
                tx=strict_load(manifest.read_bytes())
                if tx['status'] in {'rolled_back','rolling_back'}:fail('preview_already_rolled_back')
                if sha(current)==tx['after_sha256']:
                    if tx['status']=='prepared':tx['status']='applied';self._write(manifest,packed(tx))
                    return dict(tx,replayed=True)
                if tx['status']=='applied':fail('working_copy_changed_since_apply')
            if sha(current)!=binding['baseline_sha256']:fail('stale_preview')
            rows,demo=candidates(binding['candidates']);choices=decisions(binding['decisions'],rows)
            for cid,row in rows.items():row['_provenance']['grounding']=binding['grounding'][cid]
            result,counts,changes=plan(validate_database(strict_load(current)),rows,choices,binding['decisions']['reviewer'])
            new=current if result==strict_load(current) else packed(result)
            if sha(new)!=binding['result_sha256'] or counts!=summary['counts'] or changes!=summary['changes']:fail('preview_integrity_failed')
            txdir.mkdir(exist_ok=True,mode=0o700)
            backup=txdir/'before.bin'
            if backup.exists() and backup.read_bytes()!=current:fail('backup_collision')
            if not backup.exists():self._write(backup,current)
            tx=dict(transaction_id=pid,preview_id=pid,status='prepared',before_sha256=sha(current),after_sha256=sha(new),demo=self.demo,counts=counts,decisions=binding['decisions'],changes=changes,created_at=dt.datetime.now(dt.timezone.utc).isoformat())
            self._write(manifest,packed(tx))
            # Re-check after validation/journaling, immediately before replace.
            if sha(self.data.read_bytes())!=tx['before_sha256']:fail('stale_preview')
            self._write(self.data,new);tx['status']='applied';self._write(manifest,packed(tx));return tx
    def rollback(self,transaction_id,*,confirmed=False):
        if confirmed is not True:fail('explicit_confirmation_required')
        tid=self._id(transaction_id)
        with self._lock():
            txdir=self.private/'transactions'/tid;manifest=txdir/'manifest.json'
            if not manifest.exists():fail('unknown_transaction')
            tx=strict_load(manifest.read_bytes());current=self.data.read_bytes()
            if tx['status']=='rolled_back':
                if sha(current)!=tx['before_sha256']:fail('working_copy_changed_since_rollback')
                return dict(tx,replayed=True)
            outstanding=[strict_load(p.read_bytes()) for p in (self.private/'transactions').glob('*/manifest.json')]
            outstanding=[t for t in outstanding if t['status']!='rolled_back']
            if outstanding and max(outstanding,key=lambda t:t['created_at'])['transaction_id']!=tid:fail('rollback_requires_latest_transaction')
            if tx['status']=='rolling_back' and sha(current)==tx['before_sha256']:
                tx['status']='rolled_back';tx['rolled_back_at']=dt.datetime.now(dt.timezone.utc).isoformat();self._write(manifest,packed(tx));return tx
            if sha(current)!=tx['after_sha256']:fail('working_copy_changed_since_apply')
            backup=(txdir/'before.bin').read_bytes()
            if sha(backup)!=tx['before_sha256']:fail('backup_integrity_failed')
            validate_database(strict_load(backup))
            if sha(self.data.read_bytes())!=tx['after_sha256']:fail('working_copy_changed_since_apply')
            tx['status']='rolling_back';self._write(manifest,packed(tx))
            if sha(self.data.read_bytes())!=tx['after_sha256']:fail('working_copy_changed_since_apply')
            self._write(self.data,backup);tx['status']='rolled_back';tx['rolled_back_at']=dt.datetime.now(dt.timezone.utc).isoformat();self._write(manifest,packed(tx));return tx
    def state(self):
        with self._lock():
            raw=self.data.read_bytes();data=strict_load(raw)
            transactions=sorted([strict_load(p.read_bytes()) for p in (self.private/'transactions').glob('*/manifest.json')],key=lambda t:t['created_at'])
            return dict(demo=self.demo,working_sha256=sha(raw),questions=[{'id':q['id'],'title':q['title']} for q in data['questions']],transactions=transactions)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--baseline',type=Path,default=ROOT/'data.json');p.add_argument('--demo-sandbox',action='store_true')
    sub=p.add_subparsers(dest='command',required=True)
    for command in ('preview','dry-run'):
        x=sub.add_parser(command);x.add_argument('candidates',nargs='+',type=Path);x.add_argument('--decisions',required=True,type=Path)
    for command in ('apply','rollback'):
        x=sub.add_parser(command);x.add_argument('id');x.add_argument('--confirm',action='store_true')
    sub.add_parser('state');args=p.parse_args()
    try:
        store=ReviewStore(args.workspace,args.baseline,demo=args.demo_sandbox)
        if args.command in {'preview','dry-run'}:result=store.preview([strict_load(f.read_bytes()) for f in args.candidates],strict_load(args.decisions.read_bytes()))
        elif args.command=='apply':result=store.apply(args.id,confirmed=args.confirm)
        elif args.command=='rollback':result=store.rollback(args.id,confirmed=args.confirm)
        else:result=store.state()
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ReviewError,OSError) as exc:
        print(json.dumps({'error':str(exc) if isinstance(exc,ReviewError) else 'local_io_error'}));raise SystemExit(1)
if __name__=='__main__':main()
