"""Validated identifier and reference types (spec §6.1).

Identifiers are validated once, when constructed, so malformed SHAs or
references cannot travel past a boundary. Invalid input raises `ValueError`
(pydantic's `ValidationError` is a `ValueError` subclass).
"""

import re
from typing import Annotated, Any, ClassVar, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    ValidationError,
    model_validator,
)
from pydantic_core import CoreSchema, core_schema

from rca_platform.domain.enums import ArtifactKind

_POSITIVE_NUMBER_PATTERN: Final = r"[1-9][0-9]*"
_SHA_PATTERN: Final = r"[0-9a-f]{7,40}"


class _ValidatedStr(str):
    """A `str` subclass that validates its value on construction.

    Subclasses set `_pattern` and `_description`. The type also works as a
    pydantic field type, validating and serializing as a plain string.
    """

    __slots__ = ()
    _pattern: ClassVar[re.Pattern[str]]
    _description: ClassVar[str]

    def __new__(cls, value: str) -> Self:
        """Validate `value` and return it as an instance of this type.

        Raises:
            ValueError: If `value` does not match the type's format.
        """
        if not isinstance(value, str) or cls._pattern.fullmatch(value) is None:
            raise ValueError(f"invalid {cls.__name__} {value!r}: expected {cls._description}")
        return super().__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        """Validate from a string and serialize back to a plain string."""
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )


class GitSha(_ValidatedStr):
    """A full or abbreviated git object SHA: 7-40 lowercase hex characters."""

    __slots__ = ()
    _pattern = re.compile(_SHA_PATTERN)
    _description = "7-40 lowercase hex characters"


class ContentHash(_ValidatedStr):
    """Hash of a cited artifact revision, written `sha256:<64 lowercase hex>` (spec §6.1)."""

    __slots__ = ()
    _pattern = re.compile(r"sha256:[0-9a-f]{64}")
    _description = "'sha256:' followed by 64 lowercase hex characters"


class RepoId(_ValidatedStr):
    """A GitHub repository identifier, `owner/name`.

    Owner follows GitHub login rules (alphanumerics and single inner hyphens,
    at most 39 characters). Name allows alphanumerics, `.`, `-`, `_`, at most
    100 characters, and cannot be `.` or `..`.
    """

    __slots__ = ()
    _pattern = re.compile(
        r"(?=[A-Za-z0-9-]{1,39}/)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"
        r"/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}"
    )
    _description = "'owner/name' using GitHub owner and repository name rules"

    @property
    def owner(self) -> str:
        """Return the repository owner."""
        return self.split("/", 1)[0]

    @property
    def name(self) -> str:
        """Return the repository name."""
        return self.split("/", 1)[1]


