import copy
import json
import os
import sqlite3
import subprocess
import sys

import pytest

from skill_observatory.proactive import plan, plan_selected, finish
from skill_observatory.store import Store, canonical

STAMP = 1792370000


def setup(tmp_path, diagnostics=True):
    scope = tmp_path / 'project'; scope.mkdir()
    store = Store(tmp_path / 'state')
    store.settings({'scopes': [str(scope)], 'diagnostic_scopes': [str(scope)] if diagnostics else []})
    index = tmp_path / 'index.sqlite'
    with sqlite3.connect(index) as db:
        db.execute('CREATE TABLE threads(id TEXT PRIMARY KEY,rollout_path TEXT,cwd TEXT,updated_at INTEGER)')
    return store, scope, index


def source(scope, index, sid, *, version='0.163.0-alpha.10.2', updated=STAMP-1):
    p = scope / (sid + '.jsonl')
    p.write_text(json.dumps({'type': 'session_meta', 'payload': {
        'id': sid, 'session_id': sid, 'cwd': str(scope), 'cli_version': version,
        'originator': 'Codex Desktop', 'source': 'vscode'}}) + '\n')
    with sqlite3.connect(index) as db:
        db.execute('INSERT INTO threads VALUES(?,?,?,?)', (sid, str(p), str(scope), updated))
    return p


def receipt(s, b, disposition='no_change'):
    return {'schema_version': 1, 'root_session_id': 'review-root', 'results': [{
        'id': i['id'], 'fingerprint': i['fingerprint'], 'disposition': disposition,
        'evidence_sha256': s.artifact(b'Bounded synthetic root observation; no domain acceptance.'),
        'next_check_at': STAMP+3600} for i in b['items']]}


def test_selected_session_preserves_daily_pending_and_scan_cursor(tmp_path):
    s, scope, index = setup(tmp_path)
    source(scope, index, 'daily'); source(scope, index, 'manual', updated=STAMP-10)
    daily = plan(s, index, limit=1, stamp=STAMP)
    cursor = copy.deepcopy(s.get('proactive_review_state', 'scan'))
    before = index.read_bytes()
    selected = plan_selected(s, index, 'manual', stamp=STAMP)
    assert [i['session_id'] for i in selected['items']] == ['manual']
    assert selected['coverage'] == 'selected_authorized_session_only'
    assert s.get('proactive_review_batches', 'active') == daily
    assert s.get('proactive_review_state', 'scan') == cursor
    assert index.read_bytes() == before
    result = finish(s, selected['batch_id'], receipt(s, selected), stamp=STAMP)
    assert result['status'] == 'completed'
    assert s.get('proactive_review_batches', 'active') == daily
    assert not s.list('review_attempts') and not s.list('installations')


def test_selection_of_daily_pending_item_shares_its_receipt_without_discarding_others(tmp_path):
    s, scope, index = setup(tmp_path); source(scope, index, 'same')
    daily = plan(s, index, stamp=STAMP)
    selected = plan_selected(s, index, 'same', stamp=STAMP)
    assert selected['mode'] == 'selected_from_daily' and len(selected['items']) == 1
    assert selected['batch_id'] == daily['batch_id']
    result = finish(s, selected['batch_id'], receipt(s, selected), stamp=STAMP)
    assert result['status'] == 'pending' and result['remaining'] == 1
    assert s.get('proactive_review_batches', 'active')['items'] == daily['items']


@pytest.mark.parametrize('outside', [False, True])
def test_both_scopes_checked_before_any_transcript_open(tmp_path, monkeypatch, outside):
    s, scope, index = setup(tmp_path, diagnostics=False)
    source(scope, index, 'selected')
    if outside:
        s.settings({'scopes': [], 'diagnostic_scopes': [str(scope)]})
    monkeypatch.setattr('skill_observatory.proactive._source', lambda *a: pytest.fail('Unauthorized transcript read'))
    with pytest.raises(ValueError, match='OUTSIDE_SCOPE' if outside else 'DIAGNOSTIC_SCOPE_REQUIRED'):
        plan_selected(s, index, 'selected', stamp=STAMP)
    assert not s.list('proactive_review_batches')


