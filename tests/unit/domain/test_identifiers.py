"""Tests for validated identifiers and spec §6.1 artifact references."""

import pytest
from pydantic import BaseModel, TypeAdapter

from rca_platform.domain.enums import ArtifactKind
from rca_platform.domain.identifiers import (
    ArtifactRef,
    ContentHash,
    FileArtifactRef,
    GitSha,
    IssueRef,
    PullRequestRef,
    RepoId,
    parse_artifact_ref,
)

VALID_SHA_40 = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize("sha_text", ["abc1234", VALID_SHA_40, "0" * 12])
def test_git_sha_accepts_7_to_40_lowercase_hex(sha_text: str) -> None:
    """Abbreviated and full lowercase SHAs are valid."""
    assert GitSha(sha_text) == sha_text


@pytest.mark.parametrize(
    "sha_text", ["", "abc123", VALID_SHA_40 + "8", "ABC1234", "abc123g", " abc1234", "abc1234\n"]
)
def test_git_sha_rejects_malformed_values(sha_text: str) -> None:
    """Too short, too long, uppercase, non-hex, or padded SHAs are rejected."""
    with pytest.raises(ValueError, match="invalid GitSha"):
        GitSha(sha_text)


def test_content_hash_accepts_sha256_prefixed_hex() -> None:
    """A sha256-prefixed 64-hex digest is valid."""
    hash_text = "sha256:" + "a" * 64
    assert ContentHash(hash_text) == hash_text


@pytest.mark.parametrize("hash_text", ["a" * 64, "sha256:" + "a" * 63, "sha1:" + "a" * 40])
def test_content_hash_rejects_other_formats(hash_text: str) -> None:
    """Bare, truncated, or non-sha256 hashes are rejected."""
    with pytest.raises(ValueError, match="invalid ContentHash"):
        ContentHash(hash_text)


def test_repo_id_exposes_owner_and_name() -> None:
    """RepoId splits into owner and name."""
    repo_id = RepoId("encode/httpx")
    assert (repo_id.owner, repo_id.name) == ("encode", "httpx")


@pytest.mark.parametrize(
    "repo_text",
    [
        "encode",
        "encode/",
        "/httpx",
        "-encode/httpx",
        "en--code/httpx",
        "a/b/c",
        "encode/..",
        "o" * 40 + "/httpx",
        "encode/ht tpx",
    ],
)
def test_repo_id_rejects_malformed_values(repo_text: str) -> None:
    """Missing parts, bad owner hyphens, extra slashes, and dot names are rejected."""
    with pytest.raises(ValueError, match="invalid RepoId"):
        RepoId(repo_text)


def test_identifier_types_validate_and_serialize_as_pydantic_fields() -> None:
    """Identifier types validate inside models and dump as plain strings."""

    class Holder(BaseModel):
        """Model with an identifier field."""

        sha: GitSha

    assert Holder(sha="abc1234").model_dump() == {"sha": "abc1234"}
    assert isinstance(Holder(sha="abc1234").sha, GitSha)
    with pytest.raises(ValueError):
        Holder(sha="nothex!")


def test_issue_and_pull_request_refs_validate_fields() -> None:
    """Issue and PR refs require a valid repo and a positive number."""
    assert IssueRef(repo_id=RepoId("encode/httpx"), issue_number=1).issue_number == 1
    with pytest.raises(ValueError):
        PullRequestRef(repo_id=RepoId("encode/httpx"), pr_number=0)
    with pytest.raises(ValueError):
        IssueRef.model_validate({"repo_id": "not-a-repo", "issue_number": 1})


