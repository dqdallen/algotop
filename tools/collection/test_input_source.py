import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.find_spec('input_source')
if SPEC:
    import input_source as source


class InputSourceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SPEC, 'input source adapter must exist')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = 'https://example.org/posts/a'
        self.policy = {'example.org': {'terms_status': 'permitted', 'body_extraction_status': 'permitted', 'terms_url': 'https://example.org/terms', 'reviewed_at': '2026-10-27', 'allowed_paths': ['/posts/']}}

    def fetch(self, replies, policy=None):
        self.calls = []
        def transport(url):
            self.calls.append(url)
            return replies.pop(0)
        return source.fetch_source(self.url, self.policy if policy is None else policy, self.tmp.name, transport=transport, today='2026-10-27', sleeper=lambda _: None)

    def test_text_keeps_exact_offsets_and_marks_supplied(self):
        value = '  问题：什么是 LoRA？\n第二行  '
        result = source.load_import(value, self.url)
        self.assertEqual(result['text'], value)
        self.assertEqual(result['source_url'], self.url)
        self.assertEqual(result['input_kind'], 'user_supplied_text')
        self.assertEqual(result['text_sha256'], hashlib.sha256(value.encode()).hexdigest())

    def test_html_drops_active_hidden_and_noncontent_nodes(self):
        result = source.load_import('<p>问题 A</p><script>bad</script><style>bad</style><div hidden>bad</div><span aria-hidden="true">bad</span><div style="display:none">bad</div><template>bad</template><p>问题 B &amp; C</p>', self.url, 'html')
        self.assertNotIn('bad', result['text'])
        self.assertIn('问题 A', result['text'])
        self.assertIn('问题 B & C', result['text'])
        self.assertEqual(result['input_kind'], 'user_supplied_html')

    def test_import_bounds_empty_types_and_invalid_urls(self):
        cases = [('', self.url, 'text'), (' \n ', self.url, 'text'), ('x'*40001, self.url, 'text'), ('<script>'+'x'*512000+'</script>', self.url, 'html'), ('x', 'http://example.org/p', 'text'), ('x', self.url, 'pdf'), (None, self.url, 'text')]
        for args in cases:
            with self.subTest(kind=args[2]), self.assertRaises(source.InputSourceError):
                source.load_import(*args)

    def test_policy_blocks_before_network(self):
        with self.assertRaisesRegex(source.InputSourceError, '^policy_blocked$'):
            self.fetch([], {})
        self.assertEqual(self.calls, [])

    def test_metadata_permission_does_not_authorize_body(self):
        del self.policy['example.org']['body_extraction_status']
        with self.assertRaisesRegex(source.InputSourceError, '^body_policy_blocked$'):
            self.fetch([(404, 'text/plain', b''), (200, 'text/plain', b'question')])
        self.assertEqual(self.calls, [])

    def test_production_transport_requires_explicit_trusted_egress(self):
        with patch.dict('os.environ', {}, clear=True), patch.object(source, 'managed_transport') as http:
            with self.assertRaisesRegex(source.InputSourceError, '^trusted_egress_required$'):
                source.fetch_source(self.url, self.policy, self.tmp.name, today='2026-10-27', sleeper=lambda _: None)
            http.assert_not_called()

    def test_trusted_egress_acknowledgement_uses_existing_transport(self):
        with patch.dict('os.environ', {'ALGOTOP_TRUSTED_EGRESS': '1'}), patch.object(source, 'managed_transport', side_effect=[(404, 'text/plain', b''), (200, 'text/plain', b'question')]):
            result = source.fetch_source(self.url, self.policy, self.tmp.name, today='2026-10-27', sleeper=lambda _: None)
        self.assertEqual(result['text'], 'question')

    def test_robots_blocks_before_article(self):
        with self.assertRaisesRegex(source.InputSourceError, '^robots_blocked$'):
            self.fetch([(200, 'text/plain', b'User-agent: *\nDisallow: /')])
        self.assertEqual(len(self.calls), 1)

    def test_success_exposes_text_only_in_memory(self):
        result = self.fetch([(404, 'text/plain', b''), (200, 'text/html', b'<p>question body</p>')])
        self.assertEqual(result['text'], 'question body')
        self.assertEqual(result['input_kind'], 'policy_fetched_html')
        persisted = ''.join(p.read_text() for p in Path(self.tmp.name).glob('*.json'))
        self.assertNotIn('question body', persisted)
        self.assertNotIn('text_sha256', persisted)

    def test_metadata_cache_does_not_represent_body(self):
        self.fetch([(404, 'text/plain', b''), (200, 'text/plain', b'question')])
        with self.assertRaisesRegex(source.InputSourceError, '^cached_body_unavailable$'):
            self.fetch([(404, 'text/plain', b'')])
        self.assertEqual(len(self.calls), 1)

    def test_error_does_not_leak_exception_or_body(self):
        def transport(url):
            raise OSError('secret-test-value')
        with self.assertRaisesRegex(source.InputSourceError, '^fetch_error$'):
            source.fetch_source(self.url, self.policy, self.tmp.name, transport=transport, today='2026-10-27', sleeper=lambda _: None)

    def test_non_200_unsupported_and_oversized_fail_closed(self):
        for reply, reason in [((403, 'text/html', b'secret'), 'http_403'), ((200, 'application/pdf', b'secret'), 'unsupported_content'), ((200, 'text/plain', b'x'*512001), 'fetch_error')]:
            with self.subTest(reason=reason), self.assertRaisesRegex(source.InputSourceError, '^'+reason+'$'):
                self.fetch([(404, 'text/plain', b''), reply])


if __name__ == '__main__':
    unittest.main()
