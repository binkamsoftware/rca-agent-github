# CLAUDE.md

Instructions for Claude Code working in this repository. Read this first, every session.

## What this is

GitHub Issue RCA Platform: two LangGraph agents.
- **RCA Agent** investigates an issue and produces an evidence-backed root-cause analysis.
- **RCA Validation Agent** checks whether a PR addresses an approved RCA, using deterministic test evidence.

**Start every session by reading `docs/status.md`** (current milestone, blockers, next action). Update it before ending a session that changed state.

**Reading budget (keep context small):**
- Per session read: `docs/status.md`, then **only the current milestone section** of `docs/implementation-plan.md`, then **only the spec sections and ADRs that milestone cites**.
- Do not read whole documents (spec, plan, ADRs) unless the user asks or the milestone cannot be done without it.
- Read source files you will change or depend on; do not scan the whole codebase.
- Keep command output short: `pytest -q -x`, and filter or `tail` long output.
- One milestone per session. Before ending: commit, update `docs/status.md`, then the user starts a fresh session.

Sources of truth, in order:
1. `docs/spec.md` — what the platform must do.
2. `docs/adr/*.md` — how, and why.
3. This file — how to work here.

If code, spec, and ADRs disagree, **stop and ask**. Do not silently pick one.

## Non-negotiable rules

These are the rules most likely to be broken by accident. Violating any of them is a bug, even if tests pass.

1. **Layering (ADR-001).** `domain` imports only stdlib + pydantic. `application` never imports `adapters` or vendor SDKs. Only `bootstrap.py` wires adapters. Production code never imports `evaluation`.
2. **No vendor types past a port.** No Anthropic/OpenAI/Google/GitHub/SQLAlchemy/OTel/langchain types in `domain`, `ports`, or `application`.
3. **Temporal scope is mandatory (ADR-002).** Every retrieval and RepoSource call takes a scope. Never add an unscoped query path. Never read current GitHub state in replay/evaluation mode.
4. **The LLM never decides the verdict (ADR-003).** `compute_verdict` is a pure function. Do not add LLM calls, I/O, or clocks to it. Rule changes need a new `rule_version` and an ADR update.
5. **Citations are verified in code (spec §6.2).** Unverified citations never support a fact, coverage, or finding.
6. **Repository content is untrusted (ADR-004).** Never place it in instruction roles. Never execute, import, or unpickle it in platform processes. `subprocess` is allowed only under `adapters/test_evidence/`.
7. **Read-only on GitHub.** Do not add any code path that writes to GitHub.
8. **Every agent loop is bounded (spec §16).** Budgets are checked in code before each LLM or tool call.
9. **No secrets anywhere (spec §14.4).** Not in code, tests, fixtures, logs, spans, or prompts. Never read, print, or commit `.env`.

## Layout

```text
src/rca_platform/
  domain/            models, citation rules, lifecycle, verdict, errors (pure)
  ports/             Protocol interfaces
  application/
    services/        use cases
    graphs/rca/      LangGraph RCA graph
    graphs/validation/
    prompts/         versioned prompt templates
  adapters/          github/ postgres/ llm/ embeddings/ retrieval/ telemetry/ test_evidence/
  api/               FastAPI routes (thin)
  config/            pydantic-settings
  bootstrap.py       composition root
  evaluation/        separate subsystem
tests/
  unit/  graph/  temporal/  security/  validation/  integration/  evaluation/
  fakes/             in-memory port implementations
  contracts/         per-port contract suites (run against fakes + real adapters)
```

**Terminology (Hexagonal Architecture / Ports and Adapters):**
- **Port**: an interface (`typing.Protocol`) that the core defines for something it needs from outside, e.g. `Retriever`, `LLMProvider`. Lives in `ports/`.
- **Adapter**: a concrete implementation of a port for a specific vendor or technology, e.g. `PostgresRetriever`, `GitHubRepoSource`. Lives in `adapters/`.
- **Composition root**: `bootstrap.py`, the one place that chooses which adapter plugs into which port.

## Commands

The environment is a local `.venv` (Python 3.12) with `requirements.txt`. Phase 0 migrates to `pyproject.toml`. Update this section when it does.

```bash
source .venv/bin/activate
pip install -r requirements.txt

pytest -m "not integration and not e2e and not evaluation"   # default; must pass before any commit
pytest tests/temporal tests/security                          # required when touching retrieval, ingestion, prompts
pytest -m integration                                         # needs Docker services; run when touching adapters
```

Planned for Phase 0 (not yet installed; add with justification per the workflow below): `ruff` (with `N` and `D` rule sets), `mypy --strict`, `import-linter`, `pytest-asyncio`. Once present: `ruff check . && ruff format --check . && mypy src && lint-imports`.

## Coding standards

- Modern typed Python. `mypy --strict` clean. No `Any` at module boundaries. No bare `dict` at architectural boundaries.
- Pydantic v2 for external boundaries, persistence, config, and LLM structured outputs. `TypedDict`/dataclass for internal graph state.
- `async` for I/O. No blocking I/O in async paths.
- Constructor injection. No module-level clients, no `os.environ` outside `config/`.
- Typed errors from `domain/errors.py` (spec §19.2). Never `except Exception: pass`. Re-raise with context.
- Transport retries only in adapters, only for transient errors (spec §19.3). Structured-output repair: at most once (spec §16.3).
- Structured logging via the project logger; include `run_id`. Never log content of prompts, secrets, or large source excerpts.
- Small modules with one responsibility. Prefer a new small module over growing a large one.

