# 审查续接的来源配置保护 — 2026-11-14

规划器曾在返回 pending 工作单或校验新索引之前改写来源配置。
本轮实际误传调度数据库时触发了该问题，正确的会话索引路径已恢复。
现续接旧批次保持原配置；新发现通过索引格式和时间校验后，配置与工作单
在同一事务提交。后续审计失败时两者一起回滚。
6 个回归场景修复前均失败；178 项相关检查修复后通过。真实 pending 批次
回读确认误传索引不再改变配置或工作单，722 条模型尝试仍保留。
构建、分发与合同检查通过；隔离 wheel 在仓库外通过同样 178 项检查，
安装模块与源码逐字节一致。这些结果只证明工程行为。

本轮审查 24 个不同会话义务，获得 17 个选定正文视图，含 3 个压缩原件。
7 个目录身份拒绝、2 个来源的 7 条超大记录仍为覆盖缺口；变化来源由 finish
保留为 follow_up，全窗口与自然来源分母 UNKNOWN。历史已修复发现不重复立案，
子任务的组合验收、真实玩家动作和未知模型响应仍由原根接续。

另一份历史原件经既有事实构建器绑定精确任务与 Skill 版本，重复构建与回读
一致，恢复 1 个已知派发前工作单。事实输入现为 14 份；任务完成、自然来源、
环境与全部尝试成本仍未知。后台原审阅 owner 仍不可用，没有候选、独立实验、
安装或任务结果。三条常驻通道仍推进，运行制品没有升级。
固化结论为 project_record；Skill 改善 HOLD，用户效果 UNKNOWN，方法递归
UNVERIFIED。源码交付、已安装制品与实际收益分别验收。

# 精确版本采集与终态投影修复 — 2026-11-13

当前 App 的 `0.167.0-alpha.4.1` 直接子会话因旧版本门被拒绝。
本轮沿用既有身份校验，接入已观察到的 Desktop automation 与 direct v1
child 格式。用户会话、CLI、嵌套子会话和相邻构建仍未认证。
4 项实际格式回归在修复前失败。5 个已授权真实子会话在隔离账本中读取到
2,951 个事件，重复读取和重启后新增事件均为 0；1 条超大记录保留为覆盖缺口。
这些结果证明采集兼容与去重，不证明 Skill 被遵循或产生收益。

进度投影曾将已有 completed/failed 终态的 2 次审阅失败算作未知执行，
持续提示回读。现仅从未知执行计数中排除具有明确终态的 reviewer attempt。
其他尝试类型及缺失、未知终态仍要求回读。3 个终态反例在修复前失败，
7 个对照通过。真实账本前后回读确认：722 条尝试内容不变，首个阻塞恢复为
事实缺失；失败、拒绝、未知成本与晋级门均保留。

234 项采集、工作单和投影检查、52 项相关机制检查及 9 项实际 API/DOM 检查
通过；两组 Python 检查有 10 项重叠。构建与分发审计通过。
隔离 wheel 在仓库外通过 172 项检查，两个修改模块与源码逐字节一致。
本轮处理 3 批共 36 项会话义务，涉及 30 个不同会话，获得 21 次选定正文视图。
9 次目录身份拒绝、5 次旧版本拒绝及 1 次来源格式拒绝均保留；5 个旧版本来源
随后已按精确新格式读回。4 个不同超大正文记录限制了所选视图的完整性。
活跃来源的变动由 finish 降为 follow_up；全窗口与自然来源分母仍为 UNKNOWN。

上次恢复的三条后台通道继续推进，认证健康接口为 200，运行 PID 和制品未变。
当前源码修复尚未安装到该旧制品。原语义评审 owner 依赖已移除入口，仍不可用。
13 份事实输入、28 份 review 和 722 次模型尝试尚未产生可接受的候选、独立实验、
安装或任务结果。本轮未恢复退休 Provider、替换模型或重放未知执行。

前次运行已由调度器自动归档；本次完成后的归档须后续核对。
下一批 12 个会话及系统项、原 owner 接续和未决证据已保留。
固化结论为 project_record；Skill 改善 HOLD，真实用户效果 UNKNOWN，方法递归
UNVERIFIED。源码交付、运行制品升级与领域效果分别验收。

# Background progress recovery and factual continuation — 2026-11-12

The installed HTTP service remained alive while all three background lanes had
stopped updating for about 19 hours; its authenticated health endpoint returned
503. The ledger passed quick_check and had no running/dispatched/unknown jobs.
A private SQLite backup, its hash, service configuration and lane receipts were
preserved before an owner-managed stop/start of the same immutable runtime.
All three lanes then advanced with successful progress, and authenticated health
returned 200/healthy on readback. Configuration bytes and worker build identity
are unchanged. The original stop cause remains unknown; the installed older
artifact lacks the diagnostic-failure guards already present in current source.
This recovery is not an upgrade or proof that the stop cannot recur.

Two bounded batches account for 24 distinct session obligations: 17 selected
source views, five index/header cwd refusals, one compressed-size refusal and
one unsupported-source-schema refusal. Three compressed review originals were
recovered. No oversized record was skipped within the selected views; refused
sources remain coverage gaps. Actual maintenance outputs support NO_CHANGE;
child copy proposals and cloud probes retain their root integration/real-run
acceptance boundaries. Historical repaired ingress findings are not new defects.
More sources remain; full-window and natural-origin denominators are unknown.

Another compressed original supplied an exact task goal and acceptance condition
through the existing factual builder. Repeated construction and capsule readback
agree, with no missing facts. Its known pre-dispatch job now defers because the
original semantic Provider owner remains unavailable. Thirteen factual capsules,
28 reviews and 722 model attempts exist; no candidate, independent experiment,
installation or task receipt establishes improvement. Completion, natural origin,
environment and all-attempt costs remain unknown. No global Skill, hook or
Provider configuration was changed, and no other-project operation was replayed.

Eleven existing worker-lifecycle/storage checks and the contract check pass.
No source-code change is needed for this recovery. The previous completed run
was archived by the scheduler; this run's post-final archival is not yet
verifiable. Evolution disposition is project_record; Skill gain HOLD, natural
gain UNKNOWN and method UNVERIFIED. The original Provider owner continuation
and remaining bounded review work stay pending.

# Storage inventory during lossless maintenance — 2026-11-11

Storage inventory previously collected paths and read their sizes later. Actual
lossless compression between those reads removed a raw artifact and caused
FileNotFoundError; WAL disappearance had the same race. Three controlled
regression checks fail before repair. Inventory now reads each regular file's
metadata once and skips only disappearing files. Symlinks remain excluded and
permission errors remain visible. This is a concurrent observation, not an atomic
storage snapshot or evidence of reclaimed production space.

The affected suites pass 32 checks. The required-container backend passes 582
checks; nine actual API/DOM checks and the contract pass. Build/archive auditing
passes. An isolated installed wheel passes the same 32 affected checks outside
the checkout; 16 actual CLI inventories overlap compression of 128 artifacts,
whose original bytes remain readable by their hashes. Doctor passes. These are
engineering checks, not independent Skill improvement evidence. README admission
notes now match the already supported exact automation and direct-child shapes.

Three bounded batches account for 36 obligations across 35 distinct sessions:
25 selected source views and 11 index/header cwd refusals. Four distinct compressed
originals are recovered for review; eight oversized records across four distinct
sources remain gaps. One changing game source appears twice; views are not
independent tasks. Game player handoffs retain actual saved/UI revision boundaries
and unfinished full-life/100-play obligations. Historical factual-selection
concurrency findings are already repaired and covered by current regressions.
More sources remain; full-window and natural-origin denominators are unknown.

A separate compressed original supplies another real, exact-version-bound goal
and acceptance condition through the existing factual builder. Its repeat and
capsule readback agree and one known pre-dispatch job resumes. Twelve factual
capsules now exist; independent completion, origin, environment and all-attempt
cost remain unknown. The original semantic reviewer integration is still
unavailable, with no candidate, experiment, installation or independent task
receipt. Its existing owner continuation remains open. Installed worker services
are not upgraded and no global Skill/provider configuration changes occur.

The previous completed run is archived by the scheduler. The earlier interrupted
run remains visible; current post-final archival is not yet verifiable. Scoped
source delivery requires final local/remote/CI readback. Evolution disposition is
project_record; Skill gain HOLD, natural gain UNKNOWN and method UNVERIFIED.

# Exact Desktop automation and child review admission — 2026-11-10

The exact 0.167.0-alpha.3.2 adapter now admits the observed Desktop automation
and direct v1 child shapes. It retains Desktop/source, execution/logical/parent,
integer depth-one and multi-agent-version checks. Unknown versions, malformed
source labels and inconsistent identities refuse before observation. Historical
origin labels do not certify natural execution or improvement.

The final regression cases against the previous parser reproduce 25 failures;
the repaired affected suites pass 192 checks. Root real-source replay reaches
unchanged captured EOF for an automation (316,764 bytes, 12 events) and a child
(32,688,658 bytes, 1,854 events); repeat and restarted reads add zero events.
The child retains separate execution, parent and root identity. Independent
synthetic probes pass 113 checks and 1,188 differential cases find no unintended
admission. These are engineering checks, not independent domain evaluation.

Three bounded batches account for 36 obligations across 27 distinct sessions:
27 selected source views and nine index/header cwd refusals. Seven distinct
compressed originals are recovered; four distinct oversized-record gaps remain.
Changing sources reopen through the existing finish gate. More sources remain;
full-window and natural-origin denominators are unknown. Game candidates and
actual-play counting, research truth and interrupted Provider recovery remain
with their original owners; no other-project operation is replayed.

