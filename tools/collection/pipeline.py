#!/usr/bin/env python3
"""Manual server-side extraction entrypoint. No auto-merge or publication."""
import argparse
import json
import os
import sys
import tempfile
from functools import partial
from pathlib import Path
from types import SimpleNamespace as NS
from extract import Config, ExtractionError, extract
from input_source import InputSourceError, load_import, fetch_source


def bounded_read(path,limit=512000):
    with Path(path).open('rb') as file:data=file.read(limit+1)
    if len(data)>limit:raise ExtractionError('file_too_large')
    return data.decode('utf-8')


def write_private(path,result):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.candidate-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as file:
            json.dump(result,file,ensure_ascii=False,indent=2);file.write('\n')
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--text-file',type=Path);source.add_argument('--html-file',type=Path);source.add_argument('--fetch-url')
    parser.add_argument('--direct-public-egress',action='store_true')
    parser.add_argument('--source-url');parser.add_argument('--policy',type=Path)
    parser.add_argument('--cache',type=Path,default=Path('.collection/body-metadata'))
    parser.add_argument('--baseline',type=Path,default=Path(__file__).resolve().parents[2]/'data.json')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--mock-response',type=Path,help='Offline pre-extracted JSON; no SDK/API call')
    parser.add_argument('--allow-llm-content-transfer',action='store_true',help='Consent to send source body to configured provider')
    args=parser.parse_args(argv)
    try:
        if args.direct_public_egress and not args.fetch_url:raise ExtractionError('direct_mode_requires_url')
        if not args.mock_response and not args.allow_llm_content_transfer:raise ExtractionError('content_transfer_consent_required')
        if args.fetch_url:
            if not args.policy:raise ExtractionError('body_policy_required')
            policy=json.loads(bounded_read(args.policy));transport=None
            if args.direct_public_egress:
                from safe_transport import direct_transport
                transport=partial(direct_transport,allowed_hosts=set(policy))
            doc=fetch_source(args.fetch_url,policy,args.cache,transport=transport)
        else:
            if not args.source_url:raise ExtractionError('source_url_required')
            doc=load_import(bounded_read(args.text_file or args.html_file),args.source_url,'text' if args.text_file else 'html')
        sdk=None;config=None
        if args.mock_response:
            response=NS(choices=[NS(finish_reason='stop',message=NS(content=bounded_read(args.mock_response,64000),refusal=None))])
            sdk=NS(chat=NS(completions=NS(create=lambda **kwargs:response)))
            config=Config(model='manual-mock-not-api-tested')
        result=extract(doc,json.loads(bounded_read(args.baseline,10000000)),sdk,config)
        # Atomic private output; never retain a pre-existing world-readable mode.
        write_private(args.output,result)
        print(json.dumps({'status':'review_only','candidates':len(result['question_candidates']),'published':False}))
        return 0
    except (ExtractionError,InputSourceError) as exc:
        # Both exception classes carry constant error codes, not provider/source content.
        print(json.dumps({'status':'needs_manual_content' if args.fetch_url else 'failed','error':str(exc)}),file=sys.stderr)
        return 2
    except Exception:
        print('{"status":"failed","error":"input_or_output_failed"}',file=sys.stderr)
        return 2

if __name__=='__main__':sys.exit(main())
