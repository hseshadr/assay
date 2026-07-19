from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_demo() -> ModuleType:
    path = Path(__file__).resolve().parent.parent / "demo" / "run_demo.py"
    spec = importlib.util.spec_from_file_location("run_demo", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_should_prove_all_six_cases_when_demo_runs() -> None:
    # Given the runnable demo
    demo = _load_demo()
    # When main() runs end to end
    exit_code = demo.main()
    # Then it proves all six cases and exits clean
    assert exit_code == 0