The full required-container run initially passes 572 checks and errors on three
container checks because Docker is stopped. After restoring the local container
environment, all four tests in that module pass. Nine actual API/DOM checks and
the contract pass. A clean installed wheel outside the checkout passes 213
affected checks; all 35 package files match source and archive. Its actual CLI
checks automation observation, repeat/finish idempotency, compressed discovery,
identity-drift refusal, cleanup and doctor. Public-content review and exact
local/remote/CI identities are checked at delivery.

A recovered compressed original also supplies one more exact, version-bound
user goal and acceptance condition through the existing factual builder. Repeated
build and capsule readback retain unknown completion, natural origin, environment
and cost. This prepares semantic review input; it does not certify a task result.
The other selected factual gaps retain missing observed versions or the existing
compressed-source size limit.

All installed worker lanes progress on their previous immutable build. The
original semantic reviewer owner still points to a retired integration and is
unavailable; no candidate, independent experiment, installation or task receipt
is produced. Its existing concrete owner handoff remains pending, rather than
replaying attempts or substituting providers. No global Skill/hook/config or
running Observatory service upgrade occurs. The previous completed automation
is archived by the scheduler; the earlier interrupted run remains visible.
Current post-final archival is not yet verifiable. Evolution disposition is
project_record; Skill gain HOLD, natural gain UNKNOWN and method UNVERIFIED.

# Compressed review recovery and exact metadata admission — 2026-11-09

The review planner previously reported compressed original sources as missing:
its exact archive fallback only recognized uncompressed files. Review discovery
now checks the indexed basename and its exact compressed/archive counterparts,
retaining scope, session, cwd and version gates. The optional zstd reader bounds
compressed input, decoded output, decoder memory and wall time. Complete-mode
review checks stream integrity and source stability and removes temporary decoded
files on exit. Metadata-only discovery cannot establish body integrity; collector
cursors still require uncompressed sources. CI installs the optional decoder.

The adapter also admits the observed Desktop user shape for the exact
0.167.0-alpha.3.2 version and the observed 0.166.0-alpha.6 direct v1 child shape.
Unknown versions, adjacent source shapes and inconsistent execution/logical/parent
identities still refuse. One real source reaches its frozen EOF with 186 events
and no duplicates on repeat/restart; another contains only metadata. The child
body is reviewed separately by the root and is not a natural outcome sample.

Before repair, compressed-source tests reproduce six failures, while 28 new
metadata checks fail. Final compressed checks pass 21 cases, and the existing
transcript suites pass 103. Required-container backend acceptance passes 552
checks; nine actual API/DOM checks also pass. Independent compressed-reader probes
retain private temporary permissions, cleanup, corruption/limit and drift refusal.
A clean installed wheel passes 166 affected checks outside the checkout, with
all 35 package files matching the reviewed archive. Its actual CLI checks
compressed discovery, identity refusal, repeated read/finish and doctor. These
are engineering checks, not independent domain improvement evidence.

Three bounded batches account for 36 obligations across 36 distinct sessions:
23 selected source views include one metadata-only source, and 13 source schemas
remain unverified. Eleven views recover exact compressed sources, including
historical child/interrupted reviews; five oversized-record gaps remain visible.
Seven deterministic patrols retain NO_CHANGE and backlog 0/6. Full-window and
natural-origin coverage remain unknown; more sources and original-owner game,
quality, device, research and Provider-recovery follow-ups remain open.

The compressed originals also recover two real, version-bound factual-input
sources. Native-selected goals and acceptance conditions are bound through the
existing builder and capsule readback; both retries are idempotent and each
resumes one pre-dispatch evidence wait. Ten factual capsules now exist. The new
two retain unknown completion, origin, environment and all-attempt cost. This
moves those obligations to the unavailable original semantic Provider owner;
it does not create an independent review, candidate, experiment, installation
or task receipt, nor upgrade the older immutable worker service.

The previous scheduled run has no completion receipt and remains pending review;
this run resumes its durable batch. Current post-final archival is not yet
verifiable. Distribution, clean-wheel behavior, public-content review and final
source/remote/CI identities are checked at delivery. Evolution disposition is
project_record; Skill gain remains HOLD, natural gain UNKNOWN and method gain
UNVERIFIED.

# Nested read capture and terminal readback consistency — 2026-11-07

The transcript adapter now decodes bounded JSON result records and nested native
output fields before checking the full call-time Skill bytes. A captured source
replay on an isolated catalog reproduced two complete reads remaining mentioned
under the old adapter; both become verified reads after repair. A plain-text
control remains accepted. Both replays reach the same frozen EOF and reopening
adds no events. This proves read-capture behavior, not historical package
certification or natural task gain. Partial text, disk drift, unbound calls and
metadata-only content remain unverified; parser bounds and invalid JSON are checked.

Independent synthetic CLI probes also reproduced a failed terminal readback
being replaced by completed with different usage on the same attempt. The
reviewer now locks the first known terminal and accounting/output facts inside
an immediate transaction. Conflicting terminal, usage, output or identity refuses
without rewriting the attempt, job or review. Identical readback is idempotent;
unknown usage/output can still be supplied for the same terminal. The first
terminal can finalize pre-terminal partial usage, retaining the partial receipt. Scope and
frozen-input restoration continue through the existing acceptance gate.

Before repair, nine terminal refusal/concurrency checks fail while the unknown
accounting control passes. The repaired targeted factual suite passes 84 checks;
the transcript suite passes 58. Required container and distribution acceptance
are verified at delivery. Foreign attempt-reference ownership remains a separate
semantic question; content-digest acceptance alone does not establish misuse.

The bounded review continues from the previous pending batch. Missing exact
sources, unverified schemas and oversized/truncated records remain visible.
Sixteen existing verified-read receipts still lack their exact source files.
The installed workers progress but the original semantic Provider owner remains
unavailable, with no candidate, independent experiment, installation or task
receipt. These source repairs do not upgrade the older immutable service.
Skill gain remains HOLD, natural gain UNKNOWN and method gain UNVERIFIED.

# Selected factual owner validation — 2026-11-06

V2 readback now compares the facts' top-level `run_id` with the current run,
in addition to its existing source, version and policy checks. An independent
isolated probe and root replay reproduced acceptance of a foreign facts owner
when test code deliberately rewrote the internal capsule and ledger references.
This is a historical-state consistency repair, not a demonstrated bypass through
the supported factual ingress or an observed production exploit.

Before repair, two wrong-owner refusal cases fail while the valid control passes.
The repaired factual and attribution suite passes 82 checks, including review
consumption, restart and retention of the dispatched snapshot after source
restoration. The required-Docker backend suite passes 454 checks. Existing
legacy ingress, attempt costs and unknown-side-effect recovery remain unchanged.

