"""Explicit incremental adapter, limited to a selected session in an authorized scope."""
from __future__ import annotations

import json
import hashlib
import os
import time
from pathlib import Path

from .runtime import spool
from .store import canonical, digest, now

DESKTOP_APP_ORIGINATOR = "Codex Desktop"
ALPHA_17 = "0.162.0-alpha.17.2"
ALPHA_10_APP = "0.163.0-alpha.10.2"
VERIFIED_APP_VERSIONS = {ALPHA_17, ALPHA_10_APP}
VERIFIED_EXEC_VERSIONS = {"0.162.1", "0.163.0"}
CHILD_TERMINAL_EVENTS = {"SubagentStart", "SubagentStop"}


def _regular_path(path):
    path = Path(path)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("TRANSCRIPT_NOT_REGULAR")
    path = path.resolve()
    if not path.is_file():
        raise ValueError("TRANSCRIPT_NOT_REGULAR")
    return path


def _inside_scope(store, cwd):
    cwd = Path(cwd).resolve()
    return any(
        cwd == Path(s).resolve() or Path(s).resolve() in cwd.parents
        for s in store.settings()["scopes"]
    )


def _read_meta(store, path, source):
    path = _regular_path(path)
    with path.open() as f:
        try:
            first_line = f.readline(65537)
            if len(first_line) > 65536:raise ValueError("TRANSCRIPT_META_TOO_LARGE")
            first = json.loads(first_line)
        except (ValueError, TypeError) as ex:
            raise ValueError("TRANSCRIPT_META_INVALID") from ex
    if first.get("type") != "session_meta" or not isinstance(first.get("payload"), dict):
        raise ValueError("TRANSCRIPT_META_INVALID")
    meta = first["payload"]
    cwd = meta.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        raise ValueError("TRANSCRIPT_META_INVALID")
    cwd = Path(cwd).resolve()
    if not _inside_scope(store, cwd):
        raise ValueError("OUTSIDE_SCOPE")

    version = str(meta.get("cli_version") or "")
    if version in {"0.160.0", "0.160.1", "0.162.0-alpha.2"}:
        # These verified shapes use id as the transcript/session identity.
        pass
    elif version in VERIFIED_EXEC_VERSIONS:
        # Verified standalone CLI exec shape. App/child shapes need their own proof.
        if source != 'codex-cli' or meta.get('originator') != 'codex_exec' or meta.get('source') != 'exec':
            raise ValueError('TRANSCRIPT_SOURCE_SCHEMA_UNVERIFIED')
        if not isinstance(meta.get('session_id'), str) or meta.get('session_id') != meta.get('id'):
            raise ValueError('TRANSCRIPT_SCHEMA_UNVERIFIED')
    elif version in VERIFIED_APP_VERSIONS:
        # The version string alone is not a contract. Current App transcripts
        # carry both the rollout/execution id and the logical parent session.
        desktop = meta.get('originator') == DESKTOP_APP_ORIGINATOR
        cli = meta.get('originator') == 'codex_exec'
        spawned = isinstance(meta.get('source'), dict) and 'subagent' in meta['source']
        # This newer artifact was observed in Desktop and its native children.
        # Its standalone CLI shape has not been verified by those observations.
        if version == ALPHA_10_APP and (not desktop or source == 'codex-cli'
                or (source == 'codex-desktop' and meta.get('source') != 'vscode')):
            raise ValueError('TRANSCRIPT_SOURCE_SCHEMA_UNVERIFIED')
        if (source == 'codex-cli' and not (cli and meta.get('source') == 'exec')) \
                or (source == 'codex-desktop' and not (desktop and not spawned)) \
                or (source == 'codex-subagent' and not (spawned and (desktop or cli))):
            raise ValueError('TRANSCRIPT_SOURCE_SCHEMA_UNVERIFIED')
        if (
            not (desktop or cli)
            or not isinstance(meta.get("session_id"), str)
            or not meta.get("session_id")
        ):
            raise ValueError("TRANSCRIPT_SCHEMA_UNVERIFIED")
    else:
        raise ValueError("TRANSCRIPT_VERSION_UNVERIFIED")

    execution = meta.get("id") or meta.get("session_id")
    logical = meta.get("session_id") or execution
    if not isinstance(execution, str) or not execution or not isinstance(logical, str) or not logical:
        raise ValueError("TRANSCRIPT_SCHEMA_UNVERIFIED")
    return path, meta, cwd, version, execution, logical


