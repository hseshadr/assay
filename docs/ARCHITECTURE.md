# Assay architecture

> **TL;DR:** Assay has two independent production packages with one shared semantic
> scoring contract. Repository support files do not become runtime packages.

## Source to artifact map

Exactly two production source trees ship:

```text
src/assay/  ──> assay-engine wheel ──> import assay
ts/src/     ──> @edgeproc/assay npm tarball ──> import "@edgeproc/assay"
```

- `examples/` demonstrates installed artifacts.
- `docs/` explains contracts and operations.
- `tests/` enforces Python, documentation, artifact, and parity behavior.
- `testdata/` holds shared language-neutral vectors.

Those four directories support the repository. They are not a third production source
tree and do not create another import package.

## Core data flow

```text
unknown JSON
    │
    ▼
strict request parser ──> typed weighted_mean | additive | minimum request
    │
    ▼
declared-order finite binary64 arithmetic
    │
    ├──> ordered component explanations
    ├──> propagated interval or null
    └──> order-preserving inputs_hash
             │
             ▼
         ScoreResult
```

The public parser is the boundary. It rejects unknown fields, nonfinite numbers,
malformed identifiers, duplicate component IDs, invalid scales or intervals, and
method-specific shape errors before arithmetic. Requests are immutable after parsing.

The method version is caller-declared provenance. Assay includes it in the request
fingerprint but does not interpret whether that version describes a good formula.

## Portable composition core

Both packages implement the same three methods:

- weighted mean: normalize, divide positive weights by their declared total, combine;
- additive: multiply raw values by nonnegative coefficients, apply explicit signs in
  order, then apply the optional final boundary;
- minimum: normalize and choose the first lowest component.

Both surfaces preserve field order, component order, binary64 results, and the exact
`inputs_hash` for shared vectors. The fingerprint comes from a deterministic internal
request encoding; it is not a claim about the bytes emitted by a language-native JSON
serializer. [Methods](METHODS.md) defines the complete contract.

## Python package

The `assay-engine` base wheel depends only on Pydantic and includes contracts,
normalization, composition, replay validation, and stable errors. The `cli` extra adds
Typer for `assay compose`, `assay measure`, and `assay explain`. The `metrics` extra
adds NumPy, SciPy, scikit-learn, ir-measures, and settings support.

Optional dependencies load only at optional entry points. Base composition works in a
clean environment without the scientific stack. Missing extras fail with stable Assay
error codes instead of leaking dependency exceptions.

## TypeScript package

The `@edgeproc/assay` tarball ships only compiled `dist/` output and has no runtime
dependencies. Package-root exports provide strict request/result parsers, normalization,
the three combiners, stable errors, and a smaller set of binary and ranking calculators.

The TypeScript source never imports the Python package. Shared vectors, not a runtime
bridge, prove semantic agreement.

## Application boundary

Applications select the formula and method version, supply measurements and scales,
interpret the result, and own any bands, thresholds, hard gates, fairness review,
abstention rules, or decisions. Assay validates and explains declared arithmetic; it
does not replace application policy.

The engine performs no implicit persistence or runtime network I/O. The command-line
adapter is the only core surface that reads or writes files, and it does so only for
paths explicitly supplied by the operator. [Operations](OPERATIONS.md) defines that
boundary.
