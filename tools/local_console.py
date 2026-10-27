#!/usr/bin/env python3
"""Loopback-only, private, ephemeral candidate review UI; never publishes."""
import argparse
import copy
import json
import importlib.util
import re
import shutil
import multiprocessing
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'collection'))
from input_source import load_import, fetch_source, InputSourceError
from extract import extract, Config, ExtractionError
from types import SimpleNamespace as NS
from review_commit import ReviewError

MAX_REQUEST = 600_000
DEMO_TEXT = '演示材料（人工测试模拟，不是真实面经）\n什么是注意力机制？\n如何解决梯度消失？\n什么是测试用虚构技术问题？\n你在个人项目中配置的私有集群名称是什么？'
DEMO_QUESTIONS = [('什么是注意力机制？','common'),('如何解决梯度消失？','common'),('什么是测试用虚构技术问题？','common'),('你在个人项目中配置的私有集群名称是什么？','personal_project_specific')]


def _worker(pipe, function, args):
    try:
        pipe.send((True, function(*args)))
    except (InputSourceError, ExtractionError) as exc:
        pipe.send((False, str(exc)))
    except Exception:
        pipe.send((False, 'operation_failed'))
    finally:
        pipe.close()


def bounded_call(function, args, timeout):
    """Hard wall-clock process budget including DNS / parser / provider work."""
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(child, function, args), daemon=True)
    process.start(); child.close()
    try:
        if not parent.poll(timeout):
            raise InputSourceError('operation_timeout')
        try:
            ok, value = parent.recv()
        except EOFError:
            raise InputSourceError('operation_failed') from None
        if not ok:
            raise InputSourceError(value)
        return value
    finally:
        parent.close()
        if process.is_alive(): process.terminate()
        process.join(timeout=2)
        if process.is_alive(): process.kill(); process.join()


def fetch_document(url):
    policy = json.loads((ROOT / 'tools/collection/policy.json').read_text())
    # Private temporary metadata, removed on normal completion; no source bodies.
    with tempfile.TemporaryDirectory(prefix='algotop-console-') as cache:
        return fetch_source(url, policy, Path(cache))


def provider_extract(doc):
    config = Config.from_env()
    # Console permits official OpenAI only. No arbitrary endpoint / key routing.
    if config.base_url != 'https://api.openai.com/v1':
        raise ExtractionError('console_requires_official_openai_endpoint')
    config.attempts = 1; config.timeout = 30; config.budget_seconds = 35
    return extract(doc, json.loads((ROOT / 'data.json').read_text()), config=config)


def demo_extract(doc):
    rows = []
    for question, disposition in DEMO_QUESTIONS:
        start = doc['text'].index(question)
        rows.append({'question':question,'disposition':disposition,'evidence':{'quote':question,'start':start,'end':start+len(question)}})
    response = NS(choices=[NS(finish_reason='stop', message=NS(content=json.dumps({'questions':rows}), refusal=None))])
    client = NS(chat=NS(completions=NS(create=lambda **kwargs:response)))
    return extract(doc, json.loads((ROOT / 'data.json').read_text()), client=client, config=Config(model='demo-manual-fixture-not-live-api'))


