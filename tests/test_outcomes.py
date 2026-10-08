"""Synthetic kernel fixtures verify refusals/bindings, never Skill gain."""
import json
from pathlib import Path
import pytest
from skill_observatory.store import Store, canonical, digest
from skill_observatory.runtime import register
from skill_observatory.installations import grant_owner, authority_expired, seal_verdict, activate
from skill_observatory.outcomes import seal_task_receipt, accept_task_result, run_binding, verify_live


def test_original_owner_grant_and_offset_expiry(tmp_path):
    s=Store(tmp_path/'state');root=tmp_path/'owned';root.mkdir();(root/'SKILL.md').write_text('text')
    register(s,root,'skill-evolution-loop')
    evidence=s.artifact(b'Synthetic test authorization, not a pilot grant')
    g=grant_owner(s,root/'SKILL.md','fixture',evidence,'2099-01-01T00:00:00+08:00')
    assert g['owner']=='skill-evolution-loop' and s.get('authority_grants','fixture')==g
    assert grant_owner(s,root/'SKILL.md','fixture',evidence,'2099-01-01T00:00:00+08:00')==g
    assert authority_expired('2000-01-01T00:00:00+08:00')
    with pytest.raises(ValueError,match='EXPIRY_INVALID'):authority_expired('2099-01-01')
    with pytest.raises(ValueError,match='AUTHORITY_DRIFT'):grant_owner(s,root/'SKILL.md','fixture',s.artifact(b'different'))


def fixture(s,tmp_path):
    target=tmp_path/'SKILL.md';target.write_bytes(b'fixture installed')
    oracle=s.artifact(b'synthetic kernel label descriptor')
    protocol={'id':'p','oracle_sha256':oracle,'model':'fixture','max_verified_effort':'fixture','synthetic':False}
    # Trusted-kernel fixtures intentionally exercise HMAC ingress; these are not
    # runtime domain verdicts, real-case labels or improvement evidence.
    s.put('protocols',protocol)
    verdict=seal_verdict(s,{'id':'v','status':'accepted','protocol_id':'p','protocol_sha256':digest(canonical(protocol)),
        'gates':{g:True for g in ('authorization_matches','hashes_current','comparable','independent_final','coverage_sufficient','gain_pass','guardrails_pass','regressions_pass','budget_pass')}})
    s.put('verdicts',verdict);s.put('candidates',{'id':'c','verdict_id':'v'})
    s.put('installations',{'id':'i','candidate_id':'c','status':'activation_pending','target':str(target),
        'after_sha256':digest(target.read_bytes()),'created_at':'2026-01-01T00:00:00+00:00'})
    run={'id':'r','session_id':'fresh','origin':'activation_canary','event_ids':['ev'],'attributions':[
        {'attribution':'verified_read','file_sha256':digest(target.read_bytes())}],'outcome':'unverified'}
    s.put('runs',run)
    context=s.artifact(canonical({'context_id':'fresh','origin':'trusted_broker','fresh':True,'model':'fixture','effort':'fixture','created_at':'2026-01-02T00:00:00Z'}))
    return {'id':'tr','run_id':'r','installation_id':'i','run_binding_sha256':run_binding(run),
        'protocol_sha256':verdict['protocol_sha256'],'skill_sha256':digest(target.read_bytes()),'status':'accepted',
        'oracle_sha256':oracle,'result_artifact_sha256':s.artifact(b'kernel fixture result'),'context_receipt_sha256':context}


def test_task_result_requires_independent_signature_and_new_context(tmp_path):
    s=Store(tmp_path/'state');r=fixture(s,tmp_path)
    with pytest.raises(ValueError,match='UNTRUSTED'):accept_task_result(s,r)
    old=s.artifact(canonical({'context_id':'fresh','origin':'trusted_broker','fresh':True,'model':'fixture','effort':'fixture','created_at':'2025-01-01T00:00:00Z'}))
    with pytest.raises(ValueError,match='PREINSTALL_CONTEXT'):accept_task_result(s,seal_task_receipt(s,{**r,'context_receipt_sha256':old}))
    accept_task_result(s,seal_task_receipt(s,r))
    assert activate(s,'i','r')['status']=='activated'
    with pytest.raises(ValueError,match='LIVE_STATE_HOLD'):verify_live(s,'i','r')
    assert not s.get('installations','i').get('live_verified')


def test_result_cannot_accept_drifted_run_or_installation(tmp_path):
    s=Store(tmp_path/'state');r=fixture(s,tmp_path);signed=seal_task_receipt(s,r)
    run=s.get('runs','r');run['event_ids'].append('later');s.put('runs',run)
    with pytest.raises(ValueError,match='TASK_EVIDENCE_DRIFT'):accept_task_result(s,signed)
