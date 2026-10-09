"""Actual container IPC tests with a synthetic owner, never domain gain evidence."""
import os
import shutil
import subprocess
import pytest
from skill_observatory.task_broker import TaskBroker, BrokerPolicy
from skill_observatory.evaluation import Environment, EvaluationHold
from skill_observatory.store import Store

IMAGE = 'python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f'


@pytest.fixture(scope='module')
def image():
    available = shutil.which('docker') and subprocess.run(
        ['docker', 'image', 'inspect', IMAGE], capture_output=True).returncode == 0
    if not available:
        if os.environ.get('SKILLOBS_REQUIRE_CONTAINER') == '1':
            pytest.fail('Actual pinned container unavailable')
        pytest.skip('Actual pinned container unavailable')
    return IMAGE


class SyntheticOwner:
    def __init__(self): self.calls = 0
    def admit(self, p):
        return {'ok': True, 'provider': p.provider, 'model': p.model,
                'maximum_verified_effort': p.effort,
                'redacted_evidence_allowed': True, 'tool_free_context_verified': True}
    def generate(self, prompt, p, **limits):
        self.calls += 1
        assert limits['max_tokens'] > 0 and limits['max_money'] >= 0 and limits['timeout'] > 0
        return {'text': 'synthetic response', 'tokens': 3, 'money': 0,
                'context_id': 'fixture-' + str(self.calls), 'fresh_context': True,
                'provider': p.provider, 'model': p.model, 'effort': p.effort}


def broker(tmp_path, owner=None, **limits):
    return TaskBroker(Store(tmp_path/'state'), BrokerPolicy('fixture', 'fixture', 'max',
        max_calls=limits.get('max_calls', 1), max_tokens=10, max_money=0,
        wall_seconds=limits.get('wall_seconds', 10)), owner or SyntheticOwner(), {'input': b'public input'})


class MissingCost(SyntheticOwner):
    def generate(self, *a, **kw):
        result = super().generate(*a, **kw)
        result['money'] = None
        return result


class SlowOwner(SyntheticOwner):
    def generate(self, *a, **kw):
        import time
        time.sleep(30)
        return super().generate(*a, **kw)


def test_actual_broker_artifact_identity_cost_and_replay(image, tmp_path):
    b = broker(tmp_path)
    script = b'''import json,sys,os
from pathlib import Path
print(json.dumps({'op':'snapshot','name':'input'}),flush=True)
assert json.loads(sys.stdin.readline())['text']=='public input'
print(json.dumps({'op':'model','prompt':'public bounded request'}),flush=True)
r=json.loads(sys.stdin.readline())
assert os.getenv('HOST_SECRET') is None
assert not Path('/var/run/docker.sock').exists()
Path('/out/result').write_text(r['text'])
'''
    os.environ['HOST_SECRET'] = 'not-for-container'
    try:
        r = b.run('test', {'task.py': script}, 'task.py', Environment(image, timeout=10))
    finally:
        os.environ.pop('HOST_SECRET', None)
    assert r['status'] == 'completed' and r['exit_code'] == 0
    assert r['tokens'] == 3 and r['money'] == 0
    assert b.store.read_artifact(r['artifacts']['result']) == b'synthetic response'
    assert r['calls'][0]['result_artifact']
    with pytest.raises(EvaluationHold, match='ATTEMPT_ALREADY_CONSUMED'):
        b.run('test', {'task.py': script}, 'task.py', Environment(image))
    assert len(b.store.get('broker_attempts', 'test')['calls']) == 1


@pytest.mark.parametrize('broker_request,reason', [
    ({'op': 'snapshot', 'name': '/etc/passwd'}, 'NOT_AUTHORIZED'),
    ({'op': 'shell', 'command': 'cat /oracle'}, 'OPERATION_NOT_AUTHORIZED'),
    ({'op': 'model', 'prompt': 'hello', 'model': 'different'}, 'OPERATION_NOT_AUTHORIZED')])
def test_candidate_cannot_expand_broker_surface(image, tmp_path, broker_request, reason):
    import json
    b = broker(tmp_path)
    script = ('import sys\nprint(' + repr(json.dumps(broker_request)) + ',flush=True)\nsys.stdin.readline()').encode()
    r = b.run('denied', {'task.py': script}, 'task.py', Environment(image))
    assert r['status'] == 'hold' and reason in r['reason_code']
    assert r['calls'] == []


def test_unknown_usage_retains_returned_output_and_blocks_replay(image, tmp_path):
    b = broker(tmp_path, MissingCost())
    script = b'''import sys
print('{"op":"model","prompt":"bounded"}',flush=True)
sys.stdin.readline()
'''
    r = b.run('unknown', {'task.py': script}, 'task.py', Environment(image))
    assert r['status'] == 'hold' and r['calls'][0]['money'] is None
    assert r['calls'][0]['result_artifact']
    assert r['money'] is None and r['tokens'] is None


def test_model_owner_timeout_is_bounded_and_consumed(image, tmp_path):
    import time
    b = broker(tmp_path, SlowOwner(), wall_seconds=2)
    script = b'''import sys
print('{"op":"model","prompt":"bounded"}',flush=True)
sys.stdin.readline()
'''
    start = time.monotonic()
    r = b.run('timeout', {'task.py': script}, 'task.py', Environment(image))
    assert time.monotonic()-start < 10
    assert r['status'] == 'hold' and r['reason_code'] == 'MODEL_DEADLINE_ATTEMPT_CONSUMED'
    assert r['money'] is None and len(r['calls']) == 1
    with pytest.raises(EvaluationHold, match='ATTEMPT_ALREADY_CONSUMED'):
        b.run('timeout', {'task.py': script}, 'task.py', Environment(image))


def test_failed_current_admission_has_no_attempt_or_process(tmp_path):
    class Held(SyntheticOwner):
        def admit(self, p): return {'ok': False}
    b = broker(tmp_path, Held())
    with pytest.raises(EvaluationHold, match='MODEL_OWNER_ADMISSION_HOLD'):
        b.run('held', {'task.py': b''}, 'task.py', Environment(IMAGE))
    assert b.store.list('broker_attempts') == []
