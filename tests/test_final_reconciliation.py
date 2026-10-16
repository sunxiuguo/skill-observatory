"""Kernel tests with explicit fabricated receipts; no real gain certification."""
import copy
import math
import pytest
from skill_observatory.store import Store,canonical,digest
from skill_observatory.final_gate import finalize,seal_owner_receipt


def prepared(tmp_path,*,store=None,parent_bytes=b'parent',candidate_bytes=b'candidate',protocol_transform=None):
    tmp_path.mkdir(parents=True,exist_ok=True)
    s=store or Store(tmp_path/'state');target=tmp_path/'SKILL.md';target.write_bytes(parent_bytes)
    parent=s.artifact(parent_bytes);child=s.artifact(candidate_bytes);proof=s.artifact(b'mechanism fixture only')
    s.put('authority_grants',{'id':'g','status':'authorized','target':str(target),'owner':'skill-evolution-loop','surface':'single_text_file','evidence_sha256':proof})
    c={'id':'c','target':str(target),'parent_sha256':parent,'candidate_sha256':child,'authority_id':'g','cost_attempt_ids':['proposal']};s.put('candidates',c)
    labels={str(i):{'result':s.artifact(str(i).encode())} for i in range(8)}
    cases=[{'id':i,'split':'final','source':'real_incident','categories':['regression','guardrail'],'evidence_sha256':s.artifact(('provenance '+i).encode()),'input_files':{'case':s.artifact(i.encode())},'inputs_sha256':digest(canonical({'case':s.artifact(i.encode())}))} for i in labels]
    p={'id':'p','schema_version':2,'arm_files':{'parent':{'SKILL.md':parent},'candidate':{'SKILL.md':child}},'oracle_sha256':s.artifact(canonical(labels)),'cases':cases,'min_gain':0,'alpha':.05,'cost_limits':{'tokens':1000,'money':10,'wall_seconds':100},'cost_accounting':{'currency':'USD','wall_basis':'sum_duration'},'execution_identity':{'kind':'deterministic-python'}}
    if protocol_transform:p=protocol_transform(p)
    s.put('protocols',p);trials=[]
    unit={'money':.25,'tokens':10,'input_tokens':6,'output_tokens':4,'cached_input_tokens':2,'currency':'USD'}
    for case in cases:
        for arm in ['parent','candidate']:
            t={'trial_id':case['id']+arm,'case_id':case['id'],'arm':arm,'passed':arm=='candidate','receipt':{'status':'completed','exit_code':0,'container_id':case['id']+arm,'wall_seconds':1,'input_manifest_sha256':digest(canonical({**p['arm_files'][arm],**case['input_files']}))},'artifacts':labels[case['id']] if arm=='candidate' else {},'cost':unit}
            if p.get('arm_packages'):
                from skill_observatory.packages import trial_manifest
                manifest=trial_manifest(p,arm,{n:s.read_artifact(v) for n,v in p['arm_files'][arm].items()},{n:s.read_artifact(v) for n,v in case['input_files'].items()})
                t['receipt'].update(input_manifest_sha256=manifest['package_digest'],input_manifest=manifest)
            t['receipt_artifact']=s.artifact(canonical(t));trials.append(t)
    e={'id':'e','schema_version':2,'protocol_id':p['id'],'protocol_sha256':digest(canonical(p)),'attempt_id':'eval-attempt','missing':[],'paired_cases':8,'paired_gain':1,'paired_gain_lower_bound':1-math.sqrt(2*math.log(20)/8),'trials':trials}
    from skill_observatory.evaluation import claim_evaluation
    actual_attempt,_,_=claim_evaluation(s,p,cases)
    e['attempt_id']=actual_attempt
    s.put('evaluations',e)
    attempts=[('evaluation_attempts',{'id':e['attempt_id'],'status':'completed_hold','result_sha256':s.artifact(canonical(e))}),('generation_attempts',{'id':'proposal','candidate_id':'c','status':'failed','cost':{**unit,'wall_seconds':2}})]
    refs=[]
    for kind,row in attempts:
        s.put(kind,row);refs.append({'kind':kind,'id':row['id'],'sha256':s.artifact(canonical(row))})
    common={'evaluation_sha256':digest(canonical(e)),'protocol_sha256':digest(canonical(p)),'evidence_sha256':proof,'schema_version':2}
    domain={**common,'case_ids':list(labels),'oracle_sha256':p['oracle_sha256'],'independent_final':True,'comparable':True,'guardrails_pass':True,'regressions_pass':True,'regression_case_ids':list(labels),'guardrail_case_ids':list(labels),'trial_receipt_sha256':[t['receipt_artifact'] for t in trials]}
    cost={**common,'all_attempts_covered':True,'budget_pass':True,'attempt_ids':['proposal',e['attempt_id']],'attempt_refs':refs,'currency':'USD','money':4.25,'tokens':170,'wall_seconds':18}
    return s,c,p,e,domain,cost


def verdict(s,d,c):return finalize(s,'c','e',seal_owner_receipt(s,'domain',d),seal_owner_receipt(s,'cost',c))


def test_exact_positive_and_signed_999_totals_refused(tmp_path):
    s,c,p,e,d,cost=prepared(tmp_path)
    bad={**cost,'money':0,'tokens':0}
    assert 'COST_TOTAL_RECONCILIATION_MISMATCH' in verdict(s,d,bad)['missing']
    good=verdict(s,d,cost);assert good['status']=='accepted'
    # The accepted cache path is subject to the exact same accounting gate.
    with pytest.raises(ValueError,match='COST_TOTAL_RECONCILIATION_MISMATCH'):verdict(s,d,bad)


@pytest.mark.parametrize('change',['missing_arm','duplicate','score','hash','unknown_attempt','omitted_failure','currency','nan','category'])
def test_incomplete_and_forged_trusted_inputs_cannot_certify(tmp_path,change):
    s,c,p,e,d,cost=prepared(tmp_path)
    if change=='missing_arm':e['trials'].pop()
    elif change=='duplicate':e['trials'].append(e['trials'][0])
    elif change=='score':e['trials'][0]['passed']=True
    elif change=='hash':e['trials'][0]['receipt_artifact']='a'*64
    elif change=='unknown_attempt':cost['attempt_refs'][1]['id']='absent'
    elif change=='omitted_failure':cost['attempt_refs'].pop();cost.update(money=4,tokens=160,wall_seconds=16)
    elif change=='currency':cost['currency']='CNY'
    elif change=='nan':cost['money']=float('nan')
    elif change=='category':d['guardrail_case_ids']=['0']
    s.put('evaluations',e)
    if change in {'missing_arm','duplicate','score','hash'}:
        # Re-seal binding to expose reconciliation rather than only identity drift.
        eh=s.artifact(canonical(e));d['evaluation_sha256']=eh;cost['evaluation_sha256']=eh
        row=s.get('evaluation_attempts',e['attempt_id']);row['result_sha256']=eh;s.put('evaluation_attempts',row)
        cost['attempt_refs'][0]['sha256']=s.artifact(canonical(row))
    assert verdict(s,d,cost)['status']=='hold'
