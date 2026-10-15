import json
import sqlite3

import pytest

from skill_observatory.proactive import plan, finish
from skill_observatory.store import Store, canonical
from skill_observatory.transcripts import observe_session


STAMP = 1792055000


def setup(tmp_path):
    store = Store(tmp_path / 'private')
    scope = tmp_path / 'allowed'; scope.mkdir()
    store.settings({'scopes': [str(scope)]})
    index = tmp_path / 'index.sqlite'
    with sqlite3.connect(index) as db:
        db.execute('CREATE TABLE threads(id TEXT PRIMARY KEY,rollout_path TEXT,cwd TEXT,updated_at INTEGER)')
    return store, scope, index


def chat(scope, index, sid, updated=STAMP-100, version='0.162.0-alpha.17.2', origin='Codex Desktop', child=False):
    path = scope / (sid + '.jsonl')
    meta = {'id': sid, 'session_id': 'parent' if child else sid, 'cwd': str(scope),
            'cli_version': version, 'originator': origin,
            'source': 'exec' if origin == 'codex_exec' else 'vscode'}
    if child:
        meta.update(thread_source='subagent', source={'subagent': {'thread_spawn': {'parent_thread_id': 'parent'}}})
    path.write_text(json.dumps({'type': 'session_meta', 'payload': meta}) + '\n')
    with sqlite3.connect(index) as db:
        db.execute('INSERT INTO threads VALUES(?,?,?,?)', (sid, str(path), str(scope), updated))
    return path


def receipt(store, batch, stamp=STAMP, disposition='no_change', ids=None):
    h = store.artifact(b'Root evidence; this synthetic test proves worklist behavior only.')
    return {'schema_version': 1, 'root_session_id': 'native-root', 'results': [
        {'id': i['id'], 'fingerprint': i['fingerprint'], 'disposition': disposition,
         'evidence_sha256': h, 'next_check_at': stamp + 86400}
        for i in batch['items'] if ids is None or i['id'] in ids]}


def test_pending_survives_restart_and_partial_receipt_never_discards_work(tmp_path):
    s, scope, index = setup(tmp_path); chat(scope, index, 'one'); chat(scope, index, 'two')
    batch = plan(s, index, stamp=STAMP)
    partial = receipt(s, batch, ids=['self'])
    assert finish(s, batch['batch_id'], partial, stamp=STAMP)['remaining'] == 2
    resumed = plan(Store(s.root), index, stamp=STAMP+1)
    assert resumed['resumed'] and resumed['batch_id'] == batch['batch_id']
    assert list(resumed['results']) == ['self']
    final = receipt(s, batch, ids=[i['id'] for i in batch['items'] if i['id'] != 'self'])
    assert finish(s, batch['batch_id'], final, stamp=STAMP)['status'] == 'completed'
    assert plan(s, index, stamp=STAMP+2)['status'] == 'no_change'


def test_index_is_readonly_and_outside_transcript_is_never_opened(tmp_path):
    s, scope, index = setup(tmp_path); chat(scope, index, 'allowed')
    with sqlite3.connect(index) as db:
        db.execute('INSERT INTO threads VALUES(?,?,?,?)', ('outside', '/unreadable/private.jsonl', str(tmp_path/'other'), STAMP))
    before = index.read_bytes()
    batch = plan(s, index, stamp=STAMP)
    assert index.read_bytes() == before
    assert [i['session_id'] for i in batch['items'] if i['kind'] == 'chat'] == ['allowed']
    assert batch['global_denominator'] is None
    assert 'title' not in str(batch) and 'prompt' not in str(batch)


def test_changed_source_reopens_but_planning_does_not_enqueue_models(tmp_path):
    s, scope, index = setup(tmp_path); path = chat(scope, index, 'one')
    b = plan(s, index, stamp=STAMP); finish(s, b['batch_id'], receipt(s, b), stamp=STAMP)
    with path.open('a') as f:
        f.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 't'}}) + '\n')
    new = plan(s, index, stamp=STAMP+2)
    assert len(new['items']) == 1 and new['items'][0]['session_id'] == 'one'
    assert not s.jobs() and not s.list('review_attempts') and not s.list('installations')


def test_capped_discovery_advances_without_starving_unchanged_prefix(tmp_path):
    s, scope, index = setup(tmp_path)
    for i in range(5): chat(scope, index, str(i), STAMP-100+i)
    seen = set()
    for i in range(3):
        b = plan(s, index, limit=2, stamp=STAMP+i)
        seen.update(x['session_id'] for x in b['items'] if x['kind'] == 'chat')
        finish(s, b['batch_id'], receipt(s, b, stamp=STAMP+i), stamp=STAMP+i)
    assert seen == set('01234')


def test_due_followup_survives_discovery_window_and_repeated_hold_escalates(tmp_path):
    s, scope, index = setup(tmp_path); chat(scope, index, 'old')
    b = plan(s, index, stamp=STAMP)
    r = receipt(s, b, disposition='hold')
    for x in r['results']: x['next_check_at'] = STAMP + 8*86400
    finish(s, b['batch_id'], r, stamp=STAMP)
    for offset in [8*86400+1, 9*86400+2]:
        b = plan(s, index, stamp=STAMP+offset)
        assert any(x.get('session_id') == 'old' for x in b['items'])
        finish(s, b['batch_id'], receipt(s, b, stamp=STAMP+offset, disposition='hold'), stamp=STAMP+offset)
    assert all(x['escalate'] for x in s.list('proactive_review_items'))