def _identity(
    store,
    path,
    source,
    expected_session_id=None,
    expected_agent_id=None,
    expected_root_session_id=None,
):
    if source not in {"codex-desktop", "codex-cli", "codex-subagent"}:
        raise ValueError("SOURCE_NOT_SUPPORTED")
    path, meta, cwd, version, execution, logical = _read_meta(store, path, source)
    agent = execution if source == "codex-subagent" else None
    spawn = meta.get('source', {}).get('subagent', {}).get('thread_spawn', {}) if isinstance(meta.get('source'), dict) else {}
    parent = spawn.get('parent_thread_id')
    if version in VERIFIED_APP_VERSIONS and source == 'codex-subagent':
        if not isinstance(parent,str) or not parent or meta.get('thread_source')!='subagent':
            raise ValueError('TRANSCRIPT_SOURCE_SCHEMA_UNVERIFIED')
    if expected_agent_id:
        if expected_agent_id!=execution:raise ValueError('SESSION_ID_MISMATCH')
        agent=execution
    if agent:
        if parent is None:
            parent=expected_root_session_id or (expected_session_id if expected_session_id!=execution else None)
        if expected_session_id not in {execution,logical,parent}:raise ValueError('SESSION_ID_MISMATCH')
        if expected_root_session_id and expected_root_session_id not in {logical,parent}:
            raise ValueError('SESSION_ID_MISMATCH')
    elif expected_session_id is not None and expected_session_id not in {execution,logical}:
        raise ValueError('SESSION_ID_MISMATCH')
    return {'path':path,'cwd':cwd,'version':version,'execution_session_id':execution,
        'session_id':execution if agent else logical,'parent_session_id':parent if agent else None,
        'root_session_id':logical,'agent_id':agent,'originator':meta.get('originator')}


