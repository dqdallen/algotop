import json
import tempfile
import unittest
from pathlib import Path
import pipeline

class PipelineTests(unittest.TestCase):
    def test_mock_end_to_end_and_no_source_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'body.txt').write_text('什么是梯度下降？')
            (p/'response.json').write_text(json.dumps({'questions':[{'question':'什么是梯度下降？','disposition':'common','evidence':{'quote':'什么是梯度下降？','start':0,'end':8}}]},ensure_ascii=False))
            (p/'baseline.json').write_text('{}')
            code=pipeline.main(['--text-file',str(p/'body.txt'),'--source-url','https://example.com/article','--mock-response',str(p/'response.json'),'--baseline',str(p/'baseline.json'),'--output',str(p/'result.json')])
            self.assertEqual(code,0);result=json.loads((p/'result.json').read_text())
            self.assertEqual(len(result['question_candidates']),1);self.assertNotIn('text',result);self.assertFalse(result['published'])
    def test_requires_explicit_transfer_consent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'body.txt').write_text('test')
            self.assertEqual(pipeline.main(['--text-file',str(p/'body.txt'),'--source-url','https://example.com/article','--output',str(p/'out.json')]),2)
            self.assertFalse((p/'out.json').exists())

class PrivateOutputTests(unittest.TestCase):
    def test_replaces_existing_output_with_private_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'out.json';path.write_text('old');path.chmod(0o644)
            pipeline.write_private(path,{'published':False})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertFalse(json.loads(path.read_text())['published'])

class DirectCLI(unittest.TestCase):
    def test_direct_requires_url_not_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'out.json'
            self.assertEqual(pipeline.main(['--text-file','unused.txt','--source-url','https://example.com/article','--mock-response','unused.json','--direct-public-egress','--output',str(path)]),2)
            self.assertFalse(path.exists())
