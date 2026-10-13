"""Final feedback identity and atomicity, distinct from actual-container gates."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import pytest
from skill_observatory.evaluation import Case,Environment,FixedArtifactOracle,freeze_protocol,paired_evaluate,EvaluationHold
from skill_observatory.store import Store,canonical,digest
import skill_observatory.evaluation as ev

IMAGE='python@sha256:'+'a'*64
PARENT={'task.py':b'print(1)'};CANDIDATE={'task.py':b'print(2)'}


class Sandbox:
 calls=0
 def __init__(self,*a):pass
 def prepare(self,*a):pass
 def execute(self,*a):type(self).calls+=1;return {'exit_code':0}
 def collect(self):return {'result':b'ok'}
 def destroy(self):pass


@pytest.fixture
def ledger(tmp_path,monkeypatch):
 Sandbox.calls=0;monkeypatch.setattr(ev,'DockerSandbox',Sandbox)
 return Store(tmp_path/'s')


def case(id):return Case(id,{'input':id.encode()},'synthetic','final',digest(id.encode()))


def evaluate(store,cases,labels=None,entrypoint='task.py'):
 oracle=FixedArtifactOracle(labels or {c.id:{'result':b'ok'} for c in cases})
 p=freeze_protocol(PARENT,CANDIDATE,cases,oracle,Environment(IMAGE),'deterministic-python','none')
 return paired_evaluate(p,PARENT,CANDIDATE,cases,oracle,entrypoint,store)


@pytest.mark.parametrize('next_cases',[[case('a')],[case('a'),case('b')],[case('b'),case('a')]])
def test_consumed_same_super_intersection_no_arm_execution(ledger,next_cases):
 evaluate(ledger,[case('a')]);before=Sandbox.calls
 with pytest.raises(EvaluationHold,match='FINAL_SET_ALREADY_CONSUMED'):evaluate(Store(ledger.root),next_cases)
 assert Sandbox.calls==before and len(ledger.list('evaluation_attempts'))==1
 assert len(ledger.list('final_sets'))==2 # byte identity + immutable source identity


def test_case_rename_label_change_and_provenance_washing_refused(ledger):
 a=case('a');evaluate(ledger,[a]);calls=Sandbox.calls
 renamed=replace(a,id='renamed',evidence_sha256='b'*64)
 with pytest.raises(EvaluationHold,match='FINAL_SET_ALREADY_CONSUMED'):evaluate(ledger,[renamed],{'renamed':{'result':b'changed'}})
 assert Sandbox.calls==calls
 # Same provenance with altered input also cannot launder the exposed source.
 changed=replace(a,input_files={'input':b'changed'})
 with pytest.raises(EvaluationHold,match='FINAL_SET_ALREADY_CONSUMED'):evaluate(ledger,[changed])


def test_atomic_batch_refusal_does_not_consume_new_sample(ledger):
 evaluate(ledger,[case('a')])
 with pytest.raises(EvaluationHold):evaluate(ledger,[case('b'),case('a')])
 evaluate(ledger,[case('b')]);assert len(ledger.list('evaluation_attempts'))==2


def test_concurrent_protocols_claim_exactly_one_batch(ledger):
 def attempt(_):
  try:return evaluate(Store(ledger.root),[case('a')])['status']
  except EvaluationHold as e:return str(e)
 with ThreadPoolExecutor(2) as ex:results=list(ex.map(attempt,range(2)))
 assert sorted(results)==['FINAL_SET_ALREADY_CONSUMED','hold']
 assert Sandbox.calls==2


def test_crash_after_claim_is_consumed_before_first_arm(ledger,monkeypatch):
 def crash(*a):raise RuntimeError('crash')
 monkeypatch.setattr(Sandbox,'prepare',crash)
 with pytest.raises(RuntimeError):evaluate(ledger,[case('a')])
 assert Sandbox.calls==0 and ledger.list('evaluation_attempts')[0]['status']=='prepared'
 with pytest.raises(EvaluationHold,match='FINAL_SET_ALREADY_CONSUMED'):evaluate(Store(ledger.root),[case('a')])


def test_execution_before_after_freeze_identity_drift(ledger):
 oracle=FixedArtifactOracle({'a':{'result':b'ok'}})
 p=freeze_protocol(PARENT,CANDIDATE,[case('a')],oracle,Environment(IMAGE),'deterministic-python','none')
 with pytest.raises(EvaluationHold,match='EXECUTION_IDENTITY_DRIFT'):
  paired_evaluate(p,PARENT,CANDIDATE,[case('a')],oracle,'other.py',ledger)
 assert not ledger.list('final_sets')
 with pytest.raises(EvaluationHold,match='FROZEN_ENTRYPOINT_REQUIRED'):
  freeze_protocol({'one.py':b'','two.py':b''},{'one.py':b'','two.py':b''},[case('a')],oracle,Environment(IMAGE),'deterministic-python','none')


def test_legacy_set_consumption_preserved_and_unmapped_hold(ledger):
 a=case('a');oracle=FixedArtifactOracle({'a':{'result':b'ok'}})
 p=freeze_protocol(PARENT,CANDIDATE,[a],oracle,Environment(IMAGE),'deterministic-python','none')
 ledger.put('protocols',p);ledger.put('final_sets',{'id':'legacy','protocol_sha256':digest(canonical(p)),'status':'consumed'})
 with pytest.raises(EvaluationHold,match='FINAL_SET_ALREADY_CONSUMED'):evaluate(ledger,[a])
 ledger.put('final_sets',{'id':'unknown-legacy','protocol_sha256':'unknown','status':'consumed'})
 with pytest.raises(EvaluationHold,match='LEGACY_FINAL_CONSUMPTION_READBACK_REQUIRED'):evaluate(ledger,[case('b')])
 assert Sandbox.calls==0
