"""Attach limited API observations to the 30-case design, without passing product cases."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    definition=json.loads((ROOT/'evaluation/ai-cases.json').read_text(encoding='utf-8'))
    evidence=json.loads((ROOT/'evaluation/memory-api-evaluation.json').read_text(encoding='utf-8'))
    observed={row['id']:row for row in evidence['cases']}
    boundary=json.loads((ROOT/'evaluation/voice-boundary-evaluation.json').read_text(encoding='utf-8'))
    decisions={row['id']:row for row in boundary['cases'] if row.get('renderedMemoryVerified')}
    rows=[]
    for case in definition['cases']:
        result=observed.get(case['id']) or decisions.get(case['id'])
        decision=case['id'] in decisions
        checks=result.get('checks',{}) if result else {}
        rows.append({'id':case['id'],'category':case['category'],
            'execution':('voice_model_fixture_observed' if decision else 'memory_API_observed') if result and checks else 'not_run',
            'product_acceptance':'not_verified','naturalness_1_to_5':None,'personality_1_to_5':None,
            'structural_checks':checks,
            'evidence':('evaluation/voice-boundary-evaluation.json' if decision else 'evaluation/memory-api-evaluation.json') if result else None,
            'scope':('Pinned voice LLM and Dialogue; software memory/tool fixtures; actions never executed' if decision else 'Isolated RAM; program confirmation; no physical device, ASR or audible playback') if result else None})
    if len(rows)!=30 or len({row['id'] for row in rows})!=30:raise ValueError('CASE_COVERAGE_INVALID')
    report={'full_product_acceptance':False,'defined_cases':30,
        'memory_API_observed':sum(row['execution']=='memory_API_observed' for row in rows),
        'voice_model_fixture_observed':sum(row['execution']=='voice_model_fixture_observed' for row in rows),
        'product_cases_passed':0,'manual_review_completed':False,'cases':rows}
    (ROOT/'evaluation/ai-execution-index.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('defined_cases','memory_API_observed','product_cases_passed')}))


if __name__=='__main__':main()
