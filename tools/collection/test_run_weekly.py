import importlib.util
import json
import hashlib
import datetime
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
from types import SimpleNamespace
from extract import Config

SPEC=importlib.util.find_spec('run_weekly')
if SPEC:
    import run_weekly as weekly

class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SPEC, 'weekly runner missing')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.calls=[];self.now=0
        owner=self
        class Collector:
            def __init__(self,*args,**kwargs):owner.calls.append(('collector_config',kwargs))
            def run(self,sources,network=False):
                owner.calls.append(('discover',network))
                return {'source_candidates':[{'url':f'https://example.org/{i}'} for i in range(8)],'requests':1,'runs':[]}
        self.collector=Collector
        self.policy={'example.org':{'body_extraction_status':'permitted','terms_status':'permitted','terms_url':'https://example.org/terms','reviewed_at':datetime.date.today().isoformat(),'allowed_paths':['/']}}
    def fetch(self,url,policy,cache,**kwargs):
        self.calls.append(('fetch',url));return {'text':'private full body','source_url':url,'input_kind':'policy_fetched_text'}
    def extract(self,doc,baseline,client,config,**kwargs):
        self.calls.append(('extract',config.budget_seconds))
        return {'question_candidates':[{'id':'same','question':'Question?', 'evidence':[{'url':doc['source_url'],'quote':'Question?'}]}]}
    def run_job(self,**overrides):
        opts=dict(network=True,allow_llm_content_transfer=True,collector_factory=self.collector,fetcher=self.fetch,extractor=self.extract,clock=lambda:self.now,config=Config(model='mock'))
        opts.update(overrides)
        return weekly.run({'sources':[]},self.policy,{},self.tmp.name+'/checkpoint',self.tmp.name+'/cache',**opts)
    def test_offline_and_without_consent_make_no_body_or_api_calls(self):
        for args in ({'network':False},{'allow_llm_content_transfer':False}):
            self.calls=[];result=self.run_job(**args)
            self.assertIn(('discover',False),self.calls)
            self.assertFalse(any(c[0] in {'fetch','extract'} for c in self.calls))
            self.assertFalse(result['published'])
    def test_caps_documents_deduplicates_and_never_counts(self):
        result=self.run_job(max_documents=100)
        self.assertEqual(len([c for c in self.calls if c[0]=='fetch']),5)
        self.assertEqual(len(result['question_candidates']),1)
        row=result['question_candidates'][0]
        self.assertEqual(len(row['evidence']),5)
        self.assertEqual(row['verification_status'],'pending_human_approval')
        self.assertFalse(row['countEligible']);self.assertEqual(row['occurrence_count'],0)
        self.assertNotIn('private full body',str(result))
    def test_cli_direct_transport_is_explicit_opt_in(self):
        root=Path(self.tmp.name)
        for name,data in [('registry',{'sources':[]}),('policy',self.policy),('baseline',{})]:
            (root/name).write_text(json.dumps(data))
        args=['--registry',str(root/'registry'),'--policy',str(root/'policy'),'--baseline',str(root/'baseline'),'--output',str(root/'out')]
        fake=SimpleNamespace(direct_transport=lambda *a,**k:None)
        with patch.dict('sys.modules',{'safe_transport':fake}), patch.object(weekly,'run',return_value={'status':'dry_run','documents':[],'question_candidates':[]}) as run:
            self.assertEqual(weekly.main(args),0)
            self.assertNotIn('collector_factory',run.call_args.kwargs)
            self.assertEqual(weekly.main(args+['--direct-public-egress']),0)
            self.assertEqual(run.call_args.kwargs['collector_factory'].keywords['http'].keywords['allowed_hosts'],{'example.org'})
            self.assertIs(run.call_args.kwargs['fetcher'].keywords['transport'].func,fake.direct_transport)

    def test_body_policy_blocks_before_fetch(self):
        self.policy={};result=self.run_job()
        self.assertFalse(any(c[0]=='fetch' for c in self.calls))
        self.assertTrue(result['skipped'])
        self.assertTrue(all(r['status']=='body_policy_blocked' for r in result['skipped']))
        self.assertEqual(result['documents'],[])
    def test_blocked_links_do_not_consume_document_budget(self):
        class MixedCollector:
            def __init__(self,*args,**kwargs):pass
            def run(self,*args,**kwargs):return {'source_candidates':[{'url':'https://blocked.org/'+str(i)} for i in range(3)]+[{'url':'https://example.org/ok'}]}
        result=self.run_job(collector_factory=MixedCollector,max_documents=1)
        self.assertEqual(len(result['documents']),1)
        self.assertEqual(result['documents'][0]['status'],'pending_human_approval')
        self.assertEqual(len(result['skipped']),3)
        self.assertEqual(result['documents'][0]['source_url'],'https://example.org/ok')

    def test_disallowed_exact_paths_do_not_consume_document_budget(self):
        class MixedCollector:
            def __init__(self,*args,**kwargs):pass
            def run(self,*args,**kwargs):return {'source_candidates':[{'url':'https://example.org/blocked'+str(i)} for i in range(3)]+[{'url':'https://example.org/allowed'}]}
        self.policy['example.org'].pop('allowed_paths')
        self.policy['example.org']['allowed_exact_paths']=['/allowed']
        result=self.run_job(collector_factory=MixedCollector,max_documents=1)
        self.assertEqual(len(result['documents']),1)
        self.assertEqual(result['documents'][0]['source_url'],'https://example.org/allowed')
        self.assertEqual(len(result['skipped']),3)
        self.assertTrue(all(row['status']=='policy_blocked' for row in result['skipped']))
        self.assertEqual([call[1] for call in self.calls if call[0]=='fetch'],['https://example.org/allowed'])

    def test_merged_evidence_retains_document_hash_kind_and_model(self):
        result=self.run_job(max_documents=2)
        evidence=result['question_candidates'][0]['evidence']
        self.assertEqual(len(evidence),2)
        for item in evidence:
            self.assertEqual(item.get('text_sha256'),hashlib.sha256(b'private full body').hexdigest())
            self.assertEqual(item['input_kind'],'policy_fetched_text')
            self.assertEqual(item['model'],'mock')

    def test_budget_expiry_prevents_extraction_and_later_fetch(self):
        def slow(url,*args,**kwargs):
            result=self.fetch(url,*args,**kwargs);self.now=301;return result
        result=self.run_job(fetcher=slow,max_seconds=999)
        self.assertEqual(len([c for c in self.calls if c[0]=='fetch']),1)
        self.assertFalse(any(c[0]=='extract' for c in self.calls))
        self.assertEqual(result['documents'][0]['status'],'time_budget_exhausted')
    def test_extraction_budget_clamped_to_remaining(self):
        self.run_job(max_seconds=10)
        self.assertTrue(all(c[1]<=10 for c in self.calls if c[0]=='extract'))
    def test_errors_are_constant_not_exception_content(self):
        def bad(*args,**kwargs):raise ValueError('secret-value')
        result=self.run_job(fetcher=bad)
        self.assertNotIn('secret-value',str(result))
        self.assertTrue(all(r['status']=='document_failed' for r in result['documents']))

if __name__=='__main__':unittest.main()
