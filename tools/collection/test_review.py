import importlib.util
import unittest
SPEC=importlib.util.find_spec('review')
if SPEC:import review
class ReviewTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(SPEC,'review import stage missing')
  self.row={'source_url':'https://github.com/Owner/Repo/blob/main/a.md','question':'Explain AUC calculation','disposition':'common','evidence_locator':'Interview section, question 3','reviewer':'weekly reviewer','canonical_question_id':'q1'}
  self.baseline={'questions':[{'id':'q1','records':[]}],'sources':[]}
 def test_never_approved_or_counted(self):
  r=review.prepare([self.row],self.baseline)['question_candidates'][0]
  self.assertEqual(r['verification_status'],'pending_human_approval');self.assertFalse(r['countEligible']);self.assertEqual(r['occurrence_count'],0)
 def test_specific_excluded(self):
  r=review.prepare([dict(self.row,disposition='personal_project_specific')],self.baseline)
  self.assertEqual(r['question_candidates'],[]);self.assertEqual(r['excluded'][0]['reason'],'not_common')
 def test_missing_evidence_rejected(self):
  r=review.prepare([dict(self.row,evidence_locator='')],self.baseline)
  self.assertEqual(r['question_candidates'],[]);self.assertEqual(r['excluded'][0]['reason'],'invalid_evidence_locator')
 def test_repo_dedup_same_question_across_files(self):
  r=review.prepare([self.row,dict(self.row,source_url='https://github.com/owner/repo/blob/main/b.md')],self.baseline)
  self.assertEqual(len(r['question_candidates']),1);self.assertEqual(len(r['question_candidates'][0]['evidence']),2)
 def test_baseline_duplicate_explicit(self):
  self.baseline['questions'][0]['records']=[{'canonicalSourceId':'github:owner/repo'}]
  r=review.prepare([self.row],self.baseline)['question_candidates'][0]
  self.assertTrue(r['already_in_baseline']);self.assertEqual(r['proposed_action'],'duplicate_no_add')
 def test_mapping_must_exist(self):
  r=review.prepare([dict(self.row,canonical_question_id='fake')],self.baseline)
  self.assertEqual(r['excluded'][0]['reason'],'unknown_question_mapping')
 def test_deterministic(self):
  a=review.prepare([self.row,self.row],self.baseline);b=review.prepare([self.row],self.baseline)
  self.assertEqual(a,b)
if __name__=='__main__':unittest.main()
