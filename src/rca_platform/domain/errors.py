"""Typed platform error hierarchy (spec §19.2).

Every error carries a stable `error_code` and a diagnostic `context` mapping.
Context values wrapped in `SensitiveValue` are never rendered, so errors can be
logged or placed in telemetry without leaking sensitive data (spec §14.4).
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar, Final

REDACTED_PLACEHOLDER: Final = "[REDACTED]"


class SensitiveValue:
    """Wrap a context value that must never appear in rendered output (spec §14.4).

    `str()` and `repr()` both return a redaction placeholder. The wrapped value
    stays available through `reveal()` for code that genuinely needs it.
    """

    __slots__ = ("_value",)

    def __init__(self, value: object) -> None:
        """Store the sensitive value.

        Args:
            value: The value to hide from every rendered form.
        """
        self._value = value

    def reveal(self) -> object:
        """Return the wrapped value; never pass the result to logs or telemetry."""
        return self._value

    def __str__(self) -> str:
        """Return the redaction placeholder instead of the value."""
        return REDACTED_PLACEHOLDER

    def __repr__(self) -> str:
        """Return the redaction placeholder instead of the value."""
        return f"SensitiveValue({REDACTED_PLACEHOLDER})"


type ContextValue = str | int | float | bool | None | SensitiveValue
type SafeContextValue = str | int | float | bool | None


class PlatformError(Exception):
    """Base class for every error the platform raises intentionally.

    Attributes:
        error_code: Stable machine-readable identifier for the error class.
        message: Human-readable description; must not contain sensitive data.
        context: Read-only diagnostic key/value pairs.
    """

    error_code: ClassVar[str] = "platform_error"

    def __init__(self, message: str, *, context: Mapping[str, ContextValue] | None = None) -> None:
        """Create the error.

        Args:
            message: Human-readable description; must not contain sensitive data.
            context: Diagnostic values. Wrap anything sensitive in `SensitiveValue`.
        """
        super().__init__(message)
        self.message = message
        self.context: Mapping[str, ContextValue] = MappingProxyType(dict(context or {}))

    def safe_context(self) -> dict[str, SafeContextValue]:
        """Return the context with sensitive values replaced by a placeholder.

        This is the only form of the context that may be logged or put in spans.
        """
        return {
            key: REDACTED_PLACEHOLDER if isinstance(value, SensitiveValue) else value
            for key, value in self.context.items()
        }

    def __str__(self) -> str:
        """Render the message followed by the redacted context, if any."""
        if not self.context:
            return self.message
        rendered_pairs = ", ".join(f"{key}={value!r}" for key, value in self.safe_context().items())
        return f"{self.message} ({rendered_pairs})"


class RepositoryAccessError(PlatformError):
    """Reading repository or GitHub data failed."""

    error_code: ClassVar[str] = "repository_access"


class RetrievalError(PlatformError):
    """Retrieving evidence from the index failed."""

    error_code: ClassVar[str] = "retrieval"


class TemporalIsolationError(PlatformError):
    """Data outside the run's temporal scope was requested or returned.

    Never retried; the run fails (spec §19.2, ADR-002).
    """

    error_code: ClassVar[str] = "temporal_isolation"


class CitationVerificationError(PlatformError):
    """Citation verification could not be performed (spec §6.2)."""

    error_code: ClassVar[str] = "citation_verification"


class LLMProviderError(PlatformError):
    """An LLM provider call failed."""

    error_code: ClassVar[str] = "llm_provider"


class LLMTransientError(LLMProviderError):
    """An LLM provider call failed in a way that may succeed on retry (spec §19.3)."""

    error_code: ClassVar[str] = "llm_transient"


class StructuredOutputError(PlatformError):
    """LLM output did not match the required schema after bounded repair (spec §16.3)."""

    error_code: ClassVar[str] = "structured_output"


class BudgetExceededError(PlatformError):
    """A run budget would be exceeded by the next LLM or tool call (spec §16)."""

    error_code: ClassVar[str] = "budget_exceeded"


class TestEvidenceError(PlatformError):
    """Collecting deterministic test evidence failed."""

    # Not a pytest test class despite the name.
    __test__: ClassVar[bool] = False

    error_code: ClassVar[str] = "test_evidence"


class LifecycleError(PlatformError):
    """An illegal RCA lifecycle transition or unmet precondition."""

    error_code: ClassVar[str] = "lifecycle"


class StaleValidationError(PlatformError):
    """A validation refers to an RCA version or PR head that is no longer current."""

    error_code: ClassVar[str] = "stale_validation"


class PersistenceError(PlatformError):
    """Reading or writing platform state failed."""

    error_code: ClassVar[str] = "persistence"
