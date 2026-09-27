"""Tests for the spec §6.4 `RecommendedFix` and §7.1 `RCAResult` models."""

from typing import Any

import pytest
from rca_builders import FAILED, VERIFIED, build_citation, build_claim

from rca_platform.domain.rca.claim import ClaimRole, ClaimType, HypothesisResolution
from rca_platform.domain.rca.finalization import finalize_claims
from rca_platform.domain.rca.outcome import EvidenceSufficiency, RCAStatus
from rca_platform.domain.rca.rca_result import RCAResult, RecommendedFix

VERIFIED_ROOT_CAUSE_FACT = build_claim(claim_id="rc-fact", claim_type=ClaimType.FACT)


def build_result_fields(**overrides: Any) -> dict[str, Any]:
    """Return valid 'sufficient' RCAResult constructor fields, with overrides applied."""
    fields: dict[str, Any] = {
        "status": RCAStatus.COMPLETED,
        "evidence_sufficiency": EvidenceSufficiency.SUFFICIENT,
        "root_cause_summary": "The connection pool leaks on timeout.",
        "reasoning_summary": "The timeout path returns before releasing the connection.",
        "claims": (VERIFIED_ROOT_CAUSE_FACT,),
    }
    fields.update(overrides)
    return fields


def test_valid_sufficient_result_is_accepted() -> None:
    """A completed RCA with a verified root-cause fact may be sufficient."""
    rca_result = RCAResult(**build_result_fields())
    assert rca_result.evidence_sufficiency is EvidenceSufficiency.SUFFICIENT
    assert rca_result.missing_evidence == ()


def test_completed_and_insufficient_is_valid() -> None:
    """Status and sufficiency are independent; completed + insufficient is honest (§7.1)."""
    rca_result = RCAResult(
        **build_result_fields(
            evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT,
            claims=(),
            missing_evidence=("A reproduction on the affected version.",),
        )
    )
    assert rca_result.status is RCAStatus.COMPLETED


@pytest.mark.parametrize(
    "sufficiency", [EvidenceSufficiency.PARTIAL, EvidenceSufficiency.INSUFFICIENT]
)
def test_empty_missing_evidence_is_rejected_when_not_sufficient(
    sufficiency: EvidenceSufficiency,
) -> None:
    """missing_evidence is required whenever sufficiency is not 'sufficient' (§7.1)."""
    with pytest.raises(ValueError, match="missing_evidence must be non-empty"):
        RCAResult(**build_result_fields(evidence_sufficiency=sufficiency))


def test_failed_status_is_rejected() -> None:
    """A failed run produces no RCAResult, so 'failed' is not a status (plan S1)."""
    with pytest.raises(ValueError):
        RCAResult(**build_result_fields(status="failed"))


@pytest.mark.parametrize(
    "claims",
    [
        (),
        (build_claim(claim_id="symptom", role=ClaimRole.SYMPTOM),),
        (
            VERIFIED_ROOT_CAUSE_FACT,
            build_claim(
                claim_id="rc-open",
                claim_type=ClaimType.HYPOTHESIS,
                citation_statuses=(),
                resolution=HypothesisResolution.UNRESOLVED,
            ),
        ),
    ],
)
def test_sufficient_is_rejected_when_the_cap_applies(claims: tuple[Any, ...]) -> None:
    """'sufficient' cannot be stored when a §6.3 / §7.1 cap rule applies."""
    with pytest.raises(ValueError, match="exceeds the cap 'partial'"):
        RCAResult(**build_result_fields(claims=claims))


def test_budget_exhausted_cannot_be_sufficient() -> None:
    """A budget-exhausted RCA is capped at 'partial' (§16.1)."""
    with pytest.raises(ValueError, match="exceeds the cap 'partial'"):
        RCAResult(**build_result_fields(status=RCAStatus.BUDGET_EXHAUSTED))