def observe_session(store, path, expected_session_id, source):
    selected=store.get('selected_sessions','selected_'+digest(str(Path(path).resolve()).encode())[:24]) or {}
    identity = _identity(store, path, source, expected_session_id=expected_session_id,expected_root_session_id=selected.get('parent_session_id'))
    path = identity["path"]
    cwd = identity["cwd"]
    version=identity['version']
    cursor_id = "cursor_" + digest(str(path).encode())[:24]
    cursor = store.get("cursors", cursor_id) or {
        "offset": 0,
        "prefix_sha256": digest(b""),
    }
    offset = cursor["offset"]
    stat = path.stat()
    if (
        cursor.get("mtime_ns") == stat.st_mtime_ns
        and cursor.get("inode") == stat.st_ino
        and cursor.get("size") == stat.st_size and offset == stat.st_size
        and cursor.get("scan_offset", offset) >= offset
    ):
        return {
            "source": source,
            "session_id": identity["session_id"],
            "expected_session_id": expected_session_id,
            "execution_session_id": identity["execution_session_id"],
            "parent_session_id": identity["parent_session_id"],
            "agent_id": identity["agent_id"],
            "new_events": 0,
            "offset": offset,
            "coverage": "partial_versioned_adapter",
            "global_denominator": None,
        }

    lines, gaps, prefix_hash, scan_offset, source_view = _scan_records(store, path, cursor, stat)
    turn = cursor.get("turn_id")
    calls = json.loads(json.dumps(cursor.get("calls", {})))
    count = 0
    registered = store.list("skills")
    catalog = store.list("capability_catalog")
    line_offset = offset

    # A gap invalidates pending call attribution. Reaching a later terminal is
    # coverage recovery, never proof that the skipped result was read/successful.
    pending_gaps = list(gaps)
    for sequence, line in lines:
        while pending_gaps and pending_gaps[0]['byte_start'] < sequence:
            gap = pending_gaps.pop(0); gap['last_known_turn_id'] = turn; gap['turn_id']=None; calls = {}
        line_offset = sequence + len(line)
        o = json.loads(line)
        v = o.get("payload", {})
        record_type = o.get("type")
        if record_type == "turn_context":
            turn = v.get("turn_id", turn)
        base = {
            "session_id": identity["session_id"],
            "turn_id": turn,
            "cwd": str(cwd),
            "origin": "user_run",
            "source_sequence": sequence,
            "root_session_id": identity["root_session_id"],
        }
        if identity["parent_session_id"]:
            base["parent_session_id"] = identity["parent_session_id"]
        if identity["agent_id"]:
            base["agent_id"] = identity["agent_id"]
            base["execution_session_id"] = identity["execution_session_id"]
        if isinstance(o.get("timestamp"), str):
            base["occurred_at"] = o["timestamp"]
        event = None

        if record_type == "event_msg":
            event = {
                "task_started": "UserPromptSubmit",
                "task_complete": "Stop",
                "turn_aborted": "Interrupt",
                "task_interrupted": "Interrupt",
            }.get(v.get("type"))
            if v.get("turn_id"):
                base["turn_id"] = v["turn_id"]
                turn = v["turn_id"]
        elif record_type == "response_item" and v.get("type") in {"function_call", "custom_tool_call"}:
            event = "PreToolUse"
            base.update(tool_use_id=v.get("call_id"), tool_name=v.get("name"))
            raw = v.get("arguments", v.get("input", ""))
            calls[v.get("call_id")] = {
                'tool_name':v.get('name'),
                "skills": [s["id"] for s in registered if str(Path(s["path"]) / "SKILL.md") in raw],
                "caps": [
                    {
                        "capability_id": c["id"],
                        "version_id": c["version_id"],
                        "file_sha256": digest((Path(c["path"]) / "SKILL.md").read_bytes()),
                        "content_sha256": store.artifact((Path(c["path"]) / "SKILL.md").read_bytes()),
                    }
                    for c in catalog
                    if c["kind"] == "skill"
                    and str(Path(c["path"]) / "SKILL.md") in raw
                    and (Path(c["path"]) / "SKILL.md").is_file()
                ],
            }
            # spool persists only digest/path attribution, never raw input.
            base["tool_input"] = raw
        elif record_type == "response_item" and v.get("type") in {
            "function_call_output",
            "custom_tool_call_output",
        }:
            event = "PostToolUse"
            base.update(tool_use_id=v.get("call_id"))
            # Confirm exact whole Skill bytes present in a trusted native tool response.
            outputs = v.get("output", [])
            texts = []
            if isinstance(outputs, str):
                texts.append(outputs)
            elif isinstance(outputs, list):
                texts.extend(x.get("text", "") for x in outputs if isinstance(x, dict))
            expanded = list(texts)
            for t in texts:
                try:
                    j = json.loads(t)
                    if isinstance(j, dict) and isinstance(j.get("output"), str):
                        expanded.append(j["output"])
                except (ValueError, TypeError):
                    pass
            binding = calls.get(v.get("call_id"), {})
            if isinstance(binding,dict):base['tool_name']=binding.get('tool_name')
            from .evidence import diagnostic_from_output
            diagnostic=diagnostic_from_output(outputs)
            if diagnostic:base['diagnostic_fact']=diagnostic
            ids = binding.get("skills", []) if isinstance(binding, dict) else binding
            for c in binding.get("caps", []) if isinstance(binding, dict) else []:
                content = store.read_artifact(c["content_sha256"]).decode()
                version_record = store.get("capability_versions", c["version_id"])
                if version_record and version_record["manifest"]["files"].get("SKILL.md") == c["file_sha256"] and any(
                    content in t for t in expanded
                ):
                    base.setdefault("capability_observations", []).append(
                        {
                            "capability_id": c["capability_id"],
                            "version_id": c["version_id"],
                            "stage": "verified_read",
                        }
                    )
            for s in registered:
                if s["id"] in ids and isinstance(binding, dict):
                    cap_binding = next(
                        (
                            c
                            for c in binding.get("caps", [])
                            if (store.get("capability_catalog", c["capability_id"]) or {}).get("path") == s["path"]
                        ),
                        None,
                    )
                    if not isinstance(cap_binding, dict):
                        continue
                    version_record = store.get("capability_versions", cap_binding["version_id"])
                    if (
                        not version_record
                        or version_record.get("capability_id") != cap_binding["capability_id"]
                        or version_record["manifest"]["files"].get("SKILL.md") != cap_binding["file_sha256"]
                    ):
                        continue
                    content = store.read_artifact(cap_binding["content_sha256"]).decode()
                    if any(content in t for t in expanded):
                        base.setdefault("verified_attributions", []).append(
                            {
                                "skill_id": s["id"],
                                "package_sha256": version_record["package_sha256"],
                                "file_sha256": cap_binding["file_sha256"],
                                "attribution": "verified_read",
                                "capability_id": cap_binding["capability_id"],
                                "version_id": cap_binding["version_id"],
                                "loaded_version_source": "exact_whole_tool_output",
                                "observed_at": o.get("timestamp"),
                            }
                        )
            calls.pop(v.get("call_id"), None)

        if event:
            base["hook_event_name"] = event
            base["transcript_record_sha256"] = digest(line)
            # Same persistence path as lifecycle hooks; no second event store.
            r = spool(store, base, source=source)
            if r["status"] == "spooled":
                count += 1

    if pending_gaps:
        calls = {}
        for gap in pending_gaps:gap['last_known_turn_id'] = turn;gap['turn_id']=None
    end = max([offset, line_offset] + [g["byte_end"] for g in gaps])
    if len(calls)>256:raise ValueError('TRANSCRIPT_PENDING_CALL_LIMIT')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current = store.get('cursors', cursor_id, db)
        if current is not None and current != cursor:
            raise ValueError('TRANSCRIPT_CURSOR_CAS_DRIFT')
        for gap in gaps:
            gap.update(source=source, execution_session_id=identity['execution_session_id'],
                       path=str(path), created_at=now())
            store.put('transcript_gaps', gap, db)
        store.put(
        "cursors",
        {
            "id": cursor_id,
            "offset": end,
            "prefix_sha256": prefix_hash.hexdigest(),
            "turn_id": turn,
            "calls": calls,
            "scan_offset": scan_offset,
            "coverage_incomplete": bool(cursor.get("coverage_incomplete") or gaps),
            "cwd": str(cwd),
            "root_session_id": identity["root_session_id"],
            "created_at": now(),
            "source": source,
            "mtime_ns": source_view['mtime_ns'],
            "inode": source_view['inode'],
            "size": source_view['size'],
            "source_view":source_view,
            "execution_session_id": identity["execution_session_id"],
            "parent_session_id": identity["parent_session_id"],
            "agent_id": identity["agent_id"],
            "adapter_version": version,
        }, db,
        )
    return {
        "source": source,
        "session_id": identity["session_id"],
        "expected_session_id": expected_session_id,
        "execution_session_id": identity["execution_session_id"],
        "parent_session_id": identity["parent_session_id"],
        "agent_id": identity["agent_id"],
        "new_events": count,
        "offset": end,
        "scan_offset": scan_offset,
        "new_gaps": len(gaps),
        "coverage": "partial_versioned_adapter",
        "global_denominator": None,
    }


