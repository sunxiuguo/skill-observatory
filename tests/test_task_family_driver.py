"""Synthetic driver refusals; actual native execution is a separate pilot."""
import pytest
from skill_observatory.store import Store,digest
from skill_observatory.evaluation import Case,Environment,FixedArtifactOracle,freeze_protocol,EvaluationHold
from skill_observatory.task_families import NativeTaskFamilyDriver,_safe_parser


def prepared(tmp_path):
    s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
    parent={'SKILL.md':b'parent','task.py':b'pass'};candidate={'SKILL.md':b'candidate','task.py':b'pass'}
    case=Case('case',{'TASK.txt':b'Synthetic driver contract only'},'synthetic','final',s.artifact(b'provenance'))
    oracle=FixedArtifactOracle({'case':{'result.json':b'{}'}})
    identity={'kind':'native-task-family','model':'fixture','provider':'fixture','effort':'max','runtime_sha256':'a'*64,'tool_contract_sha256':'b'*64,'transcript_model':'fixture','output_files':['result.json']}
    p=freeze_protocol(parent,candidate,[case],oracle,Environment('python@sha256:'+'a'*64),'fixture','max',entrypoint='task.py',execution_identity=identity)
    p['synthetic']=True
    driver=NativeTaskFamilyDriver.prepare(s,p,parent,candidate,[case],oracle,tmp_path/'work')
    return s,p,driver,parent,candidate,case,oracle


def test_native_dispatch_requires_exact_admission_and_never_replays(tmp_path):
    s,p,driver,*_=prepared(tmp_path);run=s.get('task_family_runs',p['id']);id_=run['trial_ids'][0]
    a={'ok':True,'provider':'fixture','model':'fixture','reasoning_effort':'max','lease_id':'lease','fork_context':False,'compatibility_contract_sha256':'b'*64}
    with pytest.raises(EvaluationHold,match='ADMISSION_MISMATCH'):driver.dispatch(id_,{**a,'model':'other'},'child','root')
    driver.dispatch(id_,a,'child','root')
    with pytest.raises(EvaluationHold,match='READBACK_REQUIRED'):driver.dispatch(id_,a,'child2','root')
    assert len(s.list('task_family_attempts'))==2
    with pytest.raises(EvaluationHold,match='READBACK_REQUIRED'):driver.result()


def test_same_final_input_is_consumed_before_native_tool_dispatch(tmp_path):
    s,p,d,a,b,c,o=prepared(tmp_path)
    with pytest.raises(EvaluationHold,match='FINAL_SET_ALREADY_CONSUMED'):
        NativeTaskFamilyDriver.prepare(s,{**p,'id':'another'},a,b,[c],o,tmp_path/'second')
    assert not any(x.get('child_id') for x in s.list('task_family_attempts'))


def test_parser_contract_cannot_execute_unrelated_host_code():
    with pytest.raises(EvaluationHold,match='CODE_REJECTED'):_safe_parser('import os\nos.system("echo escaped")')
