#!/usr/bin/env python3
"""Offline replay of manually adjudicated, metadata-only private-source fixtures.

This validates grounding and review rules, NOT extraction precision/recall. No API,
network, publication or corpus writes. Raw excerpts are read only into memory.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from extract import validate
from review import prepare

ROOT = Path(__file__).resolve().parents[2]

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def audit(fixture, source_root, baseline_path):
    baseline = json.loads(Path(baseline_path).read_text())
    source_root = Path(source_root).resolve()
    documents = {}
    for doc in fixture['documents']:
        path = (source_root/doc['path']).resolve()
        if not path.is_relative_to(source_root):
            raise ValueError('invalid_snapshot_path')
        if not path.is_file():
            raise ValueError('source_snapshot_missing')
        text = path.read_text()
        if digest(text) != doc['sha256']:
            raise ValueError('document_hash_mismatch')
        documents[doc['id']] = (doc, text)
    proposals = []
    for case in fixture['cases']:
        doc, text = documents[case['document']]
        start, end = case['start'], case['end']
        if type(start) != int or type(end) != int or not 0 <= start < end <= len(text):
            raise ValueError('invalid_fragment_offsets')
        fragment = text[start:end]
        if digest(fragment) != case['fragment_sha256']:
            raise ValueError('fragment_hash_mismatch')
        if case['decision'] not in {'retain', 'exclude'}:
            raise ValueError('invalid_manual_decision')
        disposition = 'common' if case['decision'] == 'retain' else 'personal_project_specific'
        # Excluded headings/answers are manually filtered before extraction replay;
        # do not mislabel non-questions as personal-project questions in the schema.
        if case['decision'] == 'retain':
            validate({'questions':[{'question':fragment,'disposition':disposition,
                'evidence':{'quote':fragment,'start':start,'end':end}}]}, text)
        proposals.append(dict(source_url=doc['source_url'],question=fragment,
            disposition=disposition,evidence_locator=f'chars:{start}:{end}',
            reviewer='offline-manual-golden-not-model',canonical_question_id=case['baseline_mapping']))
    result = prepare(proposals, baseline)
    expected_retained_pairs = {(documents[c['document']][0]['source_url'].split('/blob/')[0], c['baseline_mapping'] or c['concept']) for c in fixture['cases'] if c['decision']=='retain'}
    errors = []
    if len(result['question_candidates']) != len(expected_retained_pairs):
        errors.append('review_pair_count_mismatch')
    if len(result['excluded']) != sum(c['decision']=='exclude' for c in fixture['cases']):
        errors.append('review_exclusion_count_mismatch')
    for row in result['question_candidates']:
        if row['countEligible'] or row['occurrence_count'] or row['verification_status']!='pending_human_approval':
            errors.append('candidate_safety_violation')
    qmap = {q['id']:q for q in baseline['questions']}
    findings = []
    corrected = []
    for finding in fixture['semantic_findings']:
        current = qmap[finding['question_id']]['title']
        if current == finding['observed_title']:
            findings.append(finding['question_id'])
        elif current == finding['proposed_title']:
            corrected.append(finding['question_id'])
        else:
            errors.append('semantic_finding_requires_rereview:'+finding['question_id'])
    return dict(schema_version=1,scope='manual-grounding-and-engine-replay-only',
        documents_checked=len(documents),cases_checked=len(fixture['cases']),
        decisions=dict(Counter(c['decision'] for c in fixture['cases'])),
        source_type_counts=dict(Counter(d['source_type'] for d in fixture['documents'])),
        review_candidates=len(result['question_candidates']),
        merged_same_repository_evidence=sum(len(c['evidence'])-1 for c in result['question_candidates']),
        baseline_mapped_cases=sum(bool(c['baseline_mapping']) for c in fixture['cases']),
        semantic_findings=findings,corrected_findings=corrected,errors=errors,
        approved_questions=0,published=False,model_calls=0,
        extraction_precision=None,extraction_recall=None)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,default=ROOT/'data.json')
    args = parser.parse_args()
    fixture = json.loads((Path(__file__).with_name('real-source-golden-v8.json')).read_text())
    report = audit(fixture,args.source_root,args.baseline)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return bool(report['errors'])

if __name__ == '__main__':
    raise SystemExit(main())