def track_hook_session(store, event):
    """Follow one trusted native hook pointer from NOW, never enumerate history."""
    sid = event.get("session_id")
    agent_id = event.get("agent_id")
    if not isinstance(sid, str) or not sid:
        raise ValueError("UPSTREAM_SESSION_IDENTITY_MISSING")
    if event.get("event") in CHILD_TERMINAL_EVENTS and (not isinstance(agent_id, str) or not agent_id):
        raise ValueError("UPSTREAM_CHILD_IDENTITY_MISSING")
    source = "codex-subagent" if agent_id else "codex-desktop"
    identity = _identity(
        store,
        event["transcript_path"],
        source,
        expected_session_id=sid,
        expected_agent_id=agent_id,
        expected_root_session_id=event.get("parent_session_id"),
    )
    path = identity["path"]
    selected_id = "selected_" + digest(str(path).encode())[:24]
    selected = store.get("selected_sessions", selected_id)
    if not selected:
        # Keep the exact attachment prefix without loading a long transcript
        # into memory. Incomplete trailing JSON remains for the adapter later.
        running = hashlib.sha256(); prefix = running.copy(); position = 0; offset = 0
        with path.open('rb') as f:
            while block := f.read(1024 * 1024):
                last = block.rfind(b'\n')
                if last >= 0:
                    prefix = running.copy(); prefix.update(block[:last + 1]); offset = position + last + 1
                running.update(block); position += len(block)
        stat = path.stat()
        store.put(
            "cursors",
            {
                "id": "cursor_" + digest(str(path).encode())[:24],
                "offset": offset,
                "prefix_sha256": prefix.hexdigest(),
                "turn_id": event.get("turn_id"),
                "calls": {},
                "created_at": now(),
                "mtime_ns": stat.st_mtime_ns,
                "inode": stat.st_ino,
                "size": stat.st_size,
                "coverage_start": "native_hook_attachment",
                "cwd": str(identity["cwd"]),
                "execution_session_id": identity["execution_session_id"],
                "parent_session_id": identity["parent_session_id"],
                "agent_id": identity["agent_id"],
                "adapter_version": identity["version"],
                "root_session_id": identity["root_session_id"],
            },
        )
        selected_session_id = identity["execution_session_id"]
        selected = {
            "id": selected_id,
            "path": str(path),
            "session_id": selected_session_id,
            "hook_session_id": sid,
            "execution_session_id": identity["execution_session_id"],
            "parent_session_id": identity["parent_session_id"],
            "agent_id": identity["agent_id"],
            "source": source,
            "created_at": now(),
            "coverage_start": "native_hook_attachment",
            "cwd": str(identity["cwd"]),
            "root_session_id": identity["root_session_id"],
            "adapter_version": identity["version"],
            "missing": ["BEFORE_ATTACHMENT_NOT_OBSERVED"],
        }
    else:
        selected.update(
            session_id=identity["execution_session_id"],
            hook_session_id=sid,
            execution_session_id=identity["execution_session_id"],
            parent_session_id=identity["parent_session_id"],
            agent_id=identity["agent_id"],
            source=source,
        )
    selected["closed"] = event.get("event") == "SessionEnd"
    store.put("selected_sessions", selected)
    return selected


