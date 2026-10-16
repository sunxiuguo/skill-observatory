"""Coverage recovery is distinct from semantic success of an oversized record."""
import hashlib
import json
from pathlib import Path
import pytest
from skill_observatory.store import Store, digest
from skill_observatory.transcripts import observe_session, track_hook_session
from skill_observatory.runtime import collect, ingest


def record(kind, payload):return json.dumps({'type':kind,'payload':payload}).encode()+b'\n'


def setup(tmp_path):
    s=Store(tmp_path/'state');s.settings({'scopes':[str(tmp_path)]})
    p=tmp_path/'session.jsonl'
    p.write_bytes(record('session_meta',{'id':'s','cwd':str(tmp_path),'cli_version':'0.162.0-alpha.2'})+record('turn_context',{'turn_id':'t'}))
    return s,p


def drain(s,p):
    for _ in range(32):
        r=observe_session(s,p,'s','codex-desktop')
        if r['offset']==p.stat().st_size:return r
    pytest.fail('bounded scanning did not reach terminal')


def test_9mib_gap_reaches_terminal_and_restart_never_double_consumes(tmp_path):
    s,p=setup(tmp_path);observe_session(s,p,'s','codex-desktop')
    large=record('response_item',{'type':'function_call_output','call_id':'lost','output':'x'*(9*1024*1024)})
    with p.open('ab') as f:f.write(large+record('event_msg',{'type':'task_complete','turn_id':'t'}))
    first=observe_session(s,p,'s','codex-desktop')
    assert first['scan_offset']-first['offset']<=4*1024*1024 and first['offset']<p.stat().st_size
    s=Store(s.root);drain(s,p);ingest(s)
    gaps=s.list('transcript_gaps');assert len(gaps)==1
    assert gaps[0]['record_sha256']==hashlib.sha256(large).hexdigest()
    assert gaps[0]['semantic_status']=='incomplete' and gaps[0]['turn_id'] is None and gaps[0]['last_known_turn_id']=='t'
    assert len(s.list('runs'))==1 and not s.list('capability_invocations')
    drain(Store(s.root),p);ingest(s)
    assert len(s.list('runs'))==1 and len(s.list('transcript_gaps'))==1


def test_partial_eof_not_consumed_and_source_drift_rejected(tmp_path):
    s,p=setup(tmp_path);r=drain(s,p);end=r['offset']
    with p.open('ab') as f:f.write(b'{"type":"event_msg","payload":')
    r=observe_session(s,p,'s','codex-desktop');assert r['offset']==end and not s.list('transcript_gaps')
    with p.open('ab') as f:f.write(b'{"type":"task_complete","turn_id":"t"}}\n')
    drain(s,p);ingest(s);assert len(s.list('runs'))==1
    data=p.read_bytes();p.write_bytes(data.replace(b'"s"',b'"z"',1))
    with pytest.raises(ValueError,match='SESSION_ID_MISMATCH'):observe_session(s,p,'s','codex-desktop')


def test_collector_uses_same_exact_archive_owner_and_closed_tail(tmp_path):
    s,p=setup(tmp_path)
    index=tmp_path/'index';archived=index/'archived_sessions';archived.mkdir(parents=True)
    s.settings({'transcript_index_parent':str(index)})
    original=track_hook_session(s,{'session_id':'s','transcript_path':str(p),'event':'SessionEnd'})
    moved=archived/p.name;p.rename(moved)
    with moved.open('ab') as f:f.write(record('event_msg',{'type':'task_complete','turn_id':'t'}))
    collect(s);assert len(s.list('runs'))==1
    replacement=s.get('selected_sessions',s.get('selected_sessions',original['id'])['relocated_to'])
    assert replacement['closed'] and replacement['path']==str(moved.resolve())
    collect(Store(s.root));assert len(s.list('runs'))==1


def test_archive_wrong_cwd_and_symlink_are_refused(tmp_path):
    s,p=setup(tmp_path);index=tmp_path/'index';d=index/'archived_sessions';d.mkdir(parents=True)
    s.settings({'transcript_index_parent':str(index)})
    selected=track_hook_session(s,{'session_id':'s','transcript_path':str(p),'event':'SessionStart'})
    data=p.read_bytes();p.unlink();moved=d/p.name
    other=tmp_path/'other';other.mkdir()
    moved.write_bytes(data.replace(str(tmp_path).encode(),str(other).encode()))
    collect(s);assert s.get('adapter_errors',selected['id'])['reason_code']=='ARCHIVE_IDENTITY_DRIFT'
    assert not s.get('selected_sessions',selected['id']).get('relocated_to')
