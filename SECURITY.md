# Security policy

> **TL;DR:** Please report vulnerabilities privately. Do not include private user data, signing
> keys, registry credentials, or other secrets in an issue or proof.

## Supported versions

Assay is currently split into unpublished Python `0.5.0.dev2` and npm `0.5.0-dev.2`
candidates for the future 0.5.0 line. Until a release is explicitly
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

The protected `npm-release` GitHub environment requires approval before either registry write.
PyPI then uses short-lived OIDC. Until npm trusted publishing is available, npm uses a package-scoped
token kept only in that environment and exposed only to the final publish step. That shell disables
tracing, immediately unsets its exported token, and passes it only to
`npm publish --provenance --ignore-scripts`. Builds, tests, dependency checks, secret scanning,
benchmarks, preflights, and registry verification never receive the credential.
Every release commit must be reachable from protected `main`. Missing registry bytes publish only
that lane, exact provenance-bound bytes skip it, and every mismatch fails closed. After both
registries serve the reviewed bytes, the same artifacts are attached to a repository-configured
immutable GitHub Release and verified through its signed release attestation.
The approved release window must have no concurrent external npm publisher or GitHub release-asset
writer because those services do not expose a compare-and-swap primitive for the final write.