class App:
    def __init__(self, workspace_dir=None):
        self.workspace_dir = Path(workspace_dir or ROOT / ".local-review")
        self.demo_directory = tempfile.TemporaryDirectory(prefix="algotop-v7-demo-")
        self.stores = {}
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.document = None
        self.result = None
        self.active_preview_id = None
    def settings(self):
        model = os.environ.get('ALGOTOP_LLM_MODEL','')
        # Configured model labels are validated, never echo arbitrary environment text.
        try:
            config = Config.from_env()
            model = config.model
            endpoint_ok = config.base_url == 'https://api.openai.com/v1'
        except ExtractionError:
            model = '未配置或配置无效'; endpoint_ok = False
        sdk_available = importlib.util.find_spec('openai') is not None
        node_available = shutil.which('node') is not None
        parser_available = importlib.util.find_spec('trafilatura') is not None
        return {'openai_sdk_available':sdk_available,'node_available':node_available,'parser_available':parser_available,'key_configured':bool(os.environ.get('OPENAI_API_KEY')),'provider':'OpenAI（官方端点）','model':model,'provider_ready':bool(os.environ.get('OPENAI_API_KEY')) and endpoint_ok and sdk_available,'csrf_token':self.token}
    def review_store(self):
        from review_commit import ReviewStore
        demo = bool(self.document['demo'])
        if demo not in self.stores:
            directory = Path(self.demo_directory.name) / 'workspace' if demo else self.workspace_dir
            self.stores[demo] = ReviewStore(directory, ROOT / 'data.json', demo=demo)
        return self.stores[demo]
    def action(self, path, data):
        fields = {'/api/demo':set(),'/api/import':{'url','text','kind'},'/api/fetch':{'url'},'/api/extract':{'document_id','mode','confirm_transfer'},'/api/export':{'document_id','excluded_ids'},'/api/reset':set()}
        fields.update({'/api/review/state':{'document_id'}, '/api/review/preview':{'document_id','decisions'}, '/api/review/apply':{'document_id','preview_id','confirmed'}, '/api/review/rollback':{'document_id','transaction_id','confirmed'}})
        if path not in fields or not isinstance(data,dict) or set(data)-fields[path]:
            raise InputSourceError('invalid_request')
        if path in {'/api/demo','/api/import','/api/fetch','/api/reset'}:
            self.document = None; self.result = None; self.active_preview_id = None
            if path == '/api/reset': return {'cleared':True}
            if path == '/api/demo':
                doc = load_import(DEMO_TEXT, 'https://example.com/algotop-synthetic-demo', 'text')
            elif path == '/api/import':
                doc = bounded_call(load_import, (data.get('text'),data.get('url'),data.get('kind')), 10)
            else:
                doc = bounded_call(fetch_document, (data.get('url'),), 25)
            doc.update(document_id=secrets.token_urlsafe(18),demo=path == '/api/demo')
            self.document = doc
            return doc
        if not self.document or data.get('document_id') != self.document['document_id']:
            raise InputSourceError('stale_or_missing_document')
        if path.startswith('/api/review/'):
            if not self.result: raise InputSourceError('extract_before_review')
            store = self.review_store()
            if path == '/api/review/state':
                state = store.state()
                state['mode'] = 'demo_sandbox' if self.document['demo'] else 'local_working_copy'
                return state
            if path == '/api/review/preview':
                self.active_preview_id = None
                preview = store.preview(self.result, data.get('decisions'), trusted_document=self.document)
                self.active_preview_id = preview['preview_id']
                return preview
            if path == '/api/review/apply':
                if not self.active_preview_id or data.get('preview_id') != self.active_preview_id:
                    raise InputSourceError('stale_preview')
                return store.apply(data.get('preview_id'), confirmed=data.get('confirmed'))
            return store.rollback(data.get('transaction_id'), confirmed=data.get('confirmed'))
        if path == '/api/extract':
            self.result = None
            self.active_preview_id = None
            # The UI must load a schema-validated review state after extraction.
            # Fail before any potentially billed call when that prerequisite is absent.
            if shutil.which('node') is None:
                raise InputSourceError('schema_validator_unavailable')
            if data.get('mode') == 'demo':
                if not self.document['demo']: raise InputSourceError('demo_requires_synthetic_fixture')
                result = demo_extract(self.document)
            elif data.get('mode') == 'provider':
                if data.get('confirm_transfer') is not True: raise InputSourceError('content_transfer_consent_required')
                if self.document['demo']: raise InputSourceError('demo_cannot_use_paid_provider')
                result = bounded_call(provider_extract, (self.document,), 40)
            else: raise InputSourceError('invalid_mode')
            for field in ('used_parser','parser_version','parser_fallback_reason','access_status'):
                result[field] = self.document.get(field)
            result['demo'] = self.document['demo']
            result['document_id'] = self.document['document_id']
            self.result = result
            return result
        if not self.result: raise InputSourceError('extract_before_export')
        excluded = data.get('excluded_ids')
        valid = {row['id'] for row in self.result['question_candidates']}
        if not isinstance(excluded,list) or any(not isinstance(v,str) or v not in valid for v in excluded):
            raise InputSourceError('invalid_exclusions')
        result = copy.deepcopy(self.result)
        result['question_candidates'] = [r for r in result['question_candidates'] if r['id'] not in excluded]
        result['manual_excluded_count'] = len(set(excluded))
        # Export is server-authored; client cannot submit replacement candidates.
        return result


