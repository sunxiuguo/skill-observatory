# Storage lifecycle

SQLite is the sole transactional ledger. Events keep durable identity/hash/time
keys; authority, attempts, costs, final-sample consumption, candidates and outcomes
retain their existing owners and replay barriers. Evidence is content-addressed.
No model-generated summary replaces any of those facts.

## Hot and cold data

- Hot event payloads stay inline. Maintenance considers only explicitly dated old
  events bound to terminal runs, with no queued/running/deferred jobs or unfinished
  experiment. Missing identity, time, run or terminal evidence excludes the event.
- Cold payloads move losslessly to `archive_event_payloads` as gzip plus SHA-256.
  The event row keeps its original ID/hash/time and a cold locator. All runtime
  consumers use `Store.event_data`; replay still compares the original identity.
- `storage_archives` stores deterministic window, count and manifest summaries.
  Their denominator is selected terminal payloads, never all user tasks.
- Artifact compression writes and verifies `<original-sha>.gz` before removing
  the redundant raw bytes. `read_artifact` verifies the original uncompressed hash.
  An interrupted compression can leave both files; the original remains readable.

`storage-status`, `storage-compress`, `storage-archive --before ISO_TIME` and
`storage-compact` default to dry runs. Add `--apply` only within current authority.
Limits bound each compression/archive batch; the maintenance file lock prevents
two maintenance writers. Hash, symlink, source drift and corruption checks refuse
unsafe changes. There is no automatic deletion of unknown attempts or evidence.

Opt-in local `settings.storage_policy={"enabled":true,"hot_days":30}` reuses the
existing evolution worker, independently of collection. It checks at most hourly, performs at most one deterministic
UTC-day maintenance batch (500 artifacts/500 events), and starts no model. Raw
artifacts must be at least seven days old; automatic hot retention cannot be less
than 30 days. Public installs default to no automatic maintenance. No new daemon,
scheduler, vector store or model summarizer is required.

## Readback, restore and compaction

Cold records are transparently read and hash-verified; missing/corrupt payloads
fail rather than returning empty evidence. To materialize an artifact, write the
bytes from `Store.read_artifact(original_sha)` into an explicitly owned private
destination. To materialize an event, use `Store.event_data` and retain its original
ID/hash. Gzip is lossless; timestamps in the compressed stream are fixed to zero.

SQLite updates can leave reusable free pages. `storage-compact --apply` requires
the service to be stopped, verifies integrity before and after, checkpoints the
WAL and runs SQLite's original `VACUUM`. It does not change evidence identities.
Keep a current private backup for offline recovery. Automatic collection never
vacuum-rewrites the entire database or scans every historical record each second.

Offline `storage-recover --backup HEALTHY_DB --apply` retains source bytes and a
hash-bound receipt. It rebuilds valid rows and restores every index-visible lost
entity from the explicitly supplied healthy backup; any unmapped lost key refuses.
Revision counters are derived and rebuilt. Optional durable tables are copied,
including archived payloads and one-time final consumption. A source hash change,
live WAL or database lock blocks replacement. Model/tool requests are not replayed.

Private historical backups and reproducible test environments are a separate
maintenance scope from production evidence. Compress and verify a restorable
bundle before releasing redundant working bytes; retain its manifest, source hash,
locator and rollback version. Public packages exclude all such private material.
