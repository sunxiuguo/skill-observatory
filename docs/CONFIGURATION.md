# Trusted local reviewer configuration

Place `reviewer.json` in the private state directory, mode 0600:

```json
{"owner_module":"/absolute/trusted-owner-adapter.py","owner_sha256":"SHA256_OF_ADAPTER_BYTES"}
```

This is local executable configuration, not an HTTP setting. Review the module
before installing it. The runtime refuses configuration with group/world access
or a changed owner hash. The module exposes `make_reviewer()` returning an object
with `review(store, run)`. `CodexReviewer` can be composed with the canonical
provider owner's fresh-context client factory and exact admission function:

```python
from skill_observatory.reviewer import CodexReviewer

def make_reviewer():
    return CodexReviewer(client_factory, admission,
        model=approved_model, provider=approved_provider,
        effort=maximum_verified_effort, cwd=empty_review_context,
        max_seconds=120, daily_attempt_limit=5)
```

`client_factory` is a context manager yielding a fresh `AppServer`. Use an
isolated provider configuration, no inherited project instructions or MCP
credentials, disabled execution/search/delegation surfaces, and read-only sandbox.
The owner authenticates through protected storage and enforces quota. The
admission receipt must have `ok=true`, `maximum_verified_effort` equal to the
chosen effort and `redacted_evidence_allowed=true`. These values are decisions
of a trusted owner backed by current evidence, never user-controlled model output.

No example credentials are included. No default external provider is selected.
Runtime output preserves provider/model/effort, token usage when supplied and
monetary cost UNKNOWN when pricing truth is absent. On a lost/failed response,
read existing output/attempt receipts before authorizing any replay.

The public runtime does not claim that every third-party Codex configuration
makes a tool-free context physically isolated. Verify actual advertised tools,
execution denials, fresh identity and data policy before admitting an adapter.
Unknown tool isolation blocks certification and automatic promotion.

## Evolution owners and independent final truth

Optional `evolution.json` uses the same private/hash-pinned owner-module format.
Its module exposes `make_pipeline(store)` and returns an `EvolutionPipeline`
with trusted proposer, evaluator and activation adapters. The local owner may
compose canonical installers and signing ingresses; candidate/model workers
must receive only bounded stage inputs, never the Store, verifier key, labels or
owner module. Loading an adapter does not certify its OS isolation.

The pipeline holds until the exact single-file human grant exists. Create it
through trusted local `installations.grant_owner`, with the actual human
authorization retained as a private evidence artifact. A review recommendation
cannot serve as a grant. The public UI cannot grant this permission.

`evaluation.paired_evaluate` consumes the final set before any trial and keeps
measured artifacts/failed costs. `final_gate.finalize` compiles an accepted
verdict only with matching independently signed domain and all-attempt cost
receipts, exact parent/candidate binding, measured gain and the frozen cost
limits. Missing/unknown truth, synthetic cases and reused final sets stay HOLD.
Domain receipts must establish comparable contexts, independent labels,
guardrail and regression coverage. Cost receipts include exploration and failed
attempts; signing is reserved to the trusted canonical accounting owner.

`outcomes.accept_task_result` takes an independently signed task receipt,
including actual artifact/oracle hashes and a trusted-broker context receipt.
Activation additionally requires verified Skill bytes and a context created
after installation. `outcomes.verify_live` requires a different later user run.
Semantic review, activation and subsequent live verification are separate.
These adapters require real domain implementations; fixture tests establish
kernel mechanics only. No configured experience-domain truth is shipped.
