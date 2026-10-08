"""Synthetic final-gate refusal tests, not real domain evidence."""
import pytest
from skill_observatory.store import Store,canonical,digest
from skill_observatory.final_gate import finalize,seal_owner_receipt
from skill_observatory.installations import validate_verdict


def test_unsupported_gain_cannot_be_promoted_by_receipt_flags(tmp_path):
    s=Store(tmp_path/'state');target=tmp_path/'SKILL.md';target.write_bytes(b'parent')
    parent=s.artifact(b'parent');candidate=s.artifact(b'candidate')
    evidence=s.artifact(b'synthetic authorization')
    s.put('authority_grants',{'id':'g','status':'authorized','target':str(target),'owner':'skill-evolution-loop','surface':'single_text_file','evidence_sha256':evidence})
    s.put('candidates',{'id':'c','target':str(target),'parent_sha256':parent,'candidate_sha256':candidate,'authority_id':'g','cost_attempt_ids':['proposal-attempt']})
    p={'id':'p','arm_files':{'parent':{'SKILL.md':parent},'candidate':{'SKILL.md':candidate}},'oracle_sha256':s.artifact(b'fixture oracle'),'cases':[{'id':'fixture','split':'final'}],'min_gain':0,'synthetic':True}
    s.put('protocols',p)
    e={'id':'e','protocol_id':'p','protocol_sha256':digest(canonical(p)),'attempt_id':'attempt','missing':['REAL_CASE_EVIDENCE_REQUIRED','NO_CONFIRMED_GAIN','DOMAIN_GUARDRAIL_RECEIPT_REQUIRED','COST_COVERAGE_REQUIRED'],'paired_gain_lower_bound':-1}
    s.put('evaluations',e);s.put('evaluation_attempts',{'id':'attempt','result_sha256':s.artifact(canonical(e))})
    common={'evaluation_sha256':digest(canonical(e)),'protocol_sha256':digest(canonical(p)),'evidence_sha256':evidence}
    domain=seal_owner_receipt(s,'domain',{**common,'case_ids':['fixture'],'oracle_sha256':p['oracle_sha256'],'independent_final':True,'comparable':True,'guardrails_pass':True,'regressions_pass':True,'regression_case_ids':['fixture'],'guardrail_case_ids':['fixture']})
    cost=seal_owner_receipt(s,'cost',{**common,'all_attempts_covered':True,'budget_pass':True,'attempt_ids':['attempt','proposal-attempt'],'money':0,'tokens':0,'wall_seconds':1})
    v=finalize(s,'c','e',domain,cost)
    assert v['status']=='hold' and 'INDEPENDENT_TRUTH_REQUIRED' in v['missing'] and 'NO_CONFIRMED_GAIN' in v['missing']
    assert not v.get('signature')
    with pytest.raises(ValueError,match='UNTRUSTED'):validate_verdict(s,v)
    forged={**domain,'independent_final':True,'signature':'a'*64}
    assert 'FINAL_RECEIPT_UNTRUSTED' in finalize(s,'c','e',forged,cost)['missing']
    assert target.read_bytes()==b'parent'
