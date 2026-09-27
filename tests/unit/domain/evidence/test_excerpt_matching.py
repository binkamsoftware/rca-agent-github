"""Table-driven tests for spec §6.2 citation checks 2-4."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from rca_platform.domain.evidence.citation import (
    Citation,
    CitationCheckError,
    ContentTrust,
    VerificationStatus,
)
from rca_platform.domain.evidence.excerpt_matching import (
    CitationCheckResult,
    check_citation_against_content,
    normalize_whitespace,
)
from rca_platform.domain.identifiers import ContentHash, GitSha, parse_artifact_ref

FULL_SHA = GitSha("abc1234" + "0" * 33)
OTHER_SHA = GitSha("def5678" + "0" * 33)
CONTENT_HASH = ContentHash("sha256:" + "a" * 64)
OTHER_CONTENT_HASH = ContentHash("sha256:" + "b" * 64)

FILE_CONTENT = (
    "import os\n"  # line 1
    "\n"  # line 2
    "def send(request):\n"  # line 3
    "    timeout   =  request.timeout\n"  # line 4
    "    return transport.handle(request,\n"  # line 5
    "                            timeout=timeout)\n"  # line 6
)
UNICODE_CONTENT = "Ошибка: соединение закрыто — retry 🚀\nnext line\n"


def build_citation(reference_text: str, excerpt: str, content_hash: str = CONTENT_HASH) -> Citation:
    """Build a consistent, unverified citation for a reference and excerpt."""
    artifact_ref = parse_artifact_ref(reference_text)
    return Citation(
        citation_id="c1",
        kind=artifact_ref.kind,
        ref=artifact_ref,
        sha=getattr(artifact_ref, "sha", None),
        line_start=getattr(artifact_ref, "line_start", None),
        line_end=getattr(artifact_ref, "line_end", None),
        content_hash=content_hash,
        excerpt=excerpt,
        content_trust=ContentTrust.UNTRUSTED,
        retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


@dataclass(frozen=True)
class CheckCase:
    """One row of the citation check table."""

    name: str
    reference_text: str
    excerpt: str
    artifact_content: str
    expected_error: CitationCheckError | None
    artifact_sha: GitSha | None = FULL_SHA
    artifact_content_hash: ContentHash = CONTENT_HASH


CHECK_CASES = [
    # Check 4: excerpt matching.
    CheckCase(
        "exact match in whole file",
        "httpx/a.py@abc1234",
        "def send(request):",
        FILE_CONTENT,
        None,
    ),
    CheckCase(
        "whitespace differences are normalized",
        "httpx/a.py@abc1234#L4",
        "timeout = request.timeout",
        FILE_CONTENT,
        None,
    ),
    CheckCase(
        "excerpt spanning lines matches after collapsing line breaks",
        "httpx/a.py@abc1234#L5-L6",
        "transport.handle(request, timeout=timeout)",
        FILE_CONTENT,
        None,
    ),
    CheckCase(
        "CRLF line ends are stripped",
        "httpx/a.py@abc1234#L1-L2",
        "import os b",
        "import os\r\nb\r\n",
        None,
    ),
    CheckCase(
        "excerpt not present",
        "httpx/a.py@abc1234",
        "def receive(request):",
        FILE_CONTENT,
        CitationCheckError.EXCERPT_NOT_FOUND,
    ),
    CheckCase(
        "excerpt present in file but outside cited lines",
        "httpx/a.py@abc1234#L4-L6",
        "def send(request):",
        FILE_CONTENT,
        CitationCheckError.EXCERPT_NOT_FOUND,
    ),
    CheckCase(
        "excerpt partly outside cited lines",
        "httpx/a.py@abc1234#L3",
        "def send(request): timeout",
        FILE_CONTENT,
        CitationCheckError.EXCERPT_NOT_FOUND,
    ),
    CheckCase(
        "matching is case-sensitive",
        "httpx/a.py@abc1234",
        "DEF SEND(request):",
        FILE_CONTENT,
        CitationCheckError.EXCERPT_NOT_FOUND,
    ),
    CheckCase(
        "unicode excerpt with non-breaking space normalized",
        "issue#1",
        "соединение закрыто — retry 🚀",
        UNICODE_CONTENT,
        None,
        artifact_sha=None,
    ),
    CheckCase(
        "unicode is not otherwise normalized",
        "issue#1",
        "Oшибка",  # Latin 'O', not Cyrillic 'О'
        UNICODE_CONTENT,
        CitationCheckError.EXCERPT_NOT_FOUND,
        artifact_sha=None,
    ),
    # Check 3: line range existence.
    CheckCase(
        "last line cited",
        "httpx/a.py@abc1234#L6",
        "timeout=timeout)",
        FILE_CONTENT,
        None,
    ),
    CheckCase(
        "trailing newline does not add a line",
        "httpx/a.py@abc1234#L7",
        "timeout",
        FILE_CONTENT,
        CitationCheckError.LINE_RANGE_OUT_OF_BOUNDS,
    ),
    CheckCase(
        "range end past last line",
        "httpx/a.py@abc1234#L5-L9",
        "transport",
        FILE_CONTENT,
        CitationCheckError.LINE_RANGE_OUT_OF_BOUNDS,
    ),
    CheckCase(
        "line cited in empty file",
        "httpx/a.py@abc1234#L1",
        "x",
        "",
        CitationCheckError.LINE_RANGE_OUT_OF_BOUNDS,
    ),
    CheckCase(
        "only newline splits lines, not form feed or line separator",
        "httpx/a.py@abc1234#L2",
        "tail",
        "head\x0cmiddle x\ntail",
        None,
    ),
    # Check 2: SHA and content hash.
    CheckCase(
        "abbreviated file sha matches full artifact sha",
        "httpx/a.py@abc1234",
        "import os",
        FILE_CONTENT,
        None,
    ),
    CheckCase(
        "file sha mismatch",
        "httpx/a.py@abc1234",
        "import os",
        FILE_CONTENT,
        CitationCheckError.SHA_MISMATCH,
        artifact_sha=OTHER_SHA,
    ),
    CheckCase(
        "file artifact without sha",
        "httpx/a.py@abc1234",
        "import os",
        FILE_CONTENT,
        CitationCheckError.SHA_MISMATCH,
        artifact_sha=None,
    ),
    CheckCase(
        "commit sha mismatch",
        "commit:abc1234",
        "fix timeout",
        "fix timeout handling",
        CitationCheckError.SHA_MISMATCH,
        artifact_sha=OTHER_SHA,
    ),
    CheckCase(
        "commit sha match",
        "commit:abc1234",
        "fix timeout",
        "fix timeout handling",
        None,
    ),
    CheckCase(
        "file content hash mismatch",
        "httpx/a.py@abc1234",
        "import os",
        FILE_CONTENT,
        CitationCheckError.CONTENT_HASH_MISMATCH,
        artifact_content_hash=OTHER_CONTENT_HASH,
    ),
    CheckCase(
        "issue edited after citation: content hash mismatch",
        "issue#123",
        "connection closed",
        "connection closed unexpectedly",
        CitationCheckError.CONTENT_HASH_MISMATCH,
        artifact_sha=None,
        artifact_content_hash=OTHER_CONTENT_HASH,
    ),
    CheckCase(
        "issue comment at cited revision",
        "issue#123/comment/9",
        "connection closed",
        "connection closed unexpectedly",
        None,
        artifact_sha=None,
    ),
    CheckCase(
        "pr comment edited after citation",
        "PR#4/comment/9",
        "looks good",
        "looks good",
        CitationCheckError.CONTENT_HASH_MISMATCH,
        artifact_sha=None,
        artifact_content_hash=OTHER_CONTENT_HASH,
    ),
    CheckCase(
        "issue citation ignores artifact sha",
        "issue#123",
        "connection closed",
        "connection closed unexpectedly",
        None,
        artifact_sha=OTHER_SHA,
    ),
    # Check order: first failing check wins.
    CheckCase(
        "sha checked before content hash, lines, and excerpt",
        "httpx/a.py@abc1234#L99",
        "absent",
        FILE_CONTENT,
        CitationCheckError.SHA_MISMATCH,
        artifact_sha=OTHER_SHA,
        artifact_content_hash=OTHER_CONTENT_HASH,
    ),
    CheckCase(
        "content hash checked before lines",
        "httpx/a.py@abc1234#L99",
        "absent",
        FILE_CONTENT,
        CitationCheckError.CONTENT_HASH_MISMATCH,
        artifact_content_hash=OTHER_CONTENT_HASH,
    ),
    CheckCase(
        "lines checked before excerpt",
        "httpx/a.py@abc1234#L99",
        "absent",
        FILE_CONTENT,
        CitationCheckError.LINE_RANGE_OUT_OF_BOUNDS,
    ),
]


@pytest.mark.parametrize("case", CHECK_CASES, ids=[case.name for case in CHECK_CASES])
def test_check_citation_against_content(case: CheckCase) -> None:
    """Each §6.2 check (2-4) passes or fails with its own error code, in spec order."""
    citation = build_citation(case.reference_text, case.excerpt)
    result = check_citation_against_content(
        citation, case.artifact_content, case.artifact_content_hash, case.artifact_sha
    )
    if case.expected_error is None:
        assert result == CitationCheckResult(VerificationStatus.VERIFIED)
        assert result.is_verified
    else:
        assert result == CitationCheckResult(VerificationStatus.FAILED, case.expected_error)
        assert not result.is_verified


def test_check_ignores_existing_citation_status() -> None:
    """A citation already marked failed is re-checked on its merits."""
    citation = build_citation("issue#1", "hello").model_copy(
        update={
            "verification_status": VerificationStatus.FAILED,
            "verification_error": CitationCheckError.EXCERPT_NOT_FOUND,
        }
    )
    result = check_citation_against_content(citation, "hello world", CONTENT_HASH, None)
    assert result.is_verified


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a  b", "a b"),
        ("  a\tb\n", "a b"),
        ("a\r\n\r\nb", "a b"),
        ("a  b", "a b"),
        ("", ""),
        (" \n\t ", ""),
        ("naïve café", "naïve café"),
    ],
)
def test_normalize_whitespace(text: str, expected: str) -> None:
    """Runs of any Unicode whitespace collapse to one space and ends are stripped."""
    assert normalize_whitespace(text) == expected


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (VerificationStatus.NOT_VERIFIED, None),
        (VerificationStatus.VERIFIED, CitationCheckError.SHA_MISMATCH),
        (VerificationStatus.FAILED, None),
    ],
)
def test_check_result_rejects_inconsistent_status(
    status: VerificationStatus, error: CitationCheckError | None
) -> None:
    """A result is verified without an error, or failed with one."""
    with pytest.raises(ValueError, match="'verified' or 'failed'|exactly when"):
        CitationCheckResult(status, error)
