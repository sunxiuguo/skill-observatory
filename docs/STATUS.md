# Current acceptance — 2026-10-15 (semantic recovery)

The previous closeout stopped at an execution HOLD before completing available
transport diagnosis and owner wiring. Two new isolated live Provider schema
reviews now complete with schema/identity checks and usage receipts, in about
94 and 109 seconds. The second uses the original failed case's selected textual
facts with new run/attempt identities; no old unknown attempt was replayed.
Its upstream took 102.931 seconds to return response headers and 104.157 seconds
for the full response. The old 120-second overall deadline and 120-second proxy
wait left little room for latency variation. The exact cause of each historical
timeout remains UNKNOWN because those runs did not record transport phases.

The local owner now uses a bounded 300-second review/proxy budget and explicitly
disables hidden HTTP/SSE retries. The guard records request/connection/header/body
phases, byte counts, durations and typed failures without prompt, credentials or
raw error bodies. The reviewer preserves bounded event/error/transport counters
and detects app-server EOF promptly. A hash-bound two-turn tool-free qualification
and schema canary certify this transport only, not domain truth or improvement.
Production code/assets and its exact status are read back after the original
service upgrade lifecycle.

`OwnerReceiptPipeline` connects the existing original-owner proposal,
`final_gate.finalize` and independently accepted fresh-context task receipts.
Trusted local `evolution-proposal-bind` and `evolution-evaluation-bind` commands
bind exact proposal/evaluation hashes. The adapter does not generate labels,
sign domain/cost receipts, duplicate installation or invoke models while waiting.
Missing owner inputs leave the stage ready with its attempt count unchanged;
one waiting stage cannot starve another ready review. Disabled automatic
promotion also leaves installation stages unclaimed. Unknown/held side effects
are never reopened by a receipt import. The local evolution owner is now wired
to these adapters; it still needs actual owner proposals, measured task-family
evaluations with independent domain/all-attempt cost receipts, and accepted
post-install task evidence. That is an explicit input boundary, not an empty
callback. An engineering canary does not substitute for those inputs.

| Evidence layer | Current boundary |
|---|---|
| Observation/storage | Earlier recovery, performance and lossless maintenance evidence below remains applicable |
| Semantic execution | Two completed live schema canaries; transport and semantic-canary proofs separate from domain correctness |
| Evolution wiring | Receipt adapters and local owner connected; missing real inputs wait without dispatch or attempt consumption |
| Real Skill / natural user gain | HOLD / UNKNOWN; no candidate promoted from synthetic canaries or self-grading |
| Method RSI | UNVERIFIED; accepted method lineage and independent downstream gain still required |

Final applicable tests, clean distribution/install, production readback, remote
SHA and final-head CI are recorded at delivery. Private receipts and owner/proof
configuration remain excluded from the public distribution.

# Earlier engineering acceptance — 2026-10-15

This iteration restores the corrupted local ledger, bounds collection work,
separates worker health from process liveness, adds lossless storage maintenance,
and repairs the related daily-workflow planner and managed installation closure.
The exact physical cause of SQLite corruption remains UNKNOWN. Offline recovery
retained 122,400 events and 893 jobs and restored all five index-visible lost
entities from a verified healthy backup; original bytes and hash receipts remain
private. No admitted model/tool operation was replayed.

| Evidence layer | Current boundary |
|---|---|
| Observation/runtime | Recovered ledger, bounded queue drain and transcript reads, backpressure, failure backoff, independent health and diagnostic scope checks verified |
| Semantic review | Tool-free two-turn transport qualification passed; three synthetic schema-review attempts timed out and remain consumed/unknown; explicit owner execution HOLD prevents further automatic dispatch |
| Evolution adapters | `awaiting_owner_adapters`; proposer, independent domain evaluator and activation owner remain absent |
| Skill improvement / natural user outcome | HOLD / UNKNOWN; no promotion or domain truth invented |
| Method recursion | UNVERIFIED |
| Storage | Lossless artifact/backup compression applied; automatic bounded maintenance enabled locally; terminal-event payloads retain 30 hot days and durable identity/replay barriers |
| Production installation | Dedicated wheel-hash runtime separates the service from the development environment; actual package/static/API/browser identity is verified at delivery |

