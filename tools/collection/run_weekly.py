#!/usr/bin/env python3
"""Discovery -> permitted bodies -> grounded review proposals; never publishes.

The budget is a start-request budget, not cancellation of an in-flight HTTP
request. Body HTTP requests retain the existing 15-second timeout. A trusted
managed proxy OR explicit DNS-pinned public-only direct mode is required.
Body-specific permission and explicit provider-transfer consent remain necessary. No source text is returned in the result or printed.
"""
import argparse
import dataclasses
import json
import hashlib
import sys
import time
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

from collect import Collector
from extract import Config, ExtractionError, extract
from ingest import Pipeline, canonical
from input_source import InputSourceError, fetch_source
from pipeline import bounded_read, write_private

_SAFE_ERRORS = {'body_policy_blocked', 'policy_blocked', 'robots_blocked', 'robots_unavailable', 'host_paused', 'trusted_egress_required', 'cached_body_unavailable', 'fetch_error', 'unsupported_content', 'empty_input', 'input_too_large', 'invalid_input', 'time_budget_exhausted', 'provider_failed', 'invalid_schema', 'invalid_evidence', 'ungrounded_evidence', 'invalid_response', 'incomplete_or_refused', 'missing_server_api_key', 'install_optional_openai_dependency'}


def run(registry, policy, baseline, checkpoint, cache, *, network=False,
        allow_llm_content_transfer=False, max_documents=3, max_seconds=240,
        collector_factory=Collector, fetcher=fetch_source, extractor=extract,
        clock=time.monotonic, config=None, client=None):
    started=clock()
    if type(max_documents) is not int or not isinstance(max_seconds,(int,float)) or not 0<=max_seconds< float('inf'):
        raise ValueError('invalid_limits')
    document_limit=max(0,min(max_documents,5));budget=min(max_seconds,300)
    remaining=lambda: budget-(clock()-started)
    live=bool(network and allow_llm_content_transfer and remaining()>0)
    result={'schema_version':1,'stage':'weekly_review_only','mode':'network' if live else 'dry_run',
            'status':'review_only' if live else 'content_transfer_consent_required' if network and not allow_llm_content_transfer else 'dry_run',
            'documents':[],'skipped':[],'question_candidates':[],'discovery_requests':0,'discovered_sources':0,
            'approved_questions':0,'occurrences_added':0,'published':False}
    def bounded_sleep(seconds):
        if seconds>=remaining():raise InputSourceError('time_budget_exhausted')
        time.sleep(seconds)
    try:
        collector=collector_factory(policy,checkpoint,max_requests=20,max_seconds=max(0,remaining()),max_candidates=100)
        discovery=collector.run(registry['sources'],network=live)
        result['discovery_requests']=discovery.get('requests',0)
        links=discovery.get('source_candidates',[])
        result['discovered_sources']=len(links)
    except Exception:
        result['status']='discovery_failed'
        return result
    if not live:return result
    gate=Pipeline(cache,policy)
    merged={};seen=set()
    for link_index,link in enumerate(links[:100]):
        if len(result['documents'])>=document_limit or remaining()<1:break
        entry={'index':link_index,'status':'document_failed'}
        attempted=False
        try:
            url=canonical(link['url'])
            if url in seen:continue
            seen.add(url)
            entry['source_url']=url
            if policy.get(urlsplit(url).hostname,{}).get('body_extraction_status')!='permitted':
                raise InputSourceError('body_policy_blocked')
            if not gate.permitted(url):raise InputSourceError('policy_blocked')
            attempted=True
            doc=fetcher(url,policy,cache,sleeper=bounded_sleep)
            left=remaining()
            if left<1:raise ExtractionError('time_budget_exhausted')
            base=config or Config.from_env()
            per_doc=dataclasses.replace(base,budget_seconds=min(base.budget_seconds,left),timeout=min(base.timeout,left))
            extracted=extractor(doc,baseline,client,per_doc,clock=clock,sleeper=bounded_sleep)
            for candidate in extracted['question_candidates']:
                key=candidate['id']
                evidence_rows=[dict(evidence,text_sha256=hashlib.sha256(doc['text'].encode('utf-8')).hexdigest(),input_kind=doc['input_kind'],model=per_doc.model) for evidence in candidate.get('evidence',[])]
                if key not in merged:
                    merged[key]=dict(candidate,evidence=evidence_rows,verification_status='pending_human_approval',countEligible=False,occurrence_count=0)
                else:
                    for evidence in evidence_rows:
                        if evidence not in merged[key]['evidence']:merged[key]['evidence'].append(evidence)
            entry['status']='pending_human_approval'
        except (InputSourceError,ExtractionError) as exc:
            entry['status']=str(exc) if str(exc) in _SAFE_ERRORS else 'document_failed'
        except Exception:
            entry['status']='document_failed'
        result['documents' if attempted else 'skipped'].append(entry)
    result['question_candidates']=sorted(merged.values(),key=lambda row:row['id'])
    if remaining()<1:result['status']='time_budget_exhausted'
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,default=Path(__file__).with_name('sources.json'))
    parser.add_argument('--policy',type=Path,default=Path(__file__).with_name('policy.json'))
    parser.add_argument('--baseline',type=Path,default=Path(__file__).resolve().parents[2]/'data.json')
    parser.add_argument('--checkpoint',type=Path,default=Path('.collection/weekly-checkpoint.json'))
    parser.add_argument('--cache',type=Path,default=Path('.collection/weekly-body-metadata'))
    parser.add_argument('--output',type=Path,default=Path('.collection/private-weekly-review.json'))
    parser.add_argument('--network',action='store_true')
    parser.add_argument('--direct-public-egress',action='store_true',help='Explicit DNS-pinned public-only transport; refuses ambient proxy')
    parser.add_argument('--allow-llm-content-transfer',action='store_true')
    parser.add_argument('--max-documents',type=int,default=3)
    parser.add_argument('--max-seconds',type=float,default=240)
    args=parser.parse_args(argv)
    try:
        policy=json.loads(bounded_read(args.policy))
        dependencies={}
        if args.direct_public_egress:
            from safe_transport import direct_transport
            http=partial(direct_transport,allowed_hosts=set(policy))
            dependencies={'collector_factory':partial(Collector,http=http),'fetcher':partial(fetch_source,transport=http)}
        result=run(json.loads(bounded_read(args.registry)),policy,json.loads(bounded_read(args.baseline,10_000_000)),args.checkpoint,args.cache,network=args.network,allow_llm_content_transfer=args.allow_llm_content_transfer,max_documents=args.max_documents,max_seconds=args.max_seconds,**dependencies)
        write_private(args.output,result)
        print(json.dumps({'status':result['status'],'documents':len(result['documents']),'candidates':len(result['question_candidates']),'published':False}))
        return 0 if result['status'] in {'dry_run','review_only'} else 2
    except Exception:
        print('{"status":"failed","error":"weekly_input_or_output_failed"}',file=sys.stderr)
        return 2


if __name__=='__main__':sys.exit(main())
