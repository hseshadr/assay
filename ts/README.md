# Assay for TypeScript

Assay turns measurements with different scales into one score and explains every contribution.

It does not sign evidence, store receipts, or decide whether a score should pass. Use Avow when you need a signed evidence receipt; Assay only calculates scores.

**Status:** `0.5.0-dev.0` is a local candidate. It is not published to npm.

## Try the local candidate

Build the package from the repository root:

```bash
corepack pnpm --dir ts install --frozen-lockfile
corepack pnpm --dir ts pack --pack-destination /tmp
```

Install it in a scratch app:

```bash
mkdir -p /tmp/assay-demo
cd /tmp/assay-demo
npm init -y
npm install /tmp/edgeproc-assay-0.5.0-dev.0.tgz
```

## Run a real score

Save this as `demo.mjs` after installing the tarball:

```typescript
import { compose, parseRequest } from "@edgeproc/assay";

const request = parseRequest({
  method: "weighted_mean",
  method_version: "screening.v1",
  components: [
    {
      id: "match_strength",
      label: "Match strength",
      value: 87,
      scale: { minimum: 0, maximum: 100, direction: "higher_is_better" },
      weight: 3,
    },
    {
      id: "data_quality",
      label: "Data quality",
      value: 0.8,
      scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
      weight: 1,
    },
  ],
  clamp: "reject",
});

const result = compose(request);
console.log(result.score);
console.log(result.components);
```

Run it:

```bash
node demo.mjs
```

The first line is:

```text
0.8525
```

## What the output means

- `score` is the combined number. Weighted mean and minimum results are between 0 and 1. An additive result can be outside that range when `clamp` is `null`.
- `components` shows each raw value, normalized value, coefficient, and contribution in declared order.
- `interval` is `null` when the inputs have no uncertainty range.
- `inputs_hash` changes when any scored field or input order changes.
- `selected_component_id` names the bottleneck for the `minimum` method. It is `null` for the other methods.

Assay supports three explicit methods: `weighted_mean`, `additive`, and `minimum`. Choose the formula that already describes your application; Assay does not silently replace it with an average.
