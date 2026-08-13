# Operational contract

**TL;DR:** Avow and Assay are local libraries, not services. They make no runtime
network calls, start no background worker, send no telemetry, and retain no hidden
copy of caller data. Receipts and ledgers are plaintext, so callers own data
minimisation, filesystem access, retention, deletion, backups, and custody of the
private signing key and pinned ledger head.

This document is the release acceptance contract. The deterministic workloads and
numeric budgets below are frozen before implementation or measurement. CI runs the
exact same benchmark entry point named here; a missed budget fails the release gate.

## Privacy and data-flow boundary

| Surface | Data accepted | Processing and egress | Persistence and retention |
|---|---|---|---|
| Python `avow` envelope | Caller-supplied Pydantic subject, Ed25519 seed, pinned public key | In-process canonical JSON, SHA-256, and Ed25519 only. No network, DNS, telemetry, subprocess, or background thread. | `sign_payload` and verification are stateless. Inputs and intermediates live for the call; the returned receipt is retained only by its caller. |
| Python `assay` scoring | Labels, scores, rankings, ratings, settings | In-process validation and local scientific-library calls, then the same envelope. No runtime egress. | No cache or implicit file. The returned receipt is retained only by its caller. |
| Python CLI | Only the request, key, receipt, ledger, and head paths explicitly passed by the operator | Reads those paths and prints success status/output paths or a stable failure code plus safe schema field path. It does not print exception messages, input values, payloads, or private-key bytes. No runtime network call. | Writes only requested key/public-key, receipt, ledger, and head files. They remain until the operator deletes them. |
| Python ledger | Plaintext signed receipts and an operator-chosen local path | One local JSONL append under a process lock; the CLI also saves its convenience head before releasing that same lock. Verification reads both files locally. | Persists plaintext until caller deletion. There is no upload, rotation, expiry, compaction, or automatic repair. |
| TypeScript `@edgeproc/avow` | Caller JSON, seed, pinned public key, labels/rankings | In-process Web Crypto-compatible Ed25519 and local arithmetic. No fetch, XHR, beacon, socket, telemetry, cookie, storage, worker, or DOM access. | No cache or storage. Returned values remain under caller control. The TS package ships no ledger. |

Package-manager traffic during `pip`/`npm` installation and an application's own use
of networked inputs or outputs are outside this runtime boundary.

### Data sensitivity, retention, and deletion

- A signature provides integrity and signer authentication; it is **not encryption**.
  Anyone who can read a receipt or ledger can read its payload. Do not place secrets or
  unnecessary personal data in a subject.
- The private seed is the only secret owned by the envelope. The Python CLI creates it
  with mode `0600`; applications must supply equivalent access control, backup, and
  rotation for any other custody mechanism. Browser JavaScript cannot provide a
  hardware security boundary.
- The library has no retention clock because it has no hidden store. The caller must
  set a retention period for every receipt, ledger, request, backup, and key it writes,
  and delete those files when that period ends. Normal file deletion is not a promise
  of secure erasure from snapshots, journaling filesystems, or backups.
- A pinned public key authenticates the signer. A pinned ledger head detects deletion,
  replay, reorder, splice, and truncation only when kept outside the ledger writer's
  control. A head stored beside its ledger is a copying convenience, not a security
  boundary.

## Reliability and recovery boundary

All malformed inputs and integrity failures raise stable coded errors; verification
never falls back to an embedded key, a file-computed head, a partial result, or network
state. Signing, scoring, and verification perform no retries because they have no
remote dependency.

The Python ledger is supported on local Unix filesystems that implement `flock`,
`fsync`, atomic same-directory `replace`, and append semantics. Network filesystems and
Windows are outside the durability contract.

