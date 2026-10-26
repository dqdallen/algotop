#!/usr/bin/env python3
"""Validate reviewer-produced generic-question proposals; never approves/publishes."""
import argparse
import json
import re
from pathlib import Path
from collect import digest, source_id
from ingest import canonical

def prepare(rows,baseline):
    questions={q['id']:q for q in baseline.get('questions',[])}
    candidates={};excluded=[]
    for index,row in enumerate(rows):
        try:
            if row.get('disposition')!='common':raise ValueError('not_common')
            for field,limit in [('question',200),('evidence_locator',500),('reviewer',100)]:
                if not isinstance(row.get(field),str) or not 0<len(row[field].strip())<=limit:raise ValueError('invalid_'+field)
            url=canonical(row['source_url']);identity=source_id(url)
            mapping=row.get('canonical_question_id')
            if mapping and mapping not in questions:raise ValueError('unknown_question_mapping')
            question=' '.join(row['question'].split())
            key=digest(identity+'|'+(mapping or re.sub(r'\W','',question).casefold()))[:24]
            evidence={'url':url,'locator':row['evidence_locator'].strip(),'reviewer':row['reviewer'].strip(),
                      'interview_date_claim':row.get('interview_date_claim'),'provenance_claim':row.get('provenance_claim','unverified')}
            duplicate=bool(mapping and any(r.get('canonicalSourceId')==identity for r in questions[mapping].get('records',[])))
            if key not in candidates:
                candidates[key]={'id':key,'question':question,'canonical_question_id':mapping,'canonical_source_id':identity,
                    'disposition':'common','verification_status':'pending_human_approval','countEligible':False,'occurrence_count':0,
                    'already_in_baseline':duplicate,'proposed_action':'duplicate_no_add' if duplicate else 'review_merge' if mapping else 'review_new_card',
                    'evidence':[],'open_checks':['verify source and date/algorithm role','confirm explicitly asked generic question','verify semantic mapping and duplicate provenance','user approval before any data/publication change']}
            if evidence not in candidates[key]['evidence']:candidates[key]['evidence'].append(evidence)
        except (ValueError,KeyError,TypeError) as exc:
            excluded.append({'input_index':index,'reason':str(exc)[:100]})
    for row in candidates.values():row['evidence'].sort(key=lambda e:(e['url'],e['locator'],e['reviewer']))
    return {'schema_version':1,'stage':'review_proposals_only','question_candidates':sorted(candidates.values(),key=lambda x:x['id']),
            'excluded':excluded,'approved_questions':0,'occurrences_added':0,'published':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--baseline',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();rows=json.loads(args.input.read_text());result=prepare(rows,json.loads(args.baseline.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'question_candidates':len(result['question_candidates']),'excluded':len(result['excluded']),'approved':0,'published':False}))
if __name__=='__main__':main()
