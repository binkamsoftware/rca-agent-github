"""Pure checks that a citation matches given artifact content (spec §6.2, checks 2-4).

Check 1, "the artifact exists in the Store within the run's temporal scope",
needs a Store and is performed by the application layer before calling
`check_citation_against_content`.
"""

from dataclasses import dataclass

from rca_platform.domain.evidence.citation import (
    SHA_CITATION_KINDS,
    Citation,
    CitationCheckError,
    VerificationStatus,
)
from rca_platform.domain.identifiers import ContentHash, GitSha


@dataclass(frozen=True, slots=True)
class CitationCheckResult:
    """Outcome of checking one citation against artifact content.

    Attributes:
        status: `verified` or `failed`; never `not_verified`.
        error: The failed check's code when `status` is `failed`, else None.
    """

    status: VerificationStatus
    error: CitationCheckError | None = None

    def __post_init__(self) -> None:
        """Validate that the status and error agree.

        Raises:
            ValueError: If status is `not_verified`, or the error is present
                without `failed` status or missing with it.
        """
        if self.status is VerificationStatus.NOT_VERIFIED:
            raise ValueError("a check result is either 'verified' or 'failed'")
        if (self.status is VerificationStatus.FAILED) != (self.error is not None):
            raise ValueError("error must be set exactly when status is 'failed'")

    @property
    def is_verified(self) -> bool:
        """Return whether every applicable check passed."""
        return self.status is VerificationStatus.VERIFIED


_VERIFIED = CitationCheckResult(VerificationStatus.VERIFIED)


def normalize_whitespace(text: str) -> str:
    r"""Collapse every run of whitespace to one space and strip both ends (spec §6.2 check 4).

    Unicode whitespace, including line ends such as `\r\n`, counts as
    whitespace. No other Unicode normalization is applied.

    Args:
        text: Any text.

    Returns:
        The text with whitespace runs collapsed to single spaces.
    """
    return " ".join(text.split())


def check_citation_against_content(
    citation: Citation,
    artifact_content: str,
    artifact_content_hash: ContentHash,
    artifact_sha: GitSha | None,
) -> CitationCheckResult:
    r"""Decide whether a citation's revision, lines, and excerpt match the artifact.

    Runs spec §6.2 checks 2-4 in order and stops at the first failure:

    2. For `file` and `commit` citations, the citation's SHA must be a prefix
       of `artifact_sha` (so abbreviated SHAs match). For every kind,
       `content_hash` must equal `artifact_content_hash`.
    3. The cited line range must exist in the content. Lines are split on
       `\n` only, as git does; a trailing newline does not add a line.
    4. The normalized excerpt must be a substring of the normalized cited
       lines, or of the whole content when the citation has no line range.

    The function is pure: it reads no state and performs no I/O.

    Args:
        citation: The citation to check. Its current status is ignored.
        artifact_content: Full text of the resolved artifact revision.
        artifact_content_hash: Content hash of that revision.
        artifact_sha: Commit SHA of that revision for `file` and `commit`
            artifacts; None for other kinds.

    Returns:
        `verified`, or `failed` with the code of the first failing check.
    """
    if citation.kind in SHA_CITATION_KINDS and (
        artifact_sha is None or citation.sha is None or not artifact_sha.startswith(citation.sha)
    ):
        return _failed(CitationCheckError.SHA_MISMATCH)
    if citation.content_hash != artifact_content_hash:
        return _failed(CitationCheckError.CONTENT_HASH_MISMATCH)

    cited_text = artifact_content
    if citation.line_start is not None:
        content_lines = _split_lines(artifact_content)
        line_end = citation.line_end if citation.line_end is not None else citation.line_start
        if line_end > len(content_lines):
            return _failed(CitationCheckError.LINE_RANGE_OUT_OF_BOUNDS)
        cited_text = "\n".join(content_lines[citation.line_start - 1 : line_end])

    if normalize_whitespace(citation.excerpt) not in normalize_whitespace(cited_text):
        return _failed(CitationCheckError.EXCERPT_NOT_FOUND)
    return _VERIFIED


def _split_lines(content: str) -> list[str]:
    r"""Split content into lines on `\n`, ignoring one trailing newline."""
    if not content:
        return []
    return content.removesuffix("\n").split("\n")


def _failed(error: CitationCheckError) -> CitationCheckResult:
    """Return a failed result carrying `error`."""
    return CitationCheckResult(VerificationStatus.FAILED, error)
