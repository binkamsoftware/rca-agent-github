"""Smoke tests for the package skeleton (plan M01)."""

import importlib
import pkgutil

import pytest

import rca_platform

EXPECTED_LAYER_PACKAGES = [
    "rca_platform.domain",
    "rca_platform.ports",
    "rca_platform.application",
    "rca_platform.adapters",
    "rca_platform.api",
    "rca_platform.config",
    "rca_platform.evaluation",
]


def list_platform_modules() -> list[str]:
    """Return the dotted names of every module under `rca_platform`."""
    discovered_modules = pkgutil.walk_packages(rca_platform.__path__, prefix="rca_platform.")
    return ["rca_platform", *(module_info.name for module_info in discovered_modules)]


def test_every_layer_package_exists() -> None:
    """Each ADR-001 layer package is present in the source tree."""
    platform_modules = list_platform_modules()
    for layer_package in EXPECTED_LAYER_PACKAGES:
        assert layer_package in platform_modules


@pytest.mark.parametrize("module_name", list_platform_modules())
def test_module_imports_and_has_docstring(module_name: str) -> None:
    """Every platform module imports cleanly and carries a module docstring."""
    module = importlib.import_module(module_name)
    assert module.__doc__ and module.__doc__.strip()
