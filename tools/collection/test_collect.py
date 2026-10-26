import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SPEC = importlib.util.find_spec('collect')
if SPEC:
    import collect

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SPEC, 'multi-source collection module missing')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.policy = {'example.org': {'terms_status':'permitted','terms_url':'https://example.org/terms','reviewed_at':'2026-10-26','allowed_paths':['/']}}
    def run_collector(self, sources, replies, **kw):
        calls=[]
        def http(url):
            calls.append(url); return replies.pop(0)
        runner=collect.Collector(self.policy, Path(self.tmp.name)/'checkpoint.json', http=http, today='2026-10-26', sleeper=lambda _:None, **kw)
        return runner.run(sources, network=True), calls
    def source(self, adapter='rss'):
        return {'id':'test','platform':'personal_blog','adapter':adapter,'url':'https://example.org/feed/','enabled':True}
    def test_exact_feed_permission_does_not_allow_article_or_sibling(self):
        self.policy['example.org']['allowed_paths']=[]
        self.policy['example.org']['allowed_exact_paths']=['/feed/']
        r,calls=self.run_collector([self.source()],[(404,'text/plain',b''),(200,'application/rss+xml',b'<rss><channel/></rss>')])
        self.assertEqual(r['runs'][0]['status'],'fetched_unverified')
        self.assertEqual(len(calls),2)
        s=dict(self.source(),url='https://example.org/feed/article')
        r,calls=self.run_collector([s],[])
        self.assertEqual(r['runs'][0]['status'],'policy_blocked');self.assertEqual(calls,[])
    def test_source_candidates_are_not_question_candidates(self):
        r,_=self.run_collector([self.source('html')],[(404,'text/plain',b''),(200,'text/html',b'<a href="/post/a">Interview question</a>')])
        self.assertIn('source_candidates',r)
        self.assertEqual(r['source_candidates'],r['candidates'])
        self.assertEqual(r['question_candidates'],[])
        self.assertEqual(r['metrics']['verified_common_questions'],0)
        self.assertEqual(r['metrics']['discovered_source_candidates'],1)
    def test_managed_transport_rejects_private_urls_before_network(self):
        self.assertTrue(hasattr(collect,'managed_transport'))
        for url in ['https://127.0.0.1/a','http://example.org/a','https://localhost/a','https://u:p@example.org/a']:
            with self.assertRaises(ValueError):collect.managed_transport(url)
    def test_missing_managed_proxy_fails_closed(self):
        with patch('urllib.request.getproxies',return_value={}):
            with self.assertRaisesRegex(ValueError,'managed HTTPS proxy'):
                collect.managed_transport('https://example.org/feed/')
    def test_checkpoint_obeys_smaller_candidate_limit(self):
        replies=[(404,'text/plain',b''),(200,'text/html',b'<a href="/a">A</a><a href="/b">B</a>')]
        a,_=self.run_collector([self.source('html')],replies,max_candidates=2)
        b,_=self.run_collector([self.source('html')],[],max_candidates=1)
        self.assertEqual(len(b['candidates']),1)
    def test_success_retains_http_status(self):
        r,_=self.run_collector([self.source()],[(404,'text/plain',b''),(200,'application/rss+xml',b'<rss/>')])
        self.assertEqual(r['runs'][0].get('http_status'),200)
    def test_rss_adapter_accepts_atom_content_type(self):
        r,_=self.run_collector([self.source('rss')],[(404,'text/plain',b''),(200,'application/atom+xml',b'<feed xmlns="http://www.w3.org/2005/Atom"/>')])
        self.assertEqual(r['runs'][0]['status'],'fetched_unverified')
    def test_html_relevance_filter_keeps_seed_not_navigation(self):
        source=dict(self.source('html'),candidate_keywords=['interview'])
        r,_=self.run_collector([source],[(404,'text/plain',b''),(200,'text/html',b'<title>Algorithm Interview</title><a href="/about">About</a><a href="/tags/interview">Interview tag</a><a href="/post/a">Another interview</a>')])
        self.assertEqual({x['url'] for x in r['candidates']},{source['url'],'https://example.org/post/a'})
        self.assertEqual(next(x for x in r['candidates'] if x['url']==source['url'])['access_status'],'fetched_source_page_unverified')
    def test_default_offline(self):
        c=collect.Collector({},Path(self.tmp.name)/'c',http=lambda _:self.fail('network'))
        r=c.run([self.source()]); self.assertEqual(r['runs'][0]['status'],'dry_run');self.assertEqual(r['candidates'],[])
    def test_closed_policy(self):
        self.policy={};r,calls=self.run_collector([self.source()],[])
        self.assertEqual(r['runs'][0]['status'],'policy_blocked');self.assertEqual(calls,[])
    def test_robots_deny(self):
        r,calls=self.run_collector([self.source()],[(200,'text/plain',b'User-agent: *\nDisallow: /')])
        self.assertEqual(r['runs'][0]['status'],'robots_blocked');self.assertEqual(len(calls),1)
    def test_rss_candidates_only(self):
        body=b'<rss><channel><item><title>Interview</title><link>https://example.org/posts/a?utm_source=x</link><description>secret entire article</description><pubDate>Mon, 26 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        r,calls=self.run_collector([self.source()],[(404,'text/plain',b''),(200,'application/rss+xml',body)])
        row=r['candidates'][0];self.assertEqual(row['url'],'https://example.org/posts/a');self.assertEqual(row['verification_status'],'candidate_unverified');self.assertEqual(row['occurrence_count'],0);self.assertNotIn('secret entire article',json.dumps(r));self.assertEqual(len(calls),2)
    def test_atom_relative_link(self):
        body=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Algorithm interview</title><link href="/posts/b"/><updated>2026-10-26</updated></entry></feed>'
        r,_=self.run_collector([self.source('atom')],[(404,'text/plain',b''),(200,'application/atom+xml',body)])
        self.assertEqual(r['candidates'][0]['url'],'https://example.org/posts/b')
    def test_html_links_no_script_no_article(self):
        body=b'<html><title>Interview</title><script>https://example.org/hidden</script><a href="/post/a">Interview question</a><a href="javascript:bad">bad</a><p>Full article not stored</p></html>'
        r,_=self.run_collector([self.source('html')],[(404,'text/plain',b''),(200,'text/html',body)])
        self.assertEqual(len(r['candidates']),1);self.assertNotIn('Full article',json.dumps(r))
    def test_github_repo_identity(self):
        body=b'[interview](https://github.com/Owner/Repo/blob/main/a.md)\n[q](https://github.com/owner/repo/issues/2)'
        r,_=self.run_collector([self.source('github_readme')],[(404,'text/plain',b''),(200,'text/plain',body)])
        self.assertEqual({x['canonical_source_id'] for x in r['candidates']},{'github:owner/repo'})
        self.assertEqual(r['independent_interview_count'],0)
    def test_checkpoint_idempotent(self):
        replies=[(404,'text/plain',b''),(200,'text/html',b'<a href="/post/a">Interview</a>')]
        a,_=self.run_collector([self.source('html')],replies)
        b,calls=self.run_collector([self.source('html')],[])
        self.assertEqual(a['candidates'],b['candidates']);self.assertEqual(calls,[]);self.assertEqual(b['runs'][0]['status'],'checkpoint_reused')
    def test_budget_includes_robots(self):
        r,calls=self.run_collector([self.source()],[(404,'text/plain',b'')],max_requests=1)
        self.assertEqual(len(calls),1);self.assertEqual(r['runs'][0]['status'],'budget_exhausted')
    def test_auth_pauses_host(self):
        s=self.source();s2=dict(s,id='second',url='https://example.org/feed/two')
        r,calls=self.run_collector([s,s2],[(404,'text/plain',b''),(403,'text/html',b'')])
        self.assertEqual(len(calls),2);self.assertEqual(r['runs'][1]['status'],'host_paused')
    def test_pending_never_network(self):
        s=dict(self.source(),enabled=False)
        r,calls=self.run_collector([s],[]);self.assertEqual(r['runs'][0]['status'],'pending');self.assertEqual(calls,[])
    def test_content_mismatch_not_success(self):
        r,_=self.run_collector([self.source()],[(404,'text/plain',b''),(200,'text/html',b'<html>Login</html>')])
        self.assertEqual(r['runs'][0]['status'],'unsupported_content')
    def test_oversized_body_rejected(self):
        r,_=self.run_collector([self.source()],[(404,'text/plain',b''),(200,'application/rss+xml',b'x'*512001)])
        self.assertEqual(r['runs'][0]['status'],'response_too_large')
    def test_personal_project_question_is_not_auto_approved(self):
        r,_=self.run_collector([self.source('html')],[(404,'text/plain',b''),(200,'text/html','<a href="/post/a">你的项目为什么用BERT</a>'.encode())])
        row=r['candidates'][0];self.assertEqual(row['common_question_status'],'needs_human_review');self.assertEqual(row['occurrence_count'],0)
    def test_redirect_not_followed(self):
        r,calls=self.run_collector([self.source()],[(404,'text/plain',b''),(302,'text/html',b'')])
        self.assertEqual(len(calls),2);self.assertEqual(r['runs'][0]['status'],'http_302')

if __name__=='__main__': unittest.main()
