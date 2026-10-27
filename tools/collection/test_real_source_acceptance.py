"""Metadata-only fixtures; private source documents are never copied into the repo."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.find_spec('real_source_acceptance')
ROOT = Path(__file__).resolve().parents[2]
SOURCES = Path(os.environ['ALGOWEN_ACCEPTANCE_SOURCES']) if os.environ.get('ALGOWEN_ACCEPTANCE_SOURCES') else None

class RealSourceAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SPEC, 'offline real-source acceptance runner missing')
        import real_source_acceptance
        self.runner = real_source_acceptance
        self.fixture = json.loads((ROOT/'tools/collection/real-source-golden-v8.json').read_text())

    def test_fixture_contains_only_locators_not_source_bodies(self):
        self.assertNotIn('quote', json.dumps(self.fixture))
        self.assertGreaterEqual(len(self.fixture['cases']), 20)
        self.assertGreaterEqual(len(self.fixture['documents']), 6)

    @unittest.skipUnless((SOURCES is not None and SOURCES.is_dir()), 'private source snapshots unavailable; not an extraction-quality pass')
    def test_manual_labels_replay_through_real_validation_and_review(self):
        before = (ROOT/'data.json').read_bytes()
        report = self.runner.audit(self.fixture, SOURCES, ROOT/'data.json')
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['approved_questions'], 0)
        self.assertFalse(report['published'])
        self.assertEqual(report['model_calls'], 0)
        self.assertEqual(report['cases_checked'], len(self.fixture['cases']))
        self.assertEqual(report['semantic_findings'], [])
        self.assertEqual(report['corrected_findings'], ['ghv3-003', 'ghv3-066'])
        self.assertEqual((ROOT/'data.json').read_bytes(), before)

    @unittest.skipUnless((SOURCES is not None and SOURCES.is_dir()), 'private source snapshots unavailable')
    def test_tampered_offsets_fail_closed(self):
        bad = copy.deepcopy(self.fixture)
        bad['cases'][0]['start'] += 1
        with self.assertRaisesRegex(ValueError, 'fragment_hash_mismatch'):
            self.runner.audit(bad, SOURCES, ROOT/'data.json')

    @unittest.skipUnless((SOURCES is not None and SOURCES.is_dir()), 'private source snapshots unavailable')
    def test_snapshot_drift_fails_closed(self):
        bad = copy.deepcopy(self.fixture)
        bad['documents'][0]['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'document_hash_mismatch'):
            self.runner.audit(bad, SOURCES, ROOT/'data.json')

    def test_baseline_wording_does_not_invent_a_subquestion(self):
        questions = {q['id']: q for q in json.loads((ROOT/'data.json').read_text())['questions']}
        for qid, title in [('ghv3-003', '介绍大模型投机采样。'), ('ghv3-066', '什么是集体通信？')]:
            self.assertEqual(questions[qid]['title'], title)
            self.assertEqual(len(questions[qid]['records']), 1)
            self.assertEqual(questions[qid]['records'][0]['wording'], title)

    def test_baseline_sample_keeps_company_and_dates_question_specific(self):
        questions = {q['id']: q for q in json.loads((ROOT/'data.json').read_text())['questions']}
        for qid, company in [('ghv3-001', '腾讯'), ('ghv3-003', '腾讯'), ('ghv3-065', '其他'), ('ghv3-066', '其他')]:
            row = questions[qid]['records'][0]
            self.assertEqual(row['company'], company)
            self.assertIsNone(row['interviewYear'])
            self.assertIsNone(row['date'])
            self.assertEqual([r['id'] for r in row['jobDirections']], ['unknown'])

    def test_portable_synthetic_replay_merges_same_repo_without_approval(self):
        # Synthetic rule coverage, not real-source extraction quality.
        import hashlib
        digest = lambda text: hashlib.sha256(text.encode()).hexdigest()
        text = 'What is sorting?\nDescribe your internship.'
        documents = [dict(id=str(i), path=f'{i}.txt', sha256=digest(text),
            source_url=f'https://github.com/example/repo/blob/main/{i}.txt',
            source_type='synthetic') for i in range(2)]
        cases = [dict(document=str(i), start=0, end=16,
            fragment_sha256=digest(text[:16]), decision='retain',
            concept='sorting', baseline_mapping=None) for i in range(2)]
        cases.append(dict(document='0', start=17, end=len(text),
            fragment_sha256=digest(text[17:]), decision='exclude',
            concept='personal', baseline_mapping=None))
        fixture = dict(documents=documents, cases=cases, semantic_findings=[])
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for doc in documents:
                (directory/doc['path']).write_text(text)
            baseline = directory/'baseline.json'
            baseline.write_text(json.dumps(dict(questions=[], sources=[])))
            report = self.runner.audit(fixture, directory, baseline)
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['review_candidates'], 1)
        self.assertEqual(report['merged_same_repository_evidence'], 1)
        self.assertEqual(report['decisions'], {'retain': 2, 'exclude': 1})
        self.assertEqual(report['approved_questions'], 0)
        self.assertIsNone(report['extraction_precision'])

    def test_missing_private_sources_is_error_not_success(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(ValueError, 'source_snapshot_missing'):
                self.runner.audit(self.fixture, Path(empty), ROOT/'data.json')

    def test_registry_local_evidence_references_are_bundled(self):
        directory = ROOT/'tools/collection'
        registry = json.loads((directory/'sources.json').read_text())
        for source in registry['sources']:
            evidence = source.get('prior_access_evidence', {})
            if 'file' in evidence:
                self.assertTrue((directory/evidence['file']).is_file(), evidence['file'])
            if 'external_historical_file' in evidence:
                self.assertIs(evidence['bundled'], False)
                self.assertTrue((directory/evidence['summary_file']).is_file())
            if '.collection/redirect-evidence.json' in source.get('canonical_endpoint_evidence', ''):
                self.assertIn('not bundled', source['canonical_endpoint_evidence'])

if __name__ == '__main__':
    unittest.main()
