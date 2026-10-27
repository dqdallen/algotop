"""Small owned synthetic fixtures only; tests never retrieve source URLs."""
import hashlib
import importlib.util
import socket
import unittest
from unittest.mock import patch
import input_source as source

URL = 'https://example.org/posts/owned'
ARTICLE = ('<html><body><nav>UNWANTED_NAV <a href="https://invalid.test/">Home</a></nav>'
           '<article><h1>本地解析测试</h1><p>什么是注意力机制？这是我们自写的测试文字，不是第三方文章。</p>'
           '<p>第二个问题：如何计算时间复杂度？Unicode café 🚀 保持原样。</p></article>'
           '<footer>UNWANTED_FOOTER</footer></body></html>')


class HtmlParserTests(unittest.TestCase):
    def test_missing_optional_dependency_retains_safe_fallback(self):
        with patch.dict('sys.modules', {'trafilatura': None}):
            doc = source.load_import(ARTICLE, URL, 'html')
        self.assertEqual(doc.get('used_parser'), 'html_fallback')
        self.assertEqual(doc.get('parser_fallback_reason'), 'dependency_unavailable')
        self.assertEqual(doc.get('access_status'), 'user_supplied_unverified')
        self.assertNotIn('UNWANTED', doc['text'])
        self.assertIn('Unicode café 🚀', doc['text'])
        self.assertEqual(doc['text_sha256'], hashlib.sha256(doc['text'].encode()).hexdigest())

    def test_plain_text_reports_no_html_parser(self):
        doc = source.load_import('  中文\nexact offsets  ', URL)
        self.assertEqual(doc.get('used_parser'), 'plain_text')
        self.assertEqual(doc['text'], '  中文\nexact offsets  ')

    @unittest.skipUnless(importlib.util.find_spec('trafilatura'), 'optional parser not installed')
    def test_actual_parser_removes_navigation_and_preserves_grounding(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            doc = source.load_import(ARTICLE, URL, 'html')
        self.assertEqual(doc.get('used_parser'), 'trafilatura')
        self.assertEqual(doc.get('parser_version'), '2.0.0')
        self.assertNotIn('UNWANTED', doc['text'])
        needle = '什么是注意力机制？'
        start = doc['text'].index(needle)
        self.assertEqual(doc['text'][start:start+len(needle)], needle)
        self.assertEqual(doc['text_sha256'], hashlib.sha256(doc['text'].encode()).hexdigest())

    @unittest.skipUnless(importlib.util.find_spec('trafilatura'), 'optional parser not installed')
    def test_empty_or_failed_optional_parser_falls_back(self):
        for value, reason in [(None, 'empty_result'), (' \n', 'empty_result'), (RuntimeError('PRIVATE'), 'parser_error')]:
            kwargs = {'side_effect': value} if isinstance(value, Exception) else {'return_value': value}
            with self.subTest(reason=reason), patch('trafilatura.extract', **kwargs):
                doc = source.load_import('<p>原文不会丢失</p>', URL, 'html')
            self.assertEqual(doc.get('used_parser'), 'html_fallback')
            self.assertEqual(doc.get('parser_fallback_reason'), reason)
            self.assertEqual(doc['text'], '原文不会丢失')
            self.assertNotIn('PRIVATE', str(doc))

    def test_hostile_hidden_external_and_truncated_markup(self):
        html = ('<!DOCTYPE html SYSTEM "file:///etc/passwd"><article><p>安全正文 café 中文</p>'
                '<script src="https://invalid.test/">SECRET</script><iframe src="https://invalid.test/">SECRET</iframe>'
                '<div hidden>SECRET</div><p style="display: none">SECRET</p><span aria-hidden="true">SECRET</span>'
                '<img src="https://invalid.test/pixel" onerror="SECRET"><p>截断结尾')
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            doc = source.load_import(html, URL, 'html')
        self.assertIn('安全正文', doc['text'])
        self.assertIn('截断结尾', doc['text'])
        self.assertNotIn('SECRET', doc['text'])
        self.assertNotIn('root:', doc['text'])
        self.assertIn(doc.get('used_parser'), ('trafilatura', 'html_fallback'))

    def test_malformed_closes_use_linear_stack_work(self):
        # Counting stack reads is deterministic, unlike a machine-speed timeout.
        # A reverse scan for every unmatched close makes this quadratic.
        class CountedStack(list):
            reads = 0
            def __getitem__(self, key):
                self.reads += 1
                return super().__getitem__(key)
        parser = source._VisibleText()
        parser.stack = CountedStack()
        count = 2000
        parser.feed('<div>' * count + '</missing>' * count + 'visible' + '</div>' * count)
        parser.close()
        self.assertLess(parser.stack.reads, count * 20)
        self.assertIn('visible', ''.join(parser.parts))
        self.assertEqual(parser.stack, [])

    def test_mismatched_closing_tags_keep_hidden_descendants_hidden(self):
        parser = source._VisibleText()
        parser.feed('<div hidden><section><span>SECRET</bogus>SECRET</section>'
                    'SECRET</div><p>public</p>')
        parser.close()
        self.assertNotIn('SECRET', ''.join(parser.parts))
        self.assertIn('public', ''.join(parser.parts))

    def test_empty_and_bounds_fail_closed(self):
        for html, error in [('<script>hidden</script>', 'empty_input'), ('<p>'+'字'*40001+'</p>', 'input_too_large'), ('<p>'+'x'*512001, 'input_too_large')]:
            with self.subTest(error=error), self.assertRaisesRegex(source.InputSourceError, '^'+error+'$'):
                source.load_import(html, URL, 'html')

if __name__ == '__main__':
    unittest.main()
