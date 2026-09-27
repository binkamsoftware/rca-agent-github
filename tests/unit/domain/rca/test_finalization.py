"""Tests for the spec §6.3 / §7.1 / §16.1 finalization and sufficiency-cap rules."""

import itertools
import random

import pytest
from rca_builders import FAILED, NOT_VERIFIED, VERIFIED, build_claim

from rca_platform.domain.evidence.citation import VerificationStatus
from rca_platform.domain.rca.claim import Claim, ClaimRole, ClaimType, HypothesisResolution
from rca_platform.domain.rca.finalization import (
    BUDGET_EXHAUSTED_REASON,
    NO_QUALIFYING_ROOT_CAUSE_REASON,
    UNVERIFIED_ROOT_CAUSE_REASON,
    cap_evidence_sufficiency,
    describe_sufficiency_caps,
    finalize_claims,
    find_finalization_violation,
)
from rca_platform.domain.rca.outcome import EvidenceSufficiency, RCAStatus

FACT = ClaimType.FACT
HYPOTHESIS = ClaimType.HYPOTHESIS
SUPPORTED = HypothesisResolution.SUPPORTED
UNRESOLVED = HypothesisResolution.UNRESOLVED
SUFFICIENT = EvidenceSufficiency.SUFFICIENT
PARTIAL = EvidenceSufficiency.PARTIAL
INSUFFICIENT = EvidenceSufficiency.INSUFFICIENT
COMPLETED = RCAStatus.COMPLETED
BUDGET_EXHAUSTED = RCAStatus.BUDGET_EXHAUSTED

CITATION_STATUS_PATTERNS: list[tuple[VerificationStatus, ...]] = [
    (),
    (VERIFIED,),
    (FAILED,),
    (NOT_VERIFIED,),
    (FAILED, NOT_VERIFIED),
    (NOT_VERIFIED, VERIFIED),
]
DRAFT_CLASSIFICATIONS: list[tuple[ClaimType, HypothesisResolution | None]] = [
    (FACT, None),
    (HYPOTHESIS, None),
    (HYPOTHESIS, SUPPORTED),
    (HYPOTHESIS, UNRESOLVED),
]


# ------------------------------------------------------------------ finalize_claims


@pytest.mark.parametrize(
    ("claim_type", "draft_resolution", "citation_statuses", "expected_type", "expected_resolution"),
    [
        # Facts keep their type only with a verified citation; otherwise downgraded (S6).
        (FACT, None, (VERIFIED,), FACT, None),
        (FACT, None, (FAILED, VERIFIED), FACT, None),
        (FACT, None, (), HYPOTHESIS, UNRESOLVED),
        (FACT, None, (FAILED,), HYPOTHESIS, UNRESOLVED),
        (FACT, None, (NOT_VERIFIED,), HYPOTHESIS, UNRESOLVED),
        # Hypotheses are resolved from verified evidence; the proposed resolution is ignored.
        (HYPOTHESIS, None, (VERIFIED,), HYPOTHESIS, SUPPORTED),
        (HYPOTHESIS, UNRESOLVED, (VERIFIED,), HYPOTHESIS, SUPPORTED),
        (HYPOTHESIS, None, (), HYPOTHESIS, UNRESOLVED),
        (HYPOTHESIS, SUPPORTED, (), HYPOTHESIS, UNRESOLVED),
        (HYPOTHESIS, SUPPORTED, (FAILED, NOT_VERIFIED), HYPOTHESIS, UNRESOLVED),
    ],
)
def test_finalize_claims_classifies_by_verified_evidence(
    claim_type: ClaimType,
    draft_resolution: HypothesisResolution | None,
    citation_statuses: tuple[VerificationStatus, ...],
    expected_type: ClaimType,
    expected_resolution: HypothesisResolution | None,
) -> None:
    """Each claim's final type and resolution depend only on its verified citations."""
    draft_claim = build_claim(
        claim_type=claim_type, citation_statuses=citation_statuses, resolution=draft_resolution
    )
    [final_claim] = finalize_claims([draft_claim])
    assert (final_claim.type, final_claim.resolution) == (expected_type, expected_resolution)


def test_unverified_fact_is_downgraded_not_removed() -> None:
    """A fact failing verification keeps its id, statement, role, and citations (plan S6)."""
    draft_claim = build_claim(
        claim_type=FACT, role=ClaimRole.CONTRIBUTING_FACTOR, citation_statuses=(FAILED,)
    )
    [final_claim] = finalize_claims([draft_claim])
    assert final_claim.claim_id == draft_claim.claim_id
    assert final_claim.statement == draft_claim.statement
    assert final_claim.role is draft_claim.role
    assert final_claim.evidence == draft_claim.evidence