def test_exact_selection_does_not_open_other_indexed_sources(tmp_path, monkeypatch):
    s, scope, index = setup(tmp_path); source(scope, index, 'selected')
    other = tmp_path / 'elsewhere'; other.mkdir(); source(other, index, 'unrelated')
    from skill_observatory import proactive
    original = proactive._source; read = []
    def selected_only(row, *args):
        read.append(row['id']); return original(row, *args)
    monkeypatch.setattr(proactive, '_source', selected_only)
    plan_selected(s, index, 'selected', stamp=STAMP)
    assert read == ['selected']


@pytest.mark.parametrize('missing', [False, True])
def test_unknown_or_missing_source_is_a_visible_gap(tmp_path, missing):
    s, scope, index = setup(tmp_path)
    p = source(scope, index, 'selected', version='99.0')
    if missing: p.unlink()
    b = plan_selected(s, index, 'selected', stamp=STAMP)
    reason = b['items'][0]['signal']['reason_code']
    assert reason == ('TRANSCRIPT_NOT_REGULAR' if missing else 'TRANSCRIPT_VERSION_UNVERIFIED')
    finish(s, b['batch_id'], receipt(s, b, 'hold'), stamp=STAMP)
    assert s.get('proactive_review_items', b['items'][0]['id'])['disposition'] == 'hold'


def test_pending_finish_and_historical_redelivery_are_idempotent(tmp_path):
    s, scope, index = setup(tmp_path); source(scope, index, 'selected')
    b = plan_selected(s, index, 'selected', stamp=STAMP)
    assert plan_selected(s, index, 'selected', stamp=STAMP)['resumed']
    r = receipt(s, b); done = finish(s, b['batch_id'], r, stamp=STAMP)
    assert finish(s, b['batch_id'], r, stamp=STAMP) == done
    newer = plan_selected(s, index, 'selected', stamp=STAMP+1)
    assert newer['batch_id'] != b['batch_id']
    assert finish(s, b['batch_id'], r, stamp=STAMP) == done
    assert s.get('proactive_review_batches', newer['id'])['status'] == 'pending'


def test_source_drift_becomes_followup_and_revoked_diagnostics_refuse_finish(tmp_path):
    s, scope, index = setup(tmp_path); p = source(scope, index, 'selected')
    b = plan_selected(s, index, 'selected', stamp=STAMP); r = receipt(s, b, 'repaired')
    s.settings({'diagnostic_scopes': []})
    with pytest.raises(ValueError, match='DIAGNOSTIC_SCOPE_REQUIRED'):
        finish(s, b['batch_id'], r, stamp=STAMP)
    s.settings({'diagnostic_scopes': [str(scope)]})
    with p.open('a') as f: f.write('{}\n')
    result = finish(s, b['batch_id'], r, stamp=STAMP)
    assert result['source_changes'] == 1
    assert s.get('proactive_review_items', b['items'][0]['id'])['disposition'] == 'follow_up'


def test_concurrent_new_review_refuses_old_manual_and_replan_uses_new_basis(tmp_path):
    s, scope, index = setup(tmp_path); source(scope, index, 'selected')
    b = plan_selected(s, index, 'selected', stamp=STAMP); r = receipt(s, b)
    newer = {**b['items'][0], 'disposition': 'follow_up', 'evidence_sha256': s.artifact(b'Newer root evidence')}
    s.put('proactive_review_items', newer)
    with pytest.raises(ValueError, match='REVIEW_CAS_MISMATCH'):
        finish(s, b['batch_id'], r, stamp=STAMP)
    assert s.get('proactive_review_items', newer['id']) == newer
    rebased = plan_selected(s, index, 'selected', stamp=STAMP+1)
    assert rebased['batch_id'] != b['batch_id']
    assert finish(s, rebased['batch_id'], receipt(s, rebased), stamp=STAMP)['status'] == 'completed'