| Event | Guaranteed outcome | Explicit bound or recovery action |
|---|---|---|
| Lock is held by another process | Append waits without changing the file, then raises coded `avow.ledger_lock_timeout`. | Default timeout: **5.0 seconds**. Poll interval: at most **10 ms**. |
| Lock timeout is negative or non-finite, or ledger and head paths alias | The call raises coded `avow.ledger_configuration_invalid` before creating or replacing either persistence file. | Supply one finite, non-negative timeout and two distinct paths. |
| Ledger exceeds 64 MiB, 100,000 entries, or one 64 KiB encoded line | Read, append, and verification fail closed with `avow.ledger_limit_exceeded`; append leaves existing bytes unchanged. | Rotate to a new externally pinned ledger before any ceiling. These are hard support limits, not tuning defaults. |
| `append` returns a head | The complete JSONL line has been flushed and `fsync` has succeeded before return. Concurrent successful appenders form one valid chain. | **RPO 0** relative to a returned head on an in-scope filesystem. The caller must export that returned pin. |
| CLI append plus convenience-head save returns | The ledger append and atomic head save happened while holding one ledger lock. A concurrent CLI writer cannot overwrite a newer head with an older one. | The saved head equals the ledger state at lock release. **RPO 0** for both returned operations; there is no cross-file crash atomicity before return. |
| Process or host fails before `append` returns | The append outcome is unknown; no success is claimed. A partial line or an entry beyond the previously pinned head fails closed. | Verify once against the last trusted external head. Do not silently trim or re-pin. |
| `save_head` returns | A complete head replaced the target atomically and both file and parent directory were synced. | **RPO 0** relative to the returned save on an in-scope filesystem. |
| Ledger/head is malformed, missing, unreadable, truncated, or inconsistent | Verification raises a coded error and returns no receipts. | Detection is one `verify_integrity` pass, **O(number of entries)**. Automatic repair and a wall-clock RTO are intentionally not promised. Restore both data and pin from a trusted backup, or investigate and explicitly authorise a new pin. |

The ledger and head remain two filesystem commits because the real head must eventually
leave the ledger writer's trust domain. The CLI holds one process lock across both so
concurrent writers cannot publish a stale final pin. A crash between the commits can
still leave a durable new entry that the old head rejects. That fail-closed mismatch is
preferable to silently accepting an entry whose head was never exported.

## Frozen performance acceptance contract

The release gate is `uv run poe benchmark` plus `pnpm --dir ts benchmark`. CI uses
CPython 3.13 and Node 22 on `ubuntu-latest`, the committed lockfiles, fixed seed
`000102...1f`, fixed generated data, `perf_counter_ns` / `performance.now`, and the
nearest-rank percentile `sorted_samples[ceil(q*n)-1]`. Each process records peak RSS;
any latency, memory, count, or integrity miss exits non-zero.

| Deterministic workload | Warm-up / measured samples | Latency budget | Peak RSS budget |
|---|---:|---|---:|
| Python envelope: sign and pinned-key verify one receipt carrying a 4,096-byte evidence string | 25 / 500 | p50 <= **2 ms**, p95 <= **4 ms**, p99 <= **10 ms** | **128 MiB** |
| TypeScript envelope: the same seed, subject, sign, and pinned-key verify | 25 / 500 | p50 <= **3 ms**, p95 <= **8 ms**, p99 <= **20 ms** | **128 MiB** |
| Python classification: `binary_scores` over 10,000 alternating labels and deterministic scores | 5 / 100 | p50 <= **75 ms**, p95 <= **150 ms**, p99 <= **300 ms** | **512 MiB** |
| Python ledger: a prebuilt 5,000-entry history, then 4 real processes append 50 fixed signed receipts each, followed by full 5,200-entry pinned-head verification | 0 / 200 timed appends | append p50 <= **10 ms**, p95 <= **50 ms**, p99 <= **250 ms**; timed append plus verify <= **15 s** | **128 MiB per worker** |

p99 is reported and enforced because every workload has at least 100 measured
operations. These are regression ceilings, not marketing claims or universal service
levels. Virtualised runner noise is included deliberately; budgets may be changed only
in a reviewed release that updates this contract before measurement and explains why.

## Operator checklist

1. Minimise the signed subject and decide its retention period.
2. Keep the signing seed out of application logs and source control.
3. Distribute the public key through a separate trusted channel.
4. Export every returned ledger head outside the ledger writer's control.
5. Rotate before 64 MiB, 100,000 entries, or a 64 KiB encoded entry.
6. Verify receipts with the pinned public key and ledgers with both pins.
7. Treat any timeout, partial write, pin mismatch, or malformed line as an incident;
   restore or re-pin only after an authorised investigation.