def test_budget_exhausted_partial_is_accepted() -> None:
    """A budget-exhausted RCA may report its best partial result."""
    rca_result = RCAResult(
        **build_result_fields(
            status=RCAStatus.BUDGET_EXHAUSTED,
            evidence_sufficiency=EvidenceSufficiency.PARTIAL,
            missing_evidence=("The investigation stopped early because a budget was exhausted.",),
        )
    )
    assert rca_result.evidence_sufficiency is EvidenceSufficiency.PARTIAL


@pytest.mark.parametrize(
    "unfinalized_claim",
    [
        build_claim(claim_id="bad-fact", claim_type=ClaimType.FACT, citation_statuses=(FAILED,)),
        build_claim(claim_id="open", claim_type=ClaimType.HYPOTHESIS, resolution=None),
        build_claim(
            claim_id="fake-supported",
            claim_type=ClaimType.HYPOTHESIS,
            citation_statuses=(FAILED,),
            resolution=HypothesisResolution.SUPPORTED,
        ),
    ],
)
def test_unfinalized_claim_is_rejected(unfinalized_claim: Any) -> None:
    """An RCAResult can only hold claims that obey §6.3."""
    with pytest.raises(ValueError, match=unfinalized_claim.claim_id):
        RCAResult(**build_result_fields(claims=(VERIFIED_ROOT_CAUSE_FACT, unfinalized_claim)))


def test_finalized_draft_claims_are_accepted() -> None:
    """Claims passed through finalize_claims always build a valid result."""
    draft_claims = [
        VERIFIED_ROOT_CAUSE_FACT,
        build_claim(claim_id="bad-fact", claim_type=ClaimType.FACT, citation_statuses=(FAILED,)),
        build_claim(claim_id="open", claim_type=ClaimType.HYPOTHESIS, role=ClaimRole.CONTEXT),
    ]
    rca_result = RCAResult(
        **build_result_fields(
            claims=tuple(finalize_claims(draft_claims)),
            evidence_sufficiency=EvidenceSufficiency.PARTIAL,
            missing_evidence=("At least one root-cause claim has no verified citation.",),
        )
    )
    assert len(rca_result.claims) == 3


def test_duplicate_claim_ids_are_rejected() -> None:
    """Claim ids are unique within an RCA."""
    with pytest.raises(ValueError, match="claim ids must be unique"):
        RCAResult(
            **build_result_fields(claims=(VERIFIED_ROOT_CAUSE_FACT, VERIFIED_ROOT_CAUSE_FACT))
        )


@pytest.mark.parametrize("field_name", ["root_cause_summary", "reasoning_summary"])
def test_blank_summary_is_rejected(field_name: str) -> None:
    """Summaries must contain text."""
    with pytest.raises(ValueError):
        RCAResult(**build_result_fields(**{field_name: "  "}))


def test_recommended_fix_round_trips_through_json() -> None:
    """A result with a recommended fix serializes and parses back unchanged."""
    recommended_fix = RecommendedFix(
        summary="Release the connection in a finally block.",
        rationale="The timeout path currently skips the release.",
        affected_components=("httpx/_pool.py",),
        evidence=(build_citation("fix-c1", VERIFIED),),
    )
    rca_result = RCAResult(**build_result_fields(recommended_fix=recommended_fix))
    assert RCAResult.model_validate_json(rca_result.model_dump_json()) == rca_result


def _collect_properties_without_description(schema: dict[str, Any]) -> list[str]:
    """Return 'Model.field' for every schema property that lacks a description."""
    models = {"RCAResult": schema, **schema.get("$defs", {})}
    return [
        f"{model_name}.{property_name}"
        for model_name, model_schema in models.items()
        for property_name, property_schema in model_schema.get("properties", {}).items()
        if "description" not in property_schema
    ]


def test_rca_result_json_schema_describes_every_field() -> None:
    """The JSON schema generates, with a description on every field of every model (M04)."""
    schema = RCAResult.model_json_schema()
    assert _collect_properties_without_description(schema) == []
    assert {"Claim", "Citation", "RecommendedFix"} <= set(schema["$defs"])