SPEC_REFERENCE_EXAMPLES: list[tuple[str, ArtifactKind]] = [
    ("httpx/_client.py@abc1234#L120-L147", ArtifactKind.FILE),
    ("issue#123", ArtifactKind.ISSUE),
    ("issue#123/comment/987654321", ArtifactKind.ISSUE_COMMENT),
    ("PR#456", ArtifactKind.PR),
    ("PR#456/comment/987654321", ArtifactKind.PR_COMMENT),
    ("commit:abc1234", ArtifactKind.COMMIT),
    ("release:0.27.0", ArtifactKind.RELEASE),
    ("ci_run#789", ArtifactKind.CI_RUN),
    # Additional file forms allowed by the §6.1 format rules.
    ("httpx/_client.py@abc1234#L120", ArtifactKind.FILE),
    ("httpx/_client.py@abc1234", ArtifactKind.FILE),
    (f"docs/a@b#c.md@{VALID_SHA_40}#L1-L2", ArtifactKind.FILE),
]


@pytest.mark.parametrize(("reference_text", "expected_kind"), SPEC_REFERENCE_EXAMPLES)
def test_artifact_ref_round_trips_every_spec_format(
    reference_text: str, expected_kind: ArtifactKind
) -> None:
    """Every §6.1 reference parses to the right kind and renders identically."""
    artifact_ref = parse_artifact_ref(reference_text)
    assert artifact_ref.kind == expected_kind
    assert artifact_ref.render() == reference_text
    assert str(artifact_ref) == reference_text


@pytest.mark.parametrize(("reference_text", "expected_kind"), SPEC_REFERENCE_EXAMPLES)
def test_artifact_ref_round_trips_through_pydantic_discriminator(
    reference_text: str, expected_kind: ArtifactKind
) -> None:
    """The ArtifactRef union serializes and re-validates by its kind discriminator."""
    adapter: TypeAdapter[ArtifactRef] = TypeAdapter(ArtifactRef)
    artifact_ref = parse_artifact_ref(reference_text)
    restored_ref = adapter.validate_python(adapter.dump_python(artifact_ref))
    assert restored_ref == artifact_ref


def test_file_ref_parses_line_range_fields() -> None:
    """Line range numbers are exposed as integers."""
    artifact_ref = parse_artifact_ref("httpx/_client.py@abc1234#L120-L147")
    assert isinstance(artifact_ref, FileArtifactRef)
    assert (artifact_ref.path, artifact_ref.sha) == ("httpx/_client.py", "abc1234")
    assert (artifact_ref.line_start, artifact_ref.line_end) == (120, 147)


@pytest.mark.parametrize(
    "reference_text",
    [
        "",
        "issue#",
        "issue#0",
        "issue#012",
        "issue#12/comment/",
        "pr#456",
        "PR#456/comment/0",
        "commit:ABC1234",
        "commit:abc12",
        "release:",
        "release:with space",
        "ci_run#-1",
        "httpx/_client.py@abc12",
        "httpx/_client.py@abc1234#L0",
        "httpx/_client.py@abc1234#L5-L5",
        "httpx/_client.py@abc1234#L9-L5",
        "httpx/_client.py@abc1234#L5-",
        "httpx/_client.py@abc1234#120",
        "/etc/passwd@abc1234",
        "httpx/../secrets@abc1234",
        "httpx//client.py@abc1234",
        "httpx\\client.py@abc1234",
        "@abc1234",
    ],
)
def test_malformed_artifact_refs_raise_value_error(reference_text: str) -> None:
    """Malformed references raise ValueError naming the bad input."""
    with pytest.raises(ValueError, match="invalid"):
        parse_artifact_ref(reference_text)


def test_file_ref_rejects_line_end_without_line_start() -> None:
    """A line end alone is not a valid range."""
    with pytest.raises(ValueError, match="line_end requires line_start"):
        FileArtifactRef(path="a.py", sha=GitSha("abc1234"), line_end=3)


def test_artifact_refs_are_immutable() -> None:
    """References cannot be mutated after construction."""
    artifact_ref = parse_artifact_ref("issue#123")
    with pytest.raises(ValueError):
        artifact_ref.issue_number = 5  # type: ignore[union-attr]
