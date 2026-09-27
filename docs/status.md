# Project Status

> Read this at the start of every session. Update it at the end of every session that changes state.

**Last updated:** 2026-09-27
**Current milestone:** M03 — Citation model and excerpt verification rules (not started)
**Blocked on:** nothing.

## Next action

1. M01 (`m01-tooling-skeleton`) and M02 (`m02-errors-value-types`, stacked on M01) are not yet merged to `main`. Push and open/merge PRs when ready.
2. Start M03 in a fresh session, plan mode, on a new branch `m03-citation-model` created from `m02-errors-value-types`.

## Completed milestones

| Milestone | Date | Commit | Notes |
|---|---|---|---|
| M01 | 2026-09-27 | ae9c0e2 | `pyproject.toml`, ruff/mypy/import-linter, 6 ADR-001 contracts, CI workflow |
| M02 | 2026-09-27 | bca38e9 | `domain/errors.py`, `identifiers.py`, `enums.py`; spec §6.1 format rules added |

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

## Known issues / notes

- Environment: local `.venv` (Python 3.12); `pip install -e ".[dev]"`. `requirements.txt` removed.
- Ruff is scoped to `*.py` so it never rewrites code snippets in docs/ADRs.
- import-linter cannot allow-list "stdlib + pydantic"; vendor SDKs are forbidden by name. Extend the lists when adding a new SDK.
- `.env` exists locally and is git-ignored; never read or print it.
- Remote: `origin` = github.com/binkamsoftware/rca-agent-github. Local `master` tracks `origin/main`. Push as GitHub user `binkamsoftware`.

## Update rules

- On milestone completion: add a row to *Completed milestones*, set *Current milestone* to the next one, and update *Next action*.
- Record any decision made (D#) or spec change applied (C#/S#) with its outcome.
- Keep this file short: facts and pointers only; details belong in the spec, ADRs, or plan.
