import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const db=JSON.parse(readFileSync(new URL('../data.json',import.meta.url)));
const q=id=>db.questions.find(q=>q.id===id);
test('private experience records are removed, without removing other general sources',()=>{
 for(const id of ['q097','q142','q164','q165','q182','q189','q204','q206','q222','q230','q248'])assert.equal(q(id),undefined,id);
 assert.ok(q('q003'));assert.ok(q('q158'));
 assert.ok(!q('q003').records.some(r=>r.wording.includes('项目未采用')));
 assert.equal(q('q158').records.length,1);
});
test('unresolved wording and unavailable originals are quarantined, not silently generalized',()=>{
 for(const id of ['q062','q071','q094','q130','q134','q163','q167','q175','q179','q225','q254','q263','q138','q139','q140','q151','q152'])assert.equal(q(id),undefined,id);
});
test('mixed project questions retain only verified explicit transferable clauses',()=>{
 assert.equal(q('q104').title,'BART与T5有哪些区别？');
 assert.equal(q('q207').title,'解释LSTM。');
 assert.equal(q('q159').title,'比较Pure Pursuit和LQR。');
 assert.ok(!db.questions.some(q=>q.id.startsWith('q159-a')));
});
test('verified independent questions split with stable IDs and evidence, no copied mixed answers',()=>{
 for(const id of ['q099-a2','q099-a3','q135-a2','q148-a2','q150-a2','q241-a2','q241-a3','q242-a2','q243-a2','q257-a2','q257-a3','q258-a2','q258-a3','q258-a4']){
  assert.ok(q(id),id);const original=q(id).records.filter(r=>!r.source.startsWith('github:'));assert.equal(original.length,1);assert.ok(original[0].generalityReview.sourceUrl);assert.equal(q(id).answerStatus,'待撰写');
 }
});
test('generic design questions survive, including a manual flag resolved against original',()=>{
 for(const id of ['q042','q074','q193','q202','q264','q269','q143','q177','q201','q156'])assert.ok(q(id),id);
 assert.equal(q('q156').records[0].generalityReview?.status,'verified_general');
});
test('all records expose only explicitly supported company and role attributions',()=>{
 for(const question of db.questions)for(const r of question.records){
  if(r.companyEvidence.certainty!=='explicit')assert.equal(r.company,'其他');
  assert.ok(r.jobDirections.every(d=>d.certainty==='explicit'||d.id==='unknown'));
 }
});
test('canonical questions and source identities support unique source counting, including compilations',()=>{
 for(const q of db.questions){assert.equal(q.canonicalQuestionId,q.id);assert.ok(!('verifiedSourceCount'in q));assert.ok(!('sourceMentionCount'in q));}
 for(const s of db.sources)assert.ok(s.canonicalSourceId,s.id);
 const s=db.sources.find(s=>s.id==='s3');assert.equal(s.countEligible,true);assert.equal(s.collectionPartition,'unknown');
 for(const q of db.questions)for(const r of q.records)if(r.source==='s3')assert.equal(r.countEligible,true);
});
test('public cleanup summary preserves exact baseline audit totals',()=>{
 const report=db.generalityCleanup;assert.equal(report.counts.excludedRecords,13);assert.equal(report.counts.quarantinedRecords,19);assert.equal(report.counts.splitInputRecords,12);assert.equal(report.counts.newAtomicCards,14);
 assert.equal(report.input.cards,271);assert.equal(report.input.records,342);assert.equal(report.output.cards,257);assert.equal(report.output.records,324);
});
