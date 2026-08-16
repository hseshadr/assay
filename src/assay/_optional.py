"""Lazy, redacted boundary for Assay's optional metric dependencies."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from importlib import import_module
from types import ModuleType
from typing import cast

from assay.errors import MetricsExtraMissing

type OptionalCallable = Callable[..., object]

_FAILED = object()


def _try_import(name: str) -> ModuleType | None:
    try:
        return import_module(name)
    except Exception:
        return None


@cache
def load_module(name: str) -> ModuleType:
    """Load one exact optional module, caching successful imports only."""
    module = _try_import(name)
    if module is None:
        raise MetricsExtraMissing
    return module


def _try_attribute(module: ModuleType, name: str) -> object:
    try:
        return getattr(module, name)
    except Exception:
        return _FAILED


@cache
def load_object(module_name: str, name: str) -> object:
    """Load one exact dependency attribute, never caching a missing attribute."""
    value = _try_attribute(load_module(module_name), name)
    if value is _FAILED:
        raise MetricsExtraMissing
    return value


@cache
def load_callable(module_name: str, name: str) -> OptionalCallable:
    """Load one exact dependency callable, caching only a callable result."""
    value = load_object(module_name, name)
    if not callable(value):
        raise MetricsExtraMissing
    return cast(OptionalCallable, value)


def call_dependency(function: OptionalCallable, *args: object, **kwargs: object) -> object:
    """Call a dependency without allowing its private exception to cross the boundary."""
    try:
        return function(*args, **kwargs)
    except Exception:
        return _FAILED


def dependency_failed(value: object) -> bool:
    """Return whether a redacted dependency invocation failed."""
    return value is _FAILED
