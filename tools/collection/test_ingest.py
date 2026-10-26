import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.find_spec('ingest')
if SPEC:
    import ingest

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SPEC, 'ingestion module not implemented yet')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.policy = {'example.org': {'terms_status':'permitted','terms_url':'https://example.org/terms','reviewed_at':'2026-10-25','allowed_paths':['/posts/']}}
    def pipeline(self, replies):
        calls=[]
        def transport(url):
            calls.append(url)
            return replies.pop(0)
        p=ingest.Pipeline(Path(self.tmp.name), self.policy, transport=transport, today='2026-10-25', sleeper=lambda _:None)
        return p,calls
    def test_canonical_tracking_not_identity(self):
        self.assertEqual(ingest.canonical('HTTPS://EXAMPLE.org/posts/1?utm_source=x&id=2#q'), 'https://example.org/posts/1?id=2')
        self.assertNotEqual(ingest.canonical('https://example.org/p?a=1&b=2'),ingest.canonical('https://example.org/p?b=2&a=1'))
    def test_invalid_urls(self):
        for u in ['file:///etc/passwd','https://u:p@example.org/p','https://127.0.0.1/p','https://example.org:443/p','http://example.org/p','https://example.org/p?token=secret']:
            with self.subTest(u=u),self.assertRaises(ValueError): ingest.canonical(u)
    def test_import_dedup_preserves_evidence(self):
        rows=ingest.import_rows([{'url':'https://example.org/p?utm_source=x','title':'a'}, {'url':'https://example.org/p#b','title':'b'}], 'fixture')
        self.assertEqual(len(rows),1); self.assertEqual(len(rows[0]['discoveries']),2)
        self.assertEqual(rows[0]['verification_status'],'candidate_unverified')
    def test_date_not_inferred(self):
        r=ingest.import_rows([{'url':'https://example.org/p','publicationDisplay':'09-07','interviewDate':None}], 'f')[0]
        self.assertEqual(r['date_status'],'unknown'); self.assertIsNone(r['interview_date'])
    def test_out_of_range_preserved(self):
        r=ingest.import_rows([{'url':'https://example.org/p','interviewDate':'2021-01-01'}],'f')[0]
        self.assertEqual(r['date_status'],'before_2022')
    def test_unknown_terms_blocks_network(self):
        p,calls=self.pipeline([]); p.policy={}
        self.assertEqual(p.fetch('https://example.org/posts/a')['status'],'policy_blocked');self.assertEqual(calls,[])
    def test_stale_review_blocks(self):
        p,calls=self.pipeline([]);p.policy['example.org']['reviewed_at']='2025-01-01'
        self.assertEqual(p.fetch('https://example.org/posts/a')['status'],'policy_blocked');self.assertEqual(calls,[])
    def test_path_boundary(self):
        p,calls=self.pipeline([])
        self.assertEqual(p.fetch('https://example.org/postsecret/a')['status'],'policy_blocked');self.assertEqual(calls,[])
    def test_robots_deny(self):
        p,calls=self.pipeline([(200,'text/plain',b'User-agent: *\nDisallow: /posts/')])
        self.assertEqual(p.fetch('https://example.org/posts/a')['status'],'robots_blocked');self.assertEqual(len(calls),1)
    def test_robots_error_fail_closed(self):
        p,calls=self.pipeline([(403,'text/plain',b'')])
        self.assertEqual(p.fetch('https://example.org/posts/a')['status'],'robots_unavailable');self.assertEqual(len(calls),1)
    def test_fetch_cache_and_title(self):
        p,calls=self.pipeline([(200,'text/plain',b'User-agent: *\nAllow: /'),(200,'text/html',b'<title>A &amp; B</title><p>Hello</p>')])
        a=p.fetch('https://example.org/posts/a');b=p.fetch('https://example.org/posts/a')
        self.assertEqual(a['status'],'fetched_unverified');self.assertEqual(a['title'],'A & B');self.assertEqual(b['status'],'cached_unverified');self.assertEqual(len(calls),2)
        self.assertTrue(a['content_sha256']);self.assertNotIn('body',a)
    def test_no_retry_auth_or_rate_limit(self):
        for code in [401,403,429,302]:
            p,calls=self.pipeline([(404,'text/plain',b''),(code,'text/html',b'')])
            self.assertEqual(p.fetch('https://example.org/posts/a')['status'],f'http_{code}');self.assertEqual(len(calls),2)
    def test_bounded_server_retry(self):
        p,calls=self.pipeline([(404,'text/plain',b''),(503,'text/html',b''),(503,'text/html',b'')])
        self.assertEqual(p.fetch('https://example.org/posts/a')['status'],'http_503');self.assertEqual(len(calls),3)
    def test_robots_html_error_is_not_permission(self):
        p,calls=self.pipeline([(200,'text/html',b'<html>Access denied</html>'),(200,'text/html',b'ok')])
        self.assertEqual(p.fetch('https://example.org/posts/a')['status'],'robots_unavailable')
    def test_access_denial_pauses_host(self):
        p,calls=self.pipeline([(404,'text/plain',b''),(429,'text/html',b''),(200,'text/html',b'ok')])
        p.fetch('https://example.org/posts/a')
        self.assertEqual(p.fetch('https://example.org/posts/b')['status'],'host_paused')
        self.assertEqual(len(calls),2)
    def test_non_html_rejected(self):
        p,calls=self.pipeline([(404,'text/plain',b''),(200,'application/pdf',b'pdf')])
        self.assertEqual(p.fetch('https://example.org/posts/a')['status'],'unsupported_content')

if __name__=='__main__':unittest.main()