class Handler(BaseHTTPRequestHandler):
    server_version = 'AlgoWenLocal/8'
    def log_message(self, *args): pass # Never log URLs, documents, or tokens.
    def setup(self):
        super().setup(); self.connection.settimeout(5)
    def respond(self, status, value, mime='application/json; charset=utf-8'):
        raw = json.dumps(value,ensure_ascii=False).encode() if mime.startswith('application/json') else value.encode()
        self.send_response(status)
        self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass
    def guard(self, post=False):
        expected = '127.0.0.1:'+str(self.server.server_port)
        hosts = self.headers.get_all('Host',[])
        origins = self.headers.get_all('Origin',[])
        if hosts != [expected] or (origins and origins != ['http://'+expected]): return False
        if self.headers.get('Sec-Fetch-Site') not in (None,'none','same-origin'): return False
        if post and (origins != ['http://'+expected] or self.headers.get_all('X-CSRF-Token',[]) != [self.server.app.token]): return False
        return True
    def do_GET(self):
        if not self.guard(): return self.respond(403,{'error':'local_origin_required'})
        if self.path == '/api/settings': return self.respond(200,self.server.app.settings())
        files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if self.path not in files: return self.respond(404,{'error':'not_found'})
        name,mime=files[self.path]
        self.respond(200,(ROOT/'local-console'/name).read_text(),mime)
    def do_POST(self):
        if not self.guard(True): return self.respond(403,{'error':'local_origin_required'})
        if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
            return self.respond(400,{'error':'json_required'})
        lengths=self.headers.get_all('Content-Length',[])
        if len(lengths)!=1 or not lengths[0].isdigit(): return self.respond(400,{'error':'invalid_length'})
        length=int(lengths[0])
        if not 0<length<=MAX_REQUEST: return self.respond(413,{'error':'input_too_large'})
        # Read bounded request bodies before taking the workflow lock. Slow clients
        # cannot block other reviewers; socket timeout still bounds this read.
        try:
            raw = self.rfile.read(length)
            if len(raw) != length: raise ValueError('incomplete_body')
            from review_commit import strict_load
            data = strict_load(raw)
        except Exception:
            return self.respond(400, {'error':'invalid_request_body'})
        if not self.server.app.lock.acquire(blocking=False): return self.respond(409,{'error':'operation_in_progress'})
        try:
            result=self.server.app.action(self.path,data)
            status, response = 200, result
        except (InputSourceError,ExtractionError,ReviewError) as exc:
            conflicts = {'stale_preview','working_copy_changed_since_apply','working_copy_changed_since_rollback','not_latest_transaction','operation_in_progress'}
            code = str(exc) if re.fullmatch(r'[a-z][a-z0-9_]{0,79}', str(exc)) else 'invalid_or_failed_request'
            status, response = (409 if code in conflicts else 400), {'error':code,'fallback':self.path=='/api/fetch'}
        except Exception:
            status, response = 400, {'error':'invalid_or_failed_request','fallback':self.path=='/api/fetch'}
        finally: self.server.app.lock.release()
        self.respond(status,response)


class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    # Bound incoming request workers, including idle clients.
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(8)
        super().__init__(*args,**kwargs)
    def server_close(self):
        super().server_close()
        if hasattr(self, "app"): self.app.demo_directory.cleanup()
    def process_request(self,request,address):
        if not self.slots.acquire(False): request.close(); return
        try: super().process_request(request,address)
        except Exception: self.slots.release(); raise
    def process_request_thread(self,request,address):
        try: super().process_request_thread(request,address)
        finally: self.slots.release()


def create_server(port=8765, workspace_dir=None):
    server=LocalServer(('127.0.0.1',port),Handler)
    server.app=App(workspace_dir)
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    server=create_server(args.port)
    print(f'本地私有控制台：http://127.0.0.1:{server.server_port}（不发布；Ctrl+C 停止）',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__': main()
