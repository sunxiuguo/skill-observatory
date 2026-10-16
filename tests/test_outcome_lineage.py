import pytest
from pathlib import Path
from skill_observatory.store import Store,canonical,digest
from skill_observatory.outcomes import freeze_cohort,cohort_report,record_cohort_sample,register_method_version,bind_generation,method_report,seal_task_receipt,accept_task_result
from test_outcomes import fixture


def cohort(s):
    installed=s.get('installations','i');parent=Path(installed['target']).with_name('parent-SKILL.md')
    parent.write_bytes(b'fixture parent installed')
    prior={**installed,'id':'i-parent','target':str(parent),'after_sha256':digest(parent.read_bytes())}
    prior.pop('before_sha256',None)
    s.put('installations',prior);s.put('installations',{**installed,'before_sha256':prior['after_sha256']})
    return {'id':'cohort','installation_id':'i','task_family':'cli-contract','start':'2026-01-01T00:00:00+00:00','end':'2026-01-10T00:00:00+00:00',
            'arm_bindings':{arm:{'installation_id':item['id'],'version_sha256':item['after_sha256']} for arm,item in [('parent',prior),('candidate',installed)]},
            'task_family_sha256':s.artifact(canonical({'id':'cli-contract','definition':'independent CLI contract tasks with the frozen domain verifier'})),
            'comparison':{'model':'fixture','effort':'fixture','harness':'native','environment_sha256':s.artifact(b'fixture environment')},
            'source_definition_sha256':s.artifact(b'independently verified natural owner tasks only; no canary, maintenance or child'),
            'denominator':{'parent':None,'candidate':None}}


def test_cohort_no_samples_stays_unknown_and_has_existing_daily_followup(tmp_path):
    s=Store(tmp_path/'state');fixture(s,tmp_path)
    c=freeze_cohort(s,cohort(s));rev=s.revision();assert freeze_cohort(s,cohort(s))==c and s.revision()==rev
    report=cohort_report(s,'cohort')
    assert report['natural_gain']=='UNKNOWN' and report['arms']['candidate']['denominator'] is None
    assert report['arms']['candidate']['money'] is None and report['arms']['candidate']['rework'] is None
    assert s.list('outcome_followups')[0]['owner']=='proactive-review'


def test_canary_cannot_enter_a_natural_denominator(tmp_path):
    s=Store(tmp_path/'state');r=fixture(s,tmp_path);accept_task_result(s,seal_task_receipt(s,r));freeze_cohort(s,cohort(s))
    with pytest.raises(ValueError,match='CANARY_OR_CHILD_NOT_NATURAL'):
        record_cohort_sample(s,{'id':'sample','cohort_id':'cohort','arm':'candidate','task_receipt_id':'tr','source_receipt':{},'rework':0,'takeovers':0,'elapsed_seconds':1,'attempt_refs':[]})
    assert not s.list('cohort_samples')


def test_bare_method_string_or_forged_generation_cannot_certify_rsi(tmp_path):
    s=Store(tmp_path/'state');h=s.artifact(b'method instructions');proof=s.artifact(b'fixture authority')
    method={'id':'m','content_sha256':h,'parent_version_id':None,'mutable_surface':['selector'],'authority_evidence_sha256':proof,'acceptance_verdict_id':None}
    register_method_version(s,method)
    assert method_report(s,'m')['method_rsi']=='UNVERIFIED'
    with pytest.raises(ValueError,match='METHOD_NOT_ACCEPTED'):
        bind_generation(s,{'id':'g','method_version_id':'m','attempt_ref':{'kind':'generation_attempts','id':'invented','sha256':h},'input_capsule_sha256':h,'protocol_sha256':h,'candidate_sha256':h,'trace_sha256':h})
    with pytest.raises(ValueError,match='MUTABLE_SURFACE'):
        register_method_version(s,{**method,'id':'bad','mutable_surface':['oracle']})
