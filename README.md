# Skill Observatory

Local-first observation and bounded evolution for Codex Skills. 中文默认；支持即时英文切换，持久化语言、筛选、当前详情和设置草稿。

**Current status: engineering preview.** Observation, durable triage, optional
semantic review, a real isolated container backend, an administration UI and
reversible service lifecycle are implemented. Skill improvement, automatic
promotion and recursive gain are **not established**. Missing domain truth
keeps promotion HOLD. A semantic review is not an independent task evaluation.

## Install from source

Requires Python 3.12+, uv, Node 22.12+ or 24+, npm. Codex CLI is required for native
observation/model integration. Docker is required only for container evaluation.

```sh
git clone https://github.com/sunxiuguo/skill-observatory.git
cd skill-observatory
uv sync --locked
uv run python scripts/build.py
uv pip install --reinstall dist/skill_observatory-0.1.0-py3-none-any.whl
uv run skillobs doctor
uv run skillobs serve --port 8765
```

Open http://127.0.0.1:8765. It binds loopback only, has same-origin browser
sessions and CSRF checks, and cannot grant authority through the UI.
The default private state directory is `~/.local/state/skill-observatory`.
Choose another with `skillobs --state /absolute/private/state ...`.

## Observe an explicitly authorized project

```sh
uv run skillobs install-hooks --project /absolute/project
uv run skillobs register /absolute/skill-directory --owner skill-evolution-loop
```

Review and trust the new project hooks using Codex's **native** hook workflow.
Installation does not confer trust. No trusted hash is forged. No global
historical session scan is performed. Hooks persist only scoped event metadata;
raw prompts and tool output are not spooled.

To cover every project under one explicitly authorized directory, place one
shared user-level collector while keeping its observation scope restricted:

```sh
uv run skillobs install-hooks --project "$HOME" --scope /absolute/authorized-root
```

Review/trust these hooks through Codex's native workflow. Existing hooks are
preserved; runtime filters exclude events outside the authorized root. Restarts
or new sessions may be required to load the new hook definitions. This does not
authorize historical session imports or automatic Skill modification.

For an explicitly selected desktop/CLI session, use the incremental adapter:

```sh
uv run skillobs observe-session /absolute/selected-session.jsonl \
  --session-id ACTUAL_SESSION_ID --source codex-desktop
```

The versioned transcript adapter currently supports the Codex 0.160 family,
checks session/scope/cursor identity, and uses the same runtime/spool.
Exact Skill bytes observed in native tool output can support `verified_read`;
mentioning/discovering a Skill cannot establish execution.

## Semantic review and owner integration

Without a configured reviewer, executions receive deterministic **triage HOLD**,
not a completed semantic review. `CodexReviewer` accepts a trusted local owner
factory and exact provider/model/maximum-effort admission function. Authentication,
quota, pricing and data authority remain with that owner. See
[configuration](docs/CONFIGURATION.md). No personal Provider path is required by
the public package. Wall time, daily attempt count and input size are bounded;
unknown monetary cost blocks promotion. A reviewer cannot install a Skill.

The `SkillEvolutionInstaller` adapter uses the original `skill-evolution`
propose/apply/rollback receipts. It does not copy that owner's implementation.
It remains disabled until a matching human authority grant, exact hashes and
an independently accepted final verdict exist. No existing Skill is modified
by installing this project. Domain oracle, permission, budget and final gates
cannot be edited in the UI.

## Run, stop, upgrade and uninstall

Foreground: `skillobs serve` / Ctrl-C. macOS user service:

```sh
uv run skillobs service-install --port 8765
uv run skillobs service-status
uv run skillobs service-stop
uv run skillobs service-start
uv run skillobs service-uninstall
uv run skillobs uninstall-hooks --project /absolute/project
```

Service/hook changes retain backups and refuse content-hash drift. Uninstall
retains private state for recovery. An upgrade is stop → rebuild/reinstall wheel
→ start, retaining state; if Python path changes, reinstall the user service.
Do not delete state to recover an interrupted attempt. Unknown model/tool side
effects become HOLD and require readback before a retry.

## Verify

```sh
uv run pytest -q
# UI state test talks to an actual loopback API, with no mock state fallback.
SKILLOBS_TEST_ORIGIN=http://127.0.0.1:8765 npm --prefix web test
```

Container tests use the immutable image digest in `tests/test_evaluation.py`.
They verify network isolation, no host secrets/mounts/socket, independent arms
and real output artifacts. Synthetic fixtures test mechanics only and stay HOLD.
The UI test establishes state/locale contracts; it does not certify visual
quality or representative user usability. See [acceptance status](docs/STATUS.md).

Licensed MIT. Dependencies retain their licenses; see [NOTICE](NOTICE.md).
