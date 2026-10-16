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
