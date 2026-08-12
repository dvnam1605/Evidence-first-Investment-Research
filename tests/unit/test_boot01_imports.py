"""Smoke tests for project initialization (BOOT-01)."""

import importlib


def test_import_src_package() -> None:
    module = importlib.import_module("src")
    assert module.__version__ == "0.1.0"


def test_import_apps_package() -> None:
    module = importlib.import_module("apps")
    assert module.__doc__ is not None
