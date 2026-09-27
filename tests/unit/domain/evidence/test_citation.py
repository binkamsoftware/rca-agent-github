"""Tests for the spec §6.1 `Citation` model and its consistency rules."""

from datetime import UTC, datetime
from typing import Any

import pytest

from rca_platform.domain.enums import ArtifactKind
from rca_platform.domain.evidence.citation import (
    Citation,
    CitationCheckError,
    CitationKind,
    ContentTrust,
    VerificationStatus,
)
from rca_platform.domain.identifiers import parse_artifact_ref

CONTENT_HASH = "sha256:" + "a" * 64
RETRIEVED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def build_citation_fields(reference_text: str, **overrides: Any) -> dict[str, Any]:
    """Return consistent Citation constructor fields for a reference, with overrides applied."""
    artifact_ref = parse_artifact_ref(reference_text)
    fields: dict[str, Any] = {
        "citation_id": "c1",
        "kind": artifact_ref.kind,
        "ref": artifact_ref,
        "sha": getattr(artifact_ref, "sha", None),
        "line_start": getattr(artifact_ref, "line_start", None),
        "line_end": getattr(artifact_ref, "line_end", None),
        "content_hash": CONTENT_HASH,
        "excerpt": "quoted text",
        "content_trust": ContentTrust.UNTRUSTED,
        "retrieved_at": RETRIEVED_AT,
    }
    fields.update(overrides)
    return fields


def test_citation_kind_is_artifact_kind() -> None:
    """CitationKind is an alias of ArtifactKind, not a second enum."""
    assert CitationKind is ArtifactKind


@pytest.mark.parametrize(
    "reference_text",
    [
        "httpx/_client.py@abc1234#L120-L147",
        "httpx/_client.py@abc1234#L120",
        "httpx/_client.py@abc1234",
        "issue#123",
        "issue#123/comment/987654321",
        "PR#456",
        "PR#456/comment/987654321",
        "commit:abc1234",
        "release:0.27.0",
        "ci_run#789",
    ],
)
def test_citation_accepts_every_reference_kind(reference_text: str) -> None:
    """A consistent citation is built for every §6.1 reference form, unverified by default."""
    citation = Citation(**build_citation_fields(reference_text))
    assert citation.ref.render() == reference_text
    assert citation.verification_status is VerificationStatus.NOT_VERIFIED


def test_citation_round_trips_through_json() -> None:
    """Serializing and re-validating a citation yields an equal citation."""
    citation = Citation(**build_citation_fields("httpx/_client.py@abc1234#L1-L3"))
    assert Citation.model_validate_json(citation.model_dump_json()) == citation


@pytest.mark.parametrize(
    ("reference_text", "overrides", "message"),
    [
        ("issue#123", {"kind": ArtifactKind.PR}, "does not match ref kind"),
        ("httpx/a.py@abc1234", {"sha": "def5678"}, "sha"),
        ("httpx/a.py@abc1234", {"sha": None}, "sha"),
        ("issue#123", {"sha": "abc1234"}, "sha"),
        ("httpx/a.py@abc1234#L1-L3", {"line_end": 4}, "line range"),
        ("httpx/a.py@abc1234", {"line_start": 1}, "line range"),
        ("commit:abc1234", {"line_start": 1}, "line range"),
    ],
)
def test_citation_rejects_fields_that_disagree_with_ref(
    reference_text: str, overrides: dict[str, Any], message: str
) -> None:
    """kind, sha, and line fields must equal the values carried by ref."""
    with pytest.raises(ValueError, match=message):
        Citation(**build_citation_fields(reference_text, **overrides))


@pytest.mark.parametrize("excerpt", ["", "   ", "\n\t "])
def test_citation_rejects_empty_or_whitespace_excerpt(excerpt: str) -> None:
    """An excerpt with no non-whitespace text cannot cite anything."""
    with pytest.raises(ValueError, match="excerpt must contain"):
        Citation(**build_citation_fields("issue#1", excerpt=excerpt))


def test_citation_requires_content_hash() -> None:
    """Every citation, including mutable artifacts, pins its revision by content hash."""
    fields = build_citation_fields("issue#1")
    del fields["content_hash"]
    with pytest.raises(ValueError, match="content_hash"):
        Citation(**fields)


def test_citation_rejects_malformed_content_hash() -> None:
    """content_hash must use the sha256:<64 hex> form."""
    with pytest.raises(ValueError, match="ContentHash"):
        Citation(**build_citation_fields("issue#1", content_hash="md5:abc"))


def test_citation_allows_system_trust_for_ci_run() -> None:
    """CI outcomes parsed by a trusted adapter may be marked system content."""
    citation = Citation(**build_citation_fields("ci_run#7", content_trust=ContentTrust.SYSTEM))
    assert citation.content_trust is ContentTrust.SYSTEM


@pytest.mark.parametrize("reference_text", ["issue#1", "httpx/a.py@abc1234", "PR#2"])
def test_citation_rejects_system_trust_for_repository_content(reference_text: str) -> None:
    """Repository and GitHub content is always untrusted (spec §6.1, ADR-004)."""
    with pytest.raises(ValueError, match="content_trust 'system' is not allowed"):
        Citation(**build_citation_fields(reference_text, content_trust=ContentTrust.SYSTEM))


def test_citation_rejects_naive_datetimes() -> None:
    """Timestamps must carry a timezone."""
    with pytest.raises(ValueError, match="timezone"):
        Citation(**build_citation_fields("issue#1", retrieved_at=datetime(2026, 9, 1)))  # noqa: DTZ001


@pytest.mark.parametrize(
    ("status", "error", "verified_at", "is_valid"),
    [
        (VerificationStatus.NOT_VERIFIED, None, None, True),
        (VerificationStatus.VERIFIED, None, RETRIEVED_AT, True),
        (VerificationStatus.FAILED, CitationCheckError.EXCERPT_NOT_FOUND, None, True),
        (VerificationStatus.NOT_VERIFIED, CitationCheckError.SHA_MISMATCH, None, False),
        (VerificationStatus.NOT_VERIFIED, None, RETRIEVED_AT, False),
        (VerificationStatus.VERIFIED, None, None, False),
        (VerificationStatus.VERIFIED, CitationCheckError.SHA_MISMATCH, RETRIEVED_AT, False),
        (VerificationStatus.FAILED, None, None, False),
        (VerificationStatus.FAILED, CitationCheckError.SHA_MISMATCH, RETRIEVED_AT, False),
    ],
)
def test_citation_status_fields_must_agree(
    status: VerificationStatus,
    error: CitationCheckError | None,
    verified_at: datetime | None,
    is_valid: bool,
) -> None:
    """Status verified needs only verified_at, failed needs only an error, not_verified neither."""
    fields = build_citation_fields(
        "issue#1", verification_status=status, verification_error=error, verified_at=verified_at
    )
    if is_valid:
        assert Citation(**fields).verification_status is status
    else:
        with pytest.raises(ValueError, match="requires verification_error"):
            Citation(**fields)


def test_citation_is_immutable() -> None:
    """Citations are frozen so a verified citation cannot be altered afterwards."""
    citation = Citation(**build_citation_fields("issue#1"))
    with pytest.raises(ValueError, match="frozen"):
        citation.excerpt = "changed"  # type: ignore[misc]