def test_real_cli_default_session_help_and_missing_selection(tmp_path):
    s, scope, index = setup(tmp_path); source(scope, index, 'selected')
    command = [sys.executable, '-m', 'skill_observatory.cli', '--state', str(s.root), 'retro-plan', '--index-db', str(index)]
    env = {**os.environ, 'CODEX_THREAD_ID': 'selected'}
    r = subprocess.run(command, env=env, capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)['items'][0]['session_id'] == 'selected'
    env.pop('CODEX_THREAD_ID')
    r = subprocess.run(command, env=env, capture_output=True, text=True)
    assert r.returncode == 1 and not r.stdout
    assert json.loads(r.stderr)['reason_code'] == 'RETRO_SESSION_REQUIRED'
    r = subprocess.run(command + ['--help'], env=env, capture_output=True, text=True)
    assert r.returncode == 0 and '--session-id' in r.stdout


def test_missing_session_and_invalid_index_do_not_create_work(tmp_path):
    s, scope, index = setup(tmp_path)
    with pytest.raises(ValueError, match='SESSION_NOT_FOUND'):
        plan_selected(s, index, 'absent', stamp=STAMP)
    for sid in (None, '', '../other'):
        with pytest.raises(ValueError, match='SESSION_REQUIRED'):
            plan_selected(s, index, sid, stamp=STAMP)
    assert not s.list('proactive_review_batches')


def test_daily_planning_keeps_pending_selected_session_with_its_owner(tmp_path):
    s, scope, index = setup(tmp_path); source(scope, index, 'selected')
    selected = plan_selected(s, index, 'selected', stamp=STAMP)
    daily = plan(s, index, stamp=STAMP)
    assert all(i.get('session_id') != 'selected' for i in daily['items'])
    assert daily['selected_pending_skipped'] == 1
    assert s.get('proactive_review_batches', selected['id'])['status'] == 'pending'


@pytest.mark.parametrize('drift_before_daily', [False, True])
def test_legacy_duplicate_daily_can_acknowledge_newer_followup_without_overwrite(tmp_path, drift_before_daily):
    s, scope, index = setup(tmp_path); p = source(scope, index, 'selected')
    selected = plan_selected(s, index, 'selected', stamp=STAMP)
    if drift_before_daily:
        with p.open('a') as f: f.write('{}\n')
    # Reconstruct a pending duplicate created by the previous planner version.
    s.put('proactive_review_batches', {**selected, 'status': 'completed'})
    daily = plan(s, index, stamp=STAMP)
    s.put('proactive_review_batches', selected)
    if not drift_before_daily:
        with p.open('a') as f: f.write('{}\n')
    assert finish(s, selected['batch_id'], receipt(s, selected, 'follow_up'), stamp=STAMP)['source_changes'] == 1
    latest = s.get('proactive_review_items', selected['items'][0]['id'])
    with pytest.raises(ValueError, match='REVIEW_CAS_MISMATCH'):
        finish(s, daily['batch_id'], receipt(s, daily), stamp=STAMP)
    acknowledged = receipt(s, daily)
    for result in acknowledged['results']:
        if result['id'] == latest['id']:
            result.update(disposition=latest['disposition'], evidence_sha256=latest['evidence_sha256'])
    result = finish(s, daily['batch_id'], acknowledged, stamp=STAMP)
    assert result['status'] == 'completed' and result['source_changes'] == 1
    assert s.get('proactive_review_items', latest['id']) == latest
    batch = s.get('proactive_review_batches', 'active')
    pointer = batch['superseded_reviews'][latest['id']]['review_sha256']
    assert json.loads(s.read_artifact(pointer)) == latest
    assert finish(s, daily['batch_id'], acknowledged, stamp=STAMP) == result


def test_newer_review_acknowledgement_cannot_cross_source_scope(tmp_path):
    s, scope, index = setup(tmp_path); source(scope, index, 'selected')
    batch = plan_selected(s, index, 'selected', stamp=STAMP)
    r = receipt(s, batch, 'follow_up')
    old = {**batch['items'][0], 'cwd': str(tmp_path / 'outside'),
           'evidence_sha256': r['results'][0]['evidence_sha256'], 'disposition': 'follow_up'}
    s.put('proactive_review_items', old)
    with pytest.raises(ValueError, match='REVIEW_CAS_MISMATCH'):
        finish(s, batch['batch_id'], r, stamp=STAMP)
    assert s.get('proactive_review_items', old['id']) == old
