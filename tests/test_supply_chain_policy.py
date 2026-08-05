"""A brand-new npm release cannot walk straight into the TypeScript lockfile.

Every version this repo resolves must have been public for a full day first. The
threat is a compromised maintainer account publishing a malicious patch release: that
window is measured in hours and the takedown usually lands inside a day, so declining
to be an early installer removes most of the exposure for the price of a day's lag.

The policy is `minimumReleaseAge` in `ts/pnpm-workspace.yaml`, and pnpm refuses the
install outright when the lockfile contains an entry younger than it — that refusal is
what turned PR #21 red. Two ways a guard like this rots into a no-op, both closed here:

* the value goes unwritten and the repo simply inherits whatever the package manager
  defaults to. That is the state this file was added to end: the quarantine was real
  and enforced in CI, but no line in the repo asked for it, so a pnpm upgrade could
  have retired it silently and every gate would have stayed green; and
* an exemption list re-opens the door for named packages. `minimumReleaseAgeExclude`
  takes a per-package allowlist, so one line can restore exactly the risk the
  quarantine exists to remove — and it is a plausible thing for a future reader to add
  under deadline. The scan below reports it from every pnpm settings file at once, and
  a planted-exemption test proves the scan can actually see one.

Scope worth stating plainly: these tests read the declared policy, they do not drive
pnpm. That the declaration is *enforced* is pnpm's behaviour, observed by hand at
pnpm 11.5.0 (raising the value made `pnpm install --frozen-lockfile` refuse the
lockfile it had just accepted) and re-observed by CI on every run.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The quarantine the repo promises, in minutes, stated as the duration it means.
QUARANTINE_MINUTES = 24 * 60

# The two files pnpm 11 reads these settings from. `.npmrc` does not exist today; it is
# scanned anyway because it is the obvious place to quietly reintroduce an exemption.
SETTINGS_FILES = ("ts/pnpm-workspace.yaml", "ts/.npmrc")

AGE = re.compile(r"^\s*minimumReleaseAge\s*[:=]\s*(\d+)\b", re.MULTILINE)
EXEMPTION = re.compile(r"minimum[-_]?release[-_]?age[-_]?exclude", re.IGNORECASE)


def _uncommented(text: str) -> str:
    """Strip `#` comments, so prose *about* the exemption key is not read *as* one.

    Both YAML and npmrc comment with `#`. Without this, the paragraph in this very
    docstring's counterpart — the note in pnpm-workspace.yaml — would trip the scan,
    and the fix a maintainer would reach for is deleting the warning."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _policy(root: Path) -> tuple[int | None, list[str], int]:
    """Return (declared quarantine in minutes, files granting exemptions, files read).

    The quarantine comes back as None when nothing declares it — the inherited-default
    case, which reads identically to a healthy repo until the default moves. The file
    count comes back too, so a caller can assert the scan examined something rather
    than trusting a clean report from a directory that has been renamed out from under
    it."""
    declared: int | None = None
    exemptions: list[str] = []
    read = 0
    for name in SETTINGS_FILES:
        path = root / name
        if not path.is_file():
            continue
        read += 1
        text = _uncommented(path.read_text(encoding="utf-8"))
        found = AGE.search(text)
        if found is not None:
            declared = int(found.group(1))
        if EXEMPTION.search(text) is not None:
            exemptions.append(name)
    return declared, exemptions, read


def test_new_npm_releases_are_quarantined_for_a_day() -> None:
    # Given the pnpm settings this repo actually ships
    declared, exemptions, read = _policy(ROOT)
    # Then the quarantine is written down here, not inherited from the package manager
    assert declared is not None
    # ...for at least the full day the header of this file promises
    assert declared >= QUARANTINE_MINUTES
    # ...with no package excused from it
    assert exemptions == []
    # ...and the scan was not vacuous: it really did read a settings file, so a moved
    # or renamed `ts/` fails here instead of reporting a clean bill of health.
    assert read > 0


def test_the_quarantine_is_a_full_day_in_minutes() -> None:
    # pnpm counts minutes, the claim is stated in days; pin the conversion so the
    # constant above cannot drift into asserting itself.
    assert QUARANTINE_MINUTES == 1440


def test_the_guard_catches_a_planted_per_package_exemption(tmp_path: Path) -> None:
    # Given a settings file that quarantines everything, then excuses one package
    workspace = tmp_path / "ts"
    workspace.mkdir()
    (workspace / "pnpm-workspace.yaml").write_text(
        "minimumReleaseAge: 1440\nminimumReleaseAgeExclude:\n  - postcss\n", encoding="utf-8"
    )
    # When the guard scans
    declared, exemptions, read = _policy(tmp_path)
    # Then the hole is reported rather than hidden behind a healthy-looking value
    assert declared == 1440
    assert exemptions == ["ts/pnpm-workspace.yaml"]
    assert read == 1


def test_the_guard_reads_the_exemption_key_in_npmrc_too(tmp_path: Path) -> None:
    # Given the exemption moved to the other file pnpm honours
    workspace = tmp_path / "ts"
    workspace.mkdir()
    (workspace / "pnpm-workspace.yaml").write_text("minimumReleaseAge: 1440\n", encoding="utf-8")
    (workspace / ".npmrc").write_text("minimum-release-age-exclude=postcss\n", encoding="utf-8")
    # Then scanning only the workspace file would have missed it
    _, exemptions, read = _policy(tmp_path)
    assert exemptions == ["ts/.npmrc"]
    assert read == 2


def test_the_guard_ignores_the_exemption_key_inside_a_comment(tmp_path: Path) -> None:
    # Given a file that only *documents* the exemption key
    workspace = tmp_path / "ts"
    workspace.mkdir()
    (workspace / "pnpm-workspace.yaml").write_text(
        "# never add minimumReleaseAgeExclude here\nminimumReleaseAge: 1440\n", encoding="utf-8"
    )
    # Then the warning is not mistaken for the thing it warns about
    declared, exemptions, _ = _policy(tmp_path)
    assert declared == 1440
    assert exemptions == []


def test_the_guard_reports_no_policy_when_nothing_declares_one(tmp_path: Path) -> None:
    # Given a workspace that leaves the quarantine to the package manager's default
    workspace = tmp_path / "ts"
    workspace.mkdir()
    (workspace / "pnpm-workspace.yaml").write_text(
        'packages:\n  - "packages/*"\n', encoding="utf-8"
    )
    # Then the policy reads as absent — and that absence is precisely what the
    # `declared is not None` assertion above converts into a failure.
    declared, exemptions, read = _policy(tmp_path)
    assert declared is None
    assert exemptions == []
    assert read == 1
