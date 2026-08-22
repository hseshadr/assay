# Security policy

> **TL;DR:** Please report vulnerabilities privately. Do not include private user data, signing
> keys, registry credentials, or other secrets in an issue or proof.

## Supported versions

Assay's Python `0.5.0.dev2` and npm `0.5.0-dev.2` development releases are published
with registry provenance. They are the supported prerelease identities for the future stable 0.5.0
line; security fixes continue on `main` and may require a newer development release.
Their embedded README files retain the immutable pre-publication snapshot; this section and
`docs/OPERATIONS.md` are the canonical current release-status record until the next version.

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
PyPI and npm then authenticate with short-lived OIDC identities; no long-lived registry token is
available to the workflow. The npm lane uses the repository- and workflow-bound trusted publisher
only for `npm publish --provenance --ignore-scripts`. Builds, tests, dependency checks, secret
scanning, benchmarks, preflights, and registry verification cannot mint that identity.
Every release commit must be reachable from protected `main`. Missing registry bytes publish only
that lane, exact provenance-bound bytes skip it, and every mismatch fails closed. After both
registries serve the reviewed bytes, the same artifacts are attached to a repository-configured
immutable GitHub Release and verified through its signed release attestation.
The dev2 registries are complete; their immutable GitHub mirror is pending a hard-bound recovery
that can use only tag `v0.5.0-dev.2`, its exact commit, and the retained reviewed artifact.
The approved release window must have no concurrent external npm publisher or GitHub release-asset
writer because those services do not expose a compare-and-swap primitive for the final write.
