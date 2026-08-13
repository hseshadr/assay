"""Repository-level rules that ordinary linters do not enforce."""

from __future__ import annotations

import ast
from pathlib import Path


def _function_lengths(path: Path) -> tuple[tuple[str, int], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = (
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return tuple(
        (node.name, (node.end_lineno or node.lineno) - node.lineno + 1) for node in functions
    )


def test_should_keep_every_shipped_python_function_within_fifteen_lines() -> None:
    # Given every Python function shipped as runtime source or release tooling
    roots = (Path("src"), Path("scripts"))
    paths = tuple(path for root in roots for path in root.rglob("*.py"))
    # When their complete physical spans (including contracts) are measured
    oversized = [
        f"{path}:{name}:{length}"
        for path in paths
        for name, length in _function_lengths(path)
        if length > 15
    ]
    # Then none exceeds the public OSS readability contract
    assert oversized == []
