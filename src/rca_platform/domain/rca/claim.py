"""The `Claim` model and its classification enumerations (spec §6.3).

Construction checks structure only, so a draft claim produced during an
investigation can still be represented. Whether a claim may appear in a final
RCA is decided by `rca_platform.domain.rca.finalization`.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from rca_platform.domain.evidence.citation import Citation, VerificationStatus

NonBlankText = Annotated[str, StringConstraints(pattern=r"\S")]
"""A string that contains at least one non-whitespace character."""


class ClaimType(StrEnum):
    """Whether a claim is asserted as established or as a candidate explanation (spec §6.3)."""

    FACT = "fact"
    HYPOTHESIS = "hypothesis"


class ClaimRole(StrEnum):
    """The part a claim plays in explaining the issue (spec §6.3)."""

    ROOT_CAUSE = "root_cause"
    CONTRIBUTING_FACTOR = "contributing_factor"
    SYMPTOM = "symptom"
    CONTEXT = "context"


class HypothesisResolution(StrEnum):
    """Outcome of a hypothesis in a final RCA (spec §6.3)."""

    SUPPORTED = "supported"
    UNRESOLVED = "unresolved"


class Claim(BaseModel):
    """One statement of an RCA together with the citations offered for it (spec §6.3).

    Only verified citations count as support (spec §6.2). Unverified citations
    stay on the claim so reviewers can see what was offered and rejected.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str = Field(
        pattern=r"^\S+$",
        max_length=128,
        description="Identifier of this claim, stable within an RCA version; no whitespace.",
    )
    type: ClaimType = Field(
        description="'fact' needs at least one verified citation in a final RCA; "
        "'hypothesis' is a candidate explanation."
    )
    role: ClaimRole = Field(description="The part this claim plays in explaining the issue.")
    statement: NonBlankText = Field(description="The claim itself, as one or more sentences.")
    evidence: tuple[Citation, ...] = Field(
        default=(),
        description="Citations offered for the claim; only verified ones count as support.",
    )
    resolution: HypothesisResolution | None = Field(
        default=None,
        description="For hypotheses only: 'supported' (at least one verified citation) or "
        "'unresolved'. None for facts, and for hypotheses still under investigation.",
    )

    @model_validator(mode="after")
    def _check_structure(self) -> Self:
        """Reject a resolution on a fact and duplicate citation ids.

        Raises:
            ValueError: If a fact has a resolution or two citations share an id.
        """
        if self.type is ClaimType.FACT and self.resolution is not None:
            raise ValueError(f"claim {self.claim_id!r}: a fact must not have a resolution")
        citation_ids = [citation.citation_id for citation in self.evidence]
        if len(citation_ids) != len(set(citation_ids)):
            raise ValueError(f"claim {self.claim_id!r}: citation ids must be unique")
        return self


def has_verified_evidence(claim: Claim) -> bool:
    """Return whether at least one of the claim's citations is verified (spec §6.2)."""
    return any(
        citation.verification_status is VerificationStatus.VERIFIED for citation in claim.evidence
    )