class _FrozenModel(BaseModel):
    """Immutable pydantic base that rejects unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class IssueRef(_FrozenModel):
    """Identifies one GitHub issue in a repository."""

    repo_id: RepoId = Field(description="Repository that owns the issue, as 'owner/name'.")
    issue_number: int = Field(gt=0, description="Issue number within the repository.")


class PullRequestRef(_FrozenModel):
    """Identifies one GitHub pull request in a repository."""

    repo_id: RepoId = Field(description="Repository that owns the pull request, as 'owner/name'.")
    pr_number: int = Field(gt=0, description="Pull request number within the repository.")


class _ArtifactRefBase(_FrozenModel):
    """Common behavior of every artifact reference: rendering to the §6.1 text form."""

    def render(self) -> str:
        """Return the canonical spec §6.1 text form of this reference."""
        raise NotImplementedError

    def __str__(self) -> str:
        """Return the canonical spec §6.1 text form of this reference."""
        return self.render()


class FileArtifactRef(_ArtifactRefBase):
    """A file at a commit, optionally narrowed to lines: `path@sha[#Lstart[-Lend]]`."""

    kind: Literal[ArtifactKind.FILE] = Field(
        default=ArtifactKind.FILE, description="Artifact kind; always 'file'."
    )
    path: str = Field(
        description="Repository-relative POSIX path, without '.' or '..' segments.",
    )
    sha: GitSha = Field(description="Commit SHA the file content is taken from.")
    line_start: int | None = Field(
        default=None, gt=0, description="First cited line (1-based), or None for the whole file."
    )
    line_end: int | None = Field(
        default=None,
        gt=0,
        description="Last cited line (inclusive). None for a single line or the whole file.",
    )

    @model_validator(mode="after")
    def _check_path_and_line_range(self) -> Self:
        """Validate the path and line range.

        Raises:
            ValueError: If the path is not a clean relative path, or the line
                range is inconsistent.
        """
        _validate_repository_path(self.path)
        if self.line_end is not None:
            if self.line_start is None:
                raise ValueError("line_end requires line_start")
            if self.line_end <= self.line_start:
                raise ValueError(
                    f"line_end ({self.line_end}) must be greater than line_start "
                    f"({self.line_start}); write a single line as line_start only"
                )
        return self

    def render(self) -> str:
        """Return `path@sha`, followed by `#Lstart` or `#Lstart-Lend` when lines are set."""
        rendered = f"{self.path}@{self.sha}"
        if self.line_start is not None:
            rendered += f"#L{self.line_start}"
        if self.line_end is not None:
            rendered += f"-L{self.line_end}"
        return rendered


class IssueArtifactRef(_ArtifactRefBase):
    """An issue body: `issue#123`."""

    kind: Literal[ArtifactKind.ISSUE] = Field(
        default=ArtifactKind.ISSUE, description="Artifact kind; always 'issue'."
    )
    issue_number: int = Field(gt=0, description="Issue number.")

    def render(self) -> str:
        """Return `issue#<issue_number>`."""
        return f"issue#{self.issue_number}"


class IssueCommentArtifactRef(_ArtifactRefBase):
    """A comment on an issue: `issue#123/comment/987654321`."""

    kind: Literal[ArtifactKind.ISSUE_COMMENT] = Field(
        default=ArtifactKind.ISSUE_COMMENT, description="Artifact kind; always 'issue_comment'."
    )
    issue_number: int = Field(gt=0, description="Issue the comment belongs to.")
    comment_id: int = Field(gt=0, description="GitHub comment identifier.")

    def render(self) -> str:
        """Return `issue#<issue_number>/comment/<comment_id>`."""
        return f"issue#{self.issue_number}/comment/{self.comment_id}"


class PullRequestArtifactRef(_ArtifactRefBase):
    """A pull request body: `PR#456`."""

    kind: Literal[ArtifactKind.PR] = Field(
        default=ArtifactKind.PR, description="Artifact kind; always 'pr'."
    )
    pr_number: int = Field(gt=0, description="Pull request number.")

    def render(self) -> str:
        """Return `PR#<pr_number>`."""
        return f"PR#{self.pr_number}"


class PullRequestCommentArtifactRef(_ArtifactRefBase):
    """A comment on a pull request: `PR#456/comment/987654321`."""

    kind: Literal[ArtifactKind.PR_COMMENT] = Field(
        default=ArtifactKind.PR_COMMENT, description="Artifact kind; always 'pr_comment'."
    )
    pr_number: int = Field(gt=0, description="Pull request the comment belongs to.")
    comment_id: int = Field(gt=0, description="GitHub comment identifier.")

    def render(self) -> str:
        """Return `PR#<pr_number>/comment/<comment_id>`."""
        return f"PR#{self.pr_number}/comment/{self.comment_id}"


class CommitArtifactRef(_ArtifactRefBase):
    """A commit: `commit:abc1234`."""

    kind: Literal[ArtifactKind.COMMIT] = Field(
        default=ArtifactKind.COMMIT, description="Artifact kind; always 'commit'."
    )
    sha: GitSha = Field(description="Commit SHA.")

    def render(self) -> str:
        """Return `commit:<sha>`."""
        return f"commit:{self.sha}"


class ReleaseArtifactRef(_ArtifactRefBase):
    """A release by tag: `release:0.27.0`."""

    kind: Literal[ArtifactKind.RELEASE] = Field(
        default=ArtifactKind.RELEASE, description="Artifact kind; always 'release'."
    )
    tag: str = Field(pattern=r"^[^\s]+$", description="Release tag name; non-empty, no whitespace.")

    def render(self) -> str:
        """Return `release:<tag>`."""
        return f"release:{self.tag}"


class CiRunArtifactRef(_ArtifactRefBase):
    """A CI run: `ci_run#789`."""

    kind: Literal[ArtifactKind.CI_RUN] = Field(
        default=ArtifactKind.CI_RUN, description="Artifact kind; always 'ci_run'."
    )
    ci_run_id: int = Field(gt=0, description="CI run identifier.")

    def render(self) -> str:
        """Return `ci_run#<ci_run_id>`."""
        return f"ci_run#{self.ci_run_id}"


type ArtifactRef = Annotated[
    FileArtifactRef
    | IssueArtifactRef
    | IssueCommentArtifactRef
    | PullRequestArtifactRef
    | PullRequestCommentArtifactRef
    | CommitArtifactRef
    | ReleaseArtifactRef
    | CiRunArtifactRef,
    Field(discriminator="kind"),
]
"""Any spec §6.1 artifact reference, discriminated by `kind`."""

_ISSUE_PATTERN: Final = re.compile(rf"issue#(?P<issue_number>{_POSITIVE_NUMBER_PATTERN})")
_ISSUE_COMMENT_PATTERN: Final = re.compile(
    rf"issue#(?P<issue_number>{_POSITIVE_NUMBER_PATTERN})"
    rf"/comment/(?P<comment_id>{_POSITIVE_NUMBER_PATTERN})"
)
_PR_PATTERN: Final = re.compile(rf"PR#(?P<pr_number>{_POSITIVE_NUMBER_PATTERN})")
_PR_COMMENT_PATTERN: Final = re.compile(
    rf"PR#(?P<pr_number>{_POSITIVE_NUMBER_PATTERN})"
    rf"/comment/(?P<comment_id>{_POSITIVE_NUMBER_PATTERN})"
)
_COMMIT_PATTERN: Final = re.compile(rf"commit:(?P<sha>{_SHA_PATTERN})")
_RELEASE_PATTERN: Final = re.compile(r"release:(?P<tag>\S+)")
_CI_RUN_PATTERN: Final = re.compile(rf"ci_run#(?P<ci_run_id>{_POSITIVE_NUMBER_PATTERN})")
# Path is matched greedily so a path containing '@' or '#' still parses from the right.
_FILE_PATTERN: Final = re.compile(
    rf"(?P<path>.+)@(?P<sha>{_SHA_PATTERN})"
    rf"(?:#L(?P<line_start>{_POSITIVE_NUMBER_PATTERN})"
    rf"(?:-L(?P<line_end>{_POSITIVE_NUMBER_PATTERN}))?)?"
)


def parse_artifact_ref(reference_text: str) -> ArtifactRef:
    """Parse a spec §6.1 reference string into a typed artifact reference.

    Parsing is strict so that `parse_artifact_ref(text).render() == text` for
    every accepted input.

    Args:
        reference_text: A reference such as `httpx/_client.py@abc1234#L120-L147`.

    Returns:
        The typed reference for the matching §6.1 format.

    Raises:
        ValueError: If the text matches no §6.1 format or has invalid parts.
            The message always names the rejected reference.
    """
    try:
        artifact_ref = _match_artifact_ref(reference_text)
    except ValidationError as error:
        reasons = "; ".join(detail["msg"] for detail in error.errors())
        raise ValueError(f"invalid artifact reference {reference_text!r}: {reasons}") from error
    if artifact_ref is None:
        raise ValueError(
            f"invalid artifact reference {reference_text!r}: expected one of "
            "'path@sha[#Lstart[-Lend]]', 'issue#N', 'issue#N/comment/ID', 'PR#N', "
            "'PR#N/comment/ID', 'commit:SHA', 'release:TAG', 'ci_run#ID'"
        )
    return artifact_ref


def _match_artifact_ref(reference_text: str) -> ArtifactRef | None:
    """Build the reference for the first matching §6.1 format, or None if none match.

    Raises:
        ValidationError: If a format matches but its parts are invalid.
    """
    if match := _ISSUE_COMMENT_PATTERN.fullmatch(reference_text):
        return IssueCommentArtifactRef(
            issue_number=int(match["issue_number"]), comment_id=int(match["comment_id"])
        )
    if match := _ISSUE_PATTERN.fullmatch(reference_text):
        return IssueArtifactRef(issue_number=int(match["issue_number"]))
    if match := _PR_COMMENT_PATTERN.fullmatch(reference_text):
        return PullRequestCommentArtifactRef(
            pr_number=int(match["pr_number"]), comment_id=int(match["comment_id"])
        )
    if match := _PR_PATTERN.fullmatch(reference_text):
        return PullRequestArtifactRef(pr_number=int(match["pr_number"]))
    if match := _COMMIT_PATTERN.fullmatch(reference_text):
        return CommitArtifactRef(sha=GitSha(match["sha"]))
    if match := _RELEASE_PATTERN.fullmatch(reference_text):
        return ReleaseArtifactRef(tag=match["tag"])
    if match := _CI_RUN_PATTERN.fullmatch(reference_text):
        return CiRunArtifactRef(ci_run_id=int(match["ci_run_id"]))
    if match := _FILE_PATTERN.fullmatch(reference_text):
        line_start = match["line_start"]
        line_end = match["line_end"]
        return FileArtifactRef(
            path=match["path"],
            sha=GitSha(match["sha"]),
            line_start=int(line_start) if line_start is not None else None,
            line_end=int(line_end) if line_end is not None else None,
        )
    return None


def _validate_repository_path(path: str) -> None:
    """Reject paths that are absolute, non-POSIX, or contain empty/dot segments.

    Raises:
        ValueError: If the path is not a clean repository-relative POSIX path.
    """
    if any(character in path for character in "\\\0\r\n"):
        raise ValueError(f"invalid path {path!r}: backslashes and control characters not allowed")
    segments = path.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise ValueError(
            f"invalid path {path!r}: must be relative, with no empty, '.' or '..' segments"
        )
