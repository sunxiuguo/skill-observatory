import gzip
import json
from pathlib import Path
import pytest
from skill_observatory.store import Store,canonical
from skill_observatory.runtime import spool,ingest,process_one
from skill_observatory.maintenance import compress_artifacts,archive_events,storage_inventory,automatic_maintenance


def old_terminal(tmp_path):
    s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
    payload=dict(hook_event_name='Stop',session_id='s',turn_id='t',cwd=str(tmp_path),timestamp='2026-01-01T00:00:00Z')
    result=spool(s,payload);ingest(s);process_one(s)
    with s.connect() as db:
        row=db.execute('SELECT data FROM events WHERE id=?',(result['id'],)).fetchone()
        value=json.loads(row[0]);value['created_at']='2026-01-01T00:00:00+00:00'
        db.execute('UPDATE events SET data=?,created_at=? WHERE id=?',(canonical(value).decode(),value['created_at'],result['id']))
    return s,result['id'],value,payload


def test_lossless_artifact_dry_run_apply_and_reuse(tmp_path):
    s=Store(tmp_path/'state');raw=b'bounded evidence\n'*1000;h=s.artifact(raw)
    before=storage_inventory(s)['groups']['artifacts']['bytes']
    plan=compress_artifacts(s);assert plan['saved_bytes']>0 and not plan['applied']
    assert (s.root/'artifacts'/h).exists()
    result=compress_artifacts(s,apply=True)
    assert result['files']==1 and not (s.root/'artifacts'/h).exists()
    assert s.read_artifact(h)==raw and s.artifact(raw)==h
    assert storage_inventory(s)['groups']['artifacts']['bytes']<before
    assert compress_artifacts(s,apply=True)['files']==0


def test_compressed_artifact_corruption_fails_without_unknown_zero(tmp_path):
    s=Store(tmp_path/'state');h=s.artifact(b'evidence'*500);compress_artifacts(s,apply=True)
    (s.root/'artifacts'/(h+'.gz')).write_bytes(gzip.compress(b'wrong'))
    with pytest.raises(ValueError,match='ARTIFACT_CORRUPT'):s.read_artifact(h)


def test_event_archive_preserves_identity_and_duplicate_barrier(tmp_path):
    s,id,value,payload=old_terminal(tmp_path)
    with s.connect() as db:before=dict(db.execute('SELECT * FROM events WHERE id=?',(id,)).fetchone())
    assert archive_events(s,'2026-02-01T00:00:00Z')['count']==1
    assert not s.list('storage_archives')
    result=archive_events(s,'2026-02-01T00:00:00Z',apply=True);assert result['count']==1
    with s.connect() as db:
        after=dict(db.execute('SELECT * FROM events WHERE id=?',(id,)).fetchone())
        assert s.event_data(after['data'],db)==value
    assert after['hash']==before['hash'] and after['id']==before['id'] and after['created_at']==before['created_at']
    attempts=s.jobs()[0]['attempts'];spool(s,payload);assert ingest(s)==0
    assert s.jobs()[0]['attempts']==attempts
    assert archive_events(s,'2026-02-01T00:00:00Z',apply=True)['count']==0


@pytest.mark.parametrize('status',['running','queued','deferred'])
def test_inflight_jobs_exclude_old_payload(tmp_path,status):
    s,id,value,payload=old_terminal(tmp_path)
    with s.connect() as db:db.execute('UPDATE jobs SET status=?',(status,))
    assert archive_events(s,'2026-02-01T00:00:00Z',apply=True)['count']==0
    with s.connect() as db:assert s.event_data(db.execute('SELECT data FROM events WHERE id=?',(id,)).fetchone()[0],db)==value


def test_cold_payload_corruption_refuses_readback(tmp_path):
    s,id,value,payload=old_terminal(tmp_path);archive_events(s,'2026-02-01T00:00:00Z',apply=True)
    with s.connect() as db:
        db.execute('UPDATE archive_event_payloads SET data=?',(gzip.compress(b'wrong'),))
        marker=db.execute('SELECT data FROM events WHERE id=?',(id,)).fetchone()[0]
    with pytest.raises(ValueError,match='ARCHIVE_EVENT_CORRUPT'):s.event_data(marker)


def test_automatic_maintenance_opt_in_and_daily_noop(tmp_path):
    s,id,value,payload=old_terminal(tmp_path);assert automatic_maintenance(s) is None
    s.settings({'storage_policy':{'enabled':True,'hot_days':30}})
    result=automatic_maintenance(s);assert result['model_calls']==0
    assert automatic_maintenance(s) is None
    s.settings({'storage_policy':{'enabled':True,'hot_days':1}})
    # A completed day remains a no-op even if the config is later narrowed.
    assert automatic_maintenance(s) is None


def test_reader_survives_raw_removal_during_compression(tmp_path,monkeypatch):
    from pathlib import Path
    s=Store(tmp_path/'state');raw=b'lossless-evidence'*500;h=s.artifact(raw)
    path=s.root/'artifacts'/h
    original=Path.read_bytes
    moved=[]
    def racing_read(selected):
        if selected==path and not moved:
            moved.append(True)
            selected.with_suffix('.gz').write_bytes(gzip.compress(raw,mtime=0))
            selected.unlink()
        return original(selected)
    monkeypatch.setattr(Path,'read_bytes',racing_read)
    assert s.read_artifact(h)==raw
    assert moved==[True]
