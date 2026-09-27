"""Enumerations shared across the RCA and Validation stages."""

from enum import StrEnum


class AgentType(StrEnum):
    """Which agent a run belongs to (spec run manifest, `agent_type`)."""

    RCA = "rca"
    VALIDATION = "validation"


class RunMode(StrEnum):
    """How a run sources its data (spec run manifest, `mode`).

    Replay and evaluation runs must never read current GitHub state (ADR-002).
    """

    LIVE = "live"
    REPLAY = "replay"
    EVALUATION = "evaluation"


class ArtifactKind(StrEnum):
    """Kind of artifact a citation or artifact reference points at (spec §6.1)."""

    FILE = "file"
    ISSUE = "issue"
    ISSUE_COMMENT = "issue_comment"
    PR = "pr"
    PR_COMMENT = "pr_comment"
    COMMIT = "commit"
    RELEASE = "release"
    CI_RUN = "ci_run"