## Naming and documentation

Code must be readable by someone who has never seen this repository.

### Naming

- `snake_case` for variables, functions, methods, modules, and packages. Join words with `_`: `rca_model`, `rca_response`, `validation_result`, `cutoff_sha`.
- `PascalCase` for classes and type aliases (`RCAResult`, `ClaimCoverage`). `UPPER_SNAKE_CASE` for constants (`MAX_REPAIR_ATTEMPTS`).
- Names say what the value **is**, in domain terms. Prefer `verified_citations` over `vc`, `issue_snapshot` over `data`, `retrieved_chunks` over `res`.
- No single-letter names except `i`/`j` in short loops and `T` for type variables. No unexplained abbreviations. Established domain acronyms are fine: `rca`, `pr`, `sha`, `llm`, `f2p`, `p2p`.
- Booleans read as yes/no questions: `is_current`, `has_verified_evidence`, `history_complete`.
- Functions start with a verb: `compute_verdict`, `verify_citation`, `build_issue_snapshot`.
- Units go in the name when the value has one: `timeout_s`, `duration_ms`, `max_cost_usd`.

### Docstrings

**Every module, class, and function — public or private — has a docstring.** Google style:

```python
def compute_verdict(
    rca_result: RCAResult,
    claim_coverage: Sequence[ClaimCoverage],
    test_evidence: TestEvidence | None,
    findings: Sequence[Finding],
) -> VerdictDecision:
    """Derive the final validation verdict from normalized evidence.

    Applies the ordered rules R0-R12 from ADR-003. The first matching rule
    decides the verdict; every matching rule is recorded in the reasons so
    the outcome can be audited.

    Args:
        rca_result: The approved RCA version being validated.
        claim_coverage: Normalized per-claim coverage from the Validation Agent.
        test_evidence: Deterministic CI/sandbox results, or None if unavailable.
        findings: Normalized validation findings.

    Returns:
        The verdict, the rule version, and the reasons for every fired rule.

    Raises:
        ValueError: If claim_coverage references a claim_id not in rca_result.
    """
```

Rules:
- The first line is a one-sentence summary of **what** the function does. The body explains **why**, or non-obvious behavior, and cites the spec section or ADR when a rule comes from one.
- Include `Args`, `Returns`, and `Raises` whenever they apply. Document every exception the function intentionally raises.
- Say what side effects happen (database writes, network calls, telemetry, budget consumption).
- Small private helpers may use a one-line docstring when the name and types make everything else obvious.
- Tests: a descriptive name (`test_verdict_is_needs_changes_when_blocking_finding_exists`) plus a one-line docstring stating the behavior under test.
- Pydantic models document every field with `Field(description=...)`, which also feeds the JSON schema given to LLMs.
- Comments explain *why*, not *what*. Delete comments that restate the code.
- Update the docstring in the same change as the behavior it describes. A stale docstring is a bug.

Enforcement (Phase 0 tooling): ruff `N` (pep8-naming) and `D` (pydocstyle, `convention = "google"`). Ruff does not check private functions, so reviewers check those.

## Testing rules

- Every domain rule gets unit tests with fakes, and no network.
- `compute_verdict` and F2P classification tests are table-driven (ADR-003). Add a row for every rule you touch.
- Any change to retrieval, ingestion, or scoping must keep the canary leakage tests green (ADR-002).
- Any change to prompt construction must keep `tests/security` green (ADR-004).
- New port → add a fake in `tests/fakes/` and a contract suite in `tests/contracts/`.
- Mark tests needing real services `@pytest.mark.integration`. Default runs must be hermetic.

## Workflow for non-trivial changes

1. Restate the requirement and cite the spec section / ADR it touches.
2. If the spec or an ADR must change, propose that edit **first** and wait for approval.
3. List affected modules and propose a short plan. Wait for approval if it crosses layers, adds a dependency, or changes a schema.
4. Implement the smallest coherent change.
5. Add or update tests; run the relevant suites.
6. Check telemetry and error paths for the change.
7. Update docs (spec, ADR, this file) if behavior or commands changed.

Do **not**:
- add a dependency, framework, service, or pattern without a one-paragraph justification in the PR (and an ADR if architectural);
- implement features from a later delivery phase (spec §24) than the current one;
- weaken a test, rule, or budget to make something pass;
- invent repository evidence in fixtures that claim to be real `encode/httpx` data.

## ADRs

Add a new ADR as `docs/adr/NNN-kebab-title.md` with sections: Context, Decision, Testing, Consequences, Alternatives considered. ADRs are never edited to reverse a decision: supersede them with a new one and mark the old one `Superseded by NNN`.

| ADR | Topic |
|---|---|
| 001 | Ports and adapters, layering, DI |
| 002 | Temporal indexing and isolation |
| 003 | Deterministic validation verdicts |
| 004 | Untrusted content and code execution |
| 005 | Observability |

## Current milestone

See `docs/status.md`. Work only on the current milestone from `docs/implementation-plan.md`.
