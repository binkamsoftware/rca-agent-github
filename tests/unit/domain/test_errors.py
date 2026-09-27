"""Tests for the platform error hierarchy (spec §19.2, §14.4)."""

import pytest

from rca_platform.domain import errors
from rca_platform.domain.errors import (
    REDACTED_PLACEHOLDER,
    LLMProviderError,
    LLMTransientError,
    PlatformError,
    SensitiveValue,
    TemporalIsolationError,
)

SPEC_HIERARCHY: list[tuple[type[PlatformError], type[PlatformError]]] = [
    (errors.RepositoryAccessError, PlatformError),
    (errors.RetrievalError, PlatformError),
    (errors.TemporalIsolationError, PlatformError),
    (errors.CitationVerificationError, PlatformError),
    (errors.LLMProviderError, PlatformError),
    (errors.LLMTransientError, errors.LLMProviderError),
    (errors.StructuredOutputError, PlatformError),
    (errors.BudgetExceededError, PlatformError),
    (errors.TestEvidenceError, PlatformError),
    (errors.LifecycleError, PlatformError),
    (errors.StaleValidationError, PlatformError),
    (errors.PersistenceError, PlatformError),
]


@pytest.mark.parametrize(("error_class", "parent_class"), SPEC_HIERARCHY)
def test_error_class_has_spec_parent(
    error_class: type[PlatformError], parent_class: type[PlatformError]
) -> None:
    """Each §19.2 error subclasses its documented parent."""
    assert error_class.__bases__ == (parent_class,)


def test_llm_transient_error_is_caught_as_llm_provider_error() -> None:
    """Handlers for LLMProviderError also catch transient failures."""
    with pytest.raises(LLMProviderError):
        raise LLMTransientError("rate limited")


def test_error_codes_are_unique_and_stable_per_class() -> None:
    """Every error class has its own error_code."""
    all_classes = [PlatformError, *(error_class for error_class, _ in SPEC_HIERARCHY)]
    error_codes = [error_class.error_code for error_class in all_classes]
    assert len(set(error_codes)) == len(error_codes)
    assert TemporalIsolationError.error_code == "temporal_isolation"


def test_str_without_context_is_message() -> None:
    """An error with no context renders as its message."""
    assert str(PlatformError("boom")) == "boom"


def test_str_includes_non_sensitive_context() -> None:
    """Non-sensitive context values appear in the rendered error."""
    error = TemporalIsolationError("out of scope", context={"run_id": "run-1", "attempt": 2})
    assert str(error) == "out of scope (run_id='run-1', attempt=2)"


def test_str_and_repr_exclude_sensitive_context_values() -> None:
    """Sensitive context values never appear in str(), repr(), or safe_context()."""
    secret_text = "ghp_not_a_real_token_value"
    error = PlatformError("auth failed", context={"token": SensitiveValue(secret_text)})
    assert secret_text not in str(error)
    assert secret_text not in repr(error)
    assert REDACTED_PLACEHOLDER in str(error)
    assert error.safe_context() == {"token": REDACTED_PLACEHOLDER}


def test_sensitive_value_reveal_returns_wrapped_value() -> None:
    """Code that needs the raw value can still get it explicitly."""
    assert SensitiveValue(42).reveal() == 42


def test_context_is_read_only_and_decoupled_from_input() -> None:
    """Mutating the input mapping or the context after construction is not possible."""
    input_context: dict[str, errors.ContextValue] = {"run_id": "run-1"}
    error = PlatformError("boom", context=input_context)
    input_context["run_id"] = "changed"
    assert error.context["run_id"] == "run-1"
    with pytest.raises(TypeError):
        error.context["run_id"] = "changed"  # type: ignore[index]
