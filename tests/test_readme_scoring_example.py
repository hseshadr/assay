"""Execute the root README scoring quickstart exactly as readers receive it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_START = "python - <<'PY'\n"
_END = "\nPY"


def _quickstart_source() -> str:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Run a real scoring example", maxsplit=1)[1]
    shell = section.split("```bash\n", maxsplit=1)[1].split("\n```", maxsplit=1)[0]
    return shell.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]


def test_should_run_the_readme_scoring_quickstart_without_edits() -> None:
    # Given the exact Python heredoc copied from the root README
    completed = subprocess.run(  # noqa: S603 - the repository-owned example is the test subject
        [sys.executable, "-c", _quickstart_source()],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    # When a reader runs it, the documented score and both explanations print cleanly
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "0.8",
        "quality 0.8 0.6000000000000001",
        "latency 0.8 0.2",
    ]