Same-ledger paired measurements (12 Store-open samples) reduce median open time
from 70.007 ms to 4.715 ms. Forty identical writes advance revision 40 → 0 times,
with wall time 1,934.5 → 439.4 ms. These are local engineering measurements, not
end-to-end task/token or business-gain claims.

Compression verified 4,422 artifact files (20,499,753 → 8,331,878 bytes) and ten
private historical backups (1,696,461,312 → 391,025,751 bytes). Combined logical
file-byte reduction is 1,317,603,436 bytes, about 1.23 GiB; APFS sharing/snapshots
mean this is not an exact filesystem free-space measurement. Current events are
only about seven days old, so none was eligible for the 30-day cold-event policy.
Cold gzip bytes remain in SQLite with verified transparent reads and deterministic
window/count/manifest summaries; authority, final-set consumption, attempts and
outcome truth are never replaced by summaries. Automatic maintenance uses no LLM.

The related daily workflow now distinguishes static metadata isolation from
pending semantic work, emits actionable machine output, and defers only planner
recommendations. Its over-budget historical run was closed through the canonical
checkpoint, and the three recommended deferrals were applied. Final inspection
found no active/recoverable/invalid runs and no remaining changed-input/defer
work. This does not certify future natural daily runs or semantic knowledge gain.
The original managed installer now includes the canonical relative-import closure;
an installed-only CLI in an isolated HOME verifies no source-checkout dependency.

Local acceptance includes required real Docker tests, real API/DOM integration,
source/wheel byte audits and isolated installation. Final counts, production
progress, loaded paths/assets and Git/CI identities are read back at delivery.
Raw runs, recovery receipts, provider configuration and authorization evidence
remain private. The reusable fixes belong to existing code owners; no new global
Skill, hook owner, scheduler, vector store or promotion authority was introduced.

# Historical reliability acceptance — 2026-10-13

The reliability iteration repairs the audited observation, review,
consumption and Web state defects. [RELIABILITY.md](RELIABILITY.md) maps R1–R13
to implementations, refusal evidence and remaining boundaries. The separately
owner-authorized user-service upgrade is applied through the original lifecycle
with private SQLite/spool backups and a rollback wheel. The loaded runtime and
actual HTTP assets match the installed package; collection advances and the
stalled backlog drains. The exact prior blocking stack root cause is still
UNKNOWN. This acceptance does not establish real Skill or user improvement.

Local acceptance: 111 backend cases including required real Docker execution;
9 Web tests against an isolated real API, including control failure and retained
detail remount; exact App/subagent/CLI fixtures; server-side pages and full-ledger
counts; required packaging/install gates are checked on the final source. Browser
QA uses an isolated 65-capability ledger, page 6, out-of-summary detail/version
loading, immediate Chinese/English switching, refresh and responsive layout.
Final Git/CI identity is read back at delivery, not inferred from this document.

| Evidence layer | Current boundary |
|---|---|
| Local engineering mechanisms | Accepted with actual applicable tests and browser readback |
| Existing production collection | Loaded code/assets, advancing event ledger, drained backlog, independent worker progress and unchanged authority/settings verified |
| Existing production semantic review | Configured, not certified; old admitted/unknown attempts remain unchanged; budget deferral and missing factual/admission evidence keep live review HOLD |
| Provider background admission | Explicit owner interface implemented; canonical background-job adapter pending |
| Real Skill pilot / natural user gain | HOLD / UNKNOWN; synthetic broker integration and canaries do not replace domain truth |
| Method recursive improvement | UNVERIFIED |
| Cross-project/global updates | Outside this iteration's write authority |

