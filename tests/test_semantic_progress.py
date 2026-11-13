import pytest

from skill_observatory.store import Store
from skill_observatory.semantic_progress import project
from skill_observatory.runtime import progress


def test_idle_health_is_not_material_progress(tmp_path):
    s=Store(tmp_path/'state');before=project(s)
    progress(s,'daemon','idle',successful=True)
    progress(s,'review_worker','idle',successful=True)
    after=project(s)
    assert after==before and all(x['last_material_at'] is None for x in after['stages'])
    s.put('task_family_attempts',{'id':'actual','status':'completed','finished_at':'2026-01-01T00:00:00+00:00'})
    current=project(s)
    assert next(x for x in current['stages'] if x['id']=='trial')['observed_count']==1
    assert current['claim_layers']=={'skill_gain':'HOLD','natural_gain':'UNKNOWN','method_rsi':'UNVERIFIED'}


@pytest.mark.parametrize('terminal_status', ['completed', 'failed', 'interrupted'])
def test_terminal_reviewer_failure_does_not_request_unknown_execution_readback(tmp_path, terminal_status):
    s=Store(tmp_path/'state')
    attempt={'id':'rejected','status':'failed_after_dispatch','terminal_status':terminal_status,
             'reason_code':'ATTRIBUTION_NOT_BOUND','missing':['MONETARY_COST_UNKNOWN']}
    s.put('review_attempts',attempt)
    with s.connect() as db:
        db.execute("INSERT INTO jobs(id,run_id,status,reason_code) VALUES('facts','run','hold','DIAGNOSTIC_FACTS_REQUIRED')")
    current=project(s)
    assert current['unknown_attempts']==0
    assert current['first_blocker']=='DIAGNOSTIC_FACTS_REQUIRED'
    assert current['next_action']=='select_native_facts'
    assert s.get('review_attempts','rejected')==attempt
    assert current['claim_layers']=={'skill_gain':'HOLD','natural_gain':'UNKNOWN','method_rsi':'UNVERIFIED'}


@pytest.mark.parametrize('terminal_status', [None, 'running', 'unrecognized'])
def test_reviewer_failure_without_known_terminal_still_requires_readback(tmp_path, terminal_status):
    s=Store(tmp_path/'state')
    s.put('review_attempts',{'id':'unresolved','status':'failed_after_dispatch','terminal_status':terminal_status})
    current=project(s)
    assert current['unknown_attempts']==1
    assert current['first_blocker']=='ATTEMPT_READBACK_REQUIRED'
    assert current['next_action']=='readback_unknown_attempt'


@pytest.mark.parametrize('kind', ['generation_attempts', 'broker_attempts', 'task_family_attempts'])
def test_reviewer_terminal_contract_does_not_resolve_other_attempt_kinds(tmp_path, kind):
    s=Store(tmp_path/'state')
    s.put(kind,{'id':'other','status':'unknown_after_dispatch','terminal_status':'completed'})
    current=project(s)
    assert current['unknown_attempts']==1
    assert current['first_blocker']=='ATTEMPT_READBACK_REQUIRED'
