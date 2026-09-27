"""The `Citation` model and its status enumerations (spec §6.1).

A citation points at one artifact revision and quotes the text a claim relies
on. Construction enforces internal consistency only; whether the quote really
exists at the stated location is decided by
`rca_platform.domain.evidence.excerpt_matching` (spec §6.2).
"""

from enum import StrEnum
from typing import Self, TypeAlias

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from rca_platform.domain.enums import ArtifactKind
from rca_platform.domain.identifiers import ArtifactRef, ContentHash, GitSha

CitationKind: TypeAlias = ArtifactKind  # noqa: UP040 - must stay usable as the enum class
"""Kind of artifact a citation points at; the same values as `ArtifactKind`."""


class ContentTrust(StrEnum):
    """Whether cited content comes from a trusted platform component (spec §6.1, ADR-004)."""

    SYSTEM = "system"
    UNTRUSTED = "untrusted"


class VerificationStatus(StrEnum):
    """Outcome of verifying a citation in code (spec §6.2)."""

    VERIFIED = "verified"
    FAILED = "failed"
    NOT_VERIFIED = "not_verified"


class CitationCheckError(StrEnum):
    """Why a citation failed verification, one code per spec §6.2 check (2-4)."""

    SHA_MISMATCH = "sha_mismatch"
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    LINE_RANGE_OUT_OF_BOUNDS = "line_range_out_of_bounds"
    EXCERPT_NOT_FOUND = "excerpt_not_found"


SHA_CITATION_KINDS = frozenset({CitationKind.FILE, CitationKind.COMMIT})
"""Citation kinds that identify their revision by git SHA as well as content hash."""
_SYSTEM_TRUST_KINDS = frozenset({CitationKind.CI_RUN})


class Citation(BaseModel):
    """A verbatim quote from one revision of one artifact (spec §6.1).

    `kind`, `sha`, `line_start`, and `line_end` repeat parts of `ref`, as the
    spec lists them as fields; construction rejects any disagreement so the two
    can never drift apart.

    A citation whose status is not `verified` must never support a fact,
    coverage, or finding (spec §6.2).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    citation_id: str = Field(
        pattern=r"^\S+$",
        max_length=128,
        description="Identifier of this citation, unique within its RCA; no whitespace.",
    )
    kind: CitationKind = Field(description="Kind of the cited artifact; must equal ref.kind.")
    ref: ArtifactRef = Field(description="Typed spec §6.1 reference to the cited artifact.")
    sha: GitSha | None = Field(
        default=None,
        description="Git SHA for 'file' and 'commit' citations (equal to ref.sha); else None.",
    )
    line_start: int | None = Field(
        default=None,
        gt=0,
        description="First cited line for 'file' citations (equal to ref.line_start); else None.",
    )
    line_end: int | None = Field(
        default=None,
        gt=0,
        description="Last cited line for 'file' citations (equal to ref.line_end); else None.",
    )
    content_hash: ContentHash = Field(
        description="Hash of the cited artifact revision, 'sha256:<64 hex>'. Pins mutable "
        "artifacts such as issues and comments to the revision that was read.",
    )
    excerpt: str = Field(
        description="Verbatim text the claim relies on; must contain non-whitespace text.",
    )
    content_trust: ContentTrust = Field(
        description="'system' only for structured output of trusted platform components "
        "(allowed on 'ci_run' citations only); everything else is 'untrusted'.",
    )
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.NOT_VERIFIED,
        description="Result of verifying the citation in code.",
    )
    verification_error: CitationCheckError | None = Field(
        default=None, description="Why verification failed; set only when status is 'failed'."
    )
    verified_at: AwareDatetime | None = Field(
        default=None, description="When verification succeeded; set only when status is 'verified'."
    )
    retrieved_at: AwareDatetime = Field(description="When the cited content was retrieved.")

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        """Validate agreement with `ref`, the excerpt, trust, and status fields.

        Raises:
            ValueError: If any field contradicts another.
        """
        self._check_matches_ref()
        if not self.excerpt.strip():
            raise ValueError("excerpt must contain non-whitespace text")
        if self.content_trust is ContentTrust.SYSTEM and self.kind not in _SYSTEM_TRUST_KINDS:
            raise ValueError(f"content_trust 'system' is not allowed for kind {self.kind.value!r}")
        self._check_status_fields()
        return self

    def _check_matches_ref(self) -> None:
        """Reject `kind`, `sha`, or line fields that differ from `ref`.

        Raises:
            ValueError: On the first field that disagrees with `ref`.
        """
        if self.kind is not self.ref.kind:
            raise ValueError(
                f"kind {self.kind.value!r} does not match ref kind {self.ref.kind.value!r}"
            )
        expected_sha = getattr(self.ref, "sha", None) if self.kind in SHA_CITATION_KINDS else None
        if self.sha != expected_sha:
            raise ValueError(f"sha {self.sha!r} does not match ref {self.ref.render()!r}")
        expected_line_start = getattr(self.ref, "line_start", None)
        expected_line_end = getattr(self.ref, "line_end", None)
        if (self.line_start, self.line_end) != (expected_line_start, expected_line_end):
            raise ValueError(
                f"line range ({self.line_start}, {self.line_end}) does not match "
                f"ref {self.ref.render()!r}"
            )

    def _check_status_fields(self) -> None:
        """Require the error and timestamp fields that the status implies, and no others.

        Raises:
            ValueError: If `verification_error` or `verified_at` contradicts the status.
        """
        has_error = self.verification_error is not None
        has_verified_at = self.verified_at is not None
        expected_error, expected_verified_at = {
            VerificationStatus.VERIFIED: (False, True),
            VerificationStatus.FAILED: (True, False),
            VerificationStatus.NOT_VERIFIED: (False, False),
        }[self.verification_status]
        if has_error != expected_error or has_verified_at != expected_verified_at:
            raise ValueError(
                f"status {self.verification_status.value!r} requires verification_error "
                f"{'set' if expected_error else 'None'} and verified_at "
                f"{'set' if expected_verified_at else 'None'}"
            )
