import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {countSources,sourceYears} from '../core.js';
const db=JSON.parse(readFileSync(new URL('../data.json',import.meta.url))),get=id=>db.questions.find(q=>q.id===id);
const ghRecords=db.questions.flatMap(q=>q.records).filter(r=>r.source.startsWith('github:'));
test('GitHub import counts three repositories, preserves 74 question occurrences and 78 evidence links',()=>{
 assert.equal(db.sources.filter(s=>s.id.startsWith('github:')).length,3);
 assert.equal(ghRecords.length,78);
 assert.equal(new Set(db.questions.flatMap(q=>q.records.filter(r=>r.source.startsWith('github:')).map(r=>q.id+'|'+r.canonicalSourceId))).size,74);
 assert.equal(new Set(ghRecords.flatMap(r=>r.evidenceUrls)).size,78);
});
test('semantic matches attach sources to established cards; broader unrelated targets are not inflated',()=>{
 for(const id of ['q135','q061','q069','q036','q135-a2','q119','q031','q073'])assert.ok(get(id).records.some(r=>r.source.startsWith('github:')),id);
 assert.ok(get('ghv3-005'));assert.ok(get('ghv3-001'));assert.ok(get('ghv3-027'));
 for(const id of ['q116','q057','q066'])assert.ok(!get(id).records.some(r=>r.source.startsWith('github:')),id);
});
test('different companies in one repository retain their own links without increasing overall source count',()=>{
 const q=get('ghv3-005');assert.ok(q);assert.equal(q.records.length,2);assert.equal(countSources(q.records,db.sources),1);
 assert.deepEqual(q.records.map(r=>r.company).sort(),['腾讯','蚂蚁集团'].sort());
 for(const r of q.records)assert.ok(r.fileEvidence.every(e=>e.company===r.company));
});
test('repository timestamps never masquerade as interview dates or evidence-backed job roles',()=>{
 const sources=db.sources.filter(s=>s.id.startsWith('github:'));assert.equal(sources.length,3);
 for(const s of sources){assert.equal(s.countEligible,true);assert.equal(s.date,null);assert.deepEqual(sourceYears(s),[]);assert.ok(s.licenseDisclosure);}
 for(const r of ghRecords){assert.equal(r.interviewDate,null);assert.ok(r.jobDirections.every(d=>d.id==='unknown'));if(r.company!=='其他')assert.equal(r.companyEvidence.certainty,'explicit');}
});
test('new cards do not reproduce repository answers and import has exact auditable totals',()=>{
 const newCards=db.questions.filter(q=>q.id.startsWith('ghv3-'));assert.equal(newCards.length,66);
 for(const q of newCards){assert.deepEqual(q.answer,{});assert.equal(q.answerStatus,'待撰写');assert.equal(q.canonicalQuestionId,q.id);}
 const report=db.githubImport;
 assert.equal(report.newCards,66);assert.equal(report.mergedIntoExisting,8);assert.equal(report.recordsAdded,78);assert.equal(report.sourcesAdded,3);
 assert.equal(db.questions.length,323);assert.equal(db.questions.reduce((n,q)=>n+q.records.length,0),402);
});
test('published collection metadata agrees with source-count policy and actual data',()=>{
 assert.equal(db.methodology.frequencyLabel,'收录来源数');assert.equal(db.collection.defaultScope,'all');
 assert.equal(db.collection.metrics.cards,db.questions.length);assert.equal(db.collection.metrics.sourceRecords,db.questions.reduce((n,q)=>n+q.records.length,0));
 assert.ok(!db.methodology.caveats.some(s=>s.includes('二次整理仅作线索')));
});
