# Assay

> **TL;DR:** Assay combines measurements recorded on different scales into one explainable score while preserving every input, transformation, and contribution.

Assay is a small scoring engine for formulas you can write down and replay. Give it
measurements, their native scales, and one explicit combining method. It returns the
score and the arithmetic behind every row.

## Installation status

> **Status:** `assay-engine` 0.5.0.dev0 and `@edgeproc/assay` 0.5.0-dev.0 are local split candidates. Neither package is published.

The future authorized registry commands are `pip install assay-engine` and
`npm install @edgeproc/assay`. They are shown for identity only; do not run them until
a release is explicitly authorized. The runnable candidate path builds from this
checkout.

## Run the Northstar example

From the checkout root, run:

```bash
bash examples/run_composite.sh
```

The script builds the real Python wheel and npm tarball, installs each in an isolated
temporary environment, computes through both public package surfaces, checks every
typed field and binary64 value against the committed oracle, and prints one explanation:

```text
Northstar weighted score: 0.92
Method: weighted_mean @ northstar.2026-08-12
Interval: null — all inputs are deterministic

security       19/20  -> 0.950000 × 0.20 = 0.19
privacy        15/15  -> 1.000000 × 0.15 = 0.15
reliability    15/15  -> 1.000000 × 0.15 = 0.15
performance    12/15  -> 0.800000 × 0.15 = 0.12
correctness    15/15  -> 1.000000 × 0.15 = 0.15
clarity        14/15  -> 0.933333 × 0.15 = 0.14
production       2/5  -> 0.400000 × 0.05 = 0.02

Total: 0.92
inputs_hash: sha256:0266b1c59c97bacf85dc945685c55bb4386856b525249c7d5663a8edf020ba06
Parity: Python and TypeScript fields and values match
```

This is uncapped arithmetic only. Northstar hard caps, evidence grades, release
decisions, and other product policies remain outside Assay.

## How the score is calculated

The example declares seven components on three native scales. Assay first normalizes
each value to 0–1, divides its positive weight by the declared total of 100, then adds
the contributions in declaration order:

```text
security:    (19 - 0) / (20 - 0) × 20/100 = 0.19
privacy:     (15 - 0) / (15 - 0) × 15/100 = 0.15
reliability: (15 - 0) / (15 - 0) × 15/100 = 0.15
performance: (12 - 0) / (15 - 0) × 15/100 = 0.12
correctness: (15 - 0) / (15 - 0) × 15/100 = 0.15
clarity:     (14 - 0) / (15 - 0) × 15/100 = 0.14
production:  ( 2 - 0) / ( 5 - 0) ×  5/100 = 0.02
total:                                            0.92
```

Assay supports exactly three composition methods:

- `weighted_mean` normalizes components, converts positive declared weights into
  coefficients that sum to one, and adds their contributions.
- `additive` applies each raw term's explicit add or subtract operation and coefficient,
  then optionally clamps the final total.
- `minimum` normalizes components and selects the first lowest value, making declaration
  order the tie-breaker.

The method is chosen by the application because it owns the formula. Assay never
silently replaces a shipped formula with an average. See [Methods](docs/METHODS.md) for
validation, uncertainty, and exact arithmetic rules.

Every result field is explicit:

| Field | Meaning |
|---|---|
| `schema` | Serialized result contract, currently `assay.result/v1`. |
| `method.id` | One of the three closed composition methods. |
| `method.version` | Caller-declared provenance for this formula revision. |
| `score` | Final finite binary64 result. |
| `interval` | Propagated uncertainty bounds, or `null` for deterministic inputs. |
| `clamp` | Requested boundary policy, or `null` only for unclamped additive scoring. |
| `intercept` | Additive starting value; `null` for the other methods. |
| `weight_total` | Weighted-mean declared weight total; otherwise `null`. |
| `components` | Ordered arithmetic rows retained for replay. |
| `id` | Stable input identifier for one row. |
| `raw` | Original finite input value; it may be sensitive. |
| `normalized` | 0–1 transformed value, or `null` for additive rows. |
| `declared_weight` | Original weighted-mean weight, otherwise `null`. |
| `operation` | `add` or `subtract`; normalized methods use `add`. |
| `coefficient` | Effective multiplier used for the row. |
| `contribution` | Pre-operation product: `normalized × coefficient` or `raw × coefficient`. For additive rows, `operation` controls how it changes the running total. |
| `contribution_interval` | Row uncertainty contribution, or `null`. |
| `inputs_hash` | Order-preserving request fingerprint used for replay comparison. |
| `selected_component_id` | Minimum-method bottleneck ID; otherwise `null`. |

