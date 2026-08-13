"""The mutation runner itself must not depend on a nested package-manager launch."""

from pathlib import Path


def test_should_launch_the_installed_vitest_binary_without_nested_pnpm() -> None:
    # Given dependencies were already installed from the pinned pnpm lockfile
    source = Path("scripts/mutation_harness.py").read_text(encoding="utf-8")
    command_body = source.split("def _vitest_command", 1)[1].split("def _vitest", 1)[0]
    # When the mutation runner's focused vitest launcher is inspected
    # Then it directly uses that installation; pnpm is not recursively launched
    assert "node_modules/.bin/vitest" in command_body
    assert '"pnpm"' not in command_body
