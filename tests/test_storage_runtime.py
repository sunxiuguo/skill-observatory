import json
import gzip
import shutil
import sqlite3
import time
from fastapi.testclient import TestClient
import pytest
from skill_observatory.store import Store,canonical
from skill_observatory.runtime import collect,spool,ingest
from skill_observatory.api import create_app
from skill_observatory.health import failure,snapshot
from skill_observatory.recovery import rebuild


def test_existing_store_open_and_identical_put_do_not_write(tmp_path):
    store=Store(tmp_path/'state');store.put('example',{'id':'one','status':'stable'})
    before=store.revision()
    for _ in range(5):
        other=Store(store.root);other.put('example',{'id':'one','status':'stable'})
    assert store.revision()==before
    with store.connect() as db:assert db.execute('PRAGMA user_version').fetchone()[0]==3


def test_idle_collection_does_not_rewrite_terminal_history(tmp_path):
    store=Store(tmp_path/'state');store.settings({'scopes':[str(tmp_path)]})
    spool(store,dict(hook_event_name='SessionEnd',session_id='s',cwd=str(tmp_path),timestamp='2026-01-02T00:00:00Z'))
    ingest(store);collect(store);revision=store.revision()
    for _ in range(5):collect(store)
    assert store.revision()==revision


def test_injected_catalog_names_do_not_create_usage(tmp_path):
    from skill_observatory.runtime import register
    store=Store(tmp_path/'state');store.settings({'scopes':[str(tmp_path)]})
    skill=tmp_path/'flow';skill.mkdir();(skill/'SKILL.md').write_text('flow')
    register(store,skill,'owner')
    spool(store,dict(hook_event_name='UserPromptSubmit',session_id='s',turn_id='t',cwd=str(tmp_path),prompt=str(skill/'SKILL.md')))
    ingest(store)
    assert not store.list('capability_invocations')


def test_health_survives_unreadable_ledger_and_api_reports_503(tmp_path):
    store=Store(tmp_path/'state')
    # The live Store is retained while the on-disk database becomes unreadable.
    store.db_path.write_bytes(b'corrupt database')
    with TestClient(create_app(store),base_url='http://127.0.0.1') as client:
        client.get('/api/session')
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and snapshot(store.root)['status']!='degraded':time.sleep(.02)
        response=client.get('/api/summary')
        assert response.status_code==503 and response.json()['reason_code']=='LEDGER_UNAVAILABLE'
        response=client.get('/api/health')
        assert response.status_code==503
        assert response.json()['status']=='degraded'
        assert any(w.get('reason_code') for w in response.json()['workers'])
    assert store.db_path.read_bytes()==b'corrupt database'


def test_failure_backoff_does_not_report_success(tmp_path):
    store=Store(tmp_path/'state')
    assert [failure(store,'daemon','DatabaseError') for _ in range(4)]==[1,2,4,8]
    worker=snapshot(store.root)['workers'][0]
    assert not worker['healthy'] and worker['consecutive_failures']==4
    assert worker.get('last_success_at') is None


def test_offline_rebuild_preserves_attempts_authority_and_no_replay(tmp_path):
    store=Store(tmp_path/'state');store.settings({'scopes':[str(tmp_path)]})
    spool(store,dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=str(tmp_path)))
    ingest(store);run=store.list('runs')[0]
    attempt={'id':'attempt','run_id':run['id'],'status':'unknown_after_dispatch','admission_sha256':'a'*64,'money':None}
    store.put('review_attempts',attempt);store.put('authority_grants',{'id':'owner','status':'authorized','surface':'single_text_file'})
    with store.connect() as db:db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    backup=tmp_path/'backup.sqlite3';shutil.copy2(store.db_path,backup)
    before=store.db_path.read_bytes();plan=rebuild(store.root,backup)
    assert not plan['applied'] and store.db_path.read_bytes()==before
    result=rebuild(store.root,backup,apply=True)
    assert result['applied'] and result['replayed_model_requests']==0
    after=Store(store.root)
    assert after.get('review_attempts','attempt')==attempt
    assert after.get('authority_grants','owner')['status']=='authorized'
    assert after.settings()['scopes']==[str(tmp_path)]
    with after.connect() as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert list((store.root/'recovery').glob('*.sqlite3'))


def test_recovery_refuses_bad_backup(tmp_path):
    store=Store(tmp_path/'state');bad=tmp_path/'bad.sqlite3';bad.write_bytes(b'broken')
    before=store.db_path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):rebuild(store.root,bad,apply=True)
    assert store.db_path.read_bytes()==before


def test_recovery_accepts_losslessly_compressed_healthy_backup(tmp_path):
    store=Store(tmp_path/'state');store.put('authority_grants',{'id':'owner','status':'authorized'})
    with store.connect() as db:db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    backup=tmp_path/'backup.sqlite3.gz';backup.write_bytes(gzip.compress(store.db_path.read_bytes(),mtime=0))
    result=rebuild(store.root,backup,apply=True)
    assert result['applied'] and Store(store.root).get('authority_grants','owner')['status']=='authorized'


def test_coalesced_worker_progress_preserves_last_collection_stats(tmp_path,monkeypatch):
    from skill_observatory.runtime import progress
    from skill_observatory.api import summary
    s=Store(tmp_path/'state');clock=[1000.0]
    monkeypatch.setattr('skill_observatory.runtime.time.time',lambda:clock[0])
    progress(s,'daemon','idle',spool_count=0,successful=True)
    clock[0]+=6
    progress(s,'daemon','collect',deadline_at=clock[0]+300)
    result=summary(s)
    assert result['metrics']['spool_count']==0
    assert result['metrics']['heartbeat_age']==0
    assert result['metrics']['daemon_running'] is True
