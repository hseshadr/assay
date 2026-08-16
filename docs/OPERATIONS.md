# Assay operational contract

> **TL;DR:** Assay computes locally and keeps no hidden copy of inputs or results.
> Callers own input limits, data sensitivity, output retention, and application policy.

## Runtime boundary

| Surface | What it does | I/O and persistence |
|---|---|---|
| Python base package | Validates, normalizes, composes, and replays scoring requests. | No network, telemetry, subprocess, background worker, cache, or file I/O. Returned values remain under caller control. |
| Python optional metrics | Runs local scientific calculators after bounded validation. | No runtime network or implicit persistence. Third-party numeric libraries run in process. |
| Python command line | Runs `compose`, `measure`, or `explain` for an explicitly supplied file. | Reads one caller path. Writes standard output or one explicit output path. No implicit store. |
| TypeScript package | Validates and composes requests and runs its smaller calculator surface. | No runtime dependencies, network, telemetry, storage, DOM, or worker access. Returned values remain under caller control. |

Package-manager traffic while installing dependencies is outside this runtime boundary.
An application that obtains inputs remotely or sends results elsewhere owns that I/O.

## Data sensitivity and retention

`ScoreResult.components` deliberately retains each raw value so another reader can
replay the arithmetic. Labels, identifiers, raw measurements, intervals, and the
derived request fingerprint may therefore be sensitive. Minimize inputs before calling
Assay and do not place secrets or unnecessary personal data in a request.

The libraries set no retention clock because they have no hidden store. The caller must
choose retention, access, deletion, backup, and logging rules for requests and results.
Stable Assay errors contain codes rather than rejected values, but an application's own
logging still needs the same care.

## Command-line files

The command line accepts JSON request/result files of at most 1,048,576 bytes. Inputs
must be regular files. A requested output cannot alias the input through an identical,
equivalent, or existing same-file path.

Output is staged in the destination directory, flushed, atomically replaced, and the
parent directory is synchronized before success returns. A failure returns a stable
code and does not print the rejected JSON value. Standard output receives one complete
JSON or explanation stream when `--out` is absent.

Former mixed-product commands intentionally return migration codes without touching
caller files. The active scoring commands are `compose`, `measure`, and `explain`.

## Composition capacity

Core weighted-mean, additive, and minimum requests have no fixed component-count ceiling.
Work grows linearly with the number of declared rows, so callers must impose a limit
suited to their latency, memory, and request-size budgets. The command line's 1 MiB
input ceiling is an adapter boundary, not a library composition limit.

All public numbers must be finite IEEE-754 binary64 values. IDs are at most 128
characters and labels at most 256 characters. Extra fields, duplicate IDs, decreasing
scales, invalid intervals, and method-specific shape errors fail before a result is
returned.

## Optional calculator limits

These safety ceilings apply to optional measurement calculators, not to core
composition:

| Resource | Maximum |
|---|---:|
| input items or ranked positions | 1,000,000 |
| bootstrap resamples | 1,000,000 |
| sample × resample work cells | 10,000,000 |
| bootstrap cells processed per batch | 1,000,000 |
| calibration bins | 10,000 |
| agreement scale levels | 10,000 |
| ranking depth | 1,000,000 |
| relevance gain | 1,000,000 |
| bootstrap seed | 2^63 - 1 |

Defaults are 30 minimum samples, 9,999 bootstrap resamples, 0.95 confidence, 15
calibration bins, seed 12,345, and ranking depth 10. Controls may be supplied in a typed
measurement request. The legacy settings API additionally reads `ASSAY_*` environment
variables only when that optional surface is constructed.

The ceilings are validation and resource-safety contracts, not performance promises.
No production latency, throughput, or memory service level is claimed for the current
local candidates.

## Failure model

- Boundary failures use stable `assay.*` codes and omit caller values.
- Invalid requests return no partial score.
- Missing optional dependencies return a specific extra-missing code.
- Composition is deterministic for the same validated request and runtime arithmetic.
- `interval: null` means the inputs were deterministic; it is not a confidence claim.
- Application policy failures are outside the engine because policy remains with the
  application.

## Local release-candidate checks

Run both gates and the installed-artifact example before reviewing a candidate:

```bash
uv run poe gate
corepack pnpm --dir ts gate
bash examples/run_composite.sh
```

The exact package status and future registry identities are in the root [README](../README.md).
Do not publish either package without a fresh, explicit authorization.