def test_finalize_claims_preserves_order_and_count() -> None:
    """Finalization never drops, adds, or reorders claims."""
    draft_claims = [
        build_claim(claim_id=f"claim-{i}", claim_type=claim_type, citation_statuses=statuses)
        for i, (claim_type, statuses) in enumerate(
            [(FACT, (FAILED,)), (HYPOTHESIS, (VERIFIED,)), (FACT, (VERIFIED,))]
        )
    ]
    final_claims = finalize_claims(draft_claims)
    assert [claim.claim_id for claim in final_claims] == ["claim-0", "claim-1", "claim-2"]


def test_finalized_claims_have_no_violations() -> None:
    """Every finalized claim, from every draft shape, is valid in a final RCA."""
    for (claim_type, draft_resolution), statuses in itertools.product(
        DRAFT_CLASSIFICATIONS, CITATION_STATUS_PATTERNS
    ):
        draft_claim = build_claim(
            claim_type=claim_type, citation_statuses=statuses, resolution=draft_resolution
        )
        [final_claim] = finalize_claims([draft_claim])
        assert find_finalization_violation(final_claim) is None


# ------------------------------------------------------------------ property tests


def _generate_random_draft_claims(rng: random.Random) -> list[Claim]:
    """Return 0-6 draft claims with random type, role, resolution, and citations."""
    draft_claims: list[Claim] = []
    for i in range(rng.randint(0, 6)):
        claim_type, draft_resolution = rng.choice(DRAFT_CLASSIFICATIONS)
        draft_claims.append(
            build_claim(
                claim_id=f"claim-{i}",
                claim_type=claim_type,
                role=rng.choice(list(ClaimRole)),
                citation_statuses=rng.choice(CITATION_STATUS_PATTERNS),
                resolution=draft_resolution,
            )
        )
    return draft_claims


@pytest.mark.parametrize("seed", range(200))
def test_finalization_properties_hold_for_random_drafts(seed: int) -> None:
    """Finalization never adds facts, never promotes a hypothesis, and is idempotent."""
    draft_claims = _generate_random_draft_claims(random.Random(seed))
    final_claims = finalize_claims(draft_claims)

    def count_facts(claims: list[Claim]) -> int:
        """Return how many claims are facts."""
        return sum(claim.type is FACT for claim in claims)

    assert count_facts(final_claims) <= count_facts(draft_claims)
    for draft_claim, final_claim in zip(draft_claims, final_claims, strict=True):
        if draft_claim.type is HYPOTHESIS:
            assert final_claim.type is HYPOTHESIS
    assert finalize_claims(final_claims) == final_claims


# ------------------------------------------------------------------ find_finalization_violation


@pytest.mark.parametrize(
    ("claim_type", "resolution", "citation_statuses", "expected_fragment"),
    [
        (FACT, None, (FAILED,), "a fact must have at least one verified citation"),
        (FACT, None, (), "a fact must have at least one verified citation"),
        (HYPOTHESIS, None, (VERIFIED,), "a final hypothesis must have a resolution"),
        (HYPOTHESIS, SUPPORTED, (NOT_VERIFIED,), "a supported hypothesis must have"),
        (FACT, None, (VERIFIED,), None),
        (HYPOTHESIS, SUPPORTED, (VERIFIED,), None),
        (HYPOTHESIS, UNRESOLVED, (), None),
        (HYPOTHESIS, UNRESOLVED, (VERIFIED,), None),
    ],
)
def test_find_finalization_violation(
    claim_type: ClaimType,
    resolution: HypothesisResolution | None,
    citation_statuses: tuple[VerificationStatus, ...],
    expected_fragment: str | None,
) -> None:
    """Only facts and supported hypotheses with verified citations, or unresolved ones, pass."""
    claim = build_claim(
        claim_type=claim_type, citation_statuses=citation_statuses, resolution=resolution
    )
    violation = find_finalization_violation(claim)
    if expected_fragment is None:
        assert violation is None
    else:
        assert violation is not None and expected_fragment in violation


# ------------------------------------------------------------------ sufficiency caps

