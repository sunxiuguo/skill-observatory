"""Root F7-F10 refusals and unmodified acceptance idempotence."""
import os
import pytest
from skill_observatory.store import canonical
from skill_observatory.packages import snapshot_package
from test_final_reconciliation import prepared,verdict


def test_exact_accepted_final_is_idempotent_and_later_failure_revokes_current_cache(tmp_path):
    s,c,p,e,d,cost=prepared(tmp_path);good=verdict(s,d,cost);revision=s.revision()
    assert verdict(s,d,cost)==good and s.revision()==revision
    final_claims=s.list('final_sets')
    row={'id':'later-failure','candidate_id':c['id'],'status':'failed','cost':{'money':100,'currency':'USD','tokens':1,'input_tokens':1,'output_tokens':0,'cached_input_tokens':0,'wall_seconds':1}}
    s.put('generation_attempts',row);c['cost_attempt_ids'].append(row['id']);s.put('candidates',c)
    cost['attempt_refs'].append({'kind':'generation_attempts','id':row['id'],'sha256':s.artifact(canonical(row))});cost['attempt_ids'].append(row['id'])
    cost.update(money=104.25,tokens=171,wall_seconds=19,budget_pass=False)
    with pytest.raises(ValueError,match='COST_COVERAGE_REQUIRED|COST_BUDGET_EXCEEDED'):verdict(s,d,cost)
    current=s.get('verdicts',good['id']);assert current['status']=='hold' and 'signature' not in current
    assert s.read_artifact(current['previous_verdict_sha256'])==canonical(good)
    assert s.list('final_sets')==final_claims


def test_ledger_linked_failed_arm_cannot_be_omitted_and_unrelated_same_id_cannot_replace_it(tmp_path):
    s,c,p,e,d,cost=prepared(tmp_path)
    row={'id':'failed-arm','protocol_id':p['id'],'attempt_id':e['attempt_id'],'case_id':'0','arm':'candidate','status':'failed',
         'cost':{'money':100,'currency':'USD','tokens':10,'input_tokens':10,'output_tokens':0,'cached_input_tokens':0,'wall_seconds':2}}
    s.put('task_family_attempts',row)
    assert 'EXPLORATION_COST_COVERAGE_REQUIRED' in verdict(s,d,cost)['missing']
    other={**row,'protocol_id':'unrelated','attempt_id':'other'};s.put('broker_attempts',other)
    cost['attempt_refs'].append({'kind':'broker_attempts','id':other['id'],'sha256':s.artifact(canonical(other))})
    assert verdict(s,d,cost)['status']=='hold'


def test_unrelated_other_protocol_failure_is_not_charged_to_candidate(tmp_path):
    s,c,p,e,d,cost=prepared(tmp_path)
    s.put('task_family_attempts',{'id':'unrelated','protocol_id':'other','attempt_id':'other','status':'unknown_after_dispatch'})
    assert verdict(s,d,cost)['status']=='accepted'


@pytest.mark.parametrize('status',['unknown_after_dispatch','interrupted','failed_after_dispatch','prepared','running','dispatched','unknown','terminal_received'])
def test_known_invoice_does_not_resolve_unknown_effects(tmp_path,status):
    s,c,p,e,d,cost=prepared(tmp_path);row=s.get('generation_attempts','proposal');row['status']=status;s.put('generation_attempts',row)
    cost['attempt_refs'][1]['sha256']=s.artifact(canonical(row))
    assert 'COST_ATTEMPT_READBACK_REQUIRED' in verdict(s,d,cost)['missing']


@pytest.mark.parametrize('mode',[0o4755,0o2755,0o1755])
def test_all_special_file_permission_bits_refuse_without_executing(tmp_path,mode):
    from skill_observatory.store import Store
    root=tmp_path/'package';root.mkdir();p=root/'helper.py';p.write_text('pass');p.chmod(0o755);s=Store(tmp_path/'state')
    before=snapshot_package(s,root);p.chmod(0o700);assert snapshot_package(s,root)!=before
    p.chmod(mode)
    try:
        with pytest.raises(ValueError,match='MODE_REJECTED'):snapshot_package(s,root)
    finally:p.chmod(0o755)


def test_fifo_and_special_directory_modes_have_explicit_boundary(tmp_path):
    from skill_observatory.store import Store
    root=tmp_path/'package';root.mkdir();(root/'SKILL.md').write_text('ordinary');s=Store(tmp_path/'state')
    fifo=root/'pipe';os.mkfifo(fifo)
    with pytest.raises(ValueError,match='TYPE_REJECTED'):snapshot_package(s,root)
    fifo.unlink();root.chmod(0o1700)
    try:
        with pytest.raises(ValueError,match='DIRECTORY_MODE_REJECTED'):snapshot_package(s,root)
    finally:root.chmod(0o700)


def test_completed_child_cost_is_referenced_but_not_double_billed(tmp_path):
    s,c,p,e,d,cost=prepared(tmp_path);trial=e['trials'][0]
    row={**{k:trial[k] for k in ('case_id','arm','passed','receipt','artifacts','cost')},
         'id':trial['trial_id'],'status':'completed','protocol_id':p['id'],'attempt_id':e['attempt_id']}
    s.put('task_family_attempts',row)
    cost['attempt_refs'].append({'kind':'task_family_attempts','id':row['id'],'sha256':s.artifact(canonical(row))})
    cost['attempt_ids'].append(row['id'])
    assert verdict(s,d,cost)['status']=='accepted'


def test_unrelated_homonymous_kind_does_not_replace_or_charge_an_owned_attempt(tmp_path):
    s,c,p,e,d,cost=prepared(tmp_path)
    s.put('broker_attempts',{'id':'proposal','protocol_id':'unrelated','status':'unknown_after_dispatch'})
    assert verdict(s,d,cost)['status']=='accepted'