def relocate_archived_transcript(store, new_path, *, old_path=None, execution_session_id=None, scan_budget=None):
    """Move one already-selected pointer; never locate or import history by scan."""
    new_path = _regular_path(new_path)
    if old_path is not None:
        old_path = Path(old_path).resolve()
        old_id = "selected_" + digest(str(old_path).encode())[:24]
        old = store.get("selected_sessions", old_id)
        if not old:
            raise ValueError("ARCHIVE_POINTER_NOT_FOUND")
    else:
        if not isinstance(execution_session_id, str) or not execution_session_id:
            raise ValueError("ARCHIVE_POINTER_REQUIRED")
        candidates = [
            s
            for s in store.list("selected_sessions")
            if not s.get("closed")
            and (
                s.get("execution_session_id") == execution_session_id
                or s.get("session_id") == execution_session_id
                or s.get("agent_id") == execution_session_id
            )
        ]
        if not candidates:
            raise ValueError("ARCHIVE_POINTER_NOT_FOUND")
        if len(candidates) > 1:
            raise ValueError("ARCHIVE_POINTER_AMBIGUOUS")
        old = candidates[0]
        old_path = Path(old["path"])

    new_id = "selected_" + digest(str(new_path).encode())[:24]
    old_id = old["id"]
    if new_id == old_id:
        raise ValueError("ARCHIVE_PATH_UNCHANGED")
    identity = _identity(
        store,
        new_path,
        old.get("source", "codex-desktop"),
        expected_session_id=old.get("session_id"),
        expected_agent_id=old.get("agent_id"),
    )
    for field, actual in (('cwd', str(identity['cwd'])), ('root_session_id', identity['root_session_id']),
                          ('parent_session_id', identity['parent_session_id']), ('adapter_version', identity['version'])):
        expected = old.get(field)
        if expected is not None and expected != actual:raise ValueError('ARCHIVE_IDENTITY_DRIFT')
    expected_execution = old.get("execution_session_id") or old.get("session_id")
    if identity["execution_session_id"] != expected_execution:
        raise ValueError("SESSION_ID_MISMATCH")

    existing_new = store.get("selected_sessions", new_id)
    if existing_new and existing_new.get("execution_session_id", existing_new.get("session_id")) != expected_execution:
        raise ValueError("ARCHIVE_POINTER_CONFLICT")

    old_cursor_id = "cursor_" + digest(str(old_path).encode())[:24]
    new_cursor_id = "cursor_" + digest(str(new_path).encode())[:24]
    old_cursor = store.get("cursors", old_cursor_id)
    stat = new_path.stat()
    if old_cursor:
        if scan_budget:
            checked=_archive_scan(store,new_path,old_cursor['offset'],scan_budget)
            if checked is None:return None
            size,prefix_hash=checked
        else:prefix_hash, size = _stream_prefix(new_path, old_cursor["offset"])
        if size != old_cursor["offset"] or prefix_hash != old_cursor["prefix_sha256"]:
            raise ValueError("TRANSCRIPT_DRIFT_HOLD")
        new_cursor = {
            **old_cursor,
            "id": new_cursor_id,
            "mtime_ns": None,
            "inode": stat.st_ino,
            "size": old_cursor["offset"],
            "execution_session_id": identity["execution_session_id"],
            "parent_session_id": identity["parent_session_id"],
            "agent_id": identity["agent_id"],
            "adapter_version": identity["version"],
                "root_session_id": identity["root_session_id"],
        }
    else:
        if scan_budget:
            checked=_archive_scan(store,new_path,None,scan_budget)
            if checked is None:return None
            offset,prefix_digest=checked
        else:offset, prefix_digest = _attachment_prefix(new_path)
        new_cursor = {
            "id": new_cursor_id,
            "offset": offset,
            "prefix_sha256": prefix_digest,
            "turn_id": None,
            "calls": {},
            "created_at": now(),
            "mtime_ns": stat.st_mtime_ns,
            "inode": stat.st_ino,
            "size": stat.st_size,
            "coverage_start": "archive_relocation_attachment",
            "execution_session_id": identity["execution_session_id"],
            "parent_session_id": identity["parent_session_id"],
            "agent_id": identity["agent_id"],
            "adapter_version": identity["version"],
                "root_session_id": identity["root_session_id"],
        }
    if old_cursor:
        for field, actual in (('cwd', str(identity['cwd'])), ('root_session_id', identity['root_session_id']),
                              ('parent_session_id', identity['parent_session_id']), ('adapter_version', identity['version'])):
            if old_cursor.get(field) is not None and old_cursor[field] != actual:raise ValueError('ARCHIVE_IDENTITY_DRIFT')
    original=dict(old)
    old.update(closed=True, relocated_to=new_id, updated_at=now())

    selected = {
        "id": new_id,
        "path": str(new_path),
        "session_id": old["session_id"],
        "execution_session_id": identity["execution_session_id"],
        "parent_session_id": identity["parent_session_id"] or old.get("parent_session_id"),
        "agent_id": identity["agent_id"],
        "source": old.get("source", "codex-desktop"),
        "created_at": old.get("created_at", now()),
        "updated_at": now(),
        "coverage_start": old.get("coverage_start", "archive_relocation_attachment"),
        "closed": old.get("closed", False),
        "cwd": str(identity["cwd"]),
        "root_session_id": identity["root_session_id"],
        "adapter_version": identity["version"],
        "missing": sorted(set(old.get("missing", []) + ["ARCHIVE_RELOCATION_FUTURE_ONLY"])),
        "relocated_from": old_id,
    }
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if store.get('selected_sessions',old_id,db)!=original or store.get('cursors',old_cursor_id,db)!=old_cursor:
            raise ValueError('ARCHIVE_POINTER_CAS_DRIFT')
        if store.get('selected_sessions',new_id,db):raise ValueError('ARCHIVE_POINTER_ALREADY_REGISTERED')
        store.put('cursors',new_cursor,db);store.put('selected_sessions',old,db);store.put('selected_sessions',selected,db)
    return selected


