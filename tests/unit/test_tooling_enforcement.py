"""Tests that the quality toolchain enforces ADR-001 layering and docstring rules (plan M01).

Each test copies the source tree into a temporary directory, plants a
deliberate violation, and runs the real tool against it with the repository's
own configuration.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
VENV_BIN_DIR = Path(sys.executable).parent


def copy_source_tree(destination_dir: Path) -> Path:
    """Copy `src/` into destination_dir and return the copied `src` path."""
    copied_src_dir = destination_dir / "src"
    shutil.copytree(
        REPOSITORY_ROOT / "src",
        copied_src_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )
    return copied_src_dir


def run_tool(
    command: list[str], working_dir: Path, python_path: Path
) -> subprocess.CompletedProcess[str]:
    """Run a toolchain command with `python_path` first on PYTHONPATH."""
    tool_environment = {**os.environ, "PYTHONPATH": str(python_path)}
    return subprocess.run(
        command,
        cwd=working_dir,
        env=tool_environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def lint_imports_executable() -> str:
    """Return the path to the `lint-imports` executable in the active environment."""
    executable_path = VENV_BIN_DIR / "lint-imports"
    if not executable_path.exists():
        pytest.fail("lint-imports is not installed; run `pip install -e '.[dev]'`")
    return str(executable_path)


def test_lint_imports_passes_on_clean_tree(tmp_path: Path, lint_imports_executable: str) -> None:
    """The unmodified skeleton satisfies every ADR-001 contract."""
    copied_src_dir = copy_source_tree(tmp_path)
    result = run_tool(
        [lint_imports_executable, "--config", str(PYPROJECT_PATH), "--no-cache"],
        working_dir=tmp_path,
        python_path=copied_src_dir,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_lint_imports_fails_when_domain_imports_adapters(
    tmp_path: Path, lint_imports_executable: str
) -> None:
    """A domain module importing adapters breaks the domain contract."""
    copied_src_dir = copy_source_tree(tmp_path)
    violating_module = copied_src_dir / "rca_platform" / "domain" / "layering_violation.py"
    violating_module.write_text(
        '"""Deliberate violation."""\n\nfrom rca_platform import adapters\n'
    )

    result = run_tool(
        [lint_imports_executable, "--config", str(PYPROJECT_PATH), "--no-cache"],
        working_dir=tmp_path,
        python_path=copied_src_dir,
    )

    assert result.returncode != 0
    assert "domain imports only stdlib and pydantic BROKEN" in result.stdout


def test_ruff_fails_on_function_without_docstring(tmp_path: Path) -> None:
    """Ruff's pydocstyle rules reject an undocumented public function."""
    undocumented_module = tmp_path / "undocumented.py"
    undocumented_module.write_text(
        '"""Module docstring."""\n\n\ndef compute_total():\n    return 1\n'
    )

    result = run_tool(
        [
            str(VENV_BIN_DIR / "ruff"),
            "check",
            "--no-cache",
            "--config",
            str(PYPROJECT_PATH),
            str(undocumented_module),
        ],
        working_dir=tmp_path,
        python_path=tmp_path,
    )

    assert result.returncode != 0
    assert "D103" in result.stdout
