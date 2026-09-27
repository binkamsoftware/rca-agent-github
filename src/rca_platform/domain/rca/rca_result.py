"""The final RCA output models: `RecommendedFix` and `RCAResult` (spec §6.4, §7.1).

An `RCAResult` can only be constructed in finalized form: every claim obeys
spec §6.3 and the evidence sufficiency respects every cap. A draft from the
LLM must pass through `rca_platform.domain.rca.finalization` first.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rca_platform.domain.evidence.citation import Citation
from rca_platform.domain.rca.claim import Claim, NonBlankText
from rca_platform.domain.rca.finalization import (
    cap_evidence_sufficiency,
    find_finalization_violation,
)
from rca_platform.domain.rca.outcome import EvidenceSufficiency, RCAStatus


class RecommendedFix(BaseModel):
    """An evidence-backed implementation direction for fixing the issue (spec §6.4).

    V1 describes a direction only and never generates code.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: NonBlankText = Field(description="One-sentence description of the proposed fix.")
    rationale: NonBlankText = Field(description="Why this fix addresses the root cause.")
    affected_components: tuple[NonBlankText, ...] = Field(
        default=(), description="Modules, files, or subsystems the fix would change."
    )
    evidence: tuple[Citation, ...] = Field(
        default=(), description="Citations that support the proposed fix direction."
    )


class RCAResult(BaseModel):
    """The finalized outcome of one RCA run (spec §7.1).

    `status` (did the run finish?) and `evidence_sufficiency` (how strong are
    the findings?) are independent; `completed` with `insufficient` is a valid,
    honest outcome.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RCAStatus = Field(
        description="'completed', or 'budget_exhausted' if the run stopped at a budget limit."
    )
    evidence_sufficiency: EvidenceSufficiency = Field(
        description="How strongly the evidence supports the findings, after capping in code."
    )
    root_cause_summary: NonBlankText = Field(description="Short statement of the root cause.")
    reasoning_summary: NonBlankText = Field(description="How the evidence leads to the root cause.")
    claims: tuple[Claim, ...] = Field(
        default=(), description="Finalized claims; claim ids are unique."
    )
    affected_components: tuple[NonBlankText, ...] = Field(
        default=(), description="Modules, files, or subsystems involved in the issue."
    )
    recommended_fix: RecommendedFix | None = Field(
        default=None, description="Proposed fix direction, or None if none can be recommended."
    )
    missing_evidence: tuple[NonBlankText, ...] = Field(
        default=(),
        description="Evidence that would strengthen the RCA; required when sufficiency is "
        "not 'sufficient'.",
    )
    unresolved_questions: tuple[NonBlankText, ...] = Field(
        default=(), description="Questions the investigation could not answer."
    )

    @model_validator(mode="after")
    def _check_finalized(self) -> Self:
        """Enforce the spec §6.3 and §7.1 rules for a final result.

        Raises:
            ValueError: If claim ids repeat, a claim is not finalized, the
                sufficiency exceeds its cap, or `missing_evidence` is empty
                while sufficiency is not `sufficient`.
        """
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim ids must be unique")
        for claim in self.claims:
            violation = find_finalization_violation(claim)
            if violation is not None:
                raise ValueError(violation)
        capped_sufficiency = cap_evidence_sufficiency(
            self.evidence_sufficiency, self.claims, self.status
        )
        if capped_sufficiency is not self.evidence_sufficiency:
            raise ValueError(
                f"evidence_sufficiency {self.evidence_sufficiency.value!r} exceeds the cap "
                f"{capped_sufficiency.value!r}"
            )
        if self.evidence_sufficiency is not EvidenceSufficiency.SUFFICIENT and not (
            self.missing_evidence
        ):
            raise ValueError(
                "missing_evidence must be non-empty when evidence_sufficiency is not 'sufficient'"
            )
        return self
