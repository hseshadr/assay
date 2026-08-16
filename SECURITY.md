# Security policy

> **TL;DR:** Please report vulnerabilities privately. Do not include private user data, signing
> keys, registry credentials, or other secrets in an issue or proof.

## Supported versions

Assay is currently an unpublished `0.5.0` split candidate. Until a release is explicitly
authorized, security fixes are made on `main`; no registry package is represented as supported.
After publication, this section will name the supported release line explicitly.

## Report a vulnerability

Use GitHub's private security-advisory flow for `hseshadr/assay`. Include the affected interface,
the smallest safe reproduction, expected behavior, observed behavior, and likely impact. If the
private advisory flow is unavailable, contact `harish.seshadri@gmail.com` without attaching secrets
or personal data. You can expect an acknowledgement within seven days.

## Security boundaries

Assay validates and combines caller-provided measurements. It does not prove that an input is true,
sign output, establish provenance, or provide a tamper-evident ledger. Applications remain
responsible for authorization, source-data quality, retention, and any evidence-sealing policy.

Release workflows use short-lived PyPI and npm OIDC identities and accept no stored registry write
token. Tests, locked dependency checks, full-history secret scanning, benchmarks, artifact builds,
and clean installs run in unprivileged jobs. Each registry is checked independently: missing bytes
publish only that lane, exact bytes with matching provenance skip it, and every mismatch fails
closed. The npm channel may remain on an exact or newer same-channel release; it is never moved
backward by a historical retry.