SCAN_BYTES = 4 * 1024 * 1024
MAX_RECORD_BYTES = 2 * 1024 * 1024


def _stream_prefix(path, limit):
    h = hashlib.sha256(); size = 0
    with Path(path).open('rb') as f:
        while size < limit:
            block = f.read(min(1024 * 1024, limit - size))
            if not block:break
            h.update(block); size += len(block)
    return h.hexdigest(), size


def _attachment_prefix(path):
    h = hashlib.sha256(); prefix = h.copy(); position = offset = 0
    with Path(path).open('rb') as f:
        while block := f.read(1024 * 1024):
            last = block.rfind(b'\n')
            if last >= 0:
                prefix = h.copy(); prefix.update(block[:last + 1]); offset = position + last + 1
            h.update(block); position += len(block)
    return offset, prefix.hexdigest()


def archive_path(path, index_parent=None):
    """Exactly one index-owned basename. No history search or scope widening."""
    path = Path(path)
    if path.exists() or path.is_symlink() or index_parent is None:return path
    candidate = Path(index_parent) / 'archived_sessions' / path.name
    if candidate.exists() or candidate.is_symlink():return _regular_path(candidate)
    return path


def resolve_selected(store, selected):
    if selected.get('relocated_to'):
        return store.get('selected_sessions', selected['relocated_to']) or selected
    config=store.get('source_configuration','transcript_index') or {}
    path = archive_path(selected['path'], store.settings().get('transcript_index_parent') or config.get('index_parent'))
    if path.resolve() != Path(selected['path']).resolve():
        result=relocate_archived_transcript(store, path, old_path=selected['path'],scan_budget=SCAN_BYTES)
        return result or {**selected,'relocation_pending':True}
    return selected


def _close_scan(state):
    if state:
        if state.get('view') is not None:state['view'].close()
        state['invalid']=True


