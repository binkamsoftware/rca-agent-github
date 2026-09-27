# Project Status

> Read this at the start of every session. Update it at the end of every session that changes state.

**Last updated:** 2026-09-27
**Current milestone:** M04 — Claims, RecommendedFix, RCAResult finalization rules (not started)
**Blocked on:** nothing.

## Next action

1. Push `m03-citation-model` and open a PR to `main`; merge after review.
2. Then start M04 in a fresh session, plan mode, on branch `m04-rca-result` from `main`.

M01 (PR #1) and M02 (PR #2) are merged to `main` (`3a8a3de`). M03 is committed on `m03-citation-model` and has not been pushed yet.

## Completed milestones

| Milestone | Date | Commit | Notes |
|---|---|---|---|
| M01 | 2026-09-27 | ae9c0e2 | `pyproject.toml`, ruff/mypy/import-linter, 6 ADR-001 contracts, CI workflow |
| M02 | 2026-09-27 | bca38e9 | `domain/errors.py`, `identifiers.py`, `enums.py`; spec §6.1 format rules added |
| M03 | 2026-09-27 | 3b044e1 | `domain/evidence/citation.py`, `excerpt_matching.py`; §6.2 checks 2–4 |

Pre-code work done: spec v0.3, ADR-001…005, `CLAUDE.md`, implementation plan, `.gitignore`.

## Decisions (plan §4)

| ID | Outcome |
|---|---|
| D1 | Anthropic first, behind `LLMProvider` |
| D2 | PostgreSQL FTS (`tsvector`/`ts_rank_cd`) → ADR-006 in M17 |
| D3 | Dulwich, read-only, `adapters/git/` (ADR-004 Addendum A) |
| D4 | CLI review; `--reviewer` + `--reason` required, no default |
| D5 | PostgreSQL job/outbox table + separate worker |
| D6 | Human-labeled rubric + frozen, versioned ground truth |
| D7 | `SecretRedactor` port + `adapters/security/`; not in domain (ADR-004 Addendum B) |
| D8 | Voyage AI `voyage-code-4` behind `EmbeddingProvider`; local adapter comparison in Phase 7 |

## Spec changes (plan §5)

C1–C3, S1–S7 applied → spec v0.3. S8–S10 resolved by D4/D5/D3.

M02 (user-approved): §6.1 gained `PR#N/comment/ID` for `pr_comment`, file line forms `#Ls-Le` / `#Ln` / none, lowercase 7–40 hex SHAs, and `content_hash` = `sha256:<64 hex>`.

M03 (user-approved): `CitationKind` is an alias of `ArtifactKind`. `content_trust = system` is allowed only on `ci_run` citations. There is no Unicode normalization beyond whitespace. Abbreviated citation SHAs match as a prefix of the artifact SHA. Lines split on `\n` only.

## Known issues / notes

- Environment: local `.venv` (Python 3.12); `pip install -e ".[dev]"`. `requirements.txt` removed.
- Ruff is scoped to `*.py` so it never rewrites code snippets in docs/ADRs.
- import-linter cannot allow-list "stdlib + pydantic"; vendor SDKs are forbidden by name. Extend the lists when adding a new SDK.
- `.env` exists locally and is git-ignored; never read or print it.
- Remote: `origin` = github.com/binkamsoftware/rca-agent-github. Local `main` tracks `origin/main` (old local `master` is redundant). Push as GitHub user `binkamsoftware`. `gh`/push need the sandbox disabled (keychain + TLS).

## Update rules

- On milestone completion: add a row to *Completed milestones*, set *Current milestone* to the next one, and update *Next action*.
- Record any decision made (D#) or spec change applied (C#/S#) with its outcome.
- Keep this file short: facts and pointers only; details belong in the spec, ADRs, or plan.
