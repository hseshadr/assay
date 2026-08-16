# Assay methods and result contract

> **TL;DR:** Assay offers exactly three declared-order methods. Every accepted number is
> finite IEEE-754 binary64, every input row remains visible, and deterministic inputs
> produce `interval: null`.

## Shared request rules

- All numeric inputs must be finite IEEE-754 binary64 values. Both languages canonicalize
  negative zero to positive zero.
- IDs are nonempty stable identifiers, at most 128 characters, beginning with a lowercase
  letter and continuing with lowercase letters, digits, or single `.`, `_`, or `-`
  separators. IDs must be unique within a request.
- Labels are nonblank Unicode-scalar text of at most 256 characters.
- A native scale requires `maximum > minimum` and an explicit direction.
- An interval requires `low < high` and must contain its point value. A deterministic
  value uses `interval: null`; a zero-width interval is invalid.
- Request and result parsers reject extra fields. They do not silently discard metadata.
- Arithmetic follows declaration order using strict finite IEEE-754 binary64 operations.
  Intermediate or final nonfinite values fail rather than being serialized.

For `higher_is_better`, normalization is:

```text
(value - minimum) / (maximum - minimum)
```

For `lower_is_better`, normalization is:

```text
(maximum - value) / (maximum - minimum)
```

The `reject` policy refuses point or interval values outside the native scale. The
`clamp` policy applies the formula first, then bounds its normalized result to 0–1.
Every normalized endpoint uses the same direction and policy as its point value.

## `weighted_mean`

Normalize each component. Every component must declare a strictly positive `weight`.
Add weights in declaration order to produce `weight_total`, divide each declared weight
by that total to produce its `coefficient`, multiply normalized value by coefficient,
and add contributions in declaration order.

```text
coefficient  = declared_weight / weight_total
contribution = normalized × coefficient
score        = contribution[0] + contribution[1] + ...
```

Weighted-mean intervals propagate through the same monotone normalization and positive
coefficient. The result interval is `null` when every component interval is `null`.

## `additive`

Do not normalize additive terms. Start at the finite `intercept` (default `0`), compute
each pre-operation `contribution` as `raw × coefficient`, and apply its explicit `add` or
`subtract` operation from left to right. Coefficients must be nonnegative; subtraction
is represented only by the operation, never by a negative coefficient.

```text
contribution = raw × coefficient
running      = running + contribution   # operation: add
running      = running - contribution   # operation: subtract
```

Apply the optional final boundary only after all terms. `clamp: "clamp"` bounds the
final point and interval to 0–1. `clamp: "reject"` requires the final point and interval
to already be inside 0–1. `clamp: null` leaves the finite final value unbounded.

Intervals preserve the declared sign: addition advances low by low and high by high;
subtraction advances low by high and high by low. Deterministic terms produce
`interval: null`.

## `minimum`

Normalize every component and choose the first lowest normalized value. Equal values
preserve declaration order; IDs are never sorted to break a tie. Each row has
`coefficient: 1`, and its normalized value is also its contribution. The chosen row's
ID becomes `selected_component_id` and its normalized value becomes `score`.

When intervals exist, result low is the minimum of all normalized lows and result high
is the minimum of all normalized highs. All-deterministic components produce
`interval: null`.

## Result fields

| Field | Exact meaning |
|---|---|
| `schema` | Result schema literal `assay.result/v1`. |
| `method.id` | `weighted_mean`, `additive`, or `minimum`. |
| `method.version` | Stable caller-declared formula provenance. |
| `score` | Final finite binary64 point value. |
| `interval` | Propagated `{low, high}` bounds, or `null` for deterministic inputs. |
| `clamp` | `reject`, `clamp`, or additive-only `null`. |
| `intercept` | Additive starting value; otherwise `null`. |
| `weight_total` | Weighted-mean declared weight sum; otherwise `null`. |
| `components` | Ordered, nonempty explanation rows. |
| `id` | The source component or term identifier. |
| `raw` | Original point value retained from the request. |
| `normalized` | Normalized 0–1 point, or `null` for additive. |
| `declared_weight` | Original weighted-mean weight, or `null`. |
| `operation` | `add` or `subtract`; normalized methods use `add`. |
| `coefficient` | Effective nonnegative multiplier. |
| `contribution` | Pre-operation row product; `operation` controls how it changes the additive running total. |
| `contribution_interval` | Propagated row bounds, or `null`. |
| `inputs_hash` | SHA-256-prefixed, order-preserving request fingerprint. |
| `selected_component_id` | First limiting minimum row, otherwise `null`. |

`inputs_hash` fingerprints the complete validated scoring request, including method,
version, order, labels, values, scales, intervals, weights or coefficients, operations,
intercept, and boundary policy. It uses a deterministic typed binary encoding rather
than language-native JSON bytes. It is useful for replay comparison, but it is not
authentication or tamper evidence.

Method versions are caller-declared provenance. They do not prove that a methodology
is correct, fair, complete, current, or suitable.

## Cross-language parity

Python and TypeScript replay shared vectors for `weighted_mean`, `additive`, and
`minimum`. Parity covers exact field sets, JSON scalar kinds, field and component order,
IEEE-754 binary64 values, and exact `inputs_hash`. It does not promise byte-identical
language-native JSON serialization.

Python's optional metric surface is broader than TypeScript's; complete optional-metric
parity is not claimed. `metrics.json` holds 23 cases: 7 ranking successes, 7 ranking
refusals, 5 classification successes, and 4 classification refusals. The documented
default ranking cutoff is 10.

## Application-owned policy and limits

Assay does not prove input truth, completeness, fairness, freshness, authenticity,
policy compliance, or decision quality. Application bands, thresholds, hard gates,
fairness review, abstention, decisions, and evidence integrity remain application-owned.
Results retain raw values and may be sensitive.

Core composition has no fixed component-count ceiling. The resource limits in
[Operations](OPERATIONS.md) apply to optional calculators or the command-line adapter,
not to direct composition calls.
