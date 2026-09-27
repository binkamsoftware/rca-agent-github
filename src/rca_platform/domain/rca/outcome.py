"""RCA run status and evidence sufficiency levels (spec §7.1, §16.1).

Kept apart from `rca_result` so the finalization rules can use these levels
without importing the result model that depends on them.
"""

from enum import StrEnum


class RCAStatus(StrEnum):
    """Whether the RCA run finished its investigation (spec §7.1).

    There is no `failed` value: a failed run produces no RCAResult and is
    recorded on the RunManifest only (spec §7.1, plan S1).
    """

    COMPLETED = "completed"
    BUDGET_EXHAUSTED = "budget_exhausted"


class EvidenceSufficiency(StrEnum):
    """How strongly the evidence supports the RCA's findings (spec §7.1)."""

    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"

    @property
    def strength(self) -> int:
        """Return the rank of this level; a higher rank means stronger evidence."""
        return _STRENGTH_BY_SUFFICIENCY[self]


_STRENGTH_BY_SUFFICIENCY = {
    EvidenceSufficiency.INSUFFICIENT: 0,
    EvidenceSufficiency.PARTIAL: 1,
    EvidenceSufficiency.SUFFICIENT: 2,
}