Python and TypeScript parity covers the three methods, typed field/value structure,
field and component order, IEEE-754 binary64 values, and the exact `inputs_hash`. It
does not promise byte-identical output from language-native JSON serializers; for
example, one serializer may spell the same number `19.0` and another `19`.

## What this proves

For a validated request, the result exposes the selected method and version, preserves
the scored inputs in declaration order, shows every transformation and contribution,
and can be replayed under the same contract. The committed vectors prove the Python and
TypeScript composition surfaces agree semantically on all three methods and on the
exact request fingerprint.

## What this does not prove

Assay does not prove input truth, completeness, fairness, freshness, authenticity,
policy compliance, or decision quality. `inputs_hash` is a deterministic fingerprint,
not authentication or tamper evidence. A caller-declared method version records
provenance; it does not validate the methodology.

Application-owned bands, thresholds, hard gates, fairness review, abstention policy,
release decisions, and other downstream decisions remain application-owned. Results
retain raw values, so callers must treat them according to the sensitivity of their
inputs.

## Architecture

There are exactly two production source-to-artifact mappings:

```text
src/assay/  ──> assay-engine wheel ──> import assay
ts/src/     ──> @edgeproc/assay npm tarball ──> import "@edgeproc/assay"
```

`examples/`, `docs/`, `tests/`, and `testdata/` are repository support files, not
runtime packages. The Python package is the broader surface: composition is in the
base wheel, the command line uses the `cli` extra, and scientific calculators use the
`metrics` extra. The npm tarball provides composition plus a smaller set of optional
binary and ranking calculators.

This README is self-contained because the Python source distribution currently ships
it, but does not ship the repository's quickstart, docs, or examples. The detailed
[architecture](docs/ARCHITECTURE.md), [operations contract](docs/OPERATIONS.md), and
[quickstart](QUICKSTART.md) are available in the source checkout.

## Use the local candidate directly

Python 3.13 code imports `assay` from the distribution named `assay-engine`:

```python
from assay import compose, parse_request

request = parse_request(
    {
        "method": "minimum",
        "method_version": "service-health.v1",
        "components": [
            {
                "id": "availability",
                "label": "Availability",
                "value": 99.9,
                "scale": {"minimum": 99.0, "maximum": 100.0, "direction": "higher_is_better"},
                "interval": None,
                "weight": None,
            },
            {
                "id": "latency",
                "label": "Latency",
                "value": 180.0,
                "scale": {"minimum": 100.0, "maximum": 500.0, "direction": "lower_is_better"},
                "interval": None,
                "weight": None,
            },
        ],
        "clamp": "reject",
    }
)

result = compose(request)
print(result.score, result.selected_component_id)
```

The command line accepts typed JSON for `assay compose`, `assay measure`, and
`assay explain`. Build and installation commands for the unpublished checkout are in
the [quickstart](QUICKSTART.md).

## Optional calculators

Python's optional scientific surface calculates typed binary-classification, ranking,
calibration, agreement, and uncertainty reports. TypeScript exposes a smaller binary
and ranking calculator set. Complete optional-metric parity is not claimed, and the
calculator resource ceilings do not limit core composition. See [Methods](docs/METHODS.md)
and [Operations](docs/OPERATIONS.md) for the exact boundary.

## Optional integration

Assay computes scores; Avow seals evidence. They are separate products in separate repositories, and neither imports or requires the other. The already-published `avow` 0.4.1 and `@edgeproc/avow` 0.4.1 artifacts remain unchanged.

An application may pass an ordinary Assay result to a separately selected evidence
system. That adapter belongs to the application or to its own versioned integration
package, never to either core scoring package.

## License

MIT © Harish Seshadri
