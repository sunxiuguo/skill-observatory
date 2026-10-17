import json
import sqlite3

import pytest

from skill_observatory.proactive import plan, finish, follow_up
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


def followup_case(tmp_path):
    s, scope, index = setup(tmp_path)
    for i in range(12): chat(scope, index, str(i))
    batch = plan(s, index, stamp=STAMP)
    finish(s, batch['batch_id'], receipt(s, batch, ids=['self']), stamp=STAMP)
    item = s.get('proactive_review_items', 'self')
    value = {'schema_version': 1, 'root_session_id': 'later-native-root',
             'fingerprint': item['fingerprint'], 'previous_evidence_sha256': item['evidence_sha256'],
             'evidence_sha256': s.artifact(b'Later owner rollout; outcome evidence remains pending.'),
             'next_check_at': STAMP + 100}
    return s, index, batch, item, value


def test_followup_preserves_finished_self_pending_items_and_next_cycle(tmp_path):
    s, index, batch, original, value = followup_case(tmp_path)
    before = s.get('proactive_review_batches', 'active')
    result = follow_up(s, batch['batch_id'], value, stamp=STAMP+1)
    after = s.get('proactive_review_batches', 'active')
    assert after['items'] == before['items'] and after['results'] == before['results']
    assert len(after['items']) - len(after['results']) == 12 and after['status'] == 'pending'
    row = s.get('proactive_review_items', 'self')
    assert all(row[k] == original[k] for k in original if k != 'eligible_at')
    assert row['followups'][0]['evidence_sha256'] == value['evidence_sha256']
    assert row['eligible_at'] == value['next_check_at']
    resumed = plan(Store(s.root), index, stamp=STAMP+2)
    assert resumed['followups'][0]['id'] == result['followup_id']
    finish(s, batch['batch_id'], receipt(s, batch, ids=[i['id'] for i in batch['items'] if i['id'] != 'self']), stamp=STAMP+2)
    new = plan(s, index, stamp=STAMP+101)
    system = next(i for i in new['items'] if i['id'] == 'self')
    assert system['previous_review']['followups'] == row['followups']
    finish(s, new['batch_id'], receipt(s, new, stamp=STAMP+101, ids=['self']), stamp=STAMP+101)
    assert s.get('proactive_review_items', 'self')['followups'] == row['followups']
    current = s.get('proactive_review_items', 'self')
    assert follow_up(s, batch['batch_id'], value, stamp=STAMP+102)['idempotent']
    assert s.get('proactive_review_items', 'self') == current


@pytest.mark.parametrize('field,value,reason', [
    ('fingerprint', '0'*64, 'PROACTIVE_SOURCE_MISMATCH'),
    ('previous_evidence_sha256', '0'*64, 'PROACTIVE_FOLLOWUP_CAS_MISMATCH'),
    ('evidence_sha256', '0'*64, 'ARTIFACT_CORRUPT'),
    ('next_check_at', STAMP, 'PROACTIVE_FOLLOW_UP_REQUIRED'),
    ('next_check_at', STAMP+31*86400, 'PROACTIVE_FOLLOW_UP_REQUIRED'),
    ('next_check_at', float('nan'), 'PROACTIVE_FOLLOWUP_INVALID'),
    ('next_check_at', True, 'PROACTIVE_FOLLOWUP_INVALID'),
    ('root_session_id', '', 'PROACTIVE_FOLLOWUP_INVALID'),
    ('item_id', 'chat_unsupported', 'PROACTIVE_FOLLOWUP_INVALID'),
])
def test_followup_refusals_are_atomic(tmp_path, field, value, reason):
    s, index, batch, item, valid = followup_case(tmp_path)
    before = s.get('proactive_review_batches', 'active')
    with pytest.raises(ValueError, match=reason):
        follow_up(s, batch['batch_id'], {**valid, field: value}, stamp=STAMP+1)
    assert s.get('proactive_review_batches', 'active') == before
    assert s.get('proactive_review_items', 'self') == item
    assert not s.list('proactive_review_followups')


