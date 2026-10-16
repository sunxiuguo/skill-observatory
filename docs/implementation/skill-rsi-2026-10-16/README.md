# RSI execution integration

This is the implementation boundary for the existing observation → facts →
independent task evaluation → original owner installation → fresh activation →
natural follow-up chain. It adds no scheduler, model pool, store or installer.
Automatic promotion remains disabled. Source delivery, deployed runtime, Skill
gain, natural gain and method recursion require separate acceptance.

## Collection and factual input

The collector and proactive reviewer share exact archived-basename resolution.
The configured Codex index supplies its parent directory; no global transcript
search is performed. Relocation verifies the selected identity and consumed
prefix, then atomically commits the pointer and cursor. Closed tails remain
eligible. Collector hashing/scanning has byte, record and time bounds.

Records above the semantic size limit produce durable hashed gaps after an LF
boundary. Scan progress is separate from semantic consumption; partial EOF never
advances the latter. Gaps and semantic cursor commit in one transaction. A gap's
unknown affected turn conservatively prevents success attribution. Hash state is
a disposable accelerator: restart reconstructs it in bounded ticks.

Terminal input changes produce an `evidence_builds` work item. The Native root
uses the existing trusted local ingress:

```sh
skillobs --state PRIVATE_STATE evidence-plan --run-id RUN_ID
skillobs --state PRIVATE_STATE evidence-build PRIVATE_SELECTION_JSON
```

The selection contains run_id, goal, success_criteria, owner, observed version_id,
result, steps (`event_id`, `fact`) and receipt_sha256. Optional artifact_refs and
attempt_refs use content digests. Unknown environment remains explicit. The v2
builder binds the original event manifest, full capability version, source class,
terminal, gaps, attempts and policy fingerprint. Local references remain private;
the reviewer must be admitted for the actual capsule schema. No-change makes no
model call. Only proven pre-dispatch waits reopen; unknown attempts need readback.

## Frozen native task family

`NativeTaskFamilyDriver` is the bridge to the host's already admitted native
spawn/bind tools. Its prepare step reuses the existing final-consumption kernel
before dispatch. Every arm gets its own full package and work directory. The
host performs the native tool invocation; the driver never spawns a shell LLM.

The local CLI exposes native-family-prepare, native-family-dispatch,
native-family-collect and native-family-result. Preparation reads a trusted spec
with protocol_sha256, parent_package, candidate_package, cases and work_root.
Cases bind input_files as name → artifact digest plus source/split/evidence and
optional regression/guardrail categories. Dispatch requires the exact admission,
child and root. Collection checks native session/model/effort/parent identity,
real tool traces, terminal, immutable inputs and actual outputs. Unknown money
stays unknown. The deterministic argparse oracle uses a frozen original CLI
parser, excludes mutation dispatch and pins its own implementation identity.

The exposed selection pilot executed both historical arms and produced equivalent
valid CLI commands. The original frozen oracle overconstrained an evidence list;
its negative labels are retained as an oracle limitation. It cannot certify a
Skill gain. Sample, independent-final, monetary-cost and budget gaps also remain.
A new final must be frozen and run by the independent owner, rather than tuning
against or reusing this consumed selection sample.

The v2 final kernel checks exact case/arm coverage, actual input/output/receipt
bytes, fresh execution contexts, independent frozen category coverage and paired
scores. It resolves typed attempt references, includes failures and retries,
checks token components/cached-input subset, currency and frozen wall basis, and
recomputes totals. Legacy accepted verdicts cannot bypass the new schema.

New protocols carry complete `arm_packages` execution manifests. The Docker
loader writes and reads back exact supported file modes as its unprivileged
user, in the same existing no-network/read-only-root/noexec/nosuid sandbox.
Trial receipts bind the complete loaded manifest and digest, including case
inputs. Final reconciliation compares that manifest, not a bytes-only digest.
Package protocols without a matching mode manifest HOLD; a runner without the
package-loading contract cannot certify that package. Existing bytes-only
single-file historical receipts retain their explicitly limited legacy scope.
Native collection also rejects full mode/type and special-directory drift.

## Packages and original owner

`packages.py` provides sorted content-addressed manifests with relative paths,
types, sizes, modes and digest. Evaluation, exact authorized changed_files and
owner requests share them. Symlinks, traversal, case collisions, partial packages,
wrong parents and unsupported executable modes refuse.

The installed generic original owner currently supports single-file transactions.
The adapter returns OWNER_PACKAGE_TRANSACTION_UNAVAILABLE for unsupported package
application. It does not simulate a package by calling a file installer repeatedly.
An original-owner extension has been prepared and exercised privately with atomic
directory exchange, a package prepared intent, interruption/readback, CAS and
rollback. Installing that global extension remains a separate owner authorization
step. Public software has no dependency on an author's private installation.
`package-change-prepare` freezes a matching authorized request; the thin adapter
can consume the original owner's package commands once that owner provides them.

`engineering-repair-import` links a real managed incident, transaction, immutable
version, run and disk/backup readback. This is engineering_verified, with no
invented independent improvement or installation timestamp.

## Activation, natural results and method lineage

Package activation additionally requires a fresh context's loaded package digest
and whole-package disk readback. Single-file receipts remain compatible.

cohort-register freezes an installation, task family, aware [start,end) window,
model/effort/harness/environment, independent natural source definition and known
or unknown denominators. cohort-sample-import requires independent task and
natural-source receipts. Canary/child/maintenance samples cannot become natural
outcomes. cohort-report keeps missing money, denominator and unobserved results
unknown. Pending outcome_followups are consumed by the existing daily reviewer.

