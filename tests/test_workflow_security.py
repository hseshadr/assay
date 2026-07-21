"""GitHub Actions must resolve third-party code from immutable commits.

A tag (even a release tag like `ci-v2`) can be repointed at new code by whoever
owns the upstream repo; a full 40-hex commit SHA cannot. Pinning is what turns
"trust the publisher forever" into "trust exactly these bytes", so every
`uses:` in this repo — including reusable workflows we own, such as
`hseshadr/ci` — resolves to a commit. Local `./...` references are exempt:
they resolve inside this repo, at this commit, by definition.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
PINNED = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}$")


def test_external_actions_are_pinned_to_full_commit_shas() -> None:
    failures: list[str] = []
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        for action in USES.findall(workflow.read_text(encoding="utf-8")):
            if not action.startswith("./") and PINNED.fullmatch(action) is None:
                failures.append(f"{workflow.name}: {action}")
    assert failures == []