def test_followup_batch_conflict_and_duplicate(tmp_path):
    s, index, batch, item, value = followup_case(tmp_path)
    with pytest.raises(ValueError, match='PROACTIVE_FOLLOWUP_BATCH_MISMATCH'):
        follow_up(s, 'stale-batch', value, stamp=STAMP+1)
    follow_up(s, batch['batch_id'], value, stamp=STAMP+1)
    before = s.get('proactive_review_batches', 'active')
    assert follow_up(s, batch['batch_id'], value, stamp=STAMP+2)['idempotent']
    assert s.get('proactive_review_batches', 'active') == before
    assert len(s.list('proactive_review_followups')) == 1
    with pytest.raises(ValueError, match='PROACTIVE_FOLLOWUP_CONFLICT'):
        follow_up(s, batch['batch_id'], {**value, 'next_check_at': STAMP+200}, stamp=STAMP+2)
    assert s.get('proactive_review_batches', 'active') == before


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


def test_fresh_history_and_due_share_budget_without_losing_sweep(tmp_path):
    s, scope, index = setup(tmp_path)
    chat(scope, index, 'due', STAMP-1000)
    first = plan(s, index, stamp=STAMP)
    finish(s, first['batch_id'], receipt(s, first), stamp=STAMP)
    for i in range(20): chat(scope, index, f'old{i:02}', STAMP-800+i)
    chat(scope, index, 'latest', STAMP+86400)
    seen = set()
    b = plan(s, index, limit=4, stamp=STAMP+86401)
    ids = {x.get('session_id') for x in b['items']}
    assert {'latest', 'due', 'old00'} <= ids
    for i in range(9):
        if b['status'] == 'no_change':
            break
        seen.update(x.get('session_id') for x in b['items'])
        finish(s, b['batch_id'], receipt(s, b, stamp=STAMP+86401+i), stamp=STAMP+86401+i)
        b = plan(s, index, limit=4, stamp=STAMP+86402+i)
    assert all(f'old{i:02}' in seen for i in range(20))


def test_single_item_rotation_does_not_starve_history(tmp_path):
    s, scope, index = setup(tmp_path)
    for i in range(6): chat(scope, index, f'old{i}', STAMP-100+i)
    seen = set()
    for i in range(10):
        chat(scope, index, f'new{i}', STAMP+i)
        b = plan(s, index, limit=1, stamp=STAMP+i)
        seen.update(x.get('session_id') for x in b['items'])
        finish(s, b['batch_id'], receipt(s, b, stamp=STAMP+i), stamp=STAMP+i)
    assert 'new0' in seen and 'old0' in seen


@pytest.mark.parametrize('fault', [None, 'identity', 'cwd', 'version', 'symlink', 'parent_symlink'])
def test_archive_exact_fallback_keeps_original_identity_gates(tmp_path, fault):
    s, scope, index = setup(tmp_path); p = chat(scope, index, 'archived')
    archive = index.parent/'archived_sessions'; archive.mkdir()
    target = archive/p.name; p.rename(target)
    if fault in {'identity','cwd','version'}:
        value=json.loads(target.read_text());m=value['payload']
        m[{'identity':'id','cwd':'cwd','version':'cli_version'}[fault]] = {
            'identity':'wrong','cwd':str(tmp_path/'outside'),'version':'99.0'}[fault]
        target.write_text(json.dumps(value)+'\n')
    if fault=='symlink':
        other=scope/'other'; target.rename(other);target.symlink_to(other)
    if fault=='parent_symlink':
        other=scope/'archive';archive.rename(other);archive.symlink_to(other, target_is_directory=True)
    item=next(x for x in plan(s,index,stamp=STAMP)['items'] if x['kind']=='chat')
    if fault is None:
        assert item['signal']['path']==str(target) and 'reason_code' not in item['signal']
    else:
        assert item['signal']['reason_code']


def test_missing_index_due_reference_stays_visible(tmp_path):
    s, scope, index = setup(tmp_path); chat(scope,index,'lost')
    b=plan(s,index,stamp=STAMP);finish(s,b['batch_id'],receipt(s,b),stamp=STAMP)
    with sqlite3.connect(index) as db:db.execute('DELETE FROM threads')
    b=plan(s,index,stamp=STAMP+86401)
    item=next(x for x in b['items'] if x['kind']=='chat')
    assert item['session_id']=='lost' and item['signal']['reason_code']=='CODEX_INDEX_REFERENCE_MISSING'
