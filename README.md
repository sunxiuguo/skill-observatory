# Skill Observatory

Local-first observation and bounded evolution for Codex Skills. 中文默认；支持即时英文切换，持久化语言、筛选、当前详情和设置草稿。

**Current status: engineering preview.** Observation, durable triage, optional
semantic review, a real isolated container backend, an administration UI and
reversible service lifecycle are implemented. Skill improvement, automatic
promotion and recursive gain are **not established**. Missing domain truth
keeps promotion HOLD. A semantic review is not an independent task evaluation.

## Project maintenance

Read [AGENTS.md](AGENTS.md), [the project contract](docs/PROJECT_CONTRACT.md) and
[current acceptance status](docs/STATUS.md) before iterating. The contract preserves
the final goal; status records evidence without treating engineering delivery as
real Skill or user improvement. Historical handoffs do not grant new authority.
The owner explicitly authorized automatic task-completion commits and pushes to
this public repository's main branch; see AGENTS for scope and readback checks.
Run `uv run python scripts/check_project_contract.py` for governance changes;
CI also checks instruction discovery, references and required regression routes.

## Install from source

Requires Python 3.12+, uv, Node 22.12+ or 24+, npm. Codex CLI is required for native
observation/model integration. Docker is required only for container evaluation.

```sh
git clone https://github.com/sunxiuguo/skill-observatory.git
cd skill-observatory
uv sync --locked
uv run python scripts/build.py
uv pip install --no-deps --reinstall dist/skill_observatory-0.2.0-py3-none-any.whl
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

The versioned transcript adapter supports certified 0.160.0/0.160.1 and
0.162.0-alpha.2 fixtures, plus the exact 0.162.0-alpha.17.2,
0.163.0-alpha.10.2 and 0.163.0-alpha.11.1 Desktop/subagent metadata shapes,
the exact 0.164.0-alpha.11.1 Desktop and App-bundled CLI exec shapes, and the
exact 0.162.1/0.163.0/0.164.0 standalone CLI exec shape. The 0.164 App's child
shape remains unverified and refused. Unknown
versions or incompatible source/schema combinations stay HOLD. It
checks session/scope/cursor identity, and uses the same runtime/spool.
Exact Skill bytes observed in native tool output can support `verified_read`;
mentioning/discovering a Skill cannot establish execution.

Collection, review and evolution have independent worker lifecycles. Configured
reviews run under a process-group deadline; a lost dispatched attempt requires
readback. Budget waits before dispatch retain a durable `eligible_at` and recover
without counting a model attempt. See [reliability acceptance](docs/RELIABILITY.md)
for the engineering results and remaining production/domain boundaries.

## Capture and reuse accepted workflows

Version 0.2 adds immutable capability versions, purpose/background and source
project/session/turn receipts, capture decisions and logical invocation history.
The capability catalog, capture queue and usage pages share the same private
ledger. Old capabilities have first-seen dates; unknown birth stays unknown.
Read, applied, executed and accepted are distinct facts, never summed.

Scoped agents discover related capabilities at task start and route meaningful
accepted procedures to their canonical creator/owner at stage completion. A
structured `capture --spec FILE --auto` receipt prefers existing owners. Trusted
pure JSON commands with actual positive/counterexample tests can be installed
and replayed locally; judgment Skills require root-reviewed independent forward
cases. Other side effects stay with their owning authorization/recovery workflow.
There is no LLM extraction on every Stop and no new scheduler. See the complete
[creation, replay and maintenance contract](docs/CAPABILITY_LIFECYCLE.md).

Creation functional acceptance does not certify improvement over an existing
method. Existing signed final/activation/live-outcome gates remain unchanged.

## Factual input and task-family execution

Changed terminal inputs create bounded factual work items. `evidence-plan` and
`evidence-build` bind Native-selected goals and facts to exact source/version
manifests without exporting raw transcripts. The native task-family bridge runs
frozen historical packages using admitted native tools, and the v2 final kernel
reconciles actual case/arm outputs and typed all-attempt costs. See the
[execution integration](docs/implementation/skill-rsi-2026-10-16/README.md) for
CLI ingress, package/owner dependencies, natural cohorts and method lineage.
The first exposed pilot produced equivalent valid commands, with an overstrict
oracle, insufficient independent samples and unresolved cost gates; it certifies
no gain. Package writes retain the original owner’s atomic transaction and matching
authority requirements. Existing user service deployment is separate.

## Semantic review and owner integration

For unattended recent-chat review and repair of both Skills and this project,
use the single [proactive review workflow](docs/PROACTIVE_REVIEW.md). Its
`proactive-plan` / `proactive-finish` commands discover changed in-scope sources,
resume unfinished batches and retain forward follow-ups in the existing ledger.
The Native root performs evidence review and authorized repairs; planning and
root accounting do not grant promotion authority or certify RSI gains.

For an immediate review of the current or explicitly selected session, use
`retro-plan --index-db CODEX_INDEX [--session-id SESSION]` and the same
`proactive-finish` receipt. This preserves daily pending work and both scope
boundaries. See [selected-session retrospectives](docs/RETROSPECTIVE.md).
After an authorized owner update, `capability-reconcile` binds reviewed bytes
to the prior catalog version without rewriting history or certifying gain.

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
For a persistent service, install the reviewed wheel into a dedicated virtual
environment created from the locked dependencies and run `service-install` with
that environment’s Python. Keep development `uv run` operations in a separate
environment; editable reinstalls can replace package static assets.
Do not delete state to recover an interrupted attempt. Unknown model/tool side
effects become HOLD and require readback before a retry.

## Storage and recovery

SQLite remains the transactional ledger; content-addressed files hold evidence.
Opening an existing ledger does not rerun migrations, unchanged writes do not
advance its revision, and collection drains bounded batches before following
transcripts. Independent worker receipts distinguish successful work from a live
process even when the ledger cannot be read:

```sh
uv run skillobs health
uv run skillobs storage-status
uv run skillobs storage-compress
uv run skillobs storage-archive --before 2026-01-01T00:00:00Z
```

Maintenance commands default to a dry run. `--apply` makes the selected change;
archives retain lossless bytes, identity/hash tombstones and a verifiable summary.
Never replace final-set consumption, unknown attempts, authority or outcome truth
with a prose summary. See [storage policy](docs/STORAGE.md) for eligibility,
restoration, hash checks and compaction boundaries.

Stop the original service before offline recovery. The trusted backup must cover
every index-visible lost entity; unexplained loss refuses replacement. Source
bytes and a recovery receipt are retained, and no model/tool operation is replayed:

```sh
uv run skillobs storage-recover --backup /absolute/known-healthy.sqlite3
uv run skillobs storage-recover --backup /absolute/known-healthy.sqlite3 --apply
```

## Verify

```sh
uv run python scripts/check_project_contract.py
uv run pytest -q
# Install Web dependencies first if scripts/build.py has not been run.
npm --prefix web ci --registry=https://registry.npmjs.org
# Starts a temporary real API, seeds a synthetic UI ledger, tests, then stops it.
uv run python scripts/test_web.py
```

Container tests use the immutable image digest in `tests/test_evaluation.py`.
They verify network isolation, no host secrets/mounts/socket, independent arms
and real output artifacts. Synthetic fixtures test mechanics only and stay HOLD.
The UI test establishes state/locale contracts; it does not certify visual
quality or representative user usability. See [acceptance status](docs/STATUS.md).

Licensed MIT. Dependencies retain their licenses; see [NOTICE](NOTICE.md).
