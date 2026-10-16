"""Incremental Native review worklist. No model, evaluator or installer here.

Only pointers/fingerprints and bounded root receipts enter the existing ledger.
Planning does not claim review, successful delivery, or authority to change a Skill.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .health import snapshot, LANES
from .store import canonical, digest, now
from .transcripts import _identity, _inside_scope

VERSION = 'proactive-review-v1'
DISPOSITIONS = {'no_change', 'candidate', 'repaired', 'hold', 'follow_up'}


def _code_identity():
    root = Path(__file__).parent
    return digest(canonical({p.name: digest(p.read_bytes()) for p in sorted(root.glob('*.py'))}))


def audit(store, stamp):
    """Stable, bounded system signals, including absent forward progress."""
    since = datetime.fromtimestamp(stamp - 7 * 86400, timezone.utc).isoformat()
    with store.connect() as db:
        jobs = [dict(r) for r in db.execute(
            'SELECT status,substr(reason_code,1,160) AS reason_code,count(*) AS count '
            'FROM jobs GROUP BY status,reason_code ORDER BY count(*) DESC LIMIT 16')]
        adapters = [dict(r) for r in db.execute(
            "SELECT substr(json_extract(data,'$.reason_code'),1,160) AS reason_code,count(*) AS count "
            "FROM entities WHERE kind='adapter_errors' AND json_extract(data,'$.created_at')>=? "
            'GROUP BY 1 ORDER BY count(*) DESC LIMIT 16', (since,))]
        counts = dict(db.execute(
            "SELECT kind,count(*) FROM entities WHERE kind IN "
            "('runs','reviews','run_evidence','experiments','candidates','installations','task_receipts') GROUP BY kind"))
        pending = db.execute(
            "SELECT count(*) FROM entities WHERE kind='experiments' AND "
            "COALESCE(json_extract(data,'$.state'),'') NOT IN ('rejected','activated','held')").fetchone()[0]
        held = [dict(r) for r in db.execute("SELECT json_extract(data,'$.reason_code') AS reason_code,count(*) AS count "
            "FROM entities WHERE kind='experiments' AND json_extract(data,'$.state')='held' GROUP BY 1")]
        unstarted = db.execute("SELECT r.data FROM entities r WHERE r.kind='reviews' "
            "AND json_extract(r.data,'$.status')='reviewed' AND json_extract(r.data,'$.decision')='CANDIDATE' "
            "AND NOT EXISTS(SELECT 1 FROM entities e WHERE e.kind='experiments' "
            "AND json_extract(e.data,'$.review_id')=r.id) ORDER BY r.rowid LIMIT 17").fetchall()
        from .pipeline import EvolutionPipeline
        pipeline = EvolutionPipeline(store); readiness = []
        for row in unstarted[:16]:
            review = json.loads(row[0]); reasons = []
            ready = pipeline._eligible_review(db, review, diagnostics=reasons) is not None
            readiness.append({'review_id': review['id'], 'ready': ready, 'reason_code': reasons[0] if reasons else None})
        coverage = dict(db.execute("SELECT 'pre_attachment',count(*) FROM entities WHERE kind='selected_sessions' "
            "AND json_extract(data,'$.coverage_start')='native_hook_attachment'"))
        coverage['closed_with_tail'] = 0
        rows = db.execute("SELECT s.data,c.data FROM entities s LEFT JOIN entities c ON c.kind='cursors' "
            "AND c.id='cursor_'||substr(s.id,10) WHERE s.kind='selected_sessions' AND json_extract(s.data,'$.closed')=1 LIMIT 201").fetchall()
        for selected_raw, cursor_raw in rows[:200]:
            selected = json.loads(selected_raw); cursor = json.loads(cursor_raw) if cursor_raw else {}
            p = Path(selected['path'])
            try:
                if not p.is_symlink() and p.is_file() and p.stat().st_size > cursor.get('offset', 0):
                    coverage['closed_with_tail'] += 1
            except OSError:
                coverage['closed_tail_unreadable'] = coverage.get('closed_tail_unreadable', 0) + 1
        coverage['closed_tail_scan_more'] = len(rows) > 200
        method_bound = db.execute("SELECT count(*) FROM entities WHERE kind='candidates' "
            "AND json_extract(data,'$.proposer_method_version_id') IS NOT NULL").fetchone()[0]
    health = snapshot(store.root, now=stamp)
    settings = store.settings()
    return {'code_sha256': _code_identity(), 'counts': counts,
            'jobs': jobs, 'adapter_causes_7d': adapters, 'pending_experiments': pending,
            'held_experiments': held, 'candidate_readiness': readiness,
            'more_candidate_readiness': len(unstarted) > 16, 'collector_coverage_gaps': coverage,
            'evidence_build_actions': evidence_actions(store),
            'outcome_followups': outcome_followups(store,stamp),
            'method_bound_candidates': method_bound, 'method_gain': 'UNVERIFIED',
            'workers': [{'id': lane, 'healthy': w['healthy'],
                         'reason_code': w.get('reason_code')} for lane, w in zip(LANES, health['workers'])],
            'reviewer_status': (store.get('runtime', 'reviewer') or {}).get('status', 'absent'),
            'evolution_status': (store.get('runtime', 'evolution') or {}).get('status', 'absent'),
            'settings': {k: settings.get(k) for k in ('paused', 'automatic_review', 'auto_promote', 'scopes')},
            'checks': ['capture_identity_and_coverage', 'facts_to_review', 'review_to_candidate',
                       'independent_evaluation_and_cost', 'owner_apply_and_fresh_activation',
                       'natural_follow_up', 'method_lineage_and_recursion',
                       'scheduler_receipt_and_storage_growth'],
            'claim': 'signals_only_not_skill_or_method_gain'}


def _source(row, store, index_parent=None):
    """Read metadata only after scope filtering. Unrecognized shapes remain visible."""
    path = Path(row['rollout_path'])
    signal = {'path': str(path)}
    try:
        from .transcripts import archive_path
        resolved = archive_path(path, index_parent)
        if resolved != path:signal.update(path=str(resolved), indexed_path=row['rollout_path'])
        path = resolved
        if path.is_symlink() or not path.is_file():
            raise ValueError('TRANSCRIPT_NOT_REGULAR')
        stat = path.stat()
        signal.update(size=stat.st_size, mtime_ns=stat.st_mtime_ns, inode=stat.st_ino)
        with path.open('rb') as f:
            first = f.readline(65537)
        if len(first) > 65536:
            raise ValueError('TRANSCRIPT_META_TOO_LARGE')
        envelope = json.loads(first)
        if not isinstance(envelope, dict) or not isinstance(envelope.get('payload'), dict):
            raise ValueError('TRANSCRIPT_META_INVALID')
        meta = envelope['payload']
        signal['meta_sha256'] = digest(first)
        child = isinstance(meta.get('source'), dict) and 'subagent' in meta['source']
        source = 'codex-subagent' if child else ('codex-desktop' if meta.get('originator') == 'Codex Desktop' else 'codex-cli')
        identity = _identity(store, path, source, expected_session_id=row['id'])
        if identity['execution_session_id'] != row['id']:
            raise ValueError('TRANSCRIPT_INDEX_ID_MISMATCH')
        if str(identity['cwd']) != str(Path(row['cwd']).resolve()):
            raise ValueError('TRANSCRIPT_INDEX_CWD_MISMATCH')
        signal.update(source=source, adapter_version=identity['version'],
                      root_session_id=identity['root_session_id'], parent_session_id=identity['parent_session_id'])
    except (OSError, ValueError, KeyError, TypeError) as ex:
        # Do not put arbitrary exception text or transcript contents in a worklist.
        signal['reason_code'] = str(ex) if isinstance(ex, ValueError) \
            and str(ex).replace('_', '').isalnum() else type(ex).__name__
    return {'id': 'chat_' + digest(row['id'].encode())[:24], 'kind': 'chat',
            'session_id': row['id'], 'cwd': row['cwd'], 'updated_at': row['updated_at'],
            'evidence_class': 'child_execution' if signal.get('source') == 'codex-subagent' else 'unclassified_execution',
            'signal': signal, 'fingerprint': digest(canonical([VERSION, row['updated_at'], signal]))}


def plan(store, index_db, *, exclude_session=None, days=7, limit=12, stamp=None):
    """Resume an unfinished batch; otherwise discover bounded, changed in-scope chats.

    Review receipts never advance the source scan cursor. A source cursor makes
    capped discovery fair; per-chat fingerprints prevent already reviewed replay.
    """
    if not 1 <= days <= 30 or not 1 <= limit <= 50:
        raise ValueError('PROACTIVE_BUDGET_INVALID')
    stamp = time.time() if stamp is None else stamp
    index_db = Path(index_db)
    if index_db.is_symlink() or not index_db.is_file():
        raise ValueError('CODEX_INDEX_REQUIRED')
    store.put('source_configuration',{'id':'transcript_index','index_parent':str(index_db.resolve().parent),'index_path':str(index_db.resolve())})
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current = store.get('proactive_review_batches', 'active', db)
        if current and current['status'] == 'pending':
            return {**current, 'resumed': True}
        prior_scan = store.get('proactive_review_state', 'scan', db) or {}
        cutoff = int(stamp - days * 86400)
        key = prior_scan.get('after', [cutoff, ''])
        key = max(key, [cutoff, ''])
        scopes = store.settings()['scopes']
        where = []; args = []
        for scope in scopes:
            scope = str(Path(scope).resolve())
            escaped = scope.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            where.append("(cwd=? OR cwd LIKE ? ESCAPE '\\')")
            args.extend([scope, escaped.rstrip('/') + '/%'])
        sources = []; fresh_sources = []; due_sources = []; missing_due = []
        if where:
            # Never open the Codex index for writing. No titles/prompts selected.
            with closing(sqlite3.connect(index_db.resolve().as_uri() + '?mode=ro', uri=True)) as index:
                columns = {r[1]: r[2].upper() for r in index.execute('PRAGMA table_info(threads)')}
                if any(columns.get(k) != t for k, t in
                       {'id': 'TEXT', 'rollout_path': 'TEXT', 'cwd': 'TEXT', 'updated_at': 'INTEGER'}.items()):
                    raise ValueError('CODEX_INDEX_SCHEMA_UNVERIFIED')
                if index.execute("SELECT 1 FROM threads WHERE typeof(updated_at)!='integer' OR updated_at>32503680000 LIMIT 1").fetchone():
                    raise ValueError('CODEX_INDEX_TIME_UNVERIFIED')
                query = ('SELECT id,rollout_path,cwd,updated_at FROM threads WHERE (' + ' OR '.join(where)
                         + ') AND updated_at>=? AND (updated_at>? OR (updated_at=? AND id>?)) '
                         + 'AND id!=? ORDER BY updated_at,id LIMIT 201')
                index.row_factory = sqlite3.Row
                sources = [dict(r) for r in index.execute(query, [*args, cutoff, key[0], key[0], key[1], exclude_session or ''])]
                fresh_sources = [dict(r) for r in index.execute(
                    'SELECT id,rollout_path,cwd,updated_at FROM threads WHERE (' + ' OR '.join(where)
                    + ') AND updated_at>=? AND id!=? ORDER BY updated_at DESC,id DESC LIMIT 201',
                    [*args, cutoff, exclude_session or ''])]
                # Follow-up obligations outlive the discovery window. They must
                # not disappear merely because no one touched the old chat.
                due = db.execute("SELECT data FROM entities WHERE kind='proactive_review_items' "
                    "AND id!='self' AND json_extract(data,'$.eligible_at')<=? "
                    "ORDER BY json_extract(data,'$.eligible_at'),id LIMIT ?", (stamp, limit)).fetchall()
                for prior in due:
                    prior_item = json.loads(prior[0]); sid = prior_item['session_id']
                    row = index.execute('SELECT id,rollout_path,cwd,updated_at FROM threads WHERE id=?', (sid,)).fetchone()
                    if row and sid != exclude_session and _inside_scope(store, row['cwd']):
                        due_sources.append(dict(row))
                    elif not row and sid != exclude_session and _inside_scope(store, prior_item['cwd']):
                        signal = {**prior_item['signal'], 'reason_code': 'CODEX_INDEX_REFERENCE_MISSING'}
                        missing_due.append({**prior_item, 'signal': signal,
                            'fingerprint': digest(canonical([VERSION, prior_item['updated_at'], signal]))})
        overflow = len(sources) > 200 or len(fresh_sources) > 200
        candidates = []
        scanned = 0; skipped_scope = 0; skipped_internal = 0
        lanes = {'fresh': iter(fresh_sources[:200]), 'history': iter(sources[:200]),
                 'due': iter(missing_due + due_sources)}
        # Weighted rotation reserves fresh work without starving sweep/due work,
        # even for a one-item budget. Only history advances the history cursor.
        schedule = ['fresh', 'history', 'fresh', 'due']
        position = prior_scan.get('position', 0) % len(schedule)
        visited = set(); exhausted = set()
        due_ids = {row.get('session_id', row['id']) for row in missing_due + due_sources}
        while len(candidates) < limit and len(exhausted) < len(lanes):
            lane = schedule[position]
            if lane in exhausted:
                position = (position + 1) % len(schedule)
                continue
            row = next(lanes[lane], None)
            if row is None:
                exhausted.add(lane)
                position = (position + 1) % len(schedule)
                continue
            if lane == 'history':
                key = [row['updated_at'], row['id']]
            # Resolved scope is rechecked before opening any transcript.
            if not _inside_scope(store, row['cwd']):
                skipped_scope += 1
                continue
            sid = row.get('session_id', row['id'])
            if sid in visited or (lane != 'due' and sid in due_ids):
                continue
            visited.add(sid)
            item = row if row.get('kind') == 'chat' else _source(row, store, index_db.resolve().parent)
            scanned += 1
            if exclude_session and item['signal'].get('root_session_id') == exclude_session:
                skipped_internal += 1
                continue
            previous = store.get('proactive_review_items', item['id'], db) or {}
            if previous.get('fingerprint') != item['fingerprint'] or previous.get('eligible_at', float('inf')) <= stamp:
                if previous:
                    item['previous_review'] = {k: previous[k] for k in
                        ('disposition', 'evidence_sha256', 'consecutive_holds', 'escalate') if k in previous}
                candidates.append(item)
                position = (position + 1) % len(schedule)
        overflow = overflow or len(exhausted) < len(lanes)
        # Restart a bounded rolling sweep after exhaustion. Pending batches resume
        # before discovery, so crashes cannot skip unfinished work.
        store.put('proactive_review_state', {'id': 'scan', 'after': key if 'history' not in exhausted else [cutoff, ''],
                                           'position': position}, db)
        signals = audit(store, stamp)
        signals['index_scope_policy'] = 'lexical_prefilter_then_resolved_scope; aliases_outside_prefilter_uncovered'
        signals['discovery_scope_skipped'] = skipped_scope
        system = {'id': 'self', 'kind': 'self', 'signal': signals,
                  'fingerprint': digest(canonical([VERSION, signals]))}
        previous = store.get('proactive_review_items', 'self', db) or {}
        if previous.get('fingerprint') != system['fingerprint'] or previous.get('eligible_at', 0) <= stamp:
            if previous:
                system['previous_review'] = {k: previous[k] for k in
                    ('disposition', 'evidence_sha256', 'consecutive_holds', 'escalate') if k in previous}
            candidates.insert(0, system)
        if not candidates:
            return {'status': 'no_change', 'items': [], 'scanned': scanned, 'more_sources': overflow,
                    'scope_skipped': skipped_scope, 'internal_skipped': skipped_internal,
                    'coverage': 'authorized_index_window_only', 'global_denominator': None}
        manifest = {'schema_version': 1, 'method_version': VERSION, 'created_at': now(),
                    'window_start': cutoff, 'window_end': int(stamp), 'items': candidates,
                    'scanned': scanned, 'more_sources': overflow,
                    'scope_skipped': skipped_scope, 'internal_skipped': skipped_internal,
                    'coverage': 'authorized_index_window_only', 'global_denominator': None}
        h = store.artifact(canonical(manifest))
        batch = {'id': 'active', 'batch_id': 'pr_' + h[:24], 'manifest_sha256': h,
                 'status': 'pending', **manifest}
        store.put('proactive_review_batches', batch, db)
        return batch


def finish(store, batch_id, receipt, *, stamp=None):
    """Root accounting only; cannot install, accept domain truth or clear HOLDs.

    Incomplete items remain pending. Same-receipt redelivery is idempotent;
    conflicts and evidence not in this content-addressed store are refused.
    """
    stamp = time.time() if stamp is None else stamp
    if not isinstance(receipt, dict) or set(receipt) != {'schema_version', 'root_session_id', 'results'} \
            or receipt['schema_version'] != 1 or not isinstance(receipt['root_session_id'], str) \
            or not receipt['root_session_id'] or not isinstance(receipt['results'], list) \
            or not 1 <= len(receipt['results']) <= 51 or len(canonical(receipt)) > 24000:
        raise ValueError('PROACTIVE_RECEIPT_INVALID')
    receipt_sha = digest(canonical(receipt))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        batch = store.get('proactive_review_batches', 'active', db)
        if not batch or batch['batch_id'] != batch_id:
            raise ValueError('PROACTIVE_BATCH_MISMATCH')
        original = json.loads(store.read_artifact(batch['manifest_sha256']))
        by_id = {item['id']: item for item in original['items']}
        results = batch.get('results', {})
        source_changes = batch.get('source_changes', {})
        seen = set()
        for result in receipt['results']:
            if not isinstance(result, dict) or set(result) != {'id', 'fingerprint', 'disposition', 'evidence_sha256', 'next_check_at'} \
                    or result['id'] not in by_id or result['id'] in seen \
                    or result['disposition'] not in DISPOSITIONS:
                raise ValueError('PROACTIVE_RESULT_INVALID')
            seen.add(result['id']); item = by_id[result['id']]
            if item['fingerprint'] != result['fingerprint']:
                raise ValueError('PROACTIVE_SOURCE_MISMATCH')
            if result['id'] in results:
                if results[result['id']] != result:
                    raise ValueError('PROACTIVE_RESULT_CONFLICT')
                continue
            evidence = store.read_artifact(result['evidence_sha256'])
            if not evidence.strip():
                raise ValueError('PROACTIVE_EVIDENCE_REQUIRED')
            due = result['next_check_at']
            if type(due) not in {int, float} or not stamp < due <= stamp + 30 * 86400:
                raise ValueError('PROACTIVE_FOLLOW_UP_REQUIRED')
            changed = False
            if item['kind'] == 'chat':
                path = Path(item['signal']['path'])
                try:
                    stat = path.stat()
                    changed = path.is_symlink() or any(item['signal'].get(k) != v for k, v in
                        [('size', stat.st_size), ('mtime_ns', stat.st_mtime_ns), ('inode', stat.st_ino)])
                except OSError:
                    changed = 'size' in item['signal']
            elif item['signal']['code_sha256'] != _code_identity():
                changed = True
            if changed: source_changes[item['id']] = True
            old = store.get('proactive_review_items', item['id'], db) or {}
            holds = (old.get('consecutive_holds', 0) + 1) if result['disposition'] == 'hold' else 0
            store.put('proactive_review_items', {**item, 'disposition': 'follow_up' if changed else result['disposition'],
                'source_changed': changed,
                'evidence_sha256': result['evidence_sha256'], 'eligible_at': stamp + 1 if changed else due,
                'reviewed_at': now(), 'root_session_id': receipt['root_session_id'],
                'consecutive_holds': holds, 'escalate': holds >= 3}, db)
            results[result['id']] = result
        store.artifact(canonical(receipt))
        batch.update(results=results, source_changes=source_changes, last_receipt_sha256=receipt_sha,
                     status='completed' if len(results) == len(by_id) else 'pending')
        store.put('proactive_review_batches', batch, db)
        store.put('proactive_review_cycles', {'id': batch_id, 'status': batch['status'],
            'manifest_sha256': batch['manifest_sha256'], 'receipt_sha256': receipt_sha,
            'results_sha256': store.artifact(canonical(results)), 'reviewed': len(results),
            'remaining': len(by_id) - len(results), 'updated_at': now()}, db)
        return {'batch_id': batch_id, 'status': batch['status'], 'reviewed': len(results),
                'remaining': len(by_id) - len(results),
                'source_changes': len(source_changes),
                'claim': 'root_review_accounting_not_promotion_or_RSI_certification'}



def evidence_actions(store):
    with store.connect() as db:
        rows=db.execute("SELECT data FROM entities WHERE kind='evidence_builds' AND json_extract(data,'$.status')!='built' ORDER BY json_extract(data,'$.created_at') LIMIT 4").fetchall()
    return [{k:r[k] for k in ('id','run_id','source_fingerprint','status','missing','observed_version_ids')} for r in [json.loads(x[0]) for x in rows]]


def outcome_followups(store,stamp):
    cutoff=datetime.fromtimestamp(stamp,timezone.utc).isoformat()
    with store.connect() as db:
        rows=db.execute("SELECT data FROM entities WHERE kind='outcome_followups' AND json_extract(data,'$.status')='pending' AND json_extract(data,'$.due_at')<=? ORDER BY json_extract(data,'$.due_at') LIMIT 16",(cutoff,)).fetchall()
    return [json.loads(r[0]) for r in rows]
