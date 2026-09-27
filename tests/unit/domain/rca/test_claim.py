"""Tests for the spec §6.3 `Claim` model's structural rules."""

import pytest
from rca_builders import FAILED, NOT_VERIFIED, VERIFIED, build_citation, build_claim

from rca_platform.domain.evidence.citation import VerificationStatus
from rca_platform.domain.rca.claim import (
    Claim,
    ClaimRole,
    ClaimType,
    HypothesisResolution,
    has_verified_evidence,
)


def test_fact_with_resolution_is_rejected() -> None:
    """A fact never carries a hypothesis resolution."""
    with pytest.raises(ValueError, match="a fact must not have a resolution"):
        build_claim(claim_type=ClaimType.FACT, resolution=HypothesisResolution.SUPPORTED)


def test_draft_hypothesis_without_resolution_is_allowed() -> None:
    """A hypothesis under investigation may have no resolution yet."""
    claim = build_claim(claim_type=ClaimType.HYPOTHESIS, citation_statuses=())
    assert claim.resolution is None


def test_duplicate_citation_ids_are_rejected() -> None:
    """Citation ids are unique within a claim."""
    citation = build_citation("c1", VERIFIED)
    with pytest.raises(ValueError, match="citation ids must be unique"):
        Claim(
            claim_id="claim-1",
            type=ClaimType.FACT,
            role=ClaimRole.SYMPTOM,
            statement="Requests hang.",
            evidence=(citation, citation),
        )


@pytest.mark.parametrize("statement", ["", "   ", "\n\t"])
def test_blank_statement_is_rejected(statement: str) -> None:
    """A claim must state something."""
    with pytest.raises(ValueError):
        Claim(claim_id="claim-1", type=ClaimType.FACT, role=ClaimRole.CONTEXT, statement=statement)


@pytest.mark.parametrize("claim_id", ["", "has space", "x" * 129])
def test_invalid_claim_id_is_rejected(claim_id: str) -> None:
    """Claim ids are non-empty, contain no whitespace, and are at most 128 characters."""
    with pytest.raises(ValueError):
        build_claim(claim_id=claim_id)


@pytest.mark.parametrize(
    ("citation_statuses", "expected"),
    [
        ((), False),
        ((FAILED,), False),
        ((NOT_VERIFIED,), False),
        ((FAILED, NOT_VERIFIED), False),
        ((VERIFIED,), True),
        ((FAILED, VERIFIED), True),
    ],
)
def test_has_verified_evidence_needs_a_verified_citation(
    citation_statuses: tuple[VerificationStatus, ...], expected: bool
) -> None:
    """Only a citation with status 'verified' counts as support (spec §6.2)."""
    claim = build_claim(claim_type=ClaimType.HYPOTHESIS, citation_statuses=citation_statuses)
    assert has_verified_evidence(claim) is expected


def test_claim_is_immutable() -> None:
    """Claims are frozen so finalization cannot be bypassed by mutation."""
    claim = build_claim()
    with pytest.raises(ValueError):
        claim.type = ClaimType.HYPOTHESIS  # type: ignore[misc]