The upgrade exposed a legacy deduplication mismatch: seven existing SessionEnd
deliveries differed only by the new execution identity derived from the same
stored session/agent. The kernel now accepts that exact equivalence while
preserving the first durable bytes. Parent/child positives and changed identity,
content, root identity and stored-hash refusals pass. Isolated replay of the seven
actual records preserves events, jobs and model attempts; production reconciliation
keeps the original quarantine evidence in the private backup.

Same-ledger upgrade snapshots from 12:06 to 12:29 UTC on 2026-10-13 show
84,636 → 102,748 stored events; the initially stalled 15,362-file spool drains,
and the final snapshot has zero spool/quarantine files with fresh worker progress.
The increase includes previously queued deliveries and newly observed events;
it is not a count of new completed user tasks. Queue arrivals continue normally.

Production attribution readback checks 2,735 new-event observation receipts mapped
to 2,555 logical invocations, with zero identity mismatches. Two actual logical
invocations combine hook/subagent channels, and selected child runs retain
execution, immediate-parent and root identity. These denominators cover observed
receipts only; absent historical identities, unsupported transcript shapes and
the global denominator remain UNKNOWN/HOLD. All 716 pre-upgrade model attempts,
owner grants, hook/service receipts, settings and dependency versions are retained.

Production browser readback confirms the real catalog count/page, detail content
and Escape recovery. The previous isolated nine-test and wide/narrow browser
evidence remains applicable to unchanged frontend bytes. No live model request,
real domain pilot or promotion is introduced by the upgrade. Source packaging,
Git and final-head CI identities are checked at delivery.

## Historical acceptance snapshot — 2026-10-09

Maintenance starts at [AGENTS.md](../AGENTS.md) and the stable
[project contract](PROJECT_CONTRACT.md). This dated status records evidence;
historical implementation prompts do not confer new publishing authority.

| Layer | Evidence | State |
|---|---|---|
| Persistent project governance | Root/Web instructions, stable O1–O7 contract, objective-to-code/regression routes, CI structure and actual distribution checks | Verified locally; does not certify model adherence or outcome gain |
| Durable kernel | Scope/privacy, dedupe/restart, unknown-attempt HOLD, hash/CAS, CSRF, settings checks | Verified locally |
| Strong container mechanics | Real Docker execution, immutable image, no network/host mount/secrets/socket, non-root, independent containers, host oracle | Verified locally |
| Container/model IPC broker | Existing container runner plus exact read-only snapshots, fixed model admission, process-group deadline, durable call intents, usage/readback and replay refusal | Actual-container mechanism verified with synthetic owner; live adapter/domain integration pending |
| Actual native observation | Native hook trust readback; scoped CLI terminal/interrupt events; explicitly selected desktop transcript with exact Skill read | Partial coverage |
| Semantic review | Real admitted external model returns HOLD/NO_CHANGE; launchd consumes queued real events including a verified-read Skill turn; actual usage receipts | Operational within admitted scope; missing outcome truth |
| Automatic evolution sequencing | Deterministic review-bound experiments, bounded owner adapters, single-writer claims, prepared intent recovery, signed final verdict → original installer → independent activation ingress | Mechanism implemented/tested; no real promoted candidate |
| Bilingual UI state | Real API + DOM integration verifies locale, filter, route, unsaved form and refresh retention | Verified contract |
| Visual/browser usability | User-visible in-app tab exercised in Chinese/English; locale/filter/draft/detail refresh retention, native Escape, responsive viewports and service stop/restart | Verified browser paths; representative human usability remains unknown |
| Original owner installation | Checked original-owner grant ingress, thin adapter; original engine exercised on an isolated fixture with actual apply/rollback/CAS refusal | Mechanics verified; not exercised on a real promoted Skill |
| Original experience-method performance pilot | No independent domain truth/calibrated final labels supplied | HOLD; no pilot Skill promoted |
| New-context activation / later live result | Signed task result binds exact bytes and a context created after completed installation readback; later live verification checks current disk bytes and records as-of evidence | Refusal/positive paths tested, including bounded lock regression; real pilot pending |
| Recursive self-improvement | No accepted method generating next candidate with independent gain | Unverified |

