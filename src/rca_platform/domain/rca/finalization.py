"""Pure rules that turn a draft RCA into an honest final result (spec §6.3, §7.1, §16.1).

These rules are applied in code after the LLM proposes a draft, so they hold
no matter which model produced it. Support is judged only by verified
citations (spec §6.2); labels proposed by the LLM are never trusted.
"""

from collections.abc import Sequence

from rca_platform.domain.rca.claim import (
    Claim,
    ClaimRole,
    ClaimType,
    HypothesisResolution,
    has_verified_evidence,
)
from rca_platform.domain.rca.outcome import EvidenceSufficiency, RCAStatus

NO_QUALIFYING_ROOT_CAUSE_REASON = (
    "No root-cause claim is a fact or a supported hypothesis backed by a verified citation."
)
UNVERIFIED_ROOT_CAUSE_REASON = "At least one root-cause claim has no verified citation."
BUDGET_EXHAUSTED_REASON = "The investigation stopped early because a budget was exhausted."


def finalize_claims(claims: Sequence[Claim]) -> list[Claim]:
    """Classify each claim by its verified evidence, as required for output (spec §6.3).

    - A fact with a verified citation stays a fact.
    - A fact without one is downgraded to `hypothesis / unresolved`, never
      removed and never kept as a fact (plan S6).
    - A hypothesis becomes `supported` with a verified citation, otherwise
      `unresolved`. Any resolution proposed by the LLM is ignored.
    - A hypothesis is never promoted to a fact.

    Order and citations are preserved, including unverified citations.

    Args:
        claims: Draft claims, in output order.

    Returns:
        The finalized claims, one per input claim, in the same order.
    """
    return [_finalize_claim(claim) for claim in claims]


def _finalize_claim(claim: Claim) -> Claim:
    """Return the finalized form of a single claim (see `finalize_claims`)."""
    is_supported = has_verified_evidence(claim)
    if claim.type is ClaimType.FACT and is_supported:
        return claim
    resolution = HypothesisResolution.SUPPORTED if is_supported else HypothesisResolution.UNRESOLVED
    return Claim.model_validate(
        {**dict(claim), "type": ClaimType.HYPOTHESIS, "resolution": resolution}
    )


def find_finalization_violation(claim: Claim) -> str | None:
    """Describe why a claim may not appear in a final RCA, or return None if it may.

    A final claim is a fact with a verified citation, a `supported` hypothesis
    with a verified citation, or an `unresolved` hypothesis (spec §6.3).

    Args:
        claim: The claim to check.

    Returns:
        A human-readable violation, or None when the claim is final.
    """
    is_supported = has_verified_evidence(claim)
    if claim.type is ClaimType.FACT and not is_supported:
        return f"claim {claim.claim_id!r}: a fact must have at least one verified citation"
    if claim.type is ClaimType.HYPOTHESIS:
        if claim.resolution is None:
            return f"claim {claim.claim_id!r}: a final hypothesis must have a resolution"
        if claim.resolution is HypothesisResolution.SUPPORTED and not is_supported:
            return (
                f"claim {claim.claim_id!r}: a supported hypothesis must have at least one "
                "verified citation"
            )
    return None


def describe_sufficiency_caps(claims: Sequence[Claim], status: RCAStatus) -> list[str]:
    """List every reason evidence sufficiency must be capped at `partial`.

    The reasons come from spec §6.3 (a sufficient RCA needs a qualifying
    root-cause claim), §7.1 (no root-cause claim may rest only on unverified
    evidence), and §16.1 (a budget-exhausted RCA is at most partial). The text
    is deterministic so callers can add it to `missing_evidence`.

    Args:
        claims: The claims of the RCA, finalized or not.
        status: Whether the run completed or exhausted a budget.

    Returns:
        The reasons, in rule order; empty when no cap applies.
    """
    root_cause_claims = [claim for claim in claims if claim.role is ClaimRole.ROOT_CAUSE]
    reasons: list[str] = []
    if not any(_is_qualifying_root_cause(claim) for claim in root_cause_claims):
        reasons.append(NO_QUALIFYING_ROOT_CAUSE_REASON)
    if any(not has_verified_evidence(claim) for claim in root_cause_claims):
        reasons.append(UNVERIFIED_ROOT_CAUSE_REASON)
    if status is RCAStatus.BUDGET_EXHAUSTED:
        reasons.append(BUDGET_EXHAUSTED_REASON)
    return reasons


def cap_evidence_sufficiency(
    proposed: EvidenceSufficiency, claims: Sequence[Claim], status: RCAStatus
) -> EvidenceSufficiency:
    """Lower the LLM-proposed evidence sufficiency to what the evidence allows (spec §7.1).

    The proposed level is kept unless a rule from `describe_sufficiency_caps`
    applies, in which case it is capped at `partial`. The level is never raised.

    Args:
        proposed: The sufficiency proposed by the LLM.
        claims: The claims of the RCA, finalized or not.
        status: Whether the run completed or exhausted a budget.

    Returns:
        The weaker of `proposed` and the cap.
    """
    if describe_sufficiency_caps(claims, status) and (
        proposed.strength > EvidenceSufficiency.PARTIAL.strength
    ):
        return EvidenceSufficiency.PARTIAL
    return proposed


def _is_qualifying_root_cause(claim: Claim) -> bool:
    """Return whether a root-cause claim is a verified fact or a verified supported hypothesis."""
    is_fact_or_supported = (
        claim.type is ClaimType.FACT or claim.resolution is HypothesisResolution.SUPPORTED
    )
    return is_fact_or_supported and has_verified_evidence(claim)