def _snapshot_view(store,path,stat):
    """An unlinked private CoW view: one point-in-time input, no raw retention.

    clonefile/FICLONE do not copy/read the source proportional to its size.
    Hashing and JSON framing of the fixed view remain under the tick budget.
    Unsupported filesystems retain stable-file scanning; growing large sources
    explicitly HOLD instead of weakening prefix verification.
    """
    import tempfile,sys
    before=path.stat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns):
        raise ValueError('TRANSCRIPT_SOURCE_CHANGED')
    with tempfile.TemporaryDirectory(prefix='transcript-view-',dir=store.root) as directory:
        target=Path(directory)/'view'
        try:
            if sys.platform=='darwin':
                import ctypes
                libc=ctypes.CDLL(None,use_errno=True)
                if libc.clonefile(os.fsencode(path),os.fsencode(target),0)!=0:raise OSError(ctypes.get_errno(),'clonefile unavailable')
            elif sys.platform.startswith('linux'):
                import fcntl
                with path.open('rb') as source,target.open('xb') as dest:fcntl.ioctl(dest.fileno(),0x40049409,source.fileno())
            else:return None
            os.chmod(target,0o600)
            view=target.open('rb');target.unlink()
        except OSError:
            return None
        after=path.stat()
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
            view.close();raise ValueError('TRANSCRIPT_SOURCE_CHANGED')
        return view


def _scan_source(store,path,state,stat,*,limit=None):
    identity=(stat.st_dev,stat.st_ino,stat.st_mtime_ns,stat.st_size)
    if state and state.get('invalid'):state=None
    if state and state.get('view') is not None:
        original=state['identity']
        if identity[:2]!=original[:2] or stat.st_size<original[3]:
            _close_scan(state);raise ValueError('TRANSCRIPT_DRIFT_HOLD')
        if stat.st_size==original[3] and identity!=original:
            _close_scan(state);raise ValueError('TRANSCRIPT_SOURCE_CHANGED')
        return state
    if state and state['identity']!=identity:
        if stat.st_size>state['identity'][3] and ((limit or state.get('base_offset',0))>SCAN_BYTES or (state.get('position',0)>0 and state['view_size']>SCAN_BYTES)):
            raise ValueError('TRANSCRIPT_STABLE_SNAPSHOT_UNAVAILABLE')
        _close_scan(state);state=None
    if state is None:
        view=_snapshot_view(store,path,stat) if stat.st_size>SCAN_BYTES else None
        return {'identity':identity,'view':view,'view_size':stat.st_size,'captured_at':now()}
    return state


