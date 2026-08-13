"""Keep the README's front door aligned with source and registry reality."""

import json
import re
from pathlib import Path

README = Path("README.md")
VERSION_SOURCE = Path("src/avow/_version.py")
TS_PACKAGE = Path("ts/package.json")


def test_opening_proof_uses_the_current_published_error_contract() -> None:
    readme = README.read_text(encoding="utf-8")
    proof = readme.split("## Run it", 1)[0]

    assert "`avow` 0.3.0 from PyPI" in proof
    assert "avow.payload_hash_mismatch" in proof
    assert "avow.replay_mismatch" not in proof


def test_readme_names_the_pair_versioned_release() -> None:
    # Given the Python and TypeScript versions shipped by one release tag
    readme = README.read_text(encoding="utf-8")
    source = VERSION_SOURCE.read_text(encoding="utf-8")
    version_match = re.search(r'__version__ = "([^"]+)"', source)
    ts_version = json.loads(TS_PACKAGE.read_text(encoding="utf-8"))["version"]

    # When the README's artifact status is compared with both package manifests
    assert version_match is not None
    version = version_match.group(1)
    # Then it names one published pair and carries no stale pre-release source split
    assert version == ts_version
    assert f"Published now: `avow` {version}" in readme
    assert f"`@edgeproc/avow` {version}" in readme
    assert "Source `main`:" not in readme
    assert "version on PyPI today" not in readme
