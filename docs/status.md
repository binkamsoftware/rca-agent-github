# Project Status

> Read this at the start of every session. Update it at the end of every session that changes state.

**Last updated:** 2026-09-27
**Current milestone:** M01 — Tooling and package skeleton (not started)
**Blocked on:** nothing.

## Next action

1. Start M01 in a fresh session, plan mode.

## Completed milestones

| Milestone | Date | Commit | Notes |
|---|---|---|---|
| — | | | No code milestones completed yet |

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

## Known issues / notes

- Environment: local `.venv` (Python 3.12) + `requirements.txt`; migrates to `pyproject.toml` in M01.
- `.env` exists locally and is git-ignored; never read or print it.
- Docs baseline committed on `master`.

## Update rules

- On milestone completion: add a row to *Completed milestones*, set *Current milestone* to the next one, and update *Next action*.
- Record any decision made (D#) or spec change applied (C#/S#) with its outcome.
- Keep this file short: facts and pointers only; details belong in the spec, ADRs, or plan.