def _scan_records(store, path, cursor, stat):
    """Bounded framing/hash verification; gaps commit together with the cursor.

    hashlib state is only a disposable accelerator. A process restart rebuilds
    it in bounded ticks from durable semantic offset, never trusting scan_offset.
    """
    cache = getattr(store, '_transcript_scans', {})
    store._transcript_scans = cache
    if len(cache)>32:_close_scan(cache.pop(next(iter(cache))))
    identity = (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)
    offset = cursor['offset']
    state = cache.get(str(path))
    if state and (state['base_offset']!=offset or state['position']>=state['view_size']):
        _close_scan(state);state=None
    previous=state
    state=_scan_source(store,path,state,stat)
    if state is not previous:
        state.update(base_offset=offset,position=0,hash=hashlib.sha256(),verified=False,record_start=offset,record_hash=hashlib.sha256(),buffer=bytearray(),oversized=False)
    cache[str(path)]=state
    budget = SCAN_BYTES; deadline = time.monotonic() + .25
    lines = []; gaps = []; completed_hash = None; completed_end = offset
    from contextlib import nullcontext
    with nullcontext(state['view']) if state['view'] is not None else path.open('rb') as f:
        f.seek(state['position'])
        while not state['verified'] and state['position'] < offset and budget > 0:
            block = f.read(min(256 * 1024, budget, offset - state['position']))
            if not block:raise ValueError('TRANSCRIPT_DRIFT_HOLD')
            state['hash'].update(block); state['position'] += len(block); budget -= len(block)
            if time.monotonic() >= deadline:break
        if state['position'] == offset and not state['verified']:
            if state['hash'].hexdigest() != cursor['prefix_sha256']:raise ValueError('TRANSCRIPT_DRIFT_HOLD')
            state['verified'] = True
        while state['verified'] and budget > 0 and time.monotonic() < deadline and len(lines)+len(gaps)<64:
            block = f.read(min(256 * 1024, budget))
            if not block:break
            budget -= len(block)
            # Split bounded chunks; no read()/readline() proportional to a record.
            for part in block.splitlines(keepends=True):
                # JSONL uses LF only; splitlines treats CR as a boundary, so
                # only LF completes a record.
                state['hash'].update(part); state['record_hash'].update(part)
                state['position'] += len(part)
                if not state['oversized']:
                    state['buffer'].extend(part)
                    if len(state['buffer']) > MAX_RECORD_BYTES:
                        state['buffer'].clear(); state['oversized'] = True
                if part.endswith(b'\n'):
                    if state['oversized']:
                        h = state['record_hash'].hexdigest()
                        gaps.append({'id': 'gap_' + digest(canonical([str(path), state['record_start'], h])),
                                     'byte_start': state['record_start'], 'byte_end': state['position'],
                                     'record_sha256': h, 'reason_code': 'TRANSCRIPT_RECORD_TOO_LARGE',
                                     'recovery_condition': 'explicit_bounded_source_reparse', 'semantic_status': 'incomplete'})
                    else:lines.append((state['record_start'], bytes(state['buffer'])))
                    completed_hash = state['hash'].copy(); completed_end = state['position']
                    state.update(record_start=state['position'], record_hash=hashlib.sha256(), buffer=bytearray(), oversized=False)
                    if len(lines)+len(gaps)>=64:break
    current = path.stat()
    if state['view'] is None and (current.st_dev,current.st_ino,current.st_mtime_ns,current.st_size)!=identity:
        _close_scan(cache.pop(str(path),None));raise ValueError('TRANSCRIPT_SOURCE_CHANGED')
    if state['view'] is not None:
        _scan_source(store,path,state,current)
        # Cursor metadata describes this immutable point-in-time view, not the
        # later mutable file. A new view rechecks the committed prefix.
        cache[str(path)]=state
    if completed_hash is not None:
        # Keep partial-record scan/hash for the next tick, bound to the newly
        # committed semantic prefix. CAS below makes concurrent scans refuse.
        state['base_offset'] = completed_end
    dev,ino,mtime,size=state['identity']
    source_view={'kind':'immutable_cow_view' if state['view'] is not None else 'stable_live_view','device':dev,'inode':ino,'mtime_ns':mtime,'size':size,'captured_at':state['captured_at']}
    return lines, gaps, completed_hash or _Digest(cursor['prefix_sha256']), state['position'], source_view


class _Digest:
    def __init__(self, value):self.value = value
    def hexdigest(self):return self.value



def _archive_scan(store,path,limit,budget):
    """The same fixed-view prefix verification, shared by relocation owner."""
    from contextlib import nullcontext
    cache=getattr(store,'_archive_scans',{});store._archive_scans=cache
    if len(cache)>16:_close_scan(cache.pop(next(iter(cache))))
    stat=path.stat();state=cache.get(str(path))
    if state and state['limit']!=limit:_close_scan(state);state=None
    previous=state;state=_scan_source(store,path,state,stat,limit=limit)
    if state is not previous:state.update(limit=limit,position=0,hash=hashlib.sha256(),prefix=hashlib.sha256(),offset=0)
    cache[str(path)]=state
    target=state['view_size'] if limit is None else limit
    if target>state['view_size']:raise ValueError('TRANSCRIPT_DRIFT_HOLD')
    with nullcontext(state['view']) if state['view'] is not None else path.open('rb') as f:
        f.seek(state['position']);remaining=min(budget,target-state['position'])
        while remaining>0:
            block=f.read(min(256*1024,remaining))
            if not block:raise ValueError('TRANSCRIPT_DRIFT_HOLD')
            last=block.rfind(b'\n')
            if last>=0:
                state['prefix']=state['hash'].copy();state['prefix'].update(block[:last+1]);state['offset']=state['position']+last+1
            state['hash'].update(block);state['position']+=len(block);remaining-=len(block)
    current=path.stat()
    if state['view'] is None and (current.st_dev,current.st_ino,current.st_mtime_ns,current.st_size)!=state['identity']:raise ValueError('TRANSCRIPT_SOURCE_CHANGED')
    if state['view'] is not None:_scan_source(store,path,state,current,limit=limit)
    if state['position']<target:return None
    cache.pop(str(path),None);_close_scan(state)
    return (state['position'],state['hash'].hexdigest()) if limit is not None else (state['offset'],state['prefix'].hexdigest())
