"""Versioned local facts: no synthetic goals, natural origin or invented success."""
import json
import pytest
from test_evidence_recovery import fixture
from skill_observatory.evidence import build_selected_evidence,evidence_plan,build_capsule


def test_selection_build_is_change_driven_private_and_version_bound(tmp_path):
    s,run,facts=fixture(tmp_path)
    first=evidence_plan(s,run['id'])[0];assert first['status']=='awaiting_native_selection'
    assert first['source_class']=='unknown' and first['actual_terminal']['truth']=='runtime_only_unverified'
    assert evidence_plan(s,run['id'])[0]==first
    before=len(s.list('review_attempts'))
    r=build_selected_evidence(s,facts);assert r['resumed_pre_dispatch_jobs']==1
    assert build_selected_evidence(s,facts)==r
    capsule=build_capsule(s,s.get('runs',run['id']))
    assert capsule['schema_version']==2 and not capsule['missing']
    assert 'local_refs' not in capsule['facts']
    assert capsule['facts']['package_digest']==s.get('capability_versions',facts['version_id'])['package_sha256']
    assert len(s.list('review_attempts'))==before
    changed={**facts,'goal':'Another unsupported rewrite'}
    with pytest.raises(ValueError,match='ALREADY_SELECTED'):build_selected_evidence(s,changed)


@pytest.mark.parametrize('failure',['secret','natural','environment','reference'])
def test_builder_rejects_sensitive_unbound_or_invented_inputs(tmp_path,failure):
    s,run,facts=fixture(tmp_path)
    if failure=='secret':facts['goal']='use password=not-for-transport'
    if failure=='natural':facts['source_class']='natural'
    if failure=='environment':facts['environment_binding']={'model':'made-up','effort':'max','harness':None,'runtime':None,'evidence_sha256':None,'missing':[]}
    if failure=='reference':facts['artifact_refs']=[{'kind':'output','sha256':'0'*64}]
    with pytest.raises((ValueError,FileNotFoundError)):build_selected_evidence(s,facts)


def test_v2_capsule_cannot_borrow_v1_transport_data_authority(tmp_path):
    from skill_observatory.reviewer import CodexReviewer
    s,run,facts=fixture(tmp_path);build_selected_evidence(s,facts)
    def forbidden_transport():raise AssertionError('unapproved v2 transport must not be created')
    admission=lambda *args:{'ok':True,'maximum_verified_effort':'max','execution_mode':'background_tool_free',
                            'tool_free_context_verified':True,'redacted_evidence_allowed':True,'evidence_capsule_versions':[1]}
    before=len(s.list('review_attempts'))
    with pytest.raises(ValueError,match='EVIDENCE_CAPSULE_DATA_AUTHORITY_REQUIRED'):
        CodexReviewer(forbidden_transport,admission,'fixture','fixture','max',tmp_path).review(s,s.get('runs',run['id']))
    assert len(s.list('review_attempts'))==before


def test_one_ineligible_historical_run_does_not_block_current_fact_work(tmp_path):
    s,run,facts=fixture(tmp_path)
    outside={**run,'id':'outside','cwd':'/outside/authorized/scope','updated_at':'2099-01-01T00:00:00+00:00'}
    s.put('runs',{**outside,'terminal':True});s.put('runs',{**run,'terminal':True})
    rows=evidence_plan(s,limit=2)
    assert any(r['run_id']=='outside' and r['status']=='blocked' and r['missing']==['OUTSIDE_SCOPE'] for r in rows)
    assert any(r['run_id']==run['id'] and r['status']=='awaiting_native_selection' for r in rows)
    with pytest.raises(ValueError,match='OUTSIDE_SCOPE'):evidence_plan(s,'outside')