method-register binds content, parent, proposer/selector-only scope and independent
acceptance. method-generation-bind requires a real execution, actual method read,
produced candidate and attempt lineage. A bare method string stays unverified.
method-comparison-bind requires separate preregistered old/new-method downstream
outputs and a v2 independent accepted verdict; it cannot reuse method acceptance.
The UI displays material stage evidence separately from worker health. Idle
callbacks do not advance factual, trial, installation or outcome timestamps.

## Execution and comparison ingress

The independent local execution owner signs `seal_native_execution` evidence;
this is not exposed as an HTTP or signing CLI. `native-family-dispatch` returns
the prepared ticket digest, child/admission binding and working directory.
`native-family-collect --execution-evidence FILE` requires that signed evidence.
The driver verifies creation after preparation, frozen context cwd, the latest
completed turn, paired tools, exact mandatory Skill/task read bytes, unchanged
inputs/modes and actual output hashes. Earlier failed tools may recover. The
owner separately attests which successful calls performed the relevant domain
operation and produced the artifacts, with the exact admitted runtime and tool
contract. A random successful tool or a preexisting result file cannot supply
that evidence. A native child can be created before dispatch/bind; bind time is
not used as an impossible lower bound on its creation.

Large growing sources use an immutable, unlinked private filesystem clone where
clonefile/FICLONE is supported on the source/state filesystem. Each view has a
fixed captured version; appended bytes wait for the next view, which verifies
the previously committed prefix again. Scanning still reads at most 4 MiB per
tick. Raw clone files are not retained. Stable files retain bounded scanning on
other filesystems; unsupported growing large sources explicitly HOLD with
TRANSCRIPT_STABLE_SNAPSHOT_UNAVAILABLE. Append does not grant permission to
ignore prefix drift, truncation, identity, scope or cursor CAS.

`grant_package_owner` is the trusted local human-authority ingress for exact
before/after manifests and changed files. A prepared package request is consumed
by `evolution-proposal-bind` with `package_request_id` and an existing original
owner package proposal. The same OwnerReceiptPipeline creates the candidate,
consumes a full-package measured evaluation/final, and uses the original owner
transaction. Only-reference/script changes are valid even when SKILL.md bytes
are identical. Default ticks keep automatic promotion disabled. An explicitly
authorized local owner can call `tick(explicit_installation=experiment_id)`;
that does not bypass the grant, final, CAS or owner readback gates. Missing owner
package capability leaves the request blocked. No installation implementation
is copied into this project.

Cohort schema 3 freezes `arm_bindings` for both installations and exact content
versions (complete package digests when packaged). The candidate's before
version must equal the actual parent. An independently signed task receipt must
bind the frozen `task_family_sha256` descriptor. Missing historical parents
remain blocked. Each signed task's `cost_manifest_sha256` attests its complete
typed attempt inventory. Empty refs are unknown unless a complete explicit
zero-cost receipt proves zero. Reports re-resolve every sample and known failed
or retried attempt; one known sample cannot hide another's missing costs.

New natural source receipts and the independent task receipt must agree on
`logical_task_id`; the task receipt additionally binds
`natural_source_definition_sha256`. Sample ingress atomically binds that logical
task and the actual execution session/turn or event source, separately from
receipt/sample IDs. Re-signing, aliases or retries cannot create independent
samples. Distinct actual tasks in one session remain separate. Costs from later
signed runs of the same task remain required even if their duplicate sample was
refused. Legacy duplicate or missing-identity rows stay visible with explicit
coverage gaps and unknown aggregates; they are not silently migrated to valid
independent observations.

`method-comparison-plan` freezes method versions, common input, generation
identity/budget and downstream design before generation, without unknown
candidate hashes. Actual outputs and the independent final protocol are bound
after generation. `method-comparison-bind` checks both stages and exact produced
artifacts; it cannot reuse method acceptance as downstream truth. Legacy bare
comparisons remain unverified. Finite subprocess/kernel fixtures establish
engineering order and bindings, not recursive gain.

Method comparison schema 3 stores the complete plan-bound typed attempt closure,
source/retry links, exact cost totals and frozen dependency digest. Failed and
interrupted exploration cannot disappear behind the two selected generations;
unassigned attempts under the same method/input require a plan binding. A
current method report rechecks method acceptance, generation reads, the current
downstream final kernel and all costs. Revocation or drift returns UNVERIFIED,
while comparison history retains its original verification time and status.

Accepted final reuse binds exact input receipts and exploration identities.
Current installation also rechecks the frozen cost/effect universe. Runtime
protocol/evaluation/source/retry relationships supply mandatory attempt coverage;
completed child costs represented by an evaluation aggregate are referenced but
not charged twice. Unknown effects remain HOLD despite a known invoice. Package
files reject setuid/setgid/sticky and nonregular types. Ordinary directories are
containers rather than versioned content; their special permission bits are
rejected. This manifest does not certify ownership, ACLs or extended attributes.

The first final, accepted cache and dependent reports share current disk and
authority checks. Disk must match the frozen parent or the exact candidate in a
matching original-owner installation/prepared intent. This preserves legitimate
installation/recovery semantics without consuming final inputs again; it does
not invent applied_at, activation or a new experiment. Other disk/symlink/package
drift or naturally expired authority invalidates current usability and preserves
the historical signed acceptance.
