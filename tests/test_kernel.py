import json
import time
import pytest
from fastapi.testclient import TestClient
from skill_observatory.store import Store, digest, canonical, now
from skill_observatory.runtime import spool, ingest, process_one, state, package_manifest
from skill_observatory.installations import rollback, recover, validate_verdict
from skill_observatory.api import create_app


@pytest.fixture
def store(tmp_path):
    s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path/'project')]});return s


def event(store, **kw):
    return dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=store.settings()['scopes'][0],**kw)


def test_durable_duplicate_restart_and_unknown_truth(store):
    spool(store,event(store));spool(store,event(store));assert ingest(store)==1
    assert ingest(Store(store.root))==0
    r=process_one(store);assert r['status']=='triaged' and r['decision']=='HOLD'
    assert state(store)['metrics']['reviewed_runs']==0
    assert state(store)['metrics']['triaged_runs']==1
    assert state(store)['metrics']['global_coverage'] is None


def test_outside_scope_no_private_spool(store):
    e=event(store);e['cwd']='/unrelated'
    assert spool(store,e)['reason_code']=='OUTSIDE_SCOPE'
    assert not list((store.root/'spool').glob('*'))


def test_interrupt_child_identity_and_no_automatic_replay(store):
    e=event(store,agent_id='child');e['hook_event_name']='Interrupt';spool(store,e);ingest(store)
    j=store.lease(seconds=-1);assert j
    assert store.lease() is None
    assert store.jobs()[0]['reason_code']=='INTERRUPTED_ATTEMPT'
    assert store.list('runs')[0]['outcome']=='partial'


def test_package_binds_scripts_and_rejects_external_symlink(tmp_path):
    (tmp_path/'SKILL.md').write_text('skill');(tmp_path/'run.py').write_text('before')
    a=package_manifest(tmp_path);(tmp_path/'run.py').write_text('after')
    assert a['package_sha256']!=package_manifest(tmp_path)['package_sha256']
    (tmp_path/'outside').symlink_to('/etc/passwd')
    with pytest.raises(ValueError,match='SYMLINK'):package_manifest(tmp_path)


def test_prepared_recovery_and_cas_rollback(store,tmp_path):
    p=tmp_path/'SKILL.md';p.write_bytes(b'before');before=store.artifact(b'before');after=store.artifact(b'after')
    store.put('installations',dict(id='i',target=str(p),before_sha256=before,after_sha256=after,status='prepared'))
    assert recover(store)[0]['status']=='activation_pending';assert p.read_bytes()==b'after'
    p.write_bytes(b'user change')
    with pytest.raises(ValueError,match='DRIFT'):rollback(store,'i')
    assert p.read_bytes()==b'user change'
    p.write_bytes(b'after');assert rollback(store,'i')['status']=='rolled_back';assert p.read_bytes()==b'before'
    assert rollback(store,'i')['status']=='rolled_back'


def test_unsigned_verdict_cannot_install(store):
    with pytest.raises(ValueError,match='UNTRUSTED'):validate_verdict(store,dict(status='accepted',gates={'gain_pass':True}))


def test_loopback_csrf_origin_and_settings_survive_restart(store):
    with TestClient(create_app(store,daemon=False),base_url="http://127.0.0.1") as c:
        assert c.get('/api/session',headers={'Host':'testserver'}).status_code==403
        assert c.get('/api/state').status_code==401
        csrf=c.get('/api/session').json()['csrf']
        assert c.post('/api/settings',json={'locale':'en'}).status_code==403
        assert c.post('/api/settings',json={'locale':'en'},headers={'x-csrf-token':csrf,'Origin':'https://evil.example'}).status_code==403
        assert c.post('/api/settings',json={'locale':'en','timezone':'UTC'},headers={'x-csrf-token':csrf}).status_code==200
        assert c.post('/api/settings',json={'auto_promote':True},headers={'x-csrf-token':csrf}).status_code==422
        assert c.get('/api/artifacts/not-a-content-hash').status_code==404
    assert Store(store.root).settings()['locale']=='en'
    assert Store(store.root).settings()['timezone']=='UTC'


def test_late_terminal_preserves_triage_status(store):
    spool(store,event(store));ingest(store);process_one(store)
    late=event(store);late['hook_event_name']='SessionEnd'
    spool(store,late);ingest(store)
    assert store.list('runs')[0]['status']=='triaged'
    assert state(store)['metrics']['reviewed_runs']==0


def test_secret_and_raw_prompt_not_persisted(store):
    e=event(store,api_key='sk-secretvalue1234567',prompt='private prompt',tool_input={'command':'curl --header secret'})
    spool(store,e)
    data=next((store.root/'spool').glob('*.json')).read_text()
    assert 'secretvalue' not in data and 'private prompt' not in data and 'curl' not in data


def test_browser_retry_cannot_replay_consumed_model_attempt(store):
    spool(store,event(store));ingest(store);job=store.lease()
    with store.connect() as db:
        db.execute("UPDATE jobs SET status='hold',reason_code='INVALID_JSON' WHERE id=?",(job['id'],))
    store.put('review_attempts',{'id':'actual-model-attempt','run_id':job['run_id'],
                              'status':'prepared','admission_sha256':'a'*64})
    with TestClient(create_app(store,daemon=False),base_url="http://127.0.0.1") as c:
        csrf=c.get('/api/session').json()['csrf']
        r=c.post('/api/jobs/'+job['id']+'/retry',headers={'x-csrf-token':csrf})
        assert r.status_code==409 and r.json()['detail']['reason_code']=='ATTEMPT_READBACK_REQUIRED'
    assert store.jobs()[0]['status']=='hold'