def test_unknown_schema_visible_own_chat_excluded_and_self_included(tmp_path):
    s, scope, index = setup(tmp_path)
    chat(scope, index, 'own'); chat(scope, index, 'future', version='99.0')
    b = plan(s, index, exclude_session='own', stamp=STAMP)
    assert b['items'][0]['kind'] == 'self'
    assert len(b['items']) == 2
    assert b['items'][1]['signal']['reason_code'] == 'TRANSCRIPT_VERSION_UNVERIFIED'


def test_malformed_metadata_remains_visible_and_changes_reopen_without_index_update(tmp_path):
    s, scope, index = setup(tmp_path); p = chat(scope, index, 'bad')
    p.write_text('[]\n')
    b = plan(s, index, stamp=STAMP)
    assert b['items'][1]['signal']['reason_code'] == 'TRANSCRIPT_META_INVALID'
    finish(s, b['batch_id'], receipt(s, b, disposition='hold'), stamp=STAMP)
    p.write_text('{"payload": []}\n')
    changed = plan(s, index, stamp=STAMP+1)
    assert len(changed['items']) == 1 and changed['items'][0]['session_id'] == 'bad'


def test_own_descendants_excluded_and_index_type_drift_refused(tmp_path):
    s, scope, index = setup(tmp_path); chat(scope, index, 'worker', child=True)
    b = plan(s, index, exclude_session='parent', stamp=STAMP)
    assert len(b['items']) == 1 and b['internal_skipped'] == 1
    finish(s, b['batch_id'], receipt(s, b), stamp=STAMP)
    with sqlite3.connect(index) as db: db.execute("UPDATE threads SET updated_at='broken'")
    with pytest.raises(ValueError, match='INDEX_TIME_UNVERIFIED'): plan(s, index, stamp=STAMP+1)


def test_finish_source_drift_is_immediate_followup_never_current_repair(tmp_path):
    s, scope, index = setup(tmp_path); p = chat(scope, index, 'one')
    b = plan(s, index, stamp=STAMP)
    p.write_text(p.read_text() + '{"new":"failure"}\n')
    outcome = finish(s, b['batch_id'], receipt(s, b, disposition='repaired'), stamp=STAMP)
    assert outcome['source_changes'] == 1
    row = next(x for x in s.list('proactive_review_items') if x['kind'] == 'chat')
    assert row['disposition'] == 'follow_up' and row['source_changed']
    followup = plan(s, index, stamp=STAMP+2)
    assert any(i.get('session_id') == 'one' for i in followup['items'])


def test_self_signals_read_real_receipt_kind_and_explain_unstarted_candidate(tmp_path):
    from skill_observatory.proactive import audit
    s, scope, index = setup(tmp_path)
    s.put('task_receipts', {'id':'actual','status':'accepted'})
    s.put('reviews', {'id':'candidate','status':'reviewed','decision':'CANDIDATE','attribution':'unknown'})
    s.put('experiments', {'id':'held','state':'held','reason_code':'SIDE_EFFECT_READBACK_REQUIRED'})
    signals = audit(s, STAMP)
    assert signals['counts']['task_receipts'] == 1 and signals['pending_experiments'] == 0
    assert signals['held_experiments'][0]['count'] == 1
    assert signals['candidate_readiness'][0]['reason_code'] == 'VERIFIED_ATTRIBUTION_REQUIRED'


def test_conflict_or_absent_evidence_rolls_back_entire_finish(tmp_path):
    s, scope, index = setup(tmp_path); chat(scope, index, 'one')
    b = plan(s, index, stamp=STAMP); r = receipt(s, b)
    r['results'][-1]['fingerprint'] = 'wrong'
    with pytest.raises(ValueError, match='SOURCE_MISMATCH'): finish(s, b['batch_id'], r, stamp=STAMP)
    assert not s.list('proactive_review_items')
    r = receipt(s, b); r['results'][-1]['evidence_sha256'] = '0'*64
    with pytest.raises(ValueError, match='ARTIFACT_CORRUPT'): finish(s, b['batch_id'], r, stamp=STAMP)
    assert not s.list('proactive_review_items')
    r = receipt(s, b); finish(s, b['batch_id'], r, stamp=STAMP)
    assert finish(s, b['batch_id'], r, stamp=STAMP+1)['status'] == 'completed'
    r['results'][0]['disposition'] = 'repaired'
    with pytest.raises(ValueError, match='CONFLICT'): finish(s, b['batch_id'], r, stamp=STAMP)


def test_exact_cli_and_child_shapes_work_but_mislabeled_origin_stays_rejected(tmp_path):
    s, scope, index = setup(tmp_path)
    for sid, child in [('cli', False), ('worker', True)]:
        p = chat(scope, index, sid, origin='codex_exec', child=child)
        with p.open('a') as f: f.write(json.dumps({'type':'event_msg','payload':{'type':'task_complete','turn_id':'t'}})+'\n')
        source = 'codex-subagent' if child else 'codex-cli'
        assert observe_session(s, p, sid, source)['new_events'] == 1
        with pytest.raises(ValueError, match='SOURCE_SCHEMA_UNVERIFIED'):
            observe_session(s, p, sid, 'codex-desktop')
    b = plan(s, index, stamp=STAMP)
    assert all('reason_code' not in i['signal'] for i in b['items'] if i['kind'] == 'chat')