Raw evidence remains private. Public code, CI and Git readback establish software
delivery only. They do not establish real Skill improvement or human usability.
Independent experience labels/representative cases are required for the chosen
experience-method pilot. No scores or final labels were invented to clear gates.
Container measurements retain domain guardrail/cost gaps. The fixed final-gate
compiler can combine them with independently signed, hash-bound domain and
all-attempt cost receipts under a frozen cost policy; it cannot invent those
receipts. Final sets are durably consumed once across protocol IDs, including
failed/HOLD attempts. The bounded container/model IPC mechanism is implemented.
A live admitted tool-free model adapter, its integration with paired evaluation,
and a calibrated domain evaluator for the experience pilot remain unfinished. This preview must
not be described as full closure.

## Capability lifecycle implementation — 0.2.0

This separate lane implements purpose/background/source project-session-turn,
immutable package snapshots, logical invocation deduplication, independent usage
stages, deterministic command validation/replay and on-demand privatecode discovery.
The existing observation hooks retain their definitions and trust; hooks capture
metadata while the root/creator decides and verifies reusable workflows.

The local catalog currently includes 71 existing canonical Skills and one new
`record-key-audit` command. Its three positive and three negative cases passed;
another CLI process replayed it from the bybit project, and the root checked the
actual result before recording acceptance. This is an activation canary, not
natural-task improvement or business gain. Existing birth/provenance unknowns
are preserved, and untracked calls are not claimed as zero.

The management UI provides catalog/capture/usage navigation, source and version
drawers, project/session/scenario search, stage/canary filters and pagination.
Chinese/English and saved navigation/filter/draft contracts use the real local API.
See [CAPABILITY_LIFECYCLE.md](CAPABILITY_LIFECYCLE.md) for research, behavior,
admission boundaries and CLI contracts. Representative human usability and
comparable token/time/business effects remain UNKNOWN.

## Governance and activation-boundary acceptance — 2026-10-09

The root instruction file was absent throughout Git history. Goals existed in
historical design/handoff files, and the Web instruction template contained
commands that did not match the current product. Root AGENTS, the stable project
contract and read-only CI checker now provide persistent routing and structural
drift refusal. Fifteen governance cases exercise both portable acceptance and
missing/overridden instructions, broken references, lost guardrails and build/CI
omissions. The actual source archive also passed these fifteen cases.

Installation freshness now uses `applied_at`, recorded after the actual write and
readback. Legacy records without that evidence remain
`INSTALLATION_APPLY_TIME_REQUIRED`; no historical time is invented. Live
verification refuses changed, missing or symlink targets and records
`live_verified_at`/`verified_skill_sha256` as historical readback evidence. A
nested installation-lock deadlock exposed by the first positive live case is
fixed; subprocess deadlines make its regression fail rather than hang.

Local acceptance: 74 backend tests with required real Docker execution, two Web
tests against an isolated real API, clean-source wheel/sdist build and byte
allowlist audit, source-archive governance checks, and isolated wheel install /
doctor with packaged Web assets. The Web entrypoint owns its temporary state and
checks API identity before running tests. Removing AGENTS from the actual source
archive fails the distribution audit. One existing Starlette/httpx deprecation
warning remains. These are engineering results; real Skill improvement, natural
user benefit and recursive gain retain their previous evidence gaps. Applying
these changes to an existing service requires a separate authorized update and
loaded-version readback.

The owner explicitly authorized automatic verified task-completion commits and
pushes to the existing public `sunxiuguo/skill-observatory` main branch. Root
AGENTS defines scope, public-content review, fast-forward/concurrency protection,
remote SHA and final-head CI checks. Current Git identity and CI receipts are
read back at delivery; unrelated prototypes and private receipts stay local.
