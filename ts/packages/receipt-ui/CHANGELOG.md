# Changelog

`@edgeproc/receipt-ui` is versioned separately from the repo's `v*`-tagged
`avow` / `@edgeproc/avow` co-releases (see the root `CHANGELOG.md`).

## [0.2.0] - unreleased

### Added

- **Injectable labels (i18n).** Every rendered string can now be overridden via
  an optional `labels` prop (type `ReceiptLabels`) on `StatusPill`,
  `ReceiptBadge` and `ReceiptPanel`: per-verdict `{ text?, icon? }` for the four
  `ReceiptStatus` states, plus the panel's envelope-metadata labels (the
  `receipt` section aria-label, `algorithm`, `signerKey`, `payloadHash`,
  `signature`). The prop is a deep partial merged field-by-field with the
  built-in English defaults, so a consumer that passes nothing renders exactly
  the 0.1.0 strings — no breaking changes. New exported types: `ReceiptLabels`,
  `PanelLabels`, `StatusLabelOverride`.

## [0.1.0] - 2026-07-22

Initial release: `ReceiptBadge`, `ReceiptPanel`, `StatusPill`,
`useReceiptVerification` and `shortenHex` — a fail-closed, four-state receipt
verdict UI over `@edgeproc/avow`.
