"""Infrastructure tests are synthetic; they do not certify a Skill improvement."""
import json
import shutil
import subprocess
import os
import pytest
from skill_observatory.evaluation import DockerSandbox, Environment, EvaluationHold, FixedArtifactOracle, Case, freeze_protocol, paired_evaluate
from skill_observatory.store import Store

PINNED_IMAGE='python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f'


@pytest.fixture(scope='module')
def image():
    def missing(message):
        if os.environ.get('SKILLOBS_REQUIRE_CONTAINER')=='1':pytest.fail(message)
        pytest.skip(message)
    if not shutil.which('docker'):missing('Docker unavailable')
    r=subprocess.run(['docker','image','inspect',PINNED_IMAGE],capture_output=True,text=True)
    if r.returncode:missing('Pinned canary image not installed')
    return PINNED_IMAGE


def test_no_mutable_image_or_arbitrary_shell():
    with pytest.raises(EvaluationHold,match='IMMUTABLE'):Environment('python:latest').validate()
    s=DockerSandbox(Environment('python@sha256:'+'a'*64))
    with pytest.raises(EvaluationHold,match='ENTRYPOINT'):s.execute('../oracle.py')


def test_real_container_isolates_host_network_secrets_and_oracle(image,monkeypatch):
    monkeypatch.setenv('SKILLOBS_SECRET_CANARY','host-only-secret')
    script=b'''import json,os,socket
from pathlib import Path
denied=False
try: Path('/etc/skillobs-write').write_text('escape')
except OSError: denied=True
network=False
try: socket.create_connection(('1.1.1.1',443),timeout=1); network=True
except OSError: pass
Path('/out/result.json').write_text(json.dumps({'root_denied':denied,'network':network,'secret':os.environ.get('SKILLOBS_SECRET_CANARY'),'socket':Path('/var/run/docker.sock').exists(),'oracle':Path('/oracle').exists(),'uid':os.getuid()}))
'''
    s=DockerSandbox(Environment(image))
    try:
        prepared=s.prepare({'task.py':script});r=s.execute('task.py');a=s.collect()
        assert prepared['host_mounts']==[] and r['exit_code']==0
        data=json.loads(a['result.json'])
        assert data=={'root_denied':True,'network':False,'secret':None,'socket':False,'oracle':False,'uid':1000}
    finally:s.destroy()
    assert s.id is None


def test_real_artifact_grading_and_synthetic_final_stays_hold(image):
    parent={'task.py':b"from pathlib import Path; Path('/out/result').write_text('wrong')"}
    candidate={'task.py':b"from pathlib import Path; Path('/out/result').write_text('right')"}
    cases=[Case('infra-fixture',{},'synthetic','final','a'*64)]
    oracle=FixedArtifactOracle({'infra-fixture':{'result':b'right'}})
    p=freeze_protocol(parent,candidate,cases,oracle,Environment(image),'deterministic-python','not-applicable-no-model',minimum_cases=2)
    r=paired_evaluate(p,parent,candidate,cases,oracle,'task.py')
    assert r['status']=='hold' and r['paired_gain']==1
    assert 'REAL_CASE_EVIDENCE_REQUIRED' in r['missing']
    assert 'INSUFFICIENT_INDEPENDENT_CASES' in r['missing']
    receipts=[x['receipt']['container_id'] for x in r['trials']]
    assert len(set(receipts))==2
    with pytest.raises(EvaluationHold,match='ARM_HASH_DRIFT'):paired_evaluate(p,parent,{'task.py':b'changed'},cases,oracle,'task.py')


def test_final_set_consumption_survives_restart_and_new_protocol(image,tmp_path):
    store=Store(tmp_path/'private')
    parent={'task.py':b"from pathlib import Path; Path('/out/result').write_text('wrong')"}
    candidate={'task.py':b"from pathlib import Path; Path('/out/result').write_text('right')"}
    cases=[Case('infra-fixture',{},'synthetic','final','a'*64)]
    oracle=FixedArtifactOracle({'infra-fixture':{'result':b'right'}})
    p=freeze_protocol(parent,candidate,cases,oracle,Environment(image),'deterministic-python','not-applicable-no-model')
    result=paired_evaluate(p,parent,candidate,cases,oracle,'task.py',store)
    assert result['status']=='hold'
    assert store.list('evaluation_attempts')[0]['result_sha256']
    assert store.list('final_sets')[0]['status']=='consumed'
    p2=freeze_protocol(parent,candidate,cases,oracle,Environment(image),'deterministic-python','not-applicable-no-model')
    assert p2['id']!=p['id']
    with pytest.raises(EvaluationHold,match='FINAL_SET_ALREADY_CONSUMED'):
        paired_evaluate(p2,parent,candidate,cases,oracle,'task.py',Store(store.root))
    assert len(store.list('evaluation_attempts'))==1
