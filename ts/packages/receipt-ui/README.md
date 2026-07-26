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

## Localize

> **Requires `@edgeproc/receipt-ui` 0.2.0 or newer.** 0.1.0 has no `labels`
> prop — it renders the built-in English strings and silently ignores the
> object. Check the version you resolved before filing a bug. See
> [`CHANGELOG.md`](CHANGELOG.md).

Every rendered string is injectable: pass a `labels` object (type
`ReceiptLabels`) to `StatusPill`, `ReceiptBadge` or `ReceiptPanel`. It is a
deep partial — omit anything to keep the built-in English default:

```tsx
<ReceiptPanel
  receipt={receipt}
  expectedPublicKey={SIGNER_KEY}
  labels={{
    status: { verified: { text: t("receipt.verified") } },
    panel: { receipt: t("receipt.section"), algorithm: t("receipt.algorithm") },
  }}
/>;
```

`labels.status` overrides the verdict chip per state (`checking` / `verified` /
`invalid` / `wrong-key`, each `{ text?, icon? }`); `labels.panel` overrides the
panel's meta strings (`receipt` — the section aria-label — plus `algorithm`,
`signerKey`, `payloadHash`, `signature`).

## Develop

```sh
pnpm gate   # biome lint -> tsc strict -> vitest (+coverage) -> tsc build
```

Tests build real avow receipts (valid, tampered, wrong-key) and assert the
component reflects avow's own verdict — the property, not the shape.
