import http.client
import importlib.util
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

class ConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.find_spec('local_console')
        assert spec is not None, 'Local console server is not implemented'
        import local_console
        cls.mod = local_console
    def setUp(self):
        self.server = self.mod.create_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = '127.0.0.1:' + str(self.server.server_port)
        self.token = self.server.app.token
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
    def request(self, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=50)
        h = {'Host':self.host, 'Origin':'http://'+self.host, 'X-CSRF-Token':self.token, 'Content-Type':'application/json'}
        h.update(headers or {})
        connection.request('POST' if body is not None else 'GET', path, json.dumps(body) if body is not None else None, h)
        response = connection.getresponse(); data = response.read(); status=response.status; connection.close()
        return status, json.loads(data) if 'application/json' in response.getheader('Content-Type','') else data.decode()
    def test_guards(self):
        for headers in [{'Host':'evil.test'}, {'Origin':'https://evil.test'}, {'X-CSRF-Token':'wrong'}]:
            self.assertEqual(self.request('/api/demo', {}, headers)[0],403)
        self.assertEqual(self.request('/',headers={'Host':'evil.test'})[0],403)
    def test_import_xss_is_text_and_provenance(self):
        status, doc=self.request('/api/import', {'url':'https://example.com/post','kind':'html','text':'<script>alert(1)</script><p>什么是注意力机制？</p>'})
        self.assertEqual(status,200); self.assertNotIn('alert',doc['text']); self.assertIn('注意力',doc['text'])
        self.assertEqual(doc['input_kind'],'user_supplied_html'); self.assertTrue(doc['document_id'])
    def test_demo_export_is_pending_and_excludes_projects(self):
        status, doc=self.request('/api/demo',{})
        self.assertEqual(status,200); self.assertTrue(doc['demo'])
        status,result=self.request('/api/extract',{'document_id':doc['document_id'],'mode':'demo'})
        self.assertEqual(status,200); self.assertTrue(result['demo']); self.assertEqual(len(result['question_candidates']),3)
        ids=[result['question_candidates'][0]['id']]
        status,export=self.request('/api/export',{'document_id':doc['document_id'],'excluded_ids':ids})
        self.assertEqual(status,200); self.assertEqual(len(export['question_candidates']),2)
        self.assertFalse(export['published']); self.assertNotIn('text',export)
        self.assertEqual(export['used_parser'], 'plain_text')
        self.assertEqual(export['access_status'], 'user_supplied_unverified')
        self.assertFalse(export['question_candidates'][0]['countEligible'])
        self.assertEqual(export['question_candidates'][0]['verification_status'],'pending_human_approval')
    def test_real_provider_needs_confirmation_and_current_document(self):
        _,doc=self.request('/api/demo',{})
        with patch.object(self.mod, 'extract', side_effect=AssertionError('must not call provider')):
            self.assertEqual(self.request('/api/extract',{'document_id':doc['document_id'],'mode':'provider'})[0],400)
            self.assertEqual(self.request('/api/extract',{'document_id':'stale','mode':'provider','confirm_transfer':True})[0],400)
    def test_policy_block_is_explicit_and_import_remains_available(self):
        status,error=self.request('/api/fetch',{'url':'https://example.com/blocked'})
        self.assertEqual(status,400); self.assertEqual(error['error'],'policy_blocked'); self.assertTrue(error['fallback'])
        self.assertEqual(self.request('/api/import',{'url':'https://example.com/blocked','kind':'text','text':'什么是注意力机制？'})[0],200)
    def test_new_input_invalidates_results_and_limits(self):
        _,doc=self.request('/api/demo',{})
        self.assertEqual(self.request('/api/import',{'url':'https://example.com/x','text':'x'*40001,'kind':'text'})[0],400)
        self.assertEqual(self.request('/api/export',{'document_id':doc['document_id'],'excluded_ids':[]})[0],400)
    def test_settings_never_exposes_key_and_ui_has_no_inline_execution(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'SENTINEL_SECRET','ALGOTOP_LLM_MODEL':'test-model'}):
            status,settings=self.request('/api/settings')
        self.assertEqual(status,200); self.assertTrue(settings['key_configured']); self.assertNotIn('SENTINEL_SECRET',json.dumps(settings))
        status,script=self.request('/app.js'); self.assertEqual(status,200)
        self.assertNotIn('innerHTML',script); self.assertNotIn('localStorage',script)
    def test_missing_key_fails_without_provider_network(self):
        with patch.dict('os.environ', {'ALGOTOP_LLM_MODEL':'test-model'}, clear=True):
            with self.assertRaisesRegex(self.mod.ExtractionError,'missing_server_api_key'):
                self.mod.provider_extract(self.mod.load_import('Q?', 'https://example.com/x'))
    def test_import_has_hard_budget(self):
        with patch.object(self.mod, 'bounded_call', side_effect=self.mod.InputSourceError('operation_timeout')):
            status,error=self.request('/api/import',{'url':'https://example.com/x','text':'Q?','kind':'text'})
        self.assertEqual(status,400)
        self.assertEqual(error['error'],'operation_timeout')
    def test_request_fields_cannot_set_secrets(self):
        self.assertEqual(self.request('/api/demo',{'api_key':'no'})[0],400)

