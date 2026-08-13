"""Keep the README's front door aligned with source and registry reality."""

from pathlib import Path

README = Path("README.md")


def test_opening_proof_uses_the_current_published_error_contract() -> None:
    readme = README.read_text(encoding="utf-8")
    proof = readme.split("## Run it", 1)[0]

    assert "`avow` 0.3.0 from PyPI" in proof
    assert "avow.payload_hash_mismatch" in proof
    assert "avow.replay_mismatch" not in proof


def test_readme_separates_published_release_from_source_main() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "Published now: `avow` 0.3.0" in readme
    assert "Source `main`: 0.4.0" in readme
    assert "version on PyPI today" not in readme