VERIFIED_ROOT_CAUSE_FACT = build_claim(claim_id="rc-fact", claim_type=FACT)
SUPPORTED_ROOT_CAUSE = build_claim(
    claim_id="rc-supported", claim_type=HYPOTHESIS, resolution=SUPPORTED
)
UNRESOLVED_ROOT_CAUSE = build_claim(
    claim_id="rc-unresolved", claim_type=HYPOTHESIS, citation_statuses=(), resolution=UNRESOLVED
)
UNVERIFIED_ROOT_CAUSE_FACT = build_claim(
    claim_id="rc-unverified-fact", claim_type=FACT, citation_statuses=(FAILED,)
)
VERIFIED_SYMPTOM_FACT = build_claim(claim_id="symptom", claim_type=FACT, role=ClaimRole.SYMPTOM)


@pytest.mark.parametrize(
    ("claims", "status", "expected_reasons"),
    [
        ([VERIFIED_ROOT_CAUSE_FACT], COMPLETED, []),
        ([SUPPORTED_ROOT_CAUSE, VERIFIED_SYMPTOM_FACT], COMPLETED, []),
        ([], COMPLETED, [NO_QUALIFYING_ROOT_CAUSE_REASON]),
        ([VERIFIED_SYMPTOM_FACT], COMPLETED, [NO_QUALIFYING_ROOT_CAUSE_REASON]),
        (
            [UNRESOLVED_ROOT_CAUSE],
            COMPLETED,
            [NO_QUALIFYING_ROOT_CAUSE_REASON, UNVERIFIED_ROOT_CAUSE_REASON],
        ),
        # An unverified 'fact' label never qualifies, even before finalization.
        (
            [UNVERIFIED_ROOT_CAUSE_FACT],
            COMPLETED,
            [NO_QUALIFYING_ROOT_CAUSE_REASON, UNVERIFIED_ROOT_CAUSE_REASON],
        ),
        # One qualifying root cause does not excuse another with only unverified evidence.
        (
            [VERIFIED_ROOT_CAUSE_FACT, UNRESOLVED_ROOT_CAUSE],
            COMPLETED,
            [UNVERIFIED_ROOT_CAUSE_REASON],
        ),
        ([VERIFIED_ROOT_CAUSE_FACT], BUDGET_EXHAUSTED, [BUDGET_EXHAUSTED_REASON]),
        (
            [],
            BUDGET_EXHAUSTED,
            [NO_QUALIFYING_ROOT_CAUSE_REASON, BUDGET_EXHAUSTED_REASON],
        ),
    ],
)
def test_describe_sufficiency_caps(
    claims: list[Claim], status: RCAStatus, expected_reasons: list[str]
) -> None:
    """Every applicable §6.3 / §7.1 / §16.1 cap rule is reported, in rule order."""
    assert describe_sufficiency_caps(claims, status) == expected_reasons


@pytest.mark.parametrize(
    ("proposed", "claims", "status", "expected"),
    [
        (SUFFICIENT, [VERIFIED_ROOT_CAUSE_FACT], COMPLETED, SUFFICIENT),
        (SUFFICIENT, [SUPPORTED_ROOT_CAUSE], COMPLETED, SUFFICIENT),
        (SUFFICIENT, [VERIFIED_SYMPTOM_FACT], COMPLETED, PARTIAL),
        (SUFFICIENT, [UNRESOLVED_ROOT_CAUSE], COMPLETED, PARTIAL),
        (SUFFICIENT, [VERIFIED_ROOT_CAUSE_FACT, UNRESOLVED_ROOT_CAUSE], COMPLETED, PARTIAL),
        (SUFFICIENT, [VERIFIED_ROOT_CAUSE_FACT], BUDGET_EXHAUSTED, PARTIAL),
        # The cap never raises a weaker proposal.
        (PARTIAL, [VERIFIED_ROOT_CAUSE_FACT], COMPLETED, PARTIAL),
        (PARTIAL, [], BUDGET_EXHAUSTED, PARTIAL),
        (INSUFFICIENT, [VERIFIED_ROOT_CAUSE_FACT], COMPLETED, INSUFFICIENT),
        (INSUFFICIENT, [], BUDGET_EXHAUSTED, INSUFFICIENT),
    ],
)
def test_cap_evidence_sufficiency(
    proposed: EvidenceSufficiency,
    claims: list[Claim],
    status: RCAStatus,
    expected: EvidenceSufficiency,
) -> None:
    """Sufficiency is capped at 'partial' when any cap rule applies, and never raised."""
    assert cap_evidence_sufficiency(proposed, claims, status) is expected