The Vite pin moves from 6.4.4 to the maintainer's
[6.4.5 patched version](https://github.com/advisories/GHSA-8g5g-mxqh-grgj).
The dependency audit drops from one moderate advisory to zero. A loopback
synthetic-file control serves normal JavaScript and refuses four denied-file
request variants. This custom control already refused them before the update;
it is a serving regression check, not a reproduction of the advisory's exploit.

Three bounded batches account for 36 obligations across 36 distinct sessions.
Twenty-three sources receive selected goal, terminal and tool inspection;
eighteen deterministic patrol results retain NO_CHANGE and backlog 0/6. Eleven
exact sources are absent and two source schemas remain unverified. One
oversized-record gap and a truncated tool output remain visible. Full-window
and natural-origin coverage are unknown. Original game/device/ads acceptance,
quality-label and Provider-recovery follow-ups retain their original owners.

The collector, review scheduler and evolution scheduler continue progressing.
The four selected factual sources remain absent; a bounded alternative lookup
does not establish an observed capability version. Eight factual capsules and
28 reviews retain no candidate, experiment, installation or independent task
receipt. The original semantic owner remains unavailable. This source repair
does not upgrade the older immutable service. Previous scheduled runs are
automatically archived; current post-final archival is not yet verifiable.

Contract, distribution, clean-wheel behavior and final source/remote/CI identities
are checked at delivery. Skill gain remains HOLD, natural gain UNKNOWN and
method gain UNVERIFIED.

# Shared factual ingress and exact Desktop observation — 2026-11-05

An independent engineering check reproduced a remaining selection-ownership
failure: the legacy factual import could replace a completed builder's receipt,
while its selected capsule stayed unchanged and the replacement remained
consumable. Both write paths now check the exact source/policy selection inside
the existing transaction. A conflicting import refuses; historical receipt
mismatch blocks consumption. Restoring the exact selected facts recovers without
replaying a model task. New source/policy facts and legacy-first input remain
supported; historical artifacts and attempt gates are retained.

Before repair, four mixed-ingress/refusal/recovery cases fail while two new-source
controls pass. The repaired factual, attribution and recovery suite passes 79
checks. A separate exact-version repair admits the observed Desktop
`0.166.0-alpha.6` shape through the existing strict identity gate. CLI, child,
identity mismatch and unknown versions remain refused. Six unchanged real
sources reach captured EOF in two passes each: 118 events, zero record gaps and
zero duplicates on reopening. The adapter suite passes 34 checks.

Three bounded batches account for 36 conversation obligations across 30 distinct
sessions. Twenty-two selected goal/terminal/tool views cover 16 distinct sources;
each captured prefix is rehashed to its frozen EOF. Twelve exact sources are
absent and two interactive CLI shapes remain unverified. Selected views retain
35 distinct oversized-record gaps. Full-window and natural-origin coverage
remain unknown. Existing product-adapter corrections, film acceptance and
Provider-recovery follow-ups stay with their original owners; no other-project
operation is replayed.

All three installed worker lanes continue progressing. Eight factual capsules
retain three consumable and five source-drift results. Twenty-eight reviews and
722 production attempts have produced no candidate, experiment, installation or
independent task receipt. Four selected factual-input sources remain absent,
including both sources with verified capability versions. The original semantic
Provider owner is still unavailable; its qualification and all-attempt cost gates
remain HOLD. These source repairs do not upgrade the older immutable service.

Validation passes 451 backend checks with required Docker execution and nine
actual API/DOM checks. Contract, source distribution and clean-wheel identities
are checked at delivery, including actual CLI behavior outside the checkout.
The previous scheduled run is automatically archived; current post-final archival
is not yet verifiable. Skill gain remains HOLD, natural gain UNKNOWN and method
gain UNVERIFIED.

# Atomic factual selection and collector recovery — 2026-11-04

A concurrent-build reproduction found that two different factual selections
could both succeed while the completed build and consumable capsule named
different selections. Selection ownership, factual binding, safe job reopening
and the completed build now commit in one SQLite transaction. Concurrent
different selections refuse the loser; identical selections remain idempotent.
An injected completion failure rolls back both the receipt and job reopening.
Before the repair, both refusal/rollback cases fail while the identical-input
control passes. The repaired factual and attribution suite passes 73 checks.

The installed collector had also stopped after a retired routing dependency
became unavailable during private owner-module import. The local owner now
loads that dependency only when required and declares an explicit reviewer
HOLD while it is absent. The existing immutable service was restarted through
its lifecycle owner: collection, review scheduling and evolution scheduling
resume; semantic execution remains blocked. No provider fallback, model call,
unknown-attempt replay or installed runtime upgrade occurred.

Three bounded batches account for 36 conversation obligations across 35
sessions. Twenty-two selected source views cover 21 distinct sessions; all
captured prefixes are rehashed to their frozen EOF. Twelve exact sources are
absent, one retains an index/source cwd mismatch and one has an unverified
source schema. The selected views retain 308 distinct oversized-record gaps.
Full-window and natural-origin coverage remain unknown. Original-owner device,
player, chapter-page and recovery follow-ups remain open; no other-project
operation is replayed.

A bounded alternative factual-source lookup finds available transcripts but no
verified capability versions; inferred attribution is not promoted. Eight
factual capsules still have three consumable and five source-drift results.
Twenty-eight reviews and 722 production attempts have produced no candidate,
experiment, installation or independent task receipt.

Validation covers 443 backend checks: the first run passes 429 and records 14
container-environment errors; starting the existing container runtime makes all
14 refused setup cases pass. Nine actual API/DOM checks, contract/build/archive
checks and clean-wheel actual CLI/doctor pass. The wheel also passes all three
new concurrency, idempotency and rollback cases outside the checkout. Final
source/remote/CI identities are read back at delivery. Skill gain remains HOLD,
natural outcomes UNKNOWN and method gain UNVERIFIED. New source repairs are
not claimed to be active in the older immutable service.

# Reviewed source selection — 2026-11-03

An independent engineering check reproduced a factual-binding defect: after a
run acquired a new terminal event, resubmitting the old selection silently bound
its old conclusion to the new source. The builder now requires the reviewed
plan's `source_fingerprint` and rejects source or policy drift before attaching
facts. A new review can select the changed source explicitly. Same-source retries
remain idempotent; old receipts, attempts and consumption gates are preserved.
The legacy factual-import contract remains unchanged.

The original implementation accepts a stale completed conclusion after an
Interrupt. Removing the new guard makes four drift regressions fail while two
same-source controls pass. The repair passes 70 factual checks and 440 backend
tests with required Docker execution. Nine actual API/DOM tests, contract and
distribution checks pass. A clean wheel's actual CLI accepts the initial build
and duplicate, refuses the changed source without replacing its receipt, and
passes doctor. Installed package bytes match the reviewed wheel and source.

Three bounded batches account for 36 conversation obligations across 31 distinct
sessions. Twenty-three selected source views cover 18 distinct sessions; each
captured prefix is rechecked against its frozen EOF and hash. Twelve exact sources
are missing and one retains an index/source cwd mismatch. The selected views
retain 272 distinct oversized-record gaps. Earlier auxiliary tool extracts could
include appended lines; those records are retained separately from the corrected
snapshot-bound readback. Full-window and natural-origin coverage remain unknown.
Current provider continuation recovery, chapter review and device/player
acceptance stay with their original owners; no uncertain operation is replayed.

The worker lanes continue progressing. Eight factual capsules retain three
consumable and five manifest-drift results. Twenty-eight reviews and 722
production review attempts have produced no candidate, experiment, installation
or independent task receipt. Four selected factual-input sources, including two
with observed versions, remain absent at their exact indexed/archive filenames.
The existing semantic qualification and all-attempt cost gates remain unchanged.
The installed immutable service has not been upgraded to the newer source fixes.

The native scheduler records this run in progress and the prior two runs
automatically archived; current post-final archival is not yet verifiable.
The configured next run is retained. Final source/remote/CI identities are read
back at delivery. This is an engineering repair: Skill gain remains HOLD,
natural gain UNKNOWN and recursive-method gain UNVERIFIED.

# Historical App child observation — 2026-11-02

The exact `0.164.0-alpha.11.1` App direct-child shape is now admitted through
its existing strict identity gate. Real child metadata and its parent's native
spawn receipt bind the transport, logical parent and execution identity. A new
case fails before repair while the CLI and newer App controls pass. All 32
transcript regressions pass after repair; malformed identities, alternate
origins, nested children and unverified versions remain refused.

The unchanged real source reaches captured EOF in three passes with 38 events.
Reopening produces zero duplicates and preserves child, parent, root and actor
identity. Selected body readback recovers the historical engineering review;
its original limited scope is retained, without independent domain acceptance.
The original refused projection remains separate from the repaired source view.

Three bounded batches account for 36 conversation obligations. Including the
recovered child, 23 sources receive selected goal/terminal/tool inspection;
12 exact sources remain unavailable and one retains an index/source cwd
mismatch. Selected views have no oversized-record gaps. More sources remain;
comprehensive window and natural-origin denominators remain unknown. Current
recovery, unfinished interviews and device/player acceptance stay with their
original owners. No uncertain external operation is replayed.

All three installed worker lanes are progressing. Eight factual capsules retain
three consumable and five manifest-drift results; 28 reviews and 722 production
review attempts have produced no candidate, experiment, installation or
independent task receipt. Two version-bound factual sources remain absent.
Existing semantic qualification and all-attempt cost gates stay unchanged.
The immutable service has not been upgraded to the newer source repairs.

Validation passes 435 backend tests with required Docker, nine actual API/DOM
tests, contract/archive checks and 32 transcript tests against a clean wheel
outside the checkout. All 30 installed Python files match the source; CLI doctor
passes. The first transcript run retained a valid refusal but failed its old
expected error stage; that expectation was corrected without removing the case.
Final source/remote/CI identities are read back at delivery. Skill gain remains
HOLD, natural gain UNKNOWN and recursive-method gain UNVERIFIED.

# Exact App child observation — 2026-11-01

A real `0.166.0-alpha.5.1` App direct-child source was refused by the
existing adapter. Its metadata and its parent's actual native spawn receipt
establish the exact transport and child identity. The adapter now admits that
single direct-child shape through the existing strict CLI-child identity gate,
with the App originator required. Nested children, alternate origins, mismatched
parents, malformed depth and unknown versions remain refused.

The new App case fails before the repair while the existing CLI control passes.
After repair, 31 transcript regressions pass. The actual unchanged source reaches
its captured EOF with 52 events in an isolated ledger; reopening adds zero events
and preserves child, parent, root and actor identity. The original worker remains
interrupted without a completed review artifact. Observation recovery does not
convert that task into accepted independent evidence.

Three batches account for 36 conversation obligations across 35 distinct sessions:
23 source views (22 distinct sources) receive bounded selected goal/terminal/tool
inspection, 12 exact sources are unavailable and one retains an index/source cwd
mismatch. No oversized-record gap occurs in these
selected sources. Full-window, comprehensive manual and natural-task coverage
remain unknown. Current source changes retain immediate follow-up. Historical
memory-path failure, current partial recovery/review work and actual App-menu
acceptance remain with their original owners; no external operation is replayed.

The current ledger has eight factual capsules: three remain consumable and five
retain source-manifest drift refusals. Two version-bound pending tasks still lack
their exact original/archive sources. There are 28 reviews and 722 production
review attempts, with no candidate, experiment, installation or independent task
receipt. Existing semantic qualification and all-attempt cost gates remain;
no exposed or consumed attempt is reused. The installed immutable runtime has
not been upgraded and still lacks newer source repairs.

A configured independent engineering reviewer performed actual public-source
reads but returned no completed reproduction or final artifact after a bounded
correction. It was closed as partial, with its costs retained. The root checked
the identified accounting boundaries and 14 relevant refusal/recovery cases pass;
no independent review success or second source defect is inferred. One reused
private projection path was overwritten during a fresh source review; the earlier
35-record source prefix still matches its frozen SHA-256, while the original
projection-file bytes remain unavailable. Subsequent batch views are separate.

Validation passes 434 backend tests with required Docker, 46 focused contract
and transcript checks, nine actual API/DOM tests, archive audit and 31 transcript
checks against the exact wheel outside the checkout. All 30 installed Python
files match current source and the installed CLI doctor passes. The initial full
run failed two contract checks after a regression test entrypoint was renamed;
its original entrypoint was restored before the passing run. Failed harness and
review attempts remain in private evidence. Final Git/remote/CI identities are
read back at delivery. Skill gain stays HOLD, natural gain UNKNOWN and recursive
method gain UNVERIFIED.

# Exact ingress and origin-bound factual reads — 2026-10-31

Independent public-source review reproduced a separate attribution defect:
a canary read could supply the observed Skill version for an ordinary run,
and different origins could merge into one invocation. The root reproduced
the original case and control. Invocation updates now reject origin changes;
factual selection and consumption require a matching origin and an actual
verified-read observation. This also withholds legacy aggregates whose label
conceals a cross-origin read. Receipts and consumed attempts are preserved.
Mixed-origin events are quarantined with their original bytes before changing
a run; valid observations can continue without replaying the refused event.
Synthetic usage metadata remains supported and cannot supply an ordinary run.

Thirteen refusal regressions fail against the original modules while two valid
controls pass. The repaired source passes 70 focused factual/usage cases,
including bidirectional origin mismatch, legacy v1/v2 consumption, duplicate
receipt readback and same-origin multichannel recovery. These are isolated
mechanism checks, not evidence of natural task gain or a complete activation
bypass. The independently reviewed finding is accepted; domain evaluation stays
with its existing owner.

Four authorized Desktop sources establish the exact `0.166.0-alpha.5.1`
shape; one standalone CLI source establishes `0.166.0` exec. The existing
adapter now admits those combinations with the same source, origin and session
identity checks. New App exec/child shapes, CLI children, incompatible identities
and future versions remain refused. Four new cases fail before the repair;
33 focused transcript tests pass after it.

All five real sources reach their captured EOF in isolated ledgers, with 24,
26, 20 and 20 Desktop events and 15 CLI events. Every source is unchanged during
validation, retains its execution identity and produces zero duplicate events
after reopening. Runtime events do not establish original task acceptance.

Validation passes 433 backend tests with required Docker execution, nine actual
API/DOM tests, build/distribution audit and 103 focused tests against the exact
current wheel outside the checkout. All 30 installed Python files match the
source; the installed CLI and doctor pass. The initial installation check chose
a historical wheel and failed; its result is retained separately from acceptance
of the current build. Final Git/remote/CI identity is read back at delivery.

Two batches account for 24 conversation obligations: 13 receive bounded body
inspection, nine exact sources are unavailable, one available transport shape
remains unverified and one retains an index/source cwd mismatch. Two large sources
retain 16 oversized-record gaps. Selected latest tool readback preserves original
visual-review and independent-owner follow-ups; partial historical workers are
not accepted independent validation. More sources remain; full-window and natural
task denominators are unknown.

All three installed worker lanes are progressing. No service update or global
Skill write is performed; the immutable installed runtime still lacks accepted
newer source repairs. The factual/evaluation chain retains eight capsules, 28
reviews and 722 production review attempts, with no candidate, experiment,
installation or independent task receipt. Existing missing-source/version,
protocol qualification and all-attempt cost obligations remain. Skill gain stays
HOLD, natural gain UNKNOWN and recursive-method gain UNVERIFIED.

# Selected factual input recovered — 2026-10-30

One authorized historical task now has a version-bound v2 factual capsule through
the existing `evidence-plan` / `evidence-build` owner. Selected source records bind
the task goal, success criteria, exact observed Skill version, execution/turn and
model/runtime evidence. Actual readback succeeds; the identical submission is
idempotent and creates no model attempt. Runtime termination and compaction
handoffs retain an unknown task result. A comparison command returning differences
is not treated as independent failed validation or evidence of Skill causality.

The ledger contains eight factual capsules: three currently pass consumption
gates and five retain manifest-drift refusals. Production review attempts remain
722, with no candidate, experiment, installation or independent task receipt.
Background semantic qualification remains HOLD under its original protocol;
no old attempt was replayed or qualification threshold changed. The remaining
version-bound historical source gap is unavailable at its exact indexed/archive
location. Other missing-version obligations remain visible.

Two batches account for 24 conversation obligations. Fourteen source bodies
received bounded inspection, including two without completed tool work; nine
exact sources are unavailable and one has a source/index cwd mismatch. Two large
document sessions retain 39 oversized-record gaps. An additional selected
historical turn supplied the new capsule; neither its scanned record count nor
terminal-looking handoffs establish comprehensive manual or task acceptance.
One recent maintenance session discarded process metadata, repeated a command
and retained no execution terminal; both attempts remain unresolved with the
original owner. More sources remain pending, with full-window and natural-task
denominators unknown.

All three installed worker lanes are progressing and the sampled spool is empty;
no service change or runtime upgrade was performed. The previous scheduled run
is archived; this run's archival can only be verified after completion. Fifty
focused evidence-builder, recovery and authority tests pass, as does the project
contract check. Only this public status record changes; source behavior and
installed global Skills are unchanged. Skill gain remains HOLD, natural gain
UNKNOWN and recursive-method gain UNVERIFIED.

# Desktop ingress and stalled-lane recovery — 2026-10-29

Five actual authorized sources establish the exact `0.165.0-alpha.1.2`
Desktop metadata shape. The existing adapter now admits it through the Desktop
source/origin gate. Desktop-only shapes also require equal execution and logical
session IDs before a cursor or spool event can be created. Fresh mismatched
identities are refused, including the previously admitted `0.164.0-alpha.11.1`
shape. New App CLI exec/child shapes and future versions remain unverified.
Four focused cases fail before the repair; all 26 transcript tests pass after it.

The five real sources reached their captured EOF in isolated ledgers, producing
24, 20, 18, 22 and 16 events. Each retained its own execution identity and one
terminal run; reopening each ledger produced zero duplicate events and no
semantic gap. Captured termination does not establish original task acceptance.
Required-Docker backend validation passes 414 tests. Nine actual API/DOM tests,
97 focused tests against a clean wheel outside the checkout, the installed CLI
and doctor pass. All 34 installed package files match. Contract and distribution
checks pass; final Git/remote/CI identity is checked at delivery. The first Web
test overlapped dependency installation and could not find its test executable;
the completed-build retry passes. That root coordination error remains rework.

The existing service had an HTTP listener but all three worker receipts had
stopped advancing for about 20 hours, with 10,915 spooled deliveries. Ledger
integrity passed; the pre-restart process sample showed idle executor threads.
After a verified database/configuration/health backup, the original lifecycle
stopped and started the same installed package. All three lanes resumed progress
and the sampled spool drained to zero. Configuration and build hashes are
unchanged. The original stall cause is not conclusively established; recovery
alone does not prove a preventive fix. Existing source-level worker failure
recovery regressions pass. This is operational recovery, not a runtime upgrade;
accepted newer source repairs remain absent from that immutable installation.

Two batches accounted for 24 conversation obligations: 15 received bounded
body/tool review, eight exact sources were unavailable and one retained an
incompatible index/source cwd. A large research source was inspected only at
selected goal, terminal and tool boundaries. Four changed frozen sources retain
immediate follow-up. Historical partial recoveries and unresolved proposal
ownership remain with their original owners. More sources remain; full-window
and natural-task denominators are unknown.

Chain readback retains seven factual capsules, 28 completed reviews and 722
production review attempts. Reviews contain 22 HOLD and six NO_CHANGE decisions;
there is no candidate, experiment or installation. Two capsules pass current
consumption gates; five retain manifest-drift refusals. The four exposed factual
fingerprints and their goal/version gaps are unchanged. Background semantic
qualification still refuses under its original frozen protocol; no old model
attempt or cutoff was replayed. Ordinary external audit admission also refused
because the current App artifact lacks exact native-child certification; the
root completed local validation without changing that gate. Skill gain remains
HOLD, natural gain UNKNOWN and method RSI UNVERIFIED. The prior scheduled run is
archived; this run's archive is verifiable only after completion.

# Review consumption, pending isolation and CLI ingress — 2026-10-28

Independent review reproduced two additional input-boundary defects. Late review
readback could consume revoked facts after restart; a daily pending batch resumed
by a different root could expose and accept that root's own work item. The root
reproduced both with isolated synthetic inputs. Normal model completion and late
readback now check current authorized facts against the dispatched capsule inside
the acceptance writer transaction. Missing bindings, policy/version drift and
corrupt artifacts are refused while terminal output and known usage remain.
Restoring authority permits the same returned result to be checked without a
new model turn. Original unknown attempts are not reopened or erased.

Daily pending views now suppress the current root and its descendants using
frozen lineage, including supported and unknown-version children and indirect
descendants. The original manifest and unfinished obligations remain unchanged
for later roots. Daily receipts recheck this exclusion and reject the entire
receipt on violation; explicit selected-session review retains its own workflow.
Eleven new regressions fail before the repairs and pass after them; additional
coverage checks revocation at the atomic acceptance boundary.

Two actual `0.165.0` standalone CLI sources and two native direct-child sources
established the new exact shapes. The adapter now admits those combinations
while requiring matching source, origin, execution identity and logical parent.
The child gate requires native spawn metadata and the observed depth of one;
nested CLI children, incompatible Desktop shapes and future versions remain
refused. Hook/transcript reads retain one logical invocation and the child's
independent identity. Three regressions fail before the change and pass after it.

All four real sources drained to their captured EOF in isolated ledgers, with
28, 41, eight and eight events respectively. Reopening each ledger produced
zero duplicate events. Neither captured CLI source had task completion;
child terminal records do not establish original task acceptance or natural gain.
Validation passes 411 backend tests with required Docker execution, 23 focused
transcript tests and nine actual API/DOM tests. A clean wheel installed outside
the checkout passes 153 focused tests; all 34 package files match and its actual
CLI and doctor pass. Build and distribution audit pass. Final Git/remote/CI
identity is checked at delivery.

Two batches accounted for 24 conversation obligations. Fourteen sources received
bounded body/tool review, nine exact sources were unavailable and one retained
incompatible source/index cwd identity. A large game source retains 19 oversized
record gaps; skipped records were hashed, not counted as reviewed. Five changed
frozen sources retain immediate follow-up. Historical transport failures,
incomplete recovery and device acceptance remain with their original owners.
More sources remain; full-window and natural-task denominators are unknown.

The live lanes remain healthy and ledger integrity passes. Current readback
retains seven factual capsules, 28 reviews and 722 production review attempts;
two capsules pass current consumption gates and five retain manifest-drift
refusals. The four exposed factual-input fingerprints and their original
goal/version gaps are unchanged. The earlier independent background qualification
remains refused, with no new protocol or proof; no unchanged semantic review was
dispatched. The immutable service still uses its earlier build. Source delivery
does not authorize a runtime upgrade or establish Skill improvement. Skill gain
remains HOLD, natural gain UNKNOWN and method RSI UNVERIFIED. The previous
scheduled run is archived; this run's archive is verifiable only after completion.

# Evidence authorization, exact exec ingress and qualification — 2026-10-27

Independent source review reproduced two factual-input failures: built capsules
remained consumable after observation-scope revocation, and a parent run could
bind a version read by another actor in the same session/turn. Factual planning,
attachment and consumption now share the exact invocation predicate used by
formal attribution, including actor, cwd and evidence-bound verified reads.
Cached pending projections refresh that predicate. Consumption rechecks current
scope, stored run identity and frozen v2 policy/source; invalid facts are withheld
while original receipts remain intact. Reviewer setup rechecks before transport
creation and before sending the model turn, covering revocation during admission
and thread setup. The independent reproducers and all 12 new regressions fail
against the earlier implementation and pass after repair. Authorized restoration,
restart, legacy v1/v2 receipts and original no-replay/history behavior are covered.

Two actual sources established the exact `0.164.0-alpha.11.1` App-bundled CLI
exec shape. The existing strict exec adapter now admits that combination, with
matching source, origin and session/execution identity required. Desktop handling
and refusals for native children, incompatible sources and future versions remain.
Both real sources drained to their captured EOF in isolated ledgers, producing
45 and 77 events; reopening each ledger produced zero duplicate events. Neither
source has terminal task completion, so their task outcomes remain unknown.

The two original regressions fail before this change and pass after it.
Validation passes 396 backend tests with required Docker execution, nine actual
API/DOM tests and 114 focused tests against a clean installed wheel outside the
checkout. All 34 installed package files match; the CLI, doctor, contract and
distribution audit pass. Final Git/remote/CI identity is checked at delivery.
The existing immutable service has not been upgraded.

Two batches accounted for 24 conversation obligations: 14 sources received
bounded body/tool review, nine exact sources were unavailable and one retained
incompatible index/source identity. Changed frozen sources retain immediate
follow-up. Historical interrupted reviews, incomplete Provider recovery and
research-service failures retain their original owners. More sources remain;
full-window and natural-task denominators are unknown.

Current original-owner execution authentication now returns HTTP 200. A new
isolated qualification completed both synthetic nonce turns and a schema review,
with terminal usage, no tools forwarded and no retries. The frozen qualification
still refuses: it requires an unverified outcome, while the returned review records
`runtime_only/failed`. The failed qualification, transport and usage are retained;
no schema proof was published, no consumed turn was replayed and no credential or
production configuration was changed. Reviewing that outcome constraint belongs
to the original qualification owner; it cannot be relaxed against this output.
Monetary cost remains unknown.

All three live lanes continue progressing and ledger integrity passes. Current
source readback retains all seven factual capsules and 722 production review
attempts; two capsules pass current consumption gates and five reviewed runs
retain their existing manifest-drift refusals. No historical evidence is deleted
or attempt reopened. The four exposed factual-input
fingerprints and their original goal/version gaps are unchanged; no unchanged
production semantic review was dispatched. Independent task truth, all-attempt
costs and natural comparison samples remain incomplete: Skill gain HOLD, natural
gain UNKNOWN and method RSI UNVERIFIED. The previous scheduled run was archived;
this run's archive can only be verified after completion.

# Daily receipt scope, current CLI ingress and qualification — 2026-10-26

Independent source review reproduced a permission gap: an unselected daily chat
could accept a repair receipt after its observation scope was revoked. Every
chat receipt now rechecks current observation scope before source inspection or
accounting. Pending manifests remain frozen; selected items additionally require
diagnostic scope. The original reproducer and a public regression fail before
the fix and pass after it. Coverage includes restart, whole-receipt rollback,
unrelated authorized metadata-only work, scope restoration and idempotence.

Two authorized sources established the exact `0.164.0` standalone CLI exec
shape. The existing adapter now admits that version through its strict CLI,
origin and matching session/execution identity gates. Desktop, child, mismatched
identity and future-version refusals remain. The existing regressions fail on
the prior source. Both actual sources drained to their captured EOF in isolated
ledgers and produced no duplicate events after restart; one original task was
still active, so this does not establish its completion or outcome.

Validation passes 382 backend tests with required Docker execution, nine actual
API/DOM tests and 100 tests against the clean installed wheel outside the
checkout. All 34 installed package files match; the CLI and doctor also pass.
Contract,
distribution and final source/remote/CI identity are checked at delivery.
The existing immutable background installation has not been upgraded.

Two batches accounted for 24 conversation obligations. Fourteen sources received
bounded body/tool review; eight exact sources were unavailable and two retained
incompatible source or index identity. Changed frozen sources retain immediate
follow-up. Historical hourly-gate timeouts, interrupted delegated reviews and
Provider recovery tasks retain their original owners. More sources remain;
the full-window and natural-task denominators are unknown.

All three background lanes were progressing and the ledger integrity check
passed. Their health does not establish semantic review readiness: the existing
reviewer's transport/schema proofs bind an older Codex binary. One isolated
renewal through that unchanged owner failed on its first synthetic turn, with
two observed HTTP 401 exchanges and unknown usage/cost. Later qualification
steps did not run; the failed turn was not replayed, no proofs were published
and production configuration remained unchanged. Current authenticated transport
and exact-runtime schema proof are required from the original Provider owner.
Quota health does not establish execution authentication.

The four exposed factual-input fingerprints are unchanged, with original goal
or observed-version gaps retained. A bounded alternative source contained its
original user request and observed historical Skill version. Its selected
tool/terminal records were checked against event offsets and call/turn identities
and bound through the existing factual builder. Legacy record-digest, environment,
cost and natural-origin gaps remain explicit. The chain now has seven factual
capsules and 28 completed reviews, without a candidate, experiment or installation.
The renewed factual input remains subject to background qualification; no
unchanged semantic review was dispatched. Skill gain remains HOLD, natural gain
UNKNOWN and method RSI UNVERIFIED. The previous scheduled run's archive was
verified; this run's archive can only be checked after completion.

# Current Desktop ingress and bounded review — 2026-10-25

Two actual archived Desktop transcripts established the exact
`0.164.0-alpha.11.1` source shape. The adapter previously refused that version;
it now accepts only its verified Desktop surface. Its CLI and child surfaces,
future versions, incompatible origins and mismatched identities remain refused.
Both real sources drained to EOF in isolated ledgers, each producing 22 events;
reopening each ledger produced no duplicate events. The regression fails on the
prior adapter. This is source-format and recovery evidence, not Skill gain.

Validation passes 61 focused tests, 379 backend tests with required Docker
execution, nine actual API/DOM tests, the project contract and distribution audit.
The clean installed-wheel check verifies package bytes, the actual CLI and the
affected tests outside the source checkout. Final source/remote/CI identity is
checked at delivery.

Two batches accounted for 24 conversation obligations: 17 sources received
bounded body/tool review, five exact sources were unavailable and two sources
retained incompatible format or identity. Frozen sources that changed retain
immediate follow-up. Interrupted reviews, domain input failures and repeated
automation-memory path failures retain their original owners; tool failures
alone do not establish a Skill defect. More sources remain and the full-window
and natural-task denominators are unknown.

All three background lanes were progressing and no recovery restart was needed.
The existing immutable installation has not been upgraded to this source.
The previous scheduled run's archive was verified; the current run's archive
can only be checked after completion. The factual chain still lacks independently
accepted candidate, experiment and installation evidence. An exact available
historical source was rechecked for missing task-goal facts; repository guidance
and tool actions cannot substitute for its absent original request. No unchanged
semantic review was redispatched. Skill gain remains HOLD, natural gain UNKNOWN
and method RSI UNVERIFIED.

# Recurring worker recovery and bounded review — 2026-10-24

All three background lanes again stopped progressing while the HTTP process
remained responsive. Independent health receipts were over 15 hours stale and
the spool held over 6,000 deliveries. A native process sample showed the event
loop and idle executor threads; the ledger passed its integrity check, with no
nonterminal jobs or pending installations. These observations do not establish
the original failure cause.

After preserving a hash-verified, losslessly compressed database backup and
configuration evidence, the original service lifecycle restarted the same
immutable installation. All three lanes resumed and the spool drained to zero.
The service entry, configuration and loaded build remain unchanged. This is
recovery evidence, not a runtime upgrade or proof against another recurrence.

Two isolated lifespan regressions reproduced a separate reliability defect:
when both normal progress and failure-report writes raise, the worker task exits;
a malformed watchdog receipt can also end checks for all subsequent lanes.
Failure reporting now retains a typed log and bounded backoff, and watchdog
errors remain isolated to their lane. Cancellation still stops the tasks and
no callback is cancelled or replayed by the watchdog. Both cases fail on the
prior source and pass after the repair; focused recovery checks pass. This
mechanism is not established as the cause of the observed production stall.
The existing immutable background runtime has not received this source repair.
An external review attempt was closed without a final deliverable; the root
performed reproduction and acceptance, with all attempt costs retained.

Two persisted batches accounted for 24 conversation obligations. Sixteen
sources received bounded body/tool review; six exact sources were unavailable
and two sources had incompatible identity or format. Three sources had changed
relative to their frozen worklist and retain immediate follow-up. Missing sources,
incomplete external reviews, interrupted work and domain data blockers retain
follow-up with their original owners. More sources remain; full-window and natural-task denominators are
unknown. The previous real scheduled run was archived by the native scheduler;
this run's post-completion archive cannot yet be verified.

The factual chain still has six capsules and 28 completed reviews, with no
candidate, experiment or installation. Previously blocked factual inputs retain
their exact source fingerprints and missing goals or observed versions; no
unchanged review was redispatched. No global Skill or cross-project owner was
modified. Skill gain remains HOLD, natural gain UNKNOWN and method RSI
UNVERIFIED. Applicable checks and final Git/CI identity are recorded at delivery.

# Review isolation, current App ingress and worker recovery — 2026-10-23

A real daily worklist selected its own child when an unverified transcript
version prevented normal identity extraction. The planner now uses strictly
index-matched child metadata solely to exclude the current root's descendants.
This hint does not admit transcript bodies or certify lineage for outcomes;
unrelated unknown versions and malformed identities remain visible gaps.

Two current Desktop transcripts were checked before admitting the exact
`0.163.0-alpha.11.1` App and native-child shapes through the existing adapter.
CLI substitutions, identity mismatch, missing child parents and future versions
remain refused. Both real sources drained to EOF in isolated ledgers, producing
10 and 30 events; restart reads produced no new events.

The original planner/parser regressions fail against the prior source. Current
validation passes 376 backend tests with required Docker execution, nine actual
API/DOM tests and 77 focused tests against a clean installed wheel outside the
checkout. All 34 installed package files match the wheel. Contract and archive
checks pass; final source/remote/CI identity is checked at delivery.

All three background lanes had stopped progressing for over 21 hours while the
HTTP service still responded. After preserving a verified private ledger/config
backup and confirming no nonterminal jobs or pending installations, the original
service lifecycle restarted the same immutable installation. All lanes resumed
and the 12,954-item spool drained to zero. The original stall's cause remains
unknown; this recovery is not a runtime upgrade or proof against recurrence.

Two batches accounted for 24 selected conversation obligations, including one
metadata-only acknowledgement of the incorrectly selected current child.
Sixteen other sessions had bounded body reads; five missing exact sources, two
unverified source shapes and oversized records retain coverage gaps. Changed
sources remain due for follow-up; more sources remain. An external review child
produced no effective tool result and was closed unused, with its attempt cost
retained. No independent review credit or new global Skill change is claimed.
Factual-input, independent-truth and natural-sample gaps remain: Skill gain HOLD,
natural gain UNKNOWN and method RSI UNVERIFIED.

# Daily selected-review scope revocation repair — 2026-10-22

Independent read-only review reproduced a scope-revocation gap: selecting an
item from a pending daily batch returned a transient selected view, but its
finish path did not retain the diagnostic requirement. Both observation and
diagnostic scope revocation could therefore leave that item's receipt accepted.
The shared batch now persists the selected item IDs and rechecks both scopes
before accepting their receipts, including after restart. Other daily items
retain their existing metadata-only accounting path.

The original regressions failed before the fix. Coverage checks whole-receipt
rollback, accumulated selections, authorization restoration, unchanged manifest
and unrelated work, idempotent selection/redelivery and source-drift behavior.
Applicable backend, distribution, isolated installation and final Git/CI evidence
are checked at delivery. The existing immutable service was not upgraded; no
global Skill, scope grant, oracle or installation authority was changed.

The daily review processed 24 conversation obligations across 23 sessions:
17 body reads covered 16 distinct sessions, seven exact sources were unavailable,
and one oversized record remains a hashed gap. Changed sources retain immediate
follow-up; full-window and natural-task coverage remain unknown. One new selected
factual capsule bound a delegated task contract, observed Skill version and exact
tool records. The original background reviewer completed with HOLD and recorded
usage; environment, independent outcome truth and monetary cost remain unknown.
This is reviewed input and a worklist repair, not independent Skill improvement.
Skill gain remains HOLD, natural gain UNKNOWN and method RSI UNVERIFIED.

# Exact stable CLI transcript ingress — 2026-10-21

The scoped daily review resumed the previous batch and reviewed a second batch:
24 conversation obligations across 23 sessions. Nineteen body reads covered 18
distinct sessions; five exact sources were unavailable, and two oversized
records remain hashed coverage gaps. Changed sources retain immediate follow-up;
active domain work remains with its original owner. This is bounded selection,
not full-window coverage or a natural-task denominator.

Two real standalone CLI transcripts were rejected solely because their exact
`0.163.0` version was not admitted. Their metadata and record structures were
checked before extending the existing exec adapter. Admission still requires
the CLI source, `codex_exec` originator, `exec` source shape and matching logical
and execution identities. Desktop/child substitutions, mismatched identities and
unverified versions remain refusals. Automation provenance is not natural-use
proof.

The original regression failed before the change. Both real sources drained in
isolated ledgers to 14 and 89 events; restart reads produced no new events.
Exact Skill-byte attribution, drift refusal, planner identity and source/version
rejection checks pass. Validation passed 362 backend tests with required Docker
execution and 15 transcript tests against a clean installed wheel outside the
checkout; contract and distribution audits pass. Final Git/remote/CI identity is
checked at delivery. The existing immutable service was not upgraded, and no
global Skill was changed. Independent final truth, all-attempt costs and later
natural samples remain incomplete: Skill gain HOLD, natural gain UNKNOWN and
method RSI UNVERIFIED.

# Daily factual-action visibility repair — 2026-10-20

Self-review reproduced a head-of-line obstruction: the four oldest factual
actions all lacked observed capability versions, hiding later selections with
exact version evidence. The bounded read-only projection now interleaves the
oldest version-bound selections with unresolved gaps. Each lane can fill the
available slots when the other is empty; built and superseded work stays out.
This changes neither source facts nor admission, installation or final truth.

The old projection failed the regression. Restart, stable ordering, progress
after completed selections, unresolved-gap retention and single-lane fallback
pass focused checks. Actual ledger readback exposes version-bound work while
retaining missing-version actions. One reviewed historical maintenance run was
bound to its observed version and source events through the existing evidence
builder; its known pre-dispatch job resumed and completed through the original
background reviewer with `NO_CHANGE` and recorded usage. Monetary cost and
independent improvement evidence remain unknown. This is selected review
input, not an independent improvement evaluation or a natural-task sample.

The daily review resumed the prior batch and continued into a new bounded batch.
Missing exact source files, source/cwd mismatches, uncertified versions and
oversized records remain coverage gaps. Existing domain work and active roots
retain ownership. Applicable backend, distribution, isolated installation and
final Git/CI checks are recorded at delivery. The existing immutable service
was not upgraded. Skill gain remains HOLD, natural gain UNKNOWN and method
RSI UNVERIFIED.

# Retrospective workflow implementation and runtime rollout — 2026-10-19

The authorized retrospective optimization is implemented and installed. The
existing experience owner now reviews seven environment aspects while retaining
root-cause attribution, deterministic-check preference, permission boundaries and
the requirement for behavior evidence before changing an apparently unused rule.
An independent forward exercise covered three mechanics fixtures and concluded
`no_change`; it does not establish natural-task improvement.

`retro-plan` selects one authorized session through the existing source adapter,
diagnostic scope and worklist ledger. Selected reviews share the original finish
protocol without consuming other daily items or advancing the historical cursor.
Independent code review reproduced a daily/manual duplicate-work CAS deadlock.
The repaired planner excludes pending selected work, and legacy batches can
explicitly acknowledge a newer exact receipt while preserving its canonical
review, follow-up obligation and supersession evidence. Scope mismatch, stale
overwrite and ambiguous batch identities remain refusals.

Capability reconciliation now binds root-reviewed installed bytes to exact prior
versions and evidence. Discovery remains read-only; history and original authority
are retained, including an explicitly pinned migration for unbound legacy
projections. Three reviewed local catalog entries were reconciled. This records
current package facts, not activation or gain.

The original private background-review owner was requalified with the current
tool-free model, exact schema/profile/source bindings and unchanged external
scopes. One known pre-dispatch factual job then completed through the original
kernel and returned `HOLD`, with terminal usage recorded and monetary cost
unknown. Six historical unknown attempts and their jobs were preserved exactly.
The final immutable service package is installed; actual API, all three workers,
settings, owner proof and authority readbacks passed. The existing daily trigger
is retained; no additional scheduler was introduced.

Validation passed 357 backend tests with required real Docker execution, 9 actual
API/DOM tests, distribution auditing and 56 focused tests against a clean installed
wheel outside the checkout. Independent code review verified the reported
concurrency fix. Final Git/remote/CI identity is checked at delivery. Skill gain
remains HOLD, natural gain UNKNOWN and method RSI UNVERIFIED.

# Daily factual work revision repair — 2026-10-19

The daily review resumed the pending batch and examined a second bounded batch.
Missing historical sources, an uncertified source schema, oversized records and
interrupted children remain explicit gaps. Active and domain-specific work stays
with its original owner; this is not full-window or natural-task coverage.

A real ledger readback reproduced obsolete factual work remaining actionable
after the current source/policy revision was already built. Planning now marks
older pending revisions superseded in the same transaction, retaining their
source identity, missing fields and successor. Historical built evidence remains
intact. Returning to an earlier policy reactivates its exact pending item; new
source facts remain pending. Self-review and material progress use these states,
while unrecognized work states remain visible.

A second regression reproduced a cached historical plan returning a capsule from
a different policy revision. Reuse now requires the exact selected capsule and
current run manifest, otherwise it refuses without attaching evidence or
reopening an attempt. Interruption rollback, source drift, policy return and
unchanged idempotency are covered. Actual reconciliation preserved the existing
capsule and attempt inventory and made no model call.

Validation passed 326 backend tests with required real Docker execution. The
actual API/DOM, contract, distribution and isolated wheel checks are recorded at
delivery. The existing immutable service and global Skills were not upgraded.
The background reviewer remains blocked because its fixed model is absent from
the canonical routable pool; ordinary child qualification cannot replace that
owner's background proof. New independent truth, feasible frozen all-attempt
budgets and natural follow-up evidence remain open. Skill gain is HOLD, natural
gain UNKNOWN and method RSI UNVERIFIED.

# Daily factual ingress repair — 2026-10-18

The resumed daily review completed a bounded source pass and continued into the
next worklist. Missing historical files, an uncertified editor source and oversized
records remain explicit coverage gaps; child and unclassified executions are not
natural improvement samples. Existing domain repairs remain with their original
owners, with no new installation or financial action inferred from their results.

A real selected-facts build reproduced an ingress defect: registered owner labels
containing spaces were refused by an identifier-only check. Evidence now reuses
the canonical registration text contract and still requires the exact catalog
owner, observed immutable version and bound source events. A real historical
capsule was built and one known pre-dispatch job resumed. It then deferred because
the configured background model is absent from the current routable pool; a
read-only original-owner plan confirms that boundary. No new review attempt was
dispatched. Model substitution needs the original owner's matching qualification;
ordinary child qualification does not certify background review.

Full regression exposed a separate test-environment dependency: a package-request
test assumed the host installer lacked package support. It now uses isolated
actual CLI fixtures for both availability states, retaining drift refusal and the
no-automatic-apply assertions. Validation passed 319 backend tests with required
real Docker execution, 9 actual API/DOM tests, contract checks, distribution audit
and clean wheel installation. Git/remote/final CI identity is checked at delivery.
This run did not upgrade the existing immutable service or change global Skills.
Skill gain remains HOLD, natural gain UNKNOWN and method RSI UNVERIFIED.

# Authorized owner and service rollout — 2026-10-17

The authorized infrastructure rollout is applied and read back. The original
managed installer now supports atomic package transactions, and the private
reviewer admits selected v1/v2 facts only within its original external scopes.
Separately authorized observation settings are preserved. Actual transport and
schema qualification completed with three requests, zero retries, zero tools
and 30,345 observed tokens; monetary cost remains UNKNOWN. The synthetic review
returned HOLD and supplies no independent domain or improvement verdict.

The first service start refused a missed shared-owner binding: `reviewer.json`
and `evolution.json` reference the same module. The latter still held its old
hash. Its old-binding refusal and matching-binding load were tested in isolation;
the unchanged pipeline factory was verified, then the existing binding was
updated through the original managed CAS/backup/readback workflow. No verifier
or permission gate was weakened.

The existing service now runs from a separate immutable wheel environment.
Process, package bytes, HTTP assets, all three workers and reviewer schema
certification match; the original ledger, settings and six historical unknown
attempts remain intact without replay. Original code, owner and database backups
are retained. The temporary implementation-follow-up automation remains paused.

The daily self item had already been reviewed by another root. The new
`proactive-followup` CLI appends evidence with batch/fingerprint/previous-evidence
checks and idempotency. Actual import and pending-batch resume expose the new
follow-up while preserving the original self result and 12 other pending items;
future self reviews retain those references. No new schedule was created.

Validation: 32 focused tests and 313 complete backend tests pass with required
real Docker execution; contract, build/distribution audit, installed-wheel CLI,
old-code recovery installation and live service readback pass. Source commit
`1bd933c3fb3cd4287a2092e29dc2f996c0674759` has passing CI. This closes the authorized
owner/reviewer/service/daily rollout, not the full evidence chain: independent
final truth, feasible frozen budgets, natural cohorts and next-generation method
evidence remain open. Skill gain is HOLD, natural gain UNKNOWN and method RSI
UNVERIFIED. No business Skill was promoted or installed by this rollout.

# Independent scheduled runs and authorized scope expansion — 2026-10-17

The existing daily review now uses a standalone task in this project's local
checkout, with native archive-after-completion enabled. The original daily time,
model and reasoning effort are preserved. A real scheduled lifecycle probe
created a fresh project session, persisted its private receipt, produced a final
answer and task-complete event, then was archived by the native scheduler.
Calling self-archive during an active turn was independently found to interrupt
the turn; the workflow therefore uses the scheduler's completion archive flag.
The temporary test schedule was restored, with one active automation identity.
Native scheduling jitter is distinct from the nominal daily time.

The newly authorized directory is registered for both observation and diagnostics;
its nested Provider project is included, while outside roots and sibling prefixes
remain excluded. Existing pending work is unchanged and resumes across sessions.
An actual standalone CLI 0.162.1 source exposed a previously unsupported format.
Its verified exec shape is now accepted by the source workflow, with source,
identity and future-version refusals retained. A real isolated parse and isolated
wheel readback pass; the existing immutable background service was not upgraded.

Validation: 33 focused regressions and 302 complete backend tests pass, including
required real-container execution; contract, build, archive audit and isolated
wheel checks pass. Lifecycle probes and scope admission do not establish full
review coverage, Skill gain, natural user benefit or method RSI. Private paths,
authorization evidence, configuration backups and run receipts remain local.

# Daily owner follow-up and engineering repairs — 2026-10-17

The daily owner resumed yesterday's unfinished batch and reviewed a second
bounded batch: 24 conversation items and two system items. Missing historical
sources, active source changes and original task-owner holds remain explicit;
this is not full-window or natural-outcome coverage.

A reproduced attribution defect is repaired in source. When PreToolUse captured
v1 but registration changed to v2 before PostToolUse, the old code could pair
v1 bytes with the current v2 package hash. The event and run now use the frozen
version, and absent bindings cannot fall back to current disk bytes. Positive,
wrong-version, legacy, privacy and duplicate-observation regressions pass.

The earlier managed command repair is now linked to its actual incident,
original-owner transaction, immutable version, source run and backup/readback.
It remains engineering_verified with missing historical applied_at preserved;
later verified reads alone do not certify activation or natural gain. The facts
sweep created eight explicit selection work items without model calls.

An existing v1-owner factual review ended failed after dispatch in about 156
seconds, with HTTP 200 transport completed and no local deadline expiry. Its
attempt and unknown usage/cost are retained without replay. Previous telemetry
kept only the generic error code other, so the exact cause is unknown. Source
diagnostics now retain a fixed failure category and error fingerprint, including
terminal-only errors, without provider prose or credentials. Qualification of
changed reviewer bytes remains required before their use.

Bounded collection recovered a selected large source through its captured EOF;
oversized records retain hashed semantic gaps and unknown affected coverage.
The original immutable v1 service was restored and read back healthy, with zero
closed unread tails at that observation. The full v2 service/global-owner rollout
and independent final inputs remain separate pending dependencies.

Validation: 301 backend tests passed with required actual Docker execution,
9 actual API/DOM tests passed, and contract/build/distribution plus isolated wheel
installation/readback passed. SQLite quick_check passed; the existing hot-history,
lossless archive and single ledger remain in use. No retention gate was lowered.

One previous private as-of readback file was accidentally overwritten by reusing
an earlier helper's fixed output. Its original hash remains recorded but the
original bytes are unavailable; the retention gap is explicit. Current readback
is stored separately, and the helper now requires an explicit output and refuses
overwriting existing files. Original Git/CI receipts remain intact. No historical
reconstruction or domain/Skill/natural/method gain is claimed.

# RSI integration — source stage accepted, 2026-10-17

The implementation candidate connects bounded collection recovery, versioned
Native-selected facts, actual native task-family execution, strict per-case and
all-attempt final reconciliation, full package identity, original-owner mapping,
natural cohorts and real method lineage. Material stage progress is separate
from worker heartbeats. Independent review accepted this source stage for the
already authorized Git delivery. Full engineering acceptance remains partial;
the existing user service has not been updated by this iteration.

| Layer | Current conclusion |
|---|---|
| Source stage | Accepted after independent F1–F16, installed-candidate/late-unknown-cost probes, 76 focused regressions and complete source/evidence identity readback |
| Complete engineering chain | Partial: independent final/budget, global original-owner package capability, reviewer v2 authority/qualification and actual daily-owner follow-up remain open |
| Live deployment | Not updated |
| Skill gain | HOLD |
| Natural user gain | UNKNOWN |
| Method RSI | UNVERIFIED |

Source acceptance authorizes this project's precise Git closeout; the actual
remote commit and applicable final-head CI are checked separately. It does not
authorize global owner/reviewer application, production deployment, a new model
attempt, a larger consumed budget or reuse of exposed final inputs.

An isolated copy of a real authorized task produced a v2 capsule without changing
the production ledger. An exposed CLI selection pilot ran both immutable historical
Skill packages in fresh native contexts under the same admitted model/maximum
verified effort. Both produced the same valid command. The frozen oracle's exact
evidence-list expectation rejected an additional valid evidence kind; those labels
are retained, rather than adjusted against consumed feedback. No difference gain
was observed. Independent final truth, enough cases and known monetary cost are
absent, and measured token usage exceeded the frozen cost ceiling. No promotion,
natural user gain or RSI certification follows from this pilot.

The actual original single-file installer was exercised in isolation, including
prepared interruption/recovery, readback, idempotency, rollback and drift refusal.
A minimal extension of that original owner, using atomic whole-directory exchange,
was also prepared and tested through the thin Observatory adapter in isolation.
It remains unapplied globally. The installed original owner's missing package
transaction capability is an explicit dependency, not a passed production gate.
The inspected existing reviewer owner admits capsule v1; v2 needs matching data
authority and fresh schema qualification against the changed reviewer. Refusal
tests prevent borrowing the older authority or dispatching an unapproved v2 call.

See [the execution integration](implementation/skill-rsi-2026-10-16/README.md) for
portable ingress, safety and follow-up contracts. Engineering checks are recorded
at candidate handoff; final Git/CI delivery follows independent acceptance.
Skill gain remains HOLD, natural gain UNKNOWN, and method RSI UNVERIFIED.

## Independent acceptance repairs — 2026-10-17

The revised candidate binds current native contexts and domain-owner execution
evidence, freezes both natural-cohort versions and per-task cost inventories,
advances a persistent bounded facts sweep, and scans growing large sources from
fixed private filesystem views. Final reuse rechecks exact inputs, runtime
attempt relationships and explicit terminal states. Special file mode bits and
nonregular package types refuse. Material progress follows actual HOLD/pending
work and readable bilingual actions.

A supported package request/proposal/pipeline flow was exercised with an
unchanged SKILL.md and a changed reference, 16 actual isolated container arms,
the prepared original-owner transaction, readback, fresh deterministic process
activation and rollback. Automatic promotion stayed disabled. Method comparison
now separates a design registered before generation from real output bindings
and the later final protocol; finite actual subprocess fixtures cover that
order. These are engineering fixtures, not evidence of Skill or recursive gain.

The current execution manifest now binds every file's exact supported mode
through the Docker loader's actual readback, Native collection, final
reconciliation and original-owner installation. Cached final usability rechecks
disk/package identity and expiring authority, while keeping historical signed
acceptance and final consumption. A matching original-owner installation or
prepared intent can explain the exact candidate bytes without a new experiment.

Natural samples bind a signed logical task identity and actual execution source;
receipt aliases and retries cannot increase an independent denominator or bill
the same task twice. Duplicate history remains visible and incomplete. Method
comparisons include the plan's full typed exploration/source/retry cost closure
and frozen budget. Current reports recheck method and downstream final validity;
historical verified facts do not preserve a revoked green status.

Validation and final package/clean-install identities are recorded in the
private revised handoff. Local validation passed 293 backend tests with required
Docker execution and zero skips, plus 9 actual API/DOM checks. The independent
review accepted the source stage, while complete engineering acceptance remains
partial. The installed global owner/reviewer and existing
user service are unchanged; v2 data authority/qualification and owner package
application remain separate dependencies. The daily-owner follow-up is a prepared
handoff and has not been imported into the production workflow. A new
current-protocol Native pair
actually read the frozen historical packages, used two tools per arm and passed
the parse-only task. Both produced an equivalent valid command, with no gain.
Measured use was 264,147 tokens against the unchanged 30,000-token policy; it
remains HOLD, alongside exposed/one-case/independent-truth and monetary-cost gaps.
The native spawn surface has no per-child input-token hard cap. No retries,
budget increase, reuse of the old final or revised consumed labels occurred.

# First scheduled review and repairs — 2026-10-16

The first daily heartbeat actually triggered. Its bounded review found fresh
conversation starvation behind the historical sweep, stale archived transcript
pointers, incomplete ordinary-delegation command examples, and a catalog-to-review
attribution gap. These were actionable engineering defects, rather than evidence
that every tool failure was caused by a Skill.

The worklist now rotates fresh, historical and due work with a bounded index
read; only historical scanning advances its cursor. Pending batches remain
immutable. Exact archived-basename recovery retains schema/session/cwd checks,
rejects symlinks and preserves missing follow-up references. Behavioral tests
cover fairness, cursor coverage, single-item budgets and refusal cases.

Verified capability reads now project the exact execution/turn/actor/cwd and
frozen historical package into review attribution. Catalog registration grants
no installation authority. Generation is constrained to observed identity tuples
or explicit unknown; local acceptance remains authoritative. The original real
attempt rejected for an unbound identity remains consumed. After a fresh synthetic
schema qualification, a different real task's selected facts completed semantic
review in about 45 seconds with correct historical attribution. Its HOLD identifies
missing environment/task evidence; it does not certify a Skill defect or outcome.

Two incomplete ordinary-delegation examples were replaced through their canonical
managed installer: real-work admission declares its workload class, and finish
supplies the required evidence kind. Installed/canonical bytes match, with backup
and rollback transactions retained. Natural reuse and task gain are still unknown.
One external coding child produced no patch after bounded warm recovery; it was
closed/rejected with its costs preserved, and the root completed the repair.

Validation: 179 backend tests passed with required real Docker execution, 9 real
API/DOM tests passed, and contract/build/distribution checks passed. An immutable
wheel runtime was installed through the existing service lifecycle after a
verified losslessly compressed SQLite backup. Loaded code, assets and reviewer
certification were read back. Storage maintenance continues to use SQLite and the
existing content-addressed/lossless archive owners; no new parallel store or ledger
was introduced. Coverage is bounded, with historical/active-source follow-ups
remaining; the global denominator is unknown.

This is an operating scheduled engineering-repair loop. Independent domain
comparison, natural downstream gain and accepted next-generation method lineage
are still missing: O2/O3 remain HOLD/UNKNOWN and O7 remains UNVERIFIED. Automatic
promotion remains disabled. Software delivery and final-head CI are checked
separately from these outcome claims.

# Earlier proactive implementation — 2026-10-15

A dedicated Native recurring review was absent from the inspected local schedules.
The owner-authorized daily heartbeat is now saved for 08:30 Asia/Shanghai and
points only to [PROACTIVE_REVIEW.md](PROACTIVE_REVIEW.md). It reviews authorized
recent Codex chats and this project's full observation-to-improvement chain,
including evidence gaps, absent candidates, independent evaluation, owner apply,
fresh activation, natural follow-up, method lineage, performance and storage.
The root retains its selected model/effort. A persisted active schedule does not
prove its first future trigger; that receipt remains a required follow-up.

`proactive-plan` reads only index metadata and bounded transcript headers within
configured scopes. Fingerprints, fair bounded discovery, unfinished-batch resume,
root receipts and due follow-ups reuse the existing private ledger. Current-root
and descendant executions are excluded, other sources remain explicitly
unclassified/child, and no review receipt certifies natural outcomes or grants
promotion. Missing evidence, unknown formats, index drift, changed source files
and repeated HOLDs remain visible. Source changes at finish force immediate
follow-up. No-change ends before additional semantic calls, though the native
daily root wake itself still has overhead.

The first real bounded audit inspected four historical sources plus the system
item; more sources remain, so this is not full-window coverage. It found missing
factual inputs, incomplete/taken-over child work and an unsupported historical
format. Existing recovered noise was not turned into additional Skill rules.
One original cause is fixed in project code: exact alpha.17.2 `codex_exec` child
metadata is supported, with source/identity/version refusal cases retained.
Independent review also found and led to correction of task-receipt kind naming,
readiness diagnostics, internal-source filtering and stale-source accounting.
Existing pipeline gates now expose read-only first-failure reasons; ambiguous
authority and unknown/held side effects are still refused, never reopened.

A collector defect skipped closed-session tails. The corrected collector drains
those tails without reattaching historical prefixes; initial attachment hashes
are streamed with bounded memory. Actual local service readback reduced 17
closed pointers with unread appended bytes to 0. Package code and served static
bytes match the dedicated immutable runtime. The active service and queue
progress are verified separately from task improvement.

Validation: 167 backend tests passed with the required real Docker runtime;
9 real API/DOM tests passed; project-contract checks, build/archive byte audits
and isolated immutable wheel import passed. Rollback runtime and a verified,
losslessly compressed ledger backup remain private. Private transcripts, state,
review receipts, machine configuration and automation identity are not distributed.
Final source/remote/CI identities are recorded in the private delivery receipt.

The new workflow actively performs authorized local repairs, including
replacement/refactoring/deletion when supported, through original owners.
It does not supply universal domain truth or automatically enable promotion.
Skill task gain and natural user gain remain UNKNOWN/HOLD; this project's method
RSI remains UNVERIFIED until accepted method lineage and independent downstream
comparison exist. The current factual-input backlog and historical coverage gaps
are follow-up work, not a completed self-improvement outcome.

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
