"""Shared pytest configuration: marker registration and suite selection (spec 21)."""

import pytest

SERVICE_MARKERS: dict[str, str] = {
    "integration": "needs real external services (Docker, provider APIs); excluded by default",
    "e2e": "end-to-end run across the whole platform; excluded by default",
    "evaluation": "benchmark harness run; excluded by default and from CI",
}


def pytest_configure(config: pytest.Config) -> None:
    """Register the service markers so `--strict-markers` accepts them."""
    for marker_name, marker_description in SERVICE_MARKERS.items():
        config.addinivalue_line("markers", f"{marker_name}: {marker_description}")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Treat an empty marker-selected suite as success.

    `pytest -m integration` must exit cleanly while no integration tests exist
    yet (plan M01). Only marker-filtered runs are relaxed, so an unfiltered run
    that collects nothing still fails loudly.
    """
    is_marker_filtered = bool(session.config.getoption("markexpr"))
    if is_marker_filtered and exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED:
        session.exitstatus = pytest.ExitCode.OK
