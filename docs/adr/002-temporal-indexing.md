# ADR-002: Temporal Indexing and Isolation

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-27 |
| Spec sections | §13, §15, §21, §22 |

## Context

The RCA Agent must see only what was knowable at a cutoff. In historical replay this is what makes evaluation valid; in live mode it makes runs reproducible.

Constraints:

1. Maintaining a separate vector index per commit is too expensive.
2. Git timestamps are unreliable: author and committer dates survive rebases and cherry-picks, so a commit authored in March may land on the default branch in June.
3. GitHub issues, comments, and PR bodies are **mutable**. The API returns the current state, which often contains the answer ("Fixed in #456", label `fixed`, state `closed`).
4. Prompt instructions cannot enforce any of this.

## Decision

### 1. Two clocks: code by ancestry, discussion by time

| Artifact class | Visibility defined by |
|---|---|
| Repository files (code, tests, docs, in-repo changelog) | **first-parent ancestry** of the default branch at `cutoff_sha` |
| Commits | reachable from `cutoff_sha` via first parent |
| Issues, comments, PRs, reviews, releases | GitHub event timestamps ≤ `cutoff_time`, per **revision** |

`cutoff_sha` is the last commit on the default branch's first-parent chain whose landing time ≤ `cutoff_time`. Landing time is the committer date of the first-parent commit (for GitHub merge and squash merges, this is the merge time). The derivation is recorded on the RunManifest.

### 2. Linearized history and validity ranges for code

During ingestion, walk the default branch's **first-parent** history and assign each commit an ordinal `seq` (0 = root). Each file version and chunk gets a half-open validity range:

```text
chunk_versions
├── chunk_id           → chunks(content_hash, content, embedding, …)
├── repo_id
├── path
├── valid_from_seq     # first seq where this content exists at this path
├── valid_to_seq       # first seq where it no longer does (NULL = still valid)
```

Retrieval for a snapshot at `s = seq(cutoff_sha)`:

```sql
WHERE repo_id = :repo
  AND valid_from_seq <= :s
  AND (valid_to_seq IS NULL OR valid_to_seq > :s)
```

`chunks` are **deduplicated by content hash**, so one embedding serves every version where the content is unchanged. Only validity rows grow with history.

Commits not on the first-parent chain (feature-branch commits) are indexed as commit artifacts only when their merge commit is reachable, with visibility at the merge's `seq`.

### 3. Revisions and validity ranges for mutable GitHub artifacts

```text
artifact_revisions
├── artifact_id        # issue#123, issue#123/comment/987, PR#456, …
├── revision_no
├── content, content_hash
├── valid_from_time    # created_at or edited_at
├── valid_to_time      # next edit, deletion, or NULL
├── history_complete   # false if prior revisions could not be obtained
```

Revision history is ingested from GitHub's edit history (GraphQL `userContentEdits`) where available.

Rules:

- A revision is visible iff `valid_from_time ≤ cutoff_time < valid_to_time` (or `valid_to_time IS NULL`).
- If an artifact was edited after the cutoff **and** `history_complete = false`, the pre-cutoff content is unknown. The artifact is **excluded** from that scope.
- Deleted artifacts keep their revisions with `valid_to_time = deleted_at`.

### 4. IssueSnapshot reconstruction

The target issue is reconstructed at `cutoff_time`:

| Field | Source |
|---|---|
| title, body | revision valid at cutoff |
| labels | replay `labeled` / `unlabeled` timeline events ≤ cutoff |
| state | replay `closed` / `reopened` events ≤ cutoff (normally `open`) |
| comments | comments with `created_at ≤ cutoff`, each at its revision at cutoff |
| assignees, milestone | timeline events ≤ cutoff |
| cross-references, linked PRs, `closed_by` | only events ≤ cutoff; never current values |

If the title or body revision at cutoff cannot be determined, the replay case is `ineligible`.

**Cutoff policy (V1 default `at_creation`):** `cutoff_time = issue.created_at`. An alternative policy `before_first_fix_signal` (earliest of: first linked PR opened, first commit referencing the issue, first maintainer comment referencing a fix, minus 1 second) is supported for experiments and recorded on the manifest. See spec Q2.

### 5. PRs, releases, and other discussion artifacts

- Historical PRs are visible only if `merged_at ≤ cutoff` or `closed_at ≤ cutoff`. PRs open at the cutoff are excluded in V1, because their diff at the cutoff time cannot be reliably reconstructed.
- Releases are visible if `published_at ≤ cutoff`.
- In-repo changelog files follow code rules (ancestry), not release rules.

### 6. Enforcement architecture

1. **Scope object.** `TemporalScope(repo_id, cutoff_time, cutoff_sha, cutoff_seq, mode, cutoff_policy)` is built by the application from the RunManifest and carried inside `RetrievalScope` (spec §15.2). `Retriever.search` requires a `RetrievalScope`; `RepoSource` methods require a `TemporalScope` for RCA runs. There is no unscoped variant.
2. **SQL predicate.** The Store adapter applies the validity predicates in every query, in both lexical and vector branches, **before** ranking and `LIMIT`.
3. **Defense in depth.** After retrieval, the application re-checks every returned item against the scope. A violation raises `TemporalIsolationError`, fails the run, emits a high-severity telemetry event, and is never retried.
4. **No live GitHub in replay.** In `replay` and `evaluation` modes, the composition root wires a Store-backed `RepoSource`. The GitHub adapter is not constructed, so the graph cannot reach current GitHub state.
5. **Ground-truth isolation.** Evaluation ground truth lives in a separate schema. The production database role used by RCA runs has no privileges on it.

### 7. Live mode

Live runs use the same machinery: `cutoff_time = run start`, `cutoff_sha = default-branch head at run start`. This makes live RCAs reproducible and later reusable as evaluation cases.

## Testing

Required in CI (`tests/temporal/`, PostgreSQL container):

1. **Fixture repository** with a scripted timeline: commits, a rebased commit with an old author date, issue edits after the cutoff, labels added after the cutoff, a fixing PR, a post-cutoff release.
2. **Property test:** for random queries and cutoffs, every retrieved item satisfies the scope predicate.
3. **Canary tokens:** unique strings planted only in post-cutoff artifacts (fix PR body, post-cutoff comment, edited issue body, future changelog line, future code). A capturing fake `LLMProvider` asserts no canary appears in any prompt across a full replay run.
4. **Rebase trap:** a commit with author date before the cutoff but landing after it is not visible.
5. **Edit trap:** an issue body edited after the cutoff returns the pre-cutoff revision; with `history_complete = false`, the artifact is excluded.
6. **Mode wiring:** constructing a replay-mode container never instantiates the GitHub adapter.

## Consequences

**Positive**
- One embedding per unique content; storage grows with change volume, not commit count.
- Leakage is prevented by construction and proven by canary tests.
- Live and replay share one code path.

**Negative**
- Ingestion is more complex: first-parent walk, validity ranges, edit-history fetching, timeline replay.
- Excluding artifacts with incomplete history reduces available evidence and the number of eligible cases.
- Non-default-branch (e.g., maintenance-branch) issues are not supported in V1.

## Alternatives considered

- **Per-SHA vector index.** Rejected: storage and ingestion cost scale with commit count.
- **Filter by commit author/committer date.** Rejected: incorrect under rebase and cherry-pick.
- **Use current issue content with prompt instructions to ignore later edits.** Rejected: prompts cannot enforce isolation; current content often states the fix.
- **Git worktree checkout at `cutoff_sha` per run.** Useful for file reads but does not cover GitHub discussion artifacts or vector search; may be added as an optimization of `RepoSource.get_file`.
