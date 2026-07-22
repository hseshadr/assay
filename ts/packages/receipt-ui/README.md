# @edgeproc/receipt-ui

Render and verify an Avow `SignedReceipt` in React.

Your app signs a receipt at the engine level; this shows the user whether it
actually checks out. Drop in a `<ReceiptBadge>` or `<ReceiptPanel>`, hand it the
receipt and the one public key you trust, and it verifies on mount and renders
one of four clearly-distinct, fail-closed states:

- **Verifying…** — the check is in flight (the initial, not-yet-trusted state).
- **Verified** — the signature is valid *and* signed by the pinned key.
- **Not verified — tampered or invalid signature** — the verifier rejected it.
- **Not verified — untrusted signer** — the receipt's key is not the one you pinned.

Only a resolved verify under the pinned key ever reads as *Verified*. Anything
else — a rejection, an error, an unpinned key, or the moment before the check
returns — reads as not-verified. Status is conveyed by icon **and** text (never
color alone) inside an ARIA `role="status"` live region.

## Install

```sh
pnpm add @edgeproc/receipt-ui @edgeproc/avow react
```

`@edgeproc/avow` and `react` are peer dependencies — the app provides them, so
there is a single avow instance and a single `SignedReceipt` type across the app
and this package.

## Use

```tsx
import { ReceiptPanel } from "@edgeproc/receipt-ui";

// `receipt` came from your engine (avow `signPayload`); `SIGNER_KEY` is the
// hex public key you trust. `verify` is optional — it defaults to avow's own
// `verifySignature`, so omit it unless your app injects a custom verifier.
<ReceiptPanel
  receipt={receipt}
  expectedPublicKey={SIGNER_KEY}
  renderPayload={(p) => <p>Score: {p.score}</p>}
/>;
```

`ReceiptBadge` takes the same `receipt` / `expectedPublicKey` / `verify` props
and renders just the one-line verdict; `ReceiptPanel` adds the envelope metadata
(algorithm, shortened signer key, payload hash, signature) and the payload body.

The verdict lives in the `useReceiptVerification` hook if you want to build your
own presentation; `StatusPill` is the standalone verdict chip.

## Develop

```sh
pnpm gate   # biome lint -> tsc strict -> vitest (+coverage) -> tsc build
```

Tests build real avow receipts (valid, tampered, wrong-key) and assert the
component reflects avow's own verdict — the property, not the shape.
