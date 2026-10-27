"""Transaction tests use disposable copies, never change shipped data."""
import copy, hashlib, json, tempfile, unittest
from pathlib import Path
import review_commit as rc
from review import prepare
ROOT=Path(__file__).resolve().parents[2]

class Transactions(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.store=rc.ReviewStore(self.root/'work',ROOT/'data.json')
  self.doc=prepare([{'question':'What is a synthetic validation tree?','disposition':'common','source_url':'https://github.com/Example/Review/blob/main/a.md','evidence_locator':'L12','reviewer':'proposal-author'}],json.loads((ROOT/'data.json').read_text()))
  self.cid=self.doc['question_candidates'][0]['id']
  self.dec={'schema_version':1,'reviewer':'Local human reviewer','decisions':[{'candidate_id':self.cid,'action':'add','common_question':True,'source_reviewed':True}]}
 def tearDown(self):self.tmp.cleanup()
 def test_preview_apply_replay_rollback_bytes(self):
  original=(ROOT/'data.json').read_bytes();p=self.store.preview(self.doc,self.dec)
  self.assertEqual(p['counts']['new_questions'],1);self.assertEqual(p['counts']['new_sources'],1)
  self.assertEqual((self.root/'work/data.json').read_bytes(),original)
  with self.assertRaises(rc.ReviewError):self.store.apply(p['preview_id'],confirmed=False)
  t=self.store.apply(p['preview_id'],confirmed=True)
  self.assertEqual(t['status'],'applied');self.assertEqual(self.store.apply(p['preview_id'],confirmed=True)['transaction_id'],t['transaction_id'])
  data=json.loads((self.root/'work/data.json').read_text());q=data['questions'][-1]
  self.assertEqual(q['answerStatus'],'待专业审核');self.assertEqual(q['records'][0]['company'],'未知')
  self.assertEqual(data['questionAliases'],json.loads(original)['questionAliases'])
  self.store.rollback(t['transaction_id'],confirmed=True)
  self.assertEqual((self.root/'work/data.json').read_bytes(),original)
  with self.assertRaises(rc.ReviewError):self.store.apply(p['preview_id'],confirmed=True)
 def test_stale_preview_and_rollback_refuse_edits(self):
  p=self.store.preview(self.doc,self.dec);f=self.root/'work/data.json';f.write_bytes(f.read_bytes()+b' ')
  with self.assertRaisesRegex(rc.ReviewError,'stale'):self.store.apply(p['preview_id'],confirmed=True)
  p=self.store.preview(self.doc,self.dec);t=self.store.apply(p['preview_id'],confirmed=True);f.write_bytes(f.read_bytes()+b' ')
  with self.assertRaisesRegex(rc.ReviewError,'changed'):self.store.rollback(t['transaction_id'],confirmed=True)
 def test_merge_preserves_id_notes_answers_and_repo_counts(self):
  base=json.loads((ROOT/'data.json').read_text());qid=base['questions'][0]['id']
  self.dec['decisions'][0].update(action='merge',target_question_id=qid)
  p=self.store.preview(self.doc,self.dec);self.assertEqual(p['counts']['new_questions'],0)
  self.store.apply(p['preview_id'],confirmed=True)
  doc=copy.deepcopy(self.doc);doc['question_candidates'][0]['id']='different-candidate';doc['question_candidates'][0]['evidence'][0]['url']='https://raw.githubusercontent.com/example/review/main/b.md'
  dec=copy.deepcopy(self.dec);dec['decisions'][0]['candidate_id']='different-candidate'
  p=self.store.preview(doc,dec)
  self.assertEqual(p['counts']['new_sources'],0);self.assertEqual(p['counts']['new_question_source_pairs'],0);self.assertEqual(p['counts']['evidence_added'],1)
  self.store.apply(p['preview_id'],confirmed=True)
  after=json.loads((self.root/'work/data.json').read_text())
  for key,value in base['questions'][0].items():
   if key!='records':self.assertEqual(after['questions'][0][key],value)
 def test_exclusion_private_and_no_source_added(self):
  self.dec['decisions'][0]={'candidate_id':self.cid,'action':'exclude','reason':'Not reusable'}
  p=self.store.preview(self.doc,self.dec);self.assertEqual(p['counts']['excluded'],1);self.assertEqual(p['counts']['new_sources'],0)
  t=self.store.apply(p['preview_id'],confirmed=True);self.assertEqual(t['status'],'applied')
  self.assertEqual((self.root/'work/data.json').read_bytes(),(ROOT/'data.json').read_bytes())
 def test_demo_blocked_outside_demo_store(self):
  self.doc['demo']=True;p=self.store.preview(self.doc,self.dec)
  with self.assertRaisesRegex(rc.ReviewError,'demo'):self.store.apply(p['preview_id'],confirmed=True)
  s=rc.ReviewStore(self.root/'demo',ROOT/'data.json',demo=True);p=s.preview(self.doc,self.dec);self.assertEqual(s.apply(p['preview_id'],confirmed=True)['status'],'applied')
 def test_candidate_approval_not_authority(self):
  self.doc['question_candidates'][0]['verification_status']='approved'
  with self.assertRaises(rc.ReviewError):self.store.preview(self.doc,self.dec)
 def test_bad_schema_fuzz_and_noncommon(self):
  for value in [None,[],True,1,'oops',{}, {'question_candidates':None}]:
   with self.subTest(value=value),self.assertRaises(rc.ReviewError):self.store.preview(value,self.dec)
  for mutation in [('disposition','personal_project_specific'),('countEligible',True),('extra','oops'),('evidence',[])]:
   d=copy.deepcopy(self.doc);d['question_candidates'][0][mutation[0]]=mutation[1]
   with self.subTest(mutation=mutation),self.assertRaises(rc.ReviewError):self.store.preview(d,self.dec)
 def test_duplicate_candidate_and_unknown_decision_rejected(self):
  self.doc['question_candidates'].append(copy.deepcopy(self.doc['question_candidates'][0]))
  with self.assertRaises(rc.ReviewError):self.store.preview(self.doc,self.dec)
 def test_add_exact_existing_title_requires_merge(self):
  self.doc['question_candidates'][0]['question']=json.loads((ROOT/'data.json').read_text())['questions'][0]['title']
  with self.assertRaisesRegex(rc.ReviewError,'merge'):self.store.preview(self.doc,self.dec)
 def test_source_identity_mismatch_rejected(self):
  self.doc['question_candidates'][0]['canonical_source_id']='github:someone/else'
  with self.assertRaises(rc.ReviewError):self.store.preview(self.doc,self.dec)
 def test_preview_deterministic(self):
  a=self.store.preview(self.doc,self.dec);b=self.store.preview(self.doc,self.dec);self.assertEqual(a,b)
 def test_replay_flag_and_latest_transaction_guard(self):
  p=self.store.preview(self.doc,self.dec);t=self.store.apply(p['preview_id'],confirmed=True)
  self.assertTrue(self.store.apply(p['preview_id'],confirmed=True).get('replayed'))
  dec=copy.deepcopy(self.dec);dec['decisions'][0]={'candidate_id':self.cid,'action':'exclude','reason':'later no-op review'}
  p2=self.store.preview(self.doc,dec);t2=self.store.apply(p2['preview_id'],confirmed=True)
  with self.assertRaisesRegex(rc.ReviewError,'latest'):self.store.rollback(t['transaction_id'],confirmed=True)
  self.store.rollback(t2['transaction_id'],confirmed=True)
  self.store.rollback(t['transaction_id'],confirmed=True)
 def test_preview_before_after_totals_have_explicit_denominators(self):
  p=self.store.preview(self.doc,self.dec);before=p['totals']['before'];after=p['totals']['after']
  self.assertEqual(after['question_count']-before['question_count'],1)
  self.assertEqual(after['source_count']-before['source_count'],1)
  self.assertEqual(after['question_source_pairs']-before['question_source_pairs'],1)
  self.assertEqual(after['record_count']-before['record_count'],1)
  self.assertEqual(after['review_evidence_count']-before['review_evidence_count'],1)
 def test_known_optional_fields_are_typed_even_when_unused(self):
  dec=copy.deepcopy(self.dec);dec['decisions'][0]['reason']=[]
  with self.assertRaises(rc.ReviewError):self.store.preview(self.doc,dec)
  doc=copy.deepcopy(self.doc);doc['approved_questions']=False
  with self.assertRaises(rc.ReviewError):self.store.preview(doc,self.dec)
  doc=copy.deepcopy(self.doc);doc['excluded']=[{'input_index':'bad','reason':'x'}]
  with self.assertRaises(rc.ReviewError):self.store.preview(doc,self.dec)
 def test_explicit_source_review_required(self):
  self.dec['decisions'][0].pop('source_reviewed')
  with self.assertRaises(rc.ReviewError):self.store.preview(self.doc,self.dec)
 def test_trusted_source_grounding(self):
  text=self.doc['question_candidates'][0]['question'];ev=self.doc['question_candidates'][0]['evidence'][0]
  ev.update(quote=text,start=0,end=len(text));self.doc['text_sha256']=hashlib.sha256(text.encode()).hexdigest()
  trusted={'source_url':ev['url'],'text':text}
  self.store.preview(self.doc,self.dec,trusted_document=trusted)
  with self.assertRaises(rc.ReviewError):self.store.preview(self.doc,self.dec,trusted_document=dict(trusted,text='wrong text'))
 def test_legacy_canonical_url_normalization(self):
  row=self.doc['question_candidates'][0];row['canonical_source_id']='https://example.com/post/?spm=x';row['evidence'][0]['url']=row['canonical_source_id']
  p=self.store.preview(self.doc,self.dec);self.assertEqual(p['changes'][0]['canonical_source_id'],'https://example.com/post')
 def test_document_provenance_survives_commit(self):
  self.doc.update(text_sha256='a'*64,input_kind='user_supplied_text',model='offline-model',used_parser='plain-text')
  p=self.store.preview(self.doc,self.dec);self.store.apply(p['preview_id'],confirmed=True)
  entry=json.loads((self.root/'work/data.json').read_text())['questions'][-1]['records'][0]['reviewEvidence'][0]
  self.assertEqual(entry['provenance']['text_sha256'],'a'*64)
  self.assertEqual(entry['provenance']['used_parser'],'plain-text')
 def test_malformed_optional_provenance_rejected(self):
  self.doc['text_sha256']='not-a-hash'
  with self.assertRaises(rc.ReviewError):self.store.preview(self.doc,self.dec)
 def test_www_github_same_repository(self):
  self.doc['question_candidates'][0]['evidence'][0]['url']='https://www.github.com/EXAMPLE/Review/blob/master/file.md'
  p=self.store.preview(self.doc,self.dec);self.assertEqual(p['counts']['new_sources'],1)
 def test_rollback_recovers_interrupted_final_manifest(self):
  p=self.store.preview(self.doc,self.dec);t=self.store.apply(p['preview_id'],confirmed=True)
  directory=self.root/'work/.review/transactions'/t['transaction_id'];manifest=directory/'manifest.json'
  transaction=json.loads(manifest.read_text());transaction['status']='rolling_back';manifest.write_text(json.dumps(transaction))
  (self.root/'work/data.json').write_bytes((directory/'before.bin').read_bytes())
  self.assertEqual(self.store.rollback(t['transaction_id'],confirmed=True)['status'],'rolled_back')
 def test_baseline_path_cannot_be_working_file(self):
  with self.assertRaises(rc.ReviewError):rc.ReviewStore(ROOT,ROOT/'data.json')

if __name__=='__main__':unittest.main()
