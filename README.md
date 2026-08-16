# Assay

> **TL;DR:** Assay turns measurements with different scales into one explainable score.

Assay computes scores; Avow seals evidence.

Assay is useful when inputs do not start on the same scale. For example, product quality
might be 8 out of 10 while latency is 20 milliseconds out of 100. Assay normalizes both
to 0–1, applies an explicit composition rule, and returns the final score plus each
component's contribution.

## Install

The current version, `0.5.0.dev0`, is a local release candidate. It is not published to a
package registry yet.

```bash
git clone https://github.com/hseshadr/assay.git
cd assay
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Install the optional scientific metrics when you need classification, calibration,
ranking, agreement, or bootstrap intervals:

```bash
python -m pip install -e '.[metrics]'
```

## Run a real scoring example

This combines product quality and latency. Both normalize to `0.8`, so the weighted
result is also `0.8`.

```bash
python - <<'PY'
from assay import ClampPolicy, Component, NativeScale, WeightedMeanRequest, compose

request = WeightedMeanRequest(
    method="weighted_mean",
    method_version="demo-v1",
    components=(
        Component(
            id="quality",
            label="Quality",
            value=8.0,
            scale=NativeScale(
                minimum=0.0,
                maximum=10.0,
                direction="higher_is_better",
            ),
            weight=3.0,
        ),
        Component(
            id="latency",
            label="Latency",
            value=20.0,
            scale=NativeScale(
                minimum=0.0,
                maximum=100.0,
                direction="lower_is_better",
            ),
            weight=1.0,
        ),
    ),
    clamp=ClampPolicy.REJECT,
)

result = compose(request)
print(result.score)
for component in result.components:
    print(component.id, component.normalized, component.contribution)
PY
```

Expected first line:

```text
0.8
```

## Current scope

Shipped now:

- typed Python contracts for normalization and composition;
- weighted mean, additive, and minimum composition;
- optional classification, calibration, ranking, agreement, and uncertainty metrics;
- stable, value-free error codes.

Still being finalized:

- the TypeScript package;
- the command-line interface;
- expanded guides and API reference.

## Limits

Assay rejects work that exceeds these bounds before calling a scientific dependency:

- at most 1,000,000 input items or ranked positions;
- at most 1,000,000 bootstrap resamples;
- at most 10,000 calibration bins or agreement levels;
- ranking depth and relevance gain at most 1,000,000;
- bootstrap seeds from 0 through 2^63 - 1.

All numeric inputs and outputs must be finite. These are safety bounds, not performance
promises. This candidate has not completed the final TypeScript, CLI, documentation, or
publication pass.

## License

MIT © Harish Seshadri
