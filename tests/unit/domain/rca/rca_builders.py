"""Builders for citations and claims used by the RCA domain tests."""

from collections.abc import Sequence
from datetime import UTC, datetime

from rca_platform.domain.evidence.citation import (
    Citation,
    CitationCheckError,
    ContentTrust,
    VerificationStatus,
)
from rca_platform.domain.identifiers import parse_artifact_ref
from rca_platform.domain.rca.claim import Claim, ClaimRole, ClaimType, HypothesisResolution

RETRIEVED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
VERIFIED_AT = datetime(2026, 9, 1, 12, 5, tzinfo=UTC)

VERIFIED = VerificationStatus.VERIFIED
FAILED = VerificationStatus.FAILED
NOT_VERIFIED = VerificationStatus.NOT_VERIFIED


def build_citation(citation_id: str, verification_status: VerificationStatus) -> Citation:
    """Return an issue citation with consistent status fields for the given status."""
    return Citation(
        citation_id=citation_id,
        kind=parse_artifact_ref("issue#123").kind,
        ref=parse_artifact_ref("issue#123"),
        content_hash="sha256:" + "a" * 64,
        excerpt="quoted text",
        content_trust=ContentTrust.UNTRUSTED,
        verification_status=verification_status,
        verification_error=(
            CitationCheckError.EXCERPT_NOT_FOUND if verification_status is FAILED else None
        ),
        verified_at=VERIFIED_AT if verification_status is VERIFIED else None,
        retrieved_at=RETRIEVED_AT,
    )


def build_claim(
    claim_id: str = "claim-1",
    claim_type: ClaimType = ClaimType.FACT,
    role: ClaimRole = ClaimRole.ROOT_CAUSE,
    citation_statuses: Sequence[VerificationStatus] = (VERIFIED,),
    resolution: HypothesisResolution | None = None,
) -> Claim:
    """Return a claim whose citations have the given verification statuses, in order."""
    return Claim(
        claim_id=claim_id,
        type=claim_type,
        role=role,
        statement="The pool is not released on timeout.",
        evidence=tuple(
            build_citation(f"{claim_id}-c{i}", status) for i, status in enumerate(citation_statuses)
        ),
        resolution=resolution,
    )
