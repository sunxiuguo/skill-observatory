"""Explicit incremental adapter, limited to a selected session in an authorized scope."""
from __future__ import annotations

import json
from pathlib import Path

from .runtime import spool
from .store import canonical, digest, now

DESKTOP_APP_ORIGINATOR = "Codex Desktop"
ALPHA_17 = "0.162.0-alpha.17.2"
CHILD_TERMINAL_EVENTS = {"SubagentStart", "SubagentStop"}


def _regular_path(path):
    path = Path(path)
    if path.is_symlink():
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
            first = json.loads(f.readline())
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
    elif version == ALPHA_17:
        # The version string alone is not a contract. Current App transcripts
        # carry both the rollout/execution id and the logical parent session.
        if source == "codex-cli":
            raise ValueError("TRANSCRIPT_SOURCE_SCHEMA_UNVERIFIED")
        if (
            meta.get("originator") != DESKTOP_APP_ORIGINATOR
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
    if version == ALPHA_17 and source == 'codex-subagent':
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
        and cursor.get("size") == stat.st_size
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

    # A replaced/truncated session file cannot inherit the previous cursor.
    with path.open("rb") as f:
        prefix = f.read(offset)
        if len(prefix) != offset or digest(prefix) != cursor["prefix_sha256"]:
            raise ValueError("TRANSCRIPT_DRIFT_HOLD")
        f.seek(offset)
        tail = f.read()
    complete = tail[: tail.rfind(b"\n") + 1] if b"\n" in tail else b""
    turn = cursor.get("turn_id")
    calls = cursor.get("calls", {})
    count = 0
    registered = store.list("skills")
    catalog = store.list("capability_catalog")
    line_offset = offset

    for raw_line in complete.split(b"\n")[:-1]:
        line = raw_line + b"\n"
        sequence = line_offset
        line_offset += len(line)
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
                if s["id"] in ids:
                    cap_binding = (
                        next(
                            (
                                c
                                for c in binding.get("caps", [])
                                if store.get("capability_catalog", c["capability_id"])["path"] == s["path"]
                            ),
                            None,
                        )
                        if isinstance(binding, dict)
                        else None
                    )
                    content = (
                        store.read_artifact(cap_binding["content_sha256"]).decode()
                        if cap_binding
                        else (Path(s["path"]) / "SKILL.md").read_text()
                    )
                    if any(content in t for t in expanded):
                        base.setdefault("verified_attributions", []).append(
                            {
                                "skill_id": s["id"],
                                "package_sha256": s["package_sha256"],
                                "file_sha256": digest(content.encode()),
                                "attribution": "verified_read",
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

    end = offset + len(complete)
    store.put(
        "cursors",
        {
            "id": cursor_id,
            "offset": end,
            "prefix_sha256": digest(prefix + complete),
            "turn_id": turn,
            "calls": calls,
            "created_at": now(),
            "source": source,
            "mtime_ns": stat.st_mtime_ns,
            "inode": stat.st_ino,
            "size": stat.st_size,
            "execution_session_id": identity["execution_session_id"],
            "parent_session_id": identity["parent_session_id"],
            "agent_id": identity["agent_id"],
            "adapter_version": version,
        },
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
        content = path.read_bytes()
        offset = content.rfind(b"\n") + 1
        stat = path.stat()
        store.put(
            "cursors",
            {
                "id": "cursor_" + digest(str(path).encode())[:24],
                "offset": offset,
                "prefix_sha256": digest(content[:offset]),
                "turn_id": event.get("turn_id"),
                "calls": {},
                "created_at": now(),
                "mtime_ns": stat.st_mtime_ns,
                "inode": stat.st_ino,
                "size": stat.st_size,
                "coverage_start": "native_hook_attachment",
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


def relocate_archived_transcript(store, new_path, *, old_path=None, execution_session_id=None):
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
        with new_path.open("rb") as f:
            prefix = f.read(old_cursor["offset"])
        if len(prefix) != old_cursor["offset"] or digest(prefix) != old_cursor["prefix_sha256"]:
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
        content = new_path.read_bytes()
        offset = content.rfind(b"\n") + 1
        new_cursor = {
            "id": new_cursor_id,
            "offset": offset,
            "prefix_sha256": digest(content[:offset]),
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
        "missing": list(set(old.get("missing", []) + ["ARCHIVE_RELOCATION_FUTURE_ONLY"])),
        "relocated_from": old_id,
    }
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if store.get('selected_sessions',old_id,db)!=original or store.get('cursors',old_cursor_id,db)!=old_cursor:
            raise ValueError('ARCHIVE_POINTER_CAS_DRIFT')
        if existing_new:raise ValueError('ARCHIVE_POINTER_ALREADY_REGISTERED')
        store.put('cursors',new_cursor,db);store.put('selected_sessions',old,db);store.put('selected_sessions',selected,db)
    return selected