if __name__=='__main__': unittest.main()

class V7ConsoleTests(ConsoleTests):
    def test_review_ui_requires_explicit_decisions_and_confirmation(self):
        _, html = self.request('/')
        self.assertIn('04 · 入库预览', html)
        self.assertIn('本地工作副本', html)
        self.assertIn('确认写入', html)
        _, script = self.request('/app.js')
        self.assertIn('pending', script)
        self.assertIn('/api/review/preview', script)
        self.assertIn('/api/review/rollback', script)
    def test_incomplete_body_does_not_hold_workflow_lock(self):
        import socket, time
        sock=socket.create_connection(('127.0.0.1',self.server.server_port))
        request=(f'POST /api/demo HTTP/1.1\r\nHost: {self.host}\r\nOrigin: http://{self.host}\r\nX-CSRF-Token: {self.token}\r\nContent-Type: application/json\r\nContent-Length: 20\r\n\r\n{{').encode()
        sock.sendall(request); time.sleep(.1)
        try:
            self.assertEqual(self.request('/api/demo',{})[0],200)
        finally: sock.close()
    def test_review_preview_requires_explicit_decisions_and_never_changes_root(self):
        baseline=(ROOT/'data.json').read_bytes()
        _,doc=self.request('/api/demo',{})
        _,result=self.request('/api/extract',{'document_id':doc['document_id'],'mode':'demo'})
        status,state=self.request('/api/review/state',{'document_id':doc['document_id']})
        self.assertEqual(status,200); self.assertEqual(state['mode'],'demo_sandbox')
        self.assertEqual(len(state['questions']),323)
        status,error=self.request('/api/review/preview',{'document_id':doc['document_id'],'decisions':{'schema_version':1,'reviewer':'test','decisions':[]}})
        self.assertEqual(status,400)
        self.assertEqual((ROOT/'data.json').read_bytes(),baseline)
    def test_sandbox_preview_commit_replay_and_rollback_are_guarded(self):
        baseline=(ROOT/'data.json').read_bytes()
        _,doc=self.request('/api/demo',{})
        _,result=self.request('/api/extract',{'document_id':doc['document_id'],'mode':'demo'})
        candidates=result['question_candidates']
        payload={'document_id':doc['document_id'],'decisions':{'schema_version':1,'reviewer':'UI test reviewer','decisions':[
            {'candidate_id':candidates[0]['id'],'action':'add','common_question':True,'source_reviewed':True},
            {'candidate_id':candidates[1]['id'],'action':'merge','target_question_id':'q001','common_question':True,'source_reviewed':True},
            {'candidate_id':candidates[2]['id'],'action':'exclude','reason':'测试排除'}]}}
        status,preview=self.request('/api/review/preview',payload)
        self.assertEqual(status,200,preview)
        self.assertEqual(preview['counts']['new_questions'],1)
        self.assertEqual(preview['counts']['excluded'],1)
        self.assertEqual(preview['totals']['before']['question_count'],323)
        self.assertEqual(preview['totals']['after']['question_count'],324)
        commit={'document_id':doc['document_id'],'preview_id':preview['preview_id'],'confirmed':False}
        self.assertEqual(self.request('/api/review/apply',commit)[0],400)
        commit['confirmed']=True
        status,tx=self.request('/api/review/apply',commit)
        self.assertEqual(status,200,tx);self.assertEqual(tx['status'],'applied')
        status,replayed=self.request('/api/review/apply',commit)
        self.assertEqual(status,200);self.assertEqual(replayed['transaction_id'],tx['transaction_id'])
        self.assertTrue(replayed['replayed'])
        rollback={'document_id':doc['document_id'],'transaction_id':tx['transaction_id'],'confirmed':False}
        self.assertEqual(self.request('/api/review/rollback',rollback)[0],400)
        rollback['confirmed']=True
        status,rolled=self.request('/api/review/rollback',rollback)
        self.assertEqual(status,200,rolled);self.assertEqual(rolled['status'],'rolled_back')
        self.assertEqual((ROOT/'data.json').read_bytes(),baseline)
        _,state=self.request('/api/review/state',{'document_id':doc['document_id']})
        self.assertEqual(len(state['questions']),323)
    def test_server_close_cleans_demo_sandbox(self):
        server=self.mod.create_server(0)
        directory=Path(server.app.demo_directory.name)
        self.assertTrue(directory.exists())
        server.server_close()
        self.assertFalse(directory.exists())
    def test_busy_review_workflow_returns_409(self):
        self.server.app.lock.acquire()
        try:self.assertEqual(self.request('/api/demo',{})[0],409)
        finally:self.server.app.lock.release()
    def test_stale_preview_returns_conflict_without_root_write(self):
        _,doc=self.request('/api/demo',{})
        _,result=self.request('/api/extract',{'document_id':doc['document_id'],'mode':'demo'})
        decisions={'schema_version':1,'reviewer':'test','decisions':[{'candidate_id':r['id'],'action':'exclude','reason':'test'} for r in result['question_candidates']]}
        _,preview=self.request('/api/review/preview',{'document_id':doc['document_id'],'decisions':decisions})
        store=self.server.app.review_store()
        store.data.write_bytes(store.data.read_bytes()+b'\n')
        status,error=self.request('/api/review/apply',{'document_id':doc['document_id'],'preview_id':preview['preview_id'],'confirmed':True})
        self.assertEqual(status,409,error)
        self.assertEqual(error['error'],'stale_preview')
    def test_duplicate_json_keys_are_rejected(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        conn.request('POST','/api/demo','{"unused":1,"unused":2}',{'Host':self.host,'Origin':'http://'+self.host,'X-CSRF-Token':self.token,'Content-Type':'application/json'})
        response=conn.getresponse();body=json.loads(response.read());conn.close()
        self.assertEqual(response.status,400)
        self.assertEqual(body['error'],'invalid_request_body')
    def test_ui_has_separate_source_attestation(self):
        _,script=self.request('/app.js')
        self.assertIn('source_reviewed',script)
        self.assertIn('不代表独立真实性验证',script)
    def test_server_trusted_text_rejects_candidate_evidence_tampering(self):
        _,doc=self.request('/api/demo',{})
        _,result=self.request('/api/extract',{'document_id':doc['document_id'],'mode':'demo'})
        self.server.app.result['question_candidates'][0]['evidence'][0]['quote']='伪造引用'
        decisions={'schema_version':1,'reviewer':'test','decisions':[{'candidate_id':r['id'],'action':'add','common_question':True,'source_reviewed':True} for r in result['question_candidates']]}
        status,error=self.request('/api/review/preview',{'document_id':doc['document_id'],'decisions':decisions})
        self.assertEqual(status,400,error)
        self.assertIn('evidence',error['error'])
    def test_failures_bring_status_into_view(self):
        _,script=self.request('/app.js')
        self.assertIn("$('status').scrollIntoView",script)
    def test_reset_copy_discloses_persisted_review_records(self):
        _,script=self.request('/app.js')
        self.assertIn('本地工作副本、审核记录及已下载文件保留',script)
    def test_preview_ui_displays_before_after_totals(self):
        _,script=self.request('/app.js')
        self.assertIn('reviewPreview.totals',script)
        self.assertIn('基线 → 结果',script)
        self.assertIn('登记来源',script)

class V8ReadinessTests(ConsoleTests):
    def make_preview(self):
        _, doc = self.request('/api/demo', {})
        _, result = self.request('/api/extract', {'document_id':doc['document_id'], 'mode':'demo'})
        decisions = {'schema_version':1, 'reviewer':'test', 'decisions':[
            {'candidate_id':r['id'], 'action':'exclude', 'reason':'test'} for r in result['question_candidates']]}
        status, preview = self.request('/api/review/preview', {'document_id':doc['document_id'], 'decisions':decisions})
        self.assertEqual(status, 200, preview)
        return doc, preview
    def test_preview_cannot_cross_document_sessions(self):
        doc, preview = self.make_preview()
        _, new_doc = self.request('/api/demo', {})
        self.request('/api/extract', {'document_id':new_doc['document_id'], 'mode':'demo'})
        status, error = self.request('/api/review/apply', {'document_id':new_doc['document_id'], 'preview_id':preview['preview_id'], 'confirmed':True})
        self.assertEqual(status, 409, error)
        self.assertEqual(error['error'], 'stale_preview')
    def test_reextract_invalidates_old_preview(self):
        doc, preview = self.make_preview()
        self.request('/api/extract', {'document_id':doc['document_id'], 'mode':'demo'})
        status, error = self.request('/api/review/apply', {'document_id':doc['document_id'], 'preview_id':preview['preview_id'], 'confirmed':True})
        self.assertEqual(status, 409, error)
    def test_errors_do_not_echo_unbounded_dependency_details(self):
        with patch.object(self.server.app, 'action', side_effect=ValueError('SECRET /private/path '+ 'x'*1000)):
            status, error = self.request('/api/demo', {})
        self.assertEqual(status, 400)
        self.assertEqual(error['error'], 'invalid_or_failed_request')
    def test_readiness_reports_local_dependencies_without_network(self):
        _, settings = self.request('/api/settings')
        self.assertIn('openai_sdk_available', settings)
        self.assertIn('node_available', settings)
        self.assertIn('parser_available', settings)
        if not settings['openai_sdk_available']:
            self.assertFalse(settings['provider_ready'])
    def test_visible_brand_and_privacy_warning(self):
        _, html = self.request('/')
        self.assertIn('AlgoWen', html)
        self.assertIn('证据片段', html)
        self.assertIn('v8', html)
    def test_reextract_ui_clears_previous_commit_and_rollback(self):
        _, script = self.request('/app.js')
        section = script.split("$('extract').onclick",1)[1].split("$('export').onclick",1)[0]
        self.assertIn('invalidatePreview()', section)
        self.assertIn('transaction=null', section)
    def test_missing_node_blocks_extraction_before_cost_or_work(self):
        _, doc = self.request('/api/demo', {})
        with patch.object(self.mod.shutil, 'which', return_value=None), patch.object(self.mod, 'demo_extract', side_effect=AssertionError('must check prerequisites first')):
            status, error = self.request('/api/extract', {'document_id':doc['document_id'], 'mode':'demo'})
        self.assertEqual(status, 400)
        self.assertEqual(error['error'], 'schema_validator_unavailable')
