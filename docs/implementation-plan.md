# Implementation Plan

| Field | Value |
|---|---|
| Status | Draft — awaiting approval |
| Based on | `docs/spec.md` v0.2, ADR-001 … ADR-005, `CLAUDE.md` |
| Scope | V1 through spec Phase 6. Phase 7 (evaluation expansion) is listed but not planned in detail. |

This plan breaks V1 into small milestones. Each one can be built, tested, and reviewed on its own, in a single Claude Code session, and produces one commit or PR.

---

## 1. Planning principles

1. **Foundations before infrastructure.** Pure domain rules first, then ports and fakes, then real adapters.
2. **Vertical increments.** Once ports and fakes exist, build a thin end-to-end RCA slice on fakes. Real infrastructure then replaces one fake at a time, and the slice's tests keep proving the behavior.
3. **RCA Agent before Validation Agent.** Validation milestones start only after the RCA lifecycle can produce an approved RCA.
4. **Gates on introducing technology:**

| Technology | Not before |
|---|---|
| LangGraph | domain contracts and ports are tested, and a single-pass RCA service works on fakes (M12) |
| PostgreSQL / pgvector | Store ports and in-memory fakes exist, with contract suites (M09) |
| Real LLM / embedding providers | `LLMProvider` is exercised through `FakeLLMProvider` in service tests (M07, M12) |
| GitHub API | `RepoSource` has a fake and a Store-backed implementation (M08, M15) |

5. **Nothing from a later phase early.** Each milestone has an explicit "deferred" list.

---

## 2. Definition of done (applies to every milestone)

A milestone is done only when all of these hold. They are not repeated in each milestone.

- `ruff check .`, `ruff format --check .`, `mypy src` (strict), and `lint-imports` pass.
- Default suite `pytest -m "not integration and not e2e and not evaluation"` passes with no network.
- Every new module, class, and function has a Google-style docstring. Every Pydantic field has `Field(description=...)`. Names follow `CLAUDE.md` naming rules.
- New ports have a fake in `tests/fakes/` and a contract suite in `tests/contracts/`.
- No secrets in code, fixtures, logs, or test output.
- Docs updated if behavior, commands, or configuration changed (spec, ADR, `CLAUDE.md`).
- No functionality from the milestone's "deferred" list.

---

## 3. Milestone map

| ID | Milestone | Spec phase | Depends on |
|---|---|---|---|
| **A — Domain foundation** ||||
| M01 | Tooling and package skeleton | 0 | — |
| M02 | Errors and shared value types | 0 | M01 |
| M03 | Citation model and excerpt verification rules | 0 | M02 |
| M04 | Claims, RecommendedFix, RCAResult finalization rules | 0 | M03 |
| M05 | Run control: RunManifest, Budgets, BudgetTracker, execution key | 0 | M02 |
| M06 | TemporalScope and visibility predicates | 0 | M02 |
| **B — Ports and fakes (RCA side)** ||||
| M07 | LLMProvider port, content blocks, FakeLLMProvider | 0 | M02, M05 |
| M08 | RepoSource and Retriever ports, IssueSnapshot, fakes | 0 | M03, M06 |
| M09 | Store ports, in-memory fakes, no-op telemetry | 0 | M04, M05 |
| **C — RCA vertical slice on fakes** ||||
| M10 | Citation verification service | 2* | M08, M09 |
| M11 | Prompt rendering, SecretRedactor, structured-output repair | 2* | M07 |
| M12 | Baseline RCA service end-to-end on fakes | 2* | M10, M11 |
| **D — Infrastructure for RCA** ||||
| M13 | Configuration and composition root | 0 | M12 |
| M14 | PostgreSQL foundation: schema, migrations, run/RCA/idempotency repositories | 0/1 | M09, M13 |
| M15 | Temporal artifact storage and Store-backed RepoSource | 1 | M06, M14 |
| M16 | Chunking | 1 | M15 |
| M17 | Lexical retrieval (after ADR-006) | 1 | M16 |
| M18 | EmbeddingProvider port, vector retrieval, hybrid fusion | 1 | M17 |
| M19 | GitHub read adapter and ingestion pipeline | 1 | M15, M16 |
| M20 | Real LLM and embedding provider adapters | 2 | M11, M18 |
| M21 | Seed evaluation set and retrieval baseline | 1 | M18, M19 |
| M22 | Baseline RCA on real infrastructure and baseline metrics | 2 | M20, M21 |
| **E — LangGraph RCA** ||||
| M23 | RCA graph on fakes | 3 | M12 |
| M24 | RCA graph on real infrastructure and comparison | 3 | M22, M23 |
| **F — RCA lifecycle** ||||
| M25 | Lifecycle rules | 4 | M04 |
| M26 | Lifecycle service, persistence, review commands | 4 | M14, M25 |
| **G — Validation Agent** ||||
| M27 | Validation domain: models, test classification, normalization, verdict, staleness | 5 | M04, M25 |
| M28 | Validation ports and fakes | 5 | M27, M08 |
| M29 | Validation service and graph on fakes | 5 | M26, M28, M23 |
| M30 | Validation on real infrastructure | 5 | M29, M19, M20 |
| **H — Hardening** ||||
| M31 | Observability adapter (OpenTelemetry + Phoenix) | 6 | M24, M30 |
| M32 | Webhook trigger and idempotent execution | 6 | M30 |
| M33 | Sandbox test execution | 6 | M30 |
| M34 | Security, resilience, operational readiness | 6 | M31–M33 |

\* Phase-2 logic built on fakes before Phase-1 infrastructure. See §5, change C2.

---

## 4. Decisions

Resolved 2026-09-27 unless marked open.

| # | Decision | Needed before | Outcome |
|---|---|---|---|
| D1 | First LLM provider | M20 | **Anthropic**, behind `LLMProvider`. One real adapter + fake. OpenAI/Gemini only when portability is deliberately tested (Phase 7). |
| D2 | Lexical retrieval (spec Q3) | M17 | **PostgreSQL FTS** (`tsvector` + `ts_rank_cd`). No Elasticsearch/OpenSearch. Recorded as ADR-006 in M17. |
| D3 | Git history access | M15 / M19 | **Dulwich**, read-only, in `adapters/git/`. Object data only: no checkout, hooks, or filters; no shell. See ADR-004 Addendum A. |
| D4 | Human review interface | M26 | **CLI first**, with an **explicit, required reviewer identity** on every review command (no default). Persist actor + timestamp + reason. HTTP review API deferred. |
| D5 | Webhook run execution | M32 | **PostgreSQL job/outbox table + separate worker process.** No FastAPI background tasks; no Redis/Kafka/Celery. |
| D6 | RCA correctness judging | M22 | **Human-labeled rubric + frozen ground truth.** Ground truth is versioned and immutable once frozen. LLM judge deferred (spec Q4). |
| D7 | Secret redaction placement | M11 | **Infrastructure concern, not domain.** `SecretRedactor` port; pattern-based implementation in `adapters/security/`; application services apply it at boundaries (before prompting, before persisting excerpts, before telemetry). |
| D8 | Embedding provider (separate decision from D1) | M18 / M20 | **Voyage AI `voyage-code-4`** as the first production adapter behind `EmbeddingProvider`. Selected because the initial workload is code-heavy retrieval (code, docs, issues, PRs) and it is a dedicated code-retrieval model; a straightforward hosted baseline; its current free allowance suits initial experimentation; no effect on domain/application contracts. Provider independence is verified by contract tests. Changing the embedding model means re-indexing under a new `retrieval_version`. **Later (Phase 7):** a local/open-weight adapter compared on Recall@K, MRR, NDCG, latency, indexing time, and infrastructure cost. |

---

## 5. Spec and doc changes

**Status: C1–C3 and S1–S7 approved and applied 2026-09-27 (spec v0.3).** S8–S10 resolved by D4, D5, D3.

### 5.1 Changes to delivery order (spec §24)

| ID | Change | Reason |
|---|---|---|
| C1 | Move "DB schema + migrations" from Phase 0 to milestone M14, after Store ports and fakes exist and the slice runs on fakes | Your constraint: no PostgreSQL until persistence interfaces exist and are exercised |
| C2 | Build the single-pass baseline RCA *logic* on fakes (M10–M12) before Phase 1 infrastructure. Phase 2's exit criteria (metrics on real data) still happen in M22. | Your constraint: vertical, testable increments. It de-risks the core flow before infrastructure work. |
| C3 | Update `CLAUDE.md` "Current phase" to reference milestones: *"Current milestone: M01. Work only on the current milestone."* | Milestones are finer-grained than phases |

### 5.2 Inconsistencies and gaps in the spec

| ID | Location | Issue | Proposal |
|---|---|---|---|
| S1 | §7.1 | `RCAResult.status` includes `failed`, but a failed run "produces no RCAResult" | Remove `failed` from `RCAResult.status` (keep it on `RunManifest.outcome`) |
| S2 | §11.1, §16.1 | `max_cost` and `usage.cost` break the naming rule (units in names) | Rename to `max_cost_usd`, `cost_usd` |
| S3 | §11.1 | `Usage` model is referenced but not defined | Define `Usage(iterations, tool_calls, llm_calls, tokens_in, tokens_out, cost_usd)` |
| S4 | §13.4, ADR-001, ADR-002 | `TemporalScope` and `RetrievalScope` are used interchangeably | `RetrievalScope(repo_id, artifact_types, path_prefixes, temporal_scope)`. `temporal_scope` is required for RCA runs; validation runs use a scope pinned to `pr_head_sha`/`base_sha`. |
| S5 | §5.2, §8.2, §15 | `IssueSnapshot`, `PullRequestSnapshot`, `RetrievedChunk`, `LLMRequest` fields are not specified | Define them in the spec as they are built (M07, M08, M28) |
| S6 | §6.3 | A fact failing verification is "removed or downgraded" (two options) | Always downgrade to `hypothesis / unresolved`. This keeps information and stays honest. |
| S7 | §4.1 | No `Clock` port, but budgets, timeouts, `retrieved_at`, and staleness need time | Add a `Clock` port so domain and application code stay deterministic in tests |
| S8 | §7.3, ADR-004 | Review "via authenticated review API" is referenced, but no API is specified | Resolved by D4 (CLI with required reviewer identity). |
| S9 | §2, §12 | Webhook-to-run execution model unspecified | Resolved by D5 |
| S10 | ADR-002 vs ADR-004 | First-parent git walk needs git access; `subprocess` is banned outside test_evidence | Resolved by D3 (ADR-004 Addendum A) |

---

## 6. Milestones

### Stage A — Domain foundation

No I/O, no frameworks except Pydantic. Everything in this stage is pure and unit-tested.

---

#### M01 — Tooling and package skeleton

1. **Goal.** A package layout and quality toolchain that enforce the architecture before any logic exists.
2. **Why it exists.** Layering, naming, docstrings, and typing are cheapest to enforce from the first commit. Every later milestone relies on these checks.
3. **Spec requirements.** §4.1, §19.1 (structure only), §21 (test markers); ADR-001 dependency rules; `CLAUDE.md` coding, naming, and docstring standards.
4. **Files/modules.**
   - `pyproject.toml` (migrates `requirements.txt` dependencies; `requirements.txt` removed or generated)
   - `src/rca_platform/{domain,ports,application,adapters,api,config,evaluation}/__init__.py` (module docstrings only)
   - `.importlinter` (or `[tool.importlinter]` in pyproject): contracts from ADR-001
   - `tests/{unit,graph,temporal,security,validation,integration,evaluation,fakes,contracts}/`
   - `tests/conftest.py`: marker registration
   - `.github/workflows/ci.yml`: lint, type, import, default test suite
   - `CLAUDE.md`: update Commands section
5. **Domain models/interfaces.** None.
6. **External dependencies.** Dev: `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `import-linter`. Runtime: unchanged (`pydantic`; `langgraph`, `langchain-core`, `fastapi`, `uvicorn` stay declared but are unused until their milestones).
7. **Tests.** A smoke test that imports every package. A test that runs `lint-imports` against a temporary module violating the domain→adapters rule and asserts failure.
8. **Acceptance criteria.**
   - All checks pass on the empty skeleton, locally and in CI.
   - A deliberate `from rca_platform.adapters import …` inside `domain/` fails `lint-imports`.
   - A function without a docstring in `src/` fails `ruff`.
   - `pytest -m integration` selects nothing and exits cleanly.
9. **Depends on.** —
10. **Deferred.** Any models, config loading, Docker, database, LLM, or GitHub code.

---

#### M02 — Errors and shared value types

1. **Goal.** The typed error hierarchy and validated identifier types used everywhere.
2. **Why it exists.** Every later module raises typed errors and passes identifiers. Validating SHAs and references once prevents malformed data at every boundary.
3. **Spec requirements.** §19.2 error hierarchy; §6.1 reference formats; §14.4 (errors must not leak sensitive data).
4. **Files/modules.** `domain/errors.py`, `domain/identifiers.py`, `domain/enums.py`
5. **Domain models/interfaces.**
   - Errors: `PlatformError` and all subclasses from §19.2. Each carries a stable `error_code` and a sanitized `context` mapping.
   - Value types: `GitSha` (hex, 7–40 chars), `ContentHash`, `RepoId` (`owner/name`), `IssueRef`, `PullRequestRef`, `ArtifactRef` (parses and renders all §6.1 formats).
   - Enums used across stages: `AgentType`, `RunMode`.
6. **External dependencies.** None.
7. **Tests.** `tests/unit/domain/test_errors.py`, `test_identifiers.py`: valid and invalid SHAs; round-trip parse/render for every `ArtifactRef` format; errors' `str()` excludes context values marked sensitive; hierarchy assertions (e.g., `LLMTransientError` is an `LLMProviderError`).
8. **Acceptance criteria.** Every §6.1 reference example parses and renders identically; malformed references raise `ValueError` with a clear message.
9. **Depends on.** M01
10. **Deferred.** Retry classification logic (adapters, M19/M20).

---

#### M03 — Citation model and excerpt verification rules

1. **Goal.** The `Citation` model and the pure checks that decide whether a citation's excerpt and location match given content.
2. **Why it exists.** Evidence is the core of the product. The pure matching rules must be correct and fully tested before any service resolves real artifacts.
3. **Spec requirements.** §6.1, §6.2 checks 2–4 (check 1, "artifact exists in scope", needs a Store and comes in M10).
4. **Files/modules.** `domain/evidence/citation.py`, `domain/evidence/excerpt_matching.py`
5. **Domain models/interfaces.**
   - `Citation`, `CitationKind`, `ContentTrust`, `VerificationStatus`
   - `normalize_whitespace(text) -> str`
   - `check_citation_against_content(citation, artifact_content, artifact_content_hash, artifact_sha) -> CitationCheckResult` (pure; returns status + error code)
6. **External dependencies.** None.
7. **Tests.** Table-driven tests: exact match; whitespace differences; excerpt not present; line range out of bounds; line range present but excerpt outside it; SHA mismatch; content-hash mismatch for mutable artifacts; empty excerpt rejected; Unicode content.
8. **Acceptance criteria.** Every §6.2 check (2–4) has passing and failing cases. A citation is `verified` only when all applicable checks pass.
9. **Depends on.** M02
10. **Deferred.** Artifact lookup and temporal-scope check (M10); runtime support/groundedness judging (spec Q4).

---

#### M04 — Claims, RecommendedFix, RCAResult finalization rules

1. **Goal.** RCA output models and the pure rules that turn a draft RCA into an honest final result.
2. **Why it exists.** These rules guarantee that facts need verified evidence and that sufficiency is never overstated. They must hold no matter which LLM produced the draft.
3. **Spec requirements.** §6.3, §6.4, §7.1 (with S1, S6 applied).
4. **Files/modules.** `domain/rca/claim.py`, `domain/rca/rca_result.py`, `domain/rca/finalization.py`
5. **Domain models/interfaces.**
   - `Claim`, `ClaimType`, `ClaimRole`, `HypothesisResolution`, `RecommendedFix`, `RCAResult`, `RCAStatus`, `EvidenceSufficiency`
   - `finalize_claims(claims) -> list[Claim]`: a fact without a verified citation is downgraded to hypothesis/unresolved; a hypothesis with a verified citation becomes supported, otherwise unresolved
   - `cap_evidence_sufficiency(proposed, claims, status) -> EvidenceSufficiency`
   - Model validator: `missing_evidence` non-empty when sufficiency ≠ sufficient
6. **External dependencies.** None.
7. **Tests.** Unit tests for each rule in §6.3 and §7.1: unverified fact is downgraded, never kept; a hypothesis never becomes a fact; `sufficient` capped when there is no qualifying root-cause claim; `budget_exhausted` capped at `partial`; validator rejects empty `missing_evidence`. Property test: finalization never increases the number of facts.
8. **Acceptance criteria.** All §6.3 and §7.1 rules are expressed as functions with tests. `RCAResult` JSON schema generates, with descriptions on every field.
9. **Depends on.** M03
10. **Deferred.** `RCARecord`, versioning, and lifecycle (M25); persistence (M14).

---

#### M05 — Run control: RunManifest, Budgets, BudgetTracker, execution key

1. **Goal.** Models and pure logic for run reproducibility, budget enforcement, and idempotency keys.
2. **Why it exists.** Every agent run must be bounded and reproducible. Budget checks must exist before any loop or LLM call is written.
3. **Spec requirements.** §11.1, §11.2, §12 (key computation only), §16.1, §16.2 (budget-based termination); S2, S3, S7.
4. **Files/modules.** `domain/runs/run_manifest.py`, `domain/runs/budgets.py`, `domain/runs/execution_key.py`
5. **Domain models/interfaces.**
   - `RunManifest`, `RunOutcome`, `Budgets`, `Usage`
   - `BudgetTracker`: `check_can_call_llm()`, `check_can_call_tool()`, `record_llm_call(tokens_in, tokens_out, cost_usd)`, `record_tool_call()`, `record_iteration()`, `is_exhausted`, `exhaustion_reason`. It takes a `Clock` for the timeout.
   - `compute_execution_key(...) -> str` (stable hash)
   - `compute_config_hash(settings_mapping) -> str` (secret-free input)
6. **External dependencies.** None.
7. **Tests.** Each budget dimension exhausts independently; check-before-call raises `BudgetExceededError` before the limit is exceeded; timeout with a fake clock; execution key is stable across dict ordering and differs when any component differs; config hash ignores ordering.
8. **Acceptance criteria.** No code path can record an LLM call without a prior successful check (enforced by tests). Keys are deterministic across processes.
9. **Depends on.** M02
10. **Deferred.** Idempotency persistence and duplicate handling (M14, M32); pricing tables (M20).

---

#### M06 — TemporalScope and visibility predicates

1. **Goal.** The scope model and the pure visibility rules from ADR-002.
2. **Why it exists.** These predicates are the single definition of "visible at the cutoff". The SQL (M15) and the defense-in-depth re-check both implement them and are tested against them.
3. **Spec requirements.** §13.1–§13.4; ADR-002 §1, §2, §3, §5, §6.1; S4.
4. **Files/modules.** `domain/temporal/scope.py`, `domain/temporal/visibility.py`
5. **Domain models/interfaces.**
   - `TemporalScope(repo_id, cutoff_time, cutoff_sha, cutoff_seq, mode, cutoff_policy)`
   - `RetrievalScope(repo_id, artifact_types, path_prefixes, temporal_scope)`
   - `is_code_version_visible(valid_from_seq, valid_to_seq, scope)`
   - `is_revision_visible(valid_from_time, valid_to_time, history_complete, edited_after_cutoff, scope)`
   - `is_pull_request_visible(merged_at, closed_at, scope)`, `is_release_visible(published_at, scope)`
   - `assert_within_scope(item, scope)` → raises `TemporalIsolationError`
6. **External dependencies.** None.
7. **Tests.** Boundary cases (exactly at cutoff, one second after); open validity ranges; incomplete history with a post-cutoff edit → excluded; open-at-cutoff PR excluded; property test: a visible item always has `valid_from ≤ cutoff`.
8. **Acceptance criteria.** Every visibility rule in ADR-002 has a predicate and tests. `assert_within_scope` raises the typed error with a sanitized context.
9. **Depends on.** M02
10. **Deferred.** SQL implementation (M15); cutoff SHA derivation from git history (M15/M19); `before_first_fix_signal` policy (spec Q2; model field only).

### Stage B — Ports and fakes (RCA side)

Only the ports the RCA path needs. Validation ports wait for M28.

---

#### M07 — LLMProvider port, content blocks, FakeLLMProvider

1. **Goal.** A provider-neutral LLM interface that separates trusted instructions from untrusted data, plus a scriptable fake.
2. **Why it exists.** Required before any service calls an LLM, and before any real provider (gate in §1).
3. **Spec requirements.** §4.2, §14.1, §16.3 (interface only); ADR-001 `LLMProvider`; ADR-004 Part B (content blocks).
4. **Files/modules.** `ports/llm_provider.py`, `domain/llm/messages.py`, `tests/fakes/fake_llm_provider.py`, `tests/contracts/test_llm_provider_contract.py`
5. **Domain models/interfaces.**
   - `TrustedInstruction`, `UntrustedData(source_ref, text)`, `LLMRequest(model_role, content_blocks, params)`, `LLMResponse[T](parsed_output, usage, model_id)`, `ModelRef`
   - `LLMProvider.generate_structured(llm_request, output_schema) -> LLMResponse[T]`
   - `FakeLLMProvider`: scripted responses per model role, records every request (used for canary and injection tests), can simulate transient errors and invalid output
6. **External dependencies.** None.
7. **Tests.** Contract suite: returns an instance of the requested schema; reports usage; raises `StructuredOutputError` on invalid output; raises `LLMTransientError` on simulated transient failure. The fake passes the contract suite.
8. **Acceptance criteria.** No vendor or LangChain types in the port. The fake records requests with untrusted blocks kept separate.
9. **Depends on.** M02, M05
10. **Deferred.** Delimiter rendering (M11); real providers, retries, pricing (M20).

---

#### M08 — RepoSource and Retriever ports, IssueSnapshot, fakes

1. **Goal.** Scoped read interfaces for repository artifacts and search, plus in-memory fakes that honor temporal scope.
2. **Why it exists.** Required before GitHub or PostgreSQL. The fakes let the RCA slice (M12) and leakage tests run with no infrastructure.
3. **Spec requirements.** §5.2, §13.3 (snapshot shape), §13.4 (scope required), §15.1–§15.2; ADR-001 `RepoSource`, `Retriever`; S5.
4. **Files/modules.** `ports/repo_source.py`, `ports/retriever.py`, `domain/repository/issue_snapshot.py`, `domain/repository/artifacts.py`, `tests/fakes/in_memory_repo_source.py`, `tests/fakes/in_memory_retriever.py`, `tests/fakes/fixture_timeline.py`, `tests/contracts/test_repo_source_contract.py`, `tests/contracts/test_retriever_contract.py`
5. **Domain models/interfaces.**
   - `IssueSnapshot(issue_ref, title, body, labels, state, comments, reconstructed_at_cutoff)`, `IssueCommentSnapshot`, `FileContent`, `RetrievalQuery`, `RetrievedChunk(chunk_id, artifact_ref, text, score, validity metadata)`
   - `RepoSource.get_issue_snapshot(issue_ref, temporal_scope)`, `RepoSource.get_file(path, git_sha, temporal_scope)`
   - `Retriever.search(retrieval_query, retrieval_scope)` (no unscoped method)
   - Fakes built from a **scripted fixture timeline** (synthetic repo, clearly not real httpx data) with pre- and post-cutoff artifacts and canary tokens.
6. **External dependencies.** None.
7. **Tests.** Contract suites: scope is honored; post-cutoff comments, edits, and labels never returned; missing file raises `RepositoryAccessError`. Retriever results always pass `assert_within_scope`. Canary tokens never appear in any returned text for pre-fix cutoffs.
8. **Acceptance criteria.** Both fakes pass their contract suites. The fixture timeline covers every ADR-002 trap (rebase, edit, label, fixing PR, future release).
9. **Depends on.** M03, M06
10. **Deferred.** `get_pull_request` and PR snapshots (M28); embeddings (M18); real storage (M15).

---

#### M09 — Store ports, in-memory fakes, no-op telemetry

1. **Goal.** Narrow persistence interfaces for the RCA path, a unit of work, in-memory implementations, and a no-op telemetry port.
2. **Why it exists.** Required before PostgreSQL (gate in §1). Services need persistence and telemetry seams from the first vertical slice.
3. **Spec requirements.** §4.1 (Store family), §12 (idempotency interface), §17 (port only), §18; ADR-001 Store family; ADR-005 §1 (port).
4. **Files/modules.** `ports/stores.py` (`ArtifactRepository`, `RunRepository`, `RCARepository`, `IdempotencyRepository`, `UnitOfWork`), `ports/telemetry.py`, `ports/clock.py`, `tests/fakes/in_memory_stores.py`, `tests/fakes/recording_telemetry.py`, `tests/fakes/fake_clock.py`, `tests/contracts/test_store_contracts.py`
5. **Domain models/interfaces.**
   - `ArtifactRepository.get_artifact_content(artifact_ref, temporal_scope)` (used by citation verification)
   - `RunRepository`: create, update usage/outcome, get
   - `RCARepository`: save a new version (draft), get by id and version, list versions. Content is immutable after save.
   - `IdempotencyRepository.claim(execution_key) -> ClaimResult(existing_run_id | new)`
   - `TelemetryProvider.span(name, kind, safe_attributes)`, `SafeAttributes` builder (allowlist)
   - `Clock.now()`
6. **External dependencies.** None.
7. **Tests.** Contract suites: RCA content cannot be overwritten; duplicate execution key returns the existing run; unit of work rollback discards writes; `SafeAttributes` rejects non-allowlisted keys.
8. **Acceptance criteria.** In-memory fakes pass every contract suite. The suites are written so M14 can run them unchanged against PostgreSQL.
9. **Depends on.** M04, M05
10. **Deferred.** `ValidationRepository` (M28); lifecycle transitions persistence (M26); OpenTelemetry (M31).

### Stage C — RCA vertical slice on fakes

The first end-to-end behavior: issue in, verified RCA out. Everything is still fake.

---

#### M10 — Citation verification service

1. **Goal.** An application service that resolves each citation within the run's scope and applies the M03 checks.
2. **Why it exists.** Completes spec §6.2 (including check 1). Every RCA and validation output passes through it.
3. **Spec requirements.** §6.2 (all checks), §13.4 (defense in depth); CLAUDE.md rule 5.
4. **Files/modules.** `application/services/citation_verification.py`
5. **Domain models/interfaces.** Uses `Citation`, `ArtifactRepository`, `TemporalScope`, `Clock`. Provides `CitationVerificationService.verify_all(citations, temporal_scope) -> list[Citation]` (status and `verified_at` set).
6. **External dependencies.** None.
7. **Tests.** Unit tests with fakes: valid citation verified; artifact outside scope → `failed` (not leaked); nonexistent artifact → `failed`; post-cutoff revision cited → `failed`; batch with mixed results; no exceptions for normal failures.
8. **Acceptance criteria.** No citation reaches `verified` without passing all four §6.2 checks. The service never returns artifact content outside scope.
9. **Depends on.** M08, M09
10. **Deferred.** Runtime groundedness judge (spec Q4).

---

#### M11 — Prompt rendering, SecretRedactor, structured-output repair

1. **Goal.** Safe prompt construction, secret redaction, and the bounded single repair attempt.
2. **Why it exists.** Prompt-injection defenses and redaction must exist before any prompt template is written, and before a real LLM ever sees repository content.
3. **Spec requirements.** §14.1, §14.4, §16.3; ADR-004 Parts B and C; D7.
4. **Files/modules.** `ports/secret_redactor.py`, `adapters/security/pattern_secret_redactor.py`, `tests/fakes/fake_secret_redactor.py`, `tests/contracts/test_secret_redactor_contract.py`, `adapters/llm/untrusted_rendering.py` (shared by all real adapters), `application/services/structured_generation.py`, `application/prompts/` (template loader + `prompt_version`)
5. **Domain models/interfaces.**
   - `SecretRedactor.redact(text) -> RedactionResult` (port; pattern-based adapter per D7). Application services apply it before prompting, before persisting excerpts, and before telemetry. The domain never imports it.
   - `render_untrusted_block(untrusted_data, boundary) -> str` with a per-request random boundary and escaping of boundary look-alikes
   - `generate_with_repair(llm_provider, llm_request, output_schema, budget_tracker)`: at most one repair, which counts against budgets
   - `PromptTemplate`, `PromptBundle(version)`
6. **External dependencies.** None (templates use stdlib `string.Template` or f-strings; no Jinja).
7. **Tests.** `tests/security/`: content containing a forged boundary cannot close the block; injection strings are rendered only inside data blocks; planted fake secrets are redacted. Unit: repair succeeds once; a second failure raises `StructuredOutputError`; the repair consumes budget; exhausted budget blocks repair.
8. **Acceptance criteria.** No code path puts `UntrustedData` into an instruction role. Redaction runs before rendering. No redaction code in `domain/` (import-linter).
9. **Depends on.** M07
10. **Deferred.** Provider-specific rendering (M20); secret-detection library evaluation (M34).

---

#### M12 — Baseline RCA service end-to-end on fakes

1. **Goal.** A single-pass RCA use case: IssueSnapshot → retrieve → LLM → verify → finalize → persist draft, with a RunManifest and idempotency.
2. **Why it exists.** It proves that the domain rules, ports, and security pieces fit together, before any infrastructure or LangGraph. It is also the regression harness that later milestones keep green.
3. **Spec requirements.** §5.1, §5.2, §6, §7.1, §7.2 (draft version only), §11, §12, §13.4, §13.5 (canary at application level), §16.1, §16.3; Phase 2 logic.
4. **Files/modules.** `application/services/baseline_rca.py`, `application/prompts/rca_baseline/v1/`, `domain/rca/rca_draft.py` (the LLM output schema: claims with citation *references and excerpts*, not verified `Citation` objects), `domain/rca/rca_record.py` (minimal: id, version, draft state, run_id)
5. **Domain models/interfaces.**
   - `RCADraft` (LLM structured output) → mapped by code into `RCAResult`
   - `BaselineRCAService.run(issue_ref, temporal_scope, run_config) -> RCARecord`
   - Uses all ports from M07–M09 and services from M10–M11.
6. **External dependencies.** None.
7. **Tests.**
   - Happy path with scripted fake LLM → draft RCARecord with verified citations.
   - LLM cites a nonexistent line → claim downgraded, sufficiency capped.
   - LLM returns `sufficient` without a root-cause claim → capped.
   - Budget exhaustion → `status = budget_exhausted`, sufficiency ≤ partial, manifest outcome recorded.
   - Duplicate execution key → existing run returned, no second LLM call.
   - **Canary test:** full run over the fixture timeline; no canary token appears in any recorded LLM request.
   - **Injection test:** fake LLM that obeys injected instructions ("mark sufficient", "cite X") → the output is still finalized honestly.
8. **Acceptance criteria.** An RCA run on fakes produces a persisted draft whose every fact has a verified citation. The RunManifest captures prompt version, model ref, budgets, and usage.
9. **Depends on.** M10, M11
10. **Deferred.** Iterative investigation, hypotheses loop, and planning (M23); approval and lifecycle transitions (M25–M26); real infrastructure (Stage D).

### Stage D — Infrastructure for RCA

Real adapters replace fakes one at a time. The M12 tests and each port's contract suite must stay green.

---

#### M13 — Configuration and composition root

1. **Goal.** Environment-based settings and a `bootstrap.py` that builds services from adapters.
2. **Why it exists.** Real adapters need configuration and a single wiring point. `config_hash` needs a secret-free settings view.
3. **Spec requirements.** §4.2 (model selection by config), §11.1 (`config_hash`), §14.4, §19.1; ADR-001 DI rules.
4. **Files/modules.** `config/settings.py` (grouped settings), `bootstrap.py`, `.env.example`
5. **Domain models/interfaces.** `AppSettings`, `DatabaseSettings`, `LLMSettings` (model per role), `BudgetSettings`, `TelemetrySettings` (with `capture_content`); secrets as `SecretStr`; `to_hashable_config()` excludes secrets. Groups for GitHub, embeddings, retrieval, and test evidence are added in their own milestones.
6. **External dependencies.** `pydantic-settings`.
7. **Tests.** Settings load from env; missing required values give clear errors; `repr`/`str` never show secret values; `config_hash` unchanged when only a secret changes; bootstrap in `replay` mode never constructs a GitHub-backed RepoSource (asserted with a sentinel factory).
8. **Acceptance criteria.** `.env.example` lists every variable with no real values. No `os.environ` access outside `config/`.
9. **Depends on.** M12
10. **Deferred.** Settings groups for adapters not yet built.

---

#### M14 — PostgreSQL foundation

1. **Goal.** Database schema, migrations, and PostgreSQL implementations of the run, RCA, and idempotency repositories.
2. **Why it exists.** The system of record. Persistence interfaces and contract suites exist (M09), so the gate is satisfied.
3. **Spec requirements.** §7.2 (immutable content), §11.1, §12 (unique key, duplicate handling), §18; change C1.
4. **Files/modules.** `adapters/postgres/{engine,models,run_repository,rca_repository,idempotency_repository,unit_of_work}.py`, `migrations/` (Alembic), `docker-compose.yml` (PostgreSQL with the pgvector image; extension enabled here but unused until M18), `tests/integration/postgres/`
5. **Domain models/interfaces.** Implements `RunRepository`, `RCARepository`, `IdempotencyRepository`, `UnitOfWork`. Adds a partial unique index on `execution_key` for non-failed runs.
6. **External dependencies.** `sqlalchemy[asyncio]` 2.x, `asyncpg`, `alembic`; Docker for tests.
7. **Tests.** M09 contract suites run against PostgreSQL (`integration`); migration up/down; concurrent claims of the same execution key yield exactly one run; RCA content update attempts are rejected.
8. **Acceptance criteria.** Contract suites pass on both fakes and PostgreSQL. `bootstrap.py` can wire PostgreSQL repositories by configuration. M12 passes with PostgreSQL stores.
9. **Depends on.** M09, M13
10. **Deferred.** Artifact and temporal tables (M15); vector columns (M18); validation tables (M30); evaluation schema (M21).

---

#### M15 — Temporal artifact storage and Store-backed RepoSource

1. **Goal.** ADR-002 storage (first-parent `seq`, chunk validity ranges, artifact revisions, timeline events) and a `RepoSource` that reconstructs IssueSnapshots from it.
2. **Why it exists.** Replay must read only from the Store (spec §13.2). This is the core of temporal correctness, built and tested before GitHub ingestion.
3. **Spec requirements.** §13.2–§13.5; ADR-002 §1–§6; D3.
4. **Files/modules.** `adapters/postgres/artifact_repository.py`, `adapters/postgres/temporal_queries.py`, `adapters/store_repo_source.py`, `application/ingestion/ingestion_models.py` (neutral ingestion records), `application/ingestion/fixture_loader.py` (loads the synthetic fixture timeline), migrations, `tests/temporal/`
5. **Domain models/interfaces.** `CommitRecord(seq, sha, landed_at)`, `FileVersion`, `ArtifactRevision`, `TimelineEvent`, `IssueSnapshotBuilder` (application: replays timeline events to the cutoff), `derive_cutoff_sha(cutoff_time, first_parent_commits)`.
6. **External dependencies.** None new.
7. **Tests.** `tests/temporal/` against PostgreSQL: ADR-002 tests 1–6 (fixture timeline, property test on scope predicate, canaries, rebase trap, edit trap, mode wiring); SQL results equal the M06 predicates on random scopes.
8. **Acceptance criteria.** Store-backed `RepoSource` passes the M08 contract suite. All temporal tests green. M12 runs in replay mode on PostgreSQL with fixture data.
9. **Depends on.** M06, M14
10. **Deferred.** Fetching real data from GitHub or git (M19); chunk embeddings (M18).

---

#### M16 — Chunking

1. **Goal.** Artifact-aware chunkers producing chunks with content hashes and validity ranges.
2. **Why it exists.** Retrieval quality depends on chunk boundaries. Chunking is pure logic and testable without a database.
3. **Spec requirements.** §15.4; ADR-002 §2 (content-hash deduplication); ADR-004 Part D (static parsing only).
4. **Files/modules.** `application/ingestion/chunking/{python_code,tests,markdown_docs,issues,pull_requests,commits}.py`, `application/ingestion/chunking/registry.py` (with `chunker_version`)
5. **Domain models/interfaces.** `Chunk(content_hash, artifact_ref, text, line_start, line_end, symbol_path)`, `Chunker` protocol, `ChunkerRegistry`.
6. **External dependencies.** None (`ast` stdlib; headings parsed without a Markdown library).
7. **Tests.** Functions/classes become chunks with correct line ranges; syntax-error files fall back to line windows; test functions detected; Markdown split by headings; identical content yields identical hashes; no `exec`, `eval`, or import of repository code (asserted by ruff banned-API rules).
8. **Acceptance criteria.** Every §15.4 artifact type has a chunker with tests. `chunker_version` feeds `retrieval_version`.
9. **Depends on.** M15
10. **Deferred.** tree-sitter / non-Python languages; tuning chunk sizes (experiments after M21).

---

#### M17 — Lexical retrieval

1. **Goal.** A PostgreSQL full-text `Retriever` that applies the temporal scope in SQL before ranking.
2. **Why it exists.** A first real retriever that needs no embeddings or external services. It is the lexical branch of hybrid retrieval.
3. **Spec requirements.** §13.4, §15.2, §15.3 (lexical branch); D2 / ADR-006.
4. **Files/modules.** `docs/adr/006-lexical-retrieval.md` (written first), `adapters/postgres/lexical_retriever.py`, `application/services/scoped_retrieval.py` (defense-in-depth re-check wrapper), migration for `tsvector` columns and indexes
5. **Domain models/interfaces.** Implements `Retriever`. `ScopedRetrievalService` calls `assert_within_scope` on every result.
6. **External dependencies.** None new.
7. **Tests.** M08 retriever contract suite on PostgreSQL; ranking sanity on the fixture corpus; scope filter applied before `LIMIT` (a post-cutoff chunk that would rank first is never returned and does not reduce the result count); temporal canary tests extended to retrieval.
8. **Acceptance criteria.** ADR-006 accepted. M12 runs with the lexical retriever on fixture data.
9. **Depends on.** M16
10. **Deferred.** Vector search, fusion, reranking (M18); BM25 extensions.

---

#### M18 — EmbeddingProvider port, vector retrieval, hybrid fusion

1. **Goal.** An embedding port with a deterministic fake, a pgvector retriever, and Reciprocal Rank Fusion.
2. **Why it exists.** Completes hybrid retrieval. The port and fake come first so vector code is tested without a real embedding model.
3. **Spec requirements.** §15.3, §15.4 (embedding per unique content hash); ADR-001 `EmbeddingProvider`; ADR-002 §2.
4. **Files/modules.** `ports/embedding_provider.py`, `tests/fakes/fake_embedding_provider.py` (deterministic hash-based vectors), `adapters/postgres/vector_retriever.py`, `application/retrieval/fusion.py`, `application/retrieval/hybrid_retriever.py`, `application/retrieval/retrieval_version.py`, migration for vector columns
5. **Domain models/interfaces.** `EmbeddingProvider.embed(texts)`, `Embedding`, `reciprocal_rank_fusion(ranked_lists, k)`, `HybridRetriever` (implements `Retriever`), `RetrievalVersion(chunker_version, embedding_model_ref, fusion_config)`.
6. **External dependencies.** `pgvector` Python package.
7. **Tests.** RRF unit tests (ties, disjoint lists); embeddings computed once per content hash; the vector branch applies scope before ranking; retriever contract suite for the vector and hybrid retrievers; temporal suite green.
8. **Acceptance criteria.** Hybrid retriever passes the contract suite. `retrieval_version` is recorded on RunManifest.
9. **Depends on.** M17
10. **Deferred.** Real embedding model (M20); reranking (evaluate after M21 metrics).

---

#### M19 — GitHub read adapter and ingestion pipeline

1. **Goal.** Read-only ingestion of a real repository: first-parent history, file versions, issues with edit history and timeline events, PRs, releases.
2. **Why it exists.** Real data for replay and evaluation. `RepoSource` already has fake and Store-backed implementations (gate in §1).
3. **Spec requirements.** §3.1, §13.3, §14.2, §19.3; ADR-002 §2–§5; D3; success criterion 1.
4. **Files/modules.** `adapters/github/{client,rest,graphql,mapping,rate_limit}.py`, `adapters/git/history_reader.py` (per D3), `application/ingestion/ingestion_service.py`, `tests/integration/github/`, recorded response fixtures
5. **Domain models/interfaces.** `GitHubArtifactSource` (adapter feeding neutral ingestion records), `IngestionService.ingest_repository(repo_id)` (incremental and resumable), live-mode `GitHubRepoSource` (implements `RepoSource`; wired only in `live` mode).
6. **External dependencies.** `httpx` (HTTP client), `dulwich` (per D3), `respx` (dev, recorded HTTP responses). GitHub token with read-only scopes.
7. **Tests.** Mapping tests on recorded responses (`userContentEdits`, timeline events, deleted comments); retries only on 429/5xx/timeouts with `Retry-After`; auth errors not retried; token-scope integration test (write attempt must fail); `GitHubRepoSource` passes the RepoSource contract suite (integration); `history_complete=false` set when edit history is unavailable.
8. **Acceptance criteria.** `encode/httpx` is ingested into PostgreSQL. Re-running ingestion is idempotent. Replay on ingested data passes the temporal suite.
9. **Depends on.** M15, M16
10. **Deferred.** PR diffs and PR snapshots for validation (M30); webhooks (M32); non-default branches.

---

#### M20 — Real LLM and embedding provider adapters

1. **Goal.** One production LLM adapter (Anthropic) and one embedding adapter (Voyage `voyage-code-4`) behind the ports, with retries, error mapping, usage, and cost.
2. **Why it exists.** Needed to run real RCAs. `LLMProvider` and `EmbeddingProvider` have been exercised through fakes since M12 and M18 (gate in §1).
3. **Spec requirements.** §4.2, §11.1 (`model_provider`, `model_id`, `pricing_version`), §16.3, §19.3; ADR-001 provider differences; ADR-004 Part B rendering; D1, D8.
4. **Files/modules.** `adapters/llm/anthropic_provider.py`, `adapters/llm/model_router.py` (role → ModelRef), `adapters/llm/pricing.py` (versioned price table), `adapters/embeddings/voyage_embeddings.py` (D8; model id from configuration), `tests/integration/llm/`
5. **Domain models/interfaces.** Implements `LLMProvider`, `EmbeddingProvider`. Maps vendor errors onto `LLMProviderError` / `LLMTransientError`.
6. **External dependencies.** `anthropic` SDK (D1); `voyageai` SDK (D8). `langchain-core` only if it simplifies the adapter, and only inside `adapters/llm/`.
7. **Tests.** The M07 contract suite runs against the real adapter (`integration`); unit tests with a mocked transport: error mapping, retry policy, usage and cost calculation, rendering of untrusted blocks through M11.
8. **Acceptance criteria.** Switching provider or model is a configuration change only. No SDK type crosses the port.
9. **Depends on.** M11, M18
10. **Deferred.** Second LLM provider (Phase 7 comparisons); reranker models.

---

#### M21 — Seed evaluation set and retrieval baseline

1. **Goal.** The separate evaluation subsystem, with 20–30 hand-checked `encode/httpx` replay cases and retrieval metrics.
2. **Why it exists.** Spec Phase 1 exit criterion. Measurement must exist before RCA quality work, or improvements cannot be shown.
3. **Spec requirements.** §22.1–§22.3 (retrieval metrics), §22.2 (contamination tags), ADR-002 §6.5 (ground-truth isolation).
4. **Files/modules.** `evaluation/{cases,ground_truth,retrieval_metrics,runner,reports}.py`, `evaluation/datasets/httpx_seed/` (case definitions), separate `evaluation` DB schema + migration, DB role without evaluation privileges for production runs
5. **Domain models/interfaces.** `HistoricalEvaluationCase`, `HiddenGroundTruth`, `recall_at_k`, `precision_at_k`, `mean_reciprocal_rank`, `ndcg_at_k`.
6. **External dependencies.** None new.
7. **Tests.** Metric unit tests against hand-computed values; import-linter proves production code does not import `evaluation`; integration test proves the production DB role cannot read the evaluation schema; eligibility rules (non-reconstructable issue body → ineligible).
8. **Acceptance criteria.** Seed cases documented with cutoff, ground truth, eligibility, and contamination tags. Ground truth **frozen** (D6): dataset version + content hash recorded; any change requires a new dataset version. Recall@K baseline recorded in `docs/evaluation/` for the M18 hybrid retriever.
9. **Depends on.** M18, M19
10. **Deferred.** RCA and validation metrics (M22, M30); benchmark expansion (Phase 7).

---

#### M22 — Baseline RCA on real infrastructure and baseline metrics

1. **Goal.** Run the M12 baseline RCA on real data, add a CLI entrypoint, and record baseline RCA metrics.
2. **Why it exists.** Spec Phase 2 exit criterion. It is the reference point that the LangGraph RCA must beat.
3. **Spec requirements.** §22.2 (no-retrieval baseline), §22.3 (RCA metrics); D6; success criteria 3–5.
4. **Files/modules.** `api/cli.py` (`run-rca`, `ingest`), `evaluation/rca_metrics.py`, `evaluation/no_retrieval_baseline.py`, `docs/evaluation/baseline-rca.md`
5. **Domain models/interfaces.** Uses existing services. Adds the evaluation-side `RCAScore` (human rubric fields + computed citation correctness, affected-component overlap, unsupported-claim rate).
6. **External dependencies.** None new (CLI with stdlib `argparse`).
7. **Tests.** CLI smoke test with fakes; metric unit tests; an e2e test marked `e2e` running one seed case end to end.
8. **Acceptance criteria.** Baseline RCA and no-retrieval baseline metrics recorded for the seed set, split by contamination risk.
9. **Depends on.** M20, M21
10. **Deferred.** LLM-judge groundedness (spec Q4); HTTP API.

### Stage E — LangGraph RCA

---

#### M23 — RCA graph on fakes

1. **Goal.** The RCA LangGraph graph with typed state, focused nodes, bounded loops, and budget-driven termination, tested entirely on fakes.
2. **Why it exists.** Iterative investigation (spec §5.3). LangGraph is introduced only now, after domain contracts, ports, and a working single-pass service are tested (gate in §1).
3. **Spec requirements.** §5.3, §16.1, §16.2, §16.3, §20; CLAUDE.md rule 8.
4. **Files/modules.** `application/graphs/rca/{state,nodes,routing,graph,finalize}.py`, `application/prompts/rca_graph/v1/`, `tests/graph/rca/`
5. **Domain models/interfaces.**
   - `RCAGraphState` (TypedDict): issue snapshot, plan, retrieved evidence, hypotheses, iteration counters, budget tracker, termination reason
   - Nodes: `load_issue`, `triage`, `plan_investigation`, `retrieve`, `analyze`, `check_sufficiency`, `refine_plan`, `build_rca`, `verify_citations`, `assess_sufficiency`, `persist`, `finalize_on_budget`
   - Routing functions are pure and unit-tested. Nodes call application services and ports only.
   - Structured LLM outputs per node (`TriageResult`, `InvestigationPlan`, `AnalysisResult`).
6. **External dependencies.** `langgraph` (already declared); in-memory checkpointer only.
7. **Tests.** Every route taken at least once; loop ends on sufficiency; loop ends after N iterations without new evidence; each budget dimension triggers `finalize_on_budget` with `status = budget_exhausted`; timeout via fake clock; LLM structured-output failure → repair → `StructuredOutputError` path; canary and injection tests from M12 re-run through the graph.
8. **Acceptance criteria.** No unbounded path (asserted by tests that force an LLM to always ask for more evidence). Graph output passes the same finalization rules as M12.
9. **Depends on.** M12
10. **Deferred.** Human-in-the-loop interrupts (spec §16.4 is optional; not in V1 plan); persistent checkpointer; real infrastructure (M24).

---

#### M24 — RCA graph on real infrastructure and comparison

1. **Goal.** Run the graph on real data and compare it against the M22 baseline.
2. **Why it exists.** Spec Phase 3 exit criterion: measurable improvement on `likely_unseen` cases.
3. **Spec requirements.** §22.2, §22.3, §24 Phase 3.
4. **Files/modules.** `api/cli.py` (`run-rca --mode graph`), `evaluation/comparisons.py`, `docs/evaluation/graph-vs-baseline.md`
5. **Domain models/interfaces.** Existing.
6. **External dependencies.** None new.
7. **Tests.** e2e test for one seed case through the graph (`e2e`); comparison report generation unit-tested.
8. **Acceptance criteria.** Comparison report recorded. If there is no improvement on `likely_unseen` cases, the report says so and the next steps are proposed. Results are not tuned to pass.
9. **Depends on.** M22, M23
10. **Deferred.** Prompt and retrieval tuning experiments beyond one iteration; model comparisons (Phase 7).

### Stage F — RCA lifecycle

---

#### M25 — Lifecycle rules

1. **Goal.** Pure lifecycle rules: allowed transitions, actor rules, approval preconditions, supersession, versioning.
2. **Why it exists.** Only an approved RCA may feed validation. These rules must be exact and fully tested.
3. **Spec requirements.** §7.2, §7.3.
4. **Files/modules.** `domain/rca/lifecycle.py`, extend `domain/rca/rca_record.py`
5. **Domain models/interfaces.** `LifecycleState`, `LifecycleTransition`, `Actor(kind: human | system, identity)`, `apply_transition(rca_record, to_state, actor, reason, clock) -> RCARecord`, `check_approval_preconditions(rca_result, reason)`, `supersede_previous_approved(...)`.
6. **External dependencies.** None.
7. **Tests.** Table-driven test over every (from, to, actor) combination; approval rejected for `budget_exhausted`, for `insufficient`, and for `partial` without an override reason; approval accepted for `partial` with an override reason; approving v2 supersedes v1; transitions are append-only.
8. **Acceptance criteria.** Every row of the §7.3 transition table and every precondition has a test. Illegal transitions raise `LifecycleError`.
9. **Depends on.** M04
10. **Deferred.** Persistence and review commands (M26).

---

#### M26 — Lifecycle service, persistence, review commands

1. **Goal.** Persisted lifecycle transitions and a way for a human to review, approve, reject, or return an RCA.
2. **Why it exists.** Completes spec Phase 4. Validation needs approved RCAs.
3. **Spec requirements.** §7.2, §7.3; D4; success criterion 6.
4. **Files/modules.** `application/services/rca_review.py`, extend `adapters/postgres/rca_repository.py` (transitions table, "one approved per rca_id" constraint), `api/cli.py` (`rca submit`, `rca approve`, `rca reject`, `rca return`, `rca show`; every state-changing command requires `--reviewer` and `--reason`, with no default from config or environment), migration
5. **Domain models/interfaces.** `RCAReviewService`; `RCARepository.append_transition`, `get_current_approved(rca_id)`.
6. **External dependencies.** None new.
7. **Tests.** Service unit tests with fakes; repository contract tests extended (append-only, single approved version under concurrency); CLI smoke tests; state-changing command without `--reviewer` fails.
8. **Acceptance criteria.** A draft produced by M24 can be submitted, approved with a recorded actor and reason, and later superseded by a new approved version.
9. **Depends on.** M14, M25
10. **Deferred.** Authenticated HTTP review API and UI (D4); notifications.

### Stage G — Validation Agent

---

#### M27 — Validation domain

1. **Goal.** Validation models, F2P/P2P classification, normalization, `compute_verdict`, and `is_current`, all pure.
2. **Why it exists.** The deterministic core of validation, fully specified by ADR-003. It is built and locked before any validation service exists.
3. **Spec requirements.** §8.5, §9.2, §10.1–§10.3; ADR-003 in full.
4. **Files/modules.** `domain/validation/{test_evidence,claim_coverage,findings,validation_result,test_classification,normalization,verdict,staleness}.py`
5. **Domain models/interfaces.** `TestResult`, `TestOutcome`, `FailToPassEvidence`, `PassToPassEvidence`, `TestEvidence`, `ClaimCoverage`, `CoverageLevel`, `Finding`, `FindingKind`, `FindingSeverity`, `ValidationResult`, `VerdictDecision`, `VerdictReason`; `classify_fail_to_pass`, `classify_pass_to_pass`, `normalize_validation_inputs`, `compute_verdict`, `is_current`.
6. **External dependencies.** None.
7. **Tests.** `tests/unit/domain/test_verdict.py` and `tests/validation/`: every F2P table cell; every rule R0–R12; precedence cases; every normalization row; property tests (adding a blocking finding never produces `pass`; removing evidence never produces `pass`); staleness when the head moves and when the RCA is superseded.
8. **Acceptance criteria.** Test coverage of `domain/validation/` is 100% of branches. `rule_version = "verdict-v1"` is recorded on every decision.
9. **Depends on.** M04, M25
10. **Deferred.** `test_not_feasible` exemption (spec Q1); quality gate (outside V1).

---

#### M28 — Validation ports and fakes

1. **Goal.** Ports for PR snapshots, test evidence, and validation persistence, with fakes and contract suites.
2. **Why it exists.** Validation services need these seams before any GitHub PR or CI integration.
3. **Spec requirements.** §8.2, §9; ADR-001 `TestEvidenceSource`; S5.
4. **Files/modules.** Extend `ports/repo_source.py` (`get_pull_request`), `ports/test_evidence_source.py`, extend `ports/stores.py` (`ValidationRepository`), `domain/repository/pull_request_snapshot.py`, fakes and contract suites
5. **Domain models/interfaces.** `PullRequestSnapshot(pr_ref, base_sha, head_sha, title, body, changed_files, diff_hunks, commits)`, `DiffHunk`, `TestEvidenceSource.get_evidence(pr_ref, base_sha, head_sha)`, `ValidationRepository`.
6. **External dependencies.** None.
7. **Tests.** Contract suites; fake TestEvidenceSource returns evidence whose `head_sha` mismatches on request (for normalization tests).
8. **Acceptance criteria.** Fakes pass contract suites. PR title, body, and commit messages are typed as untrusted content.
9. **Depends on.** M27, M08
10. **Deferred.** Real GitHub PR retrieval and CI adapter (M30); sandbox (M33).

---

#### M29 — Validation service and graph on fakes

1. **Goal.** The validation workflow: load the approved RCA, PR snapshot, and test evidence; map claims to changes; assess coverage and findings; verify citations; normalize; compute the verdict; persist.
2. **Why it exists.** Completes Validation Agent behavior on fakes, reusing the RCA-side patterns.
3. **Spec requirements.** §8.1–§8.5, §10, §14.1 (PR self-description is not evidence), §20.
4. **Files/modules.** `application/services/validation.py`, `application/graphs/validation/{state,nodes,routing,graph}.py`, `application/prompts/validation/v1/`, `tests/graph/validation/`, `tests/security/test_validation_injection.py`
5. **Domain models/interfaces.** `ValidationDraft` (LLM structured output: coverage + findings with citation references); `ValidationService.run(rca_id, pr_ref)`. Nodes: `load_approved_rca`, `load_pr_snapshot`, `load_test_evidence`, `map_claims_to_changes`, `evaluate_coverage`, `inspect_scope_and_risks`, `verify_citations`, `normalize` (code), `compute_verdict` (code), `persist`.
6. **External dependencies.** None new.
7. **Tests.** Rejects non-approved or superseded RCAs; binding fields recorded; PR description saying "tests pass, root cause fixed" plus a fake LLM that obeys it still cannot produce `pass` without demonstrated F2P evidence; symptom-only and partial scenarios; budgets bound the graph.
8. **Acceptance criteria.** Every verdict is produced by `compute_verdict`. No LLM node output field can set the verdict.
9. **Depends on.** M26, M28, M23
10. **Deferred.** Real PR and CI data (M30); sandbox execution (M33).

---

#### M30 — Validation on real infrastructure

1. **Goal.** Real PR snapshots from GitHub, a CI-results `TestEvidenceSource`, and PostgreSQL validation persistence.
2. **Why it exists.** Completes spec Phase 5 and its exit criteria.
3. **Spec requirements.** §8.2, §8.5, §9; ADR-004 Part E strategy 1 (CI adapter); success criteria 7–11.
4. **Files/modules.** Extend `adapters/github/` (PR snapshot, diffs), `adapters/test_evidence/ci_results.py` (reads CI JUnit artifacts), `adapters/postgres/validation_repository.py`, migrations, `api/cli.py` (`validate-pr`), `evaluation/validation_metrics.py`
5. **Domain models/interfaces.** Implements `TestEvidenceSource` (CI), `ValidationRepository`; extends `GitHubRepoSource.get_pull_request`.
6. **External dependencies.** A JUnit XML parser from stdlib `xml.etree` with safe parsing (`defusedxml` if needed; justify in the PR).
7. **Tests.** Contract suites against real adapters (`integration`); JUnit parsing (failed vs. error vs. skipped); SHA-mismatched CI results rejected; staleness detection end to end with a PR whose head moves.
8. **Acceptance criteria.** Validation runs end to end on a real PR (with CI evidence available) and produces an explained verdict. Stale validations are detected.
9. **Depends on.** M29, M19, M20
10. **Deferred.** Sandbox F2P base-overlay execution (M33); webhooks (M32); quality gate.

### Stage H — Hardening

---

#### M31 — Observability adapter (OpenTelemetry + Phoenix)

1. **Goal.** OpenTelemetry implementation of `TelemetryProvider`, exported to self-hosted Phoenix, following ADR-005.
2. **Why it exists.** Spec Phase 6. Until now telemetry calls go to the no-op/recording fake, so every service already emits spans through the port.
3. **Spec requirements.** §17; ADR-005 in full; success criterion 14.
4. **Files/modules.** `adapters/telemetry/{otel_provider,openinference_attributes,safe_attributes_export,metrics}.py`, `config/settings.py` (telemetry group completed), `docker-compose.yml` (Phoenix service), structured logging with trace IDs
5. **Domain models/interfaces.** Implements `TelemetryProvider`; metric instruments from ADR-005 §5.
6. **External dependencies.** `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, an OpenInference semantic-conventions package; a structured logging library if the stdlib logger is insufficient (justify).
7. **Tests.** In-memory exporter asserts span tree shape and required attributes for one RCA and one validation run; `capture_content=false` → no prompt content in any span or log; secrets redacted when `true`; exporter failure does not fail a run; `temporal.isolation.violations` counter increments on a forced violation. Integration: traces arrive in Phoenix.
8. **Acceptance criteria.** A full RCA run is visible in Phoenix with correlation IDs. No sensitive data in telemetry (security test).
9. **Depends on.** M24, M30
10. **Deferred.** OpenTelemetry Collector, tail sampling, second backend.

---

#### M32 — Webhook trigger and idempotent execution

1. **Goal.** GitHub webhooks trigger RCA and validation runs, exactly once per execution key.
2. **Why it exists.** Spec Phase 6: webhooks are delivered at least once.
3. **Spec requirements.** §2, §12; D5; S9.
4. **Files/modules.** `api/webhooks.py` (FastAPI, signature verification), `application/services/run_dispatcher.py`, `adapters/postgres/job_outbox.py` (job/outbox table, `FOR UPDATE SKIP LOCKED` claiming), `worker.py` (separate worker process), migration
5. **Domain models/interfaces.** `TriggerEvent`, `RunJob`, `RunDispatcher.dispatch(trigger_event)`; uses `IdempotencyRepository`.
6. **External dependencies.** `fastapi`, `uvicorn` (already declared). Webhook secret via settings.
7. **Tests.** Invalid signature rejected; duplicate deliveries (including concurrent) produce one run; `failed` key permits a linked retry attempt; issue-opened triggers RCA; PR synchronize triggers validation only when an approved RCA is linked.
8. **Acceptance criteria.** Replaying the same webhook payload 10 times concurrently creates exactly one run.
9. **Depends on.** M30
10. **Deferred.** Posting results back to GitHub (out of V1 scope); multi-repository installation management.

---

#### M33 — Sandbox test execution

1. **Goal.** A sandbox `TestEvidenceSource` adapter that runs F2P (with base overlay) and P2P tests in an isolated runner.
2. **Why it exists.** Most repositories' CI does not run the F2P base-overlay procedure (ADR-004 Part E).
3. **Spec requirements.** §9, §14.3; ADR-004 Parts D and E.
4. **Files/modules.** `adapters/test_evidence/sandbox_client.py`, `sandbox_runner/` (separate deployable: container image, job spec, JUnit collection), `docs/runbooks/sandbox.md`
5. **Domain models/interfaces.** Implements `TestEvidenceSource`; `SandboxJobSpec(repo, base_sha, head_sha, test_ids, limits)`; `environment_ref` populated.
6. **External dependencies.** Container runtime on the runner host (gVisor/Firecracker-class recommended). No new platform-process dependencies beyond the client.
7. **Tests.** Contract suite (`integration`); the runner has no network in the test phase, no secrets in env, non-root, read-only root filesystem (assertion tests inside a probe job); a timeout yields the `timeout` outcome; the base overlay copies only test files; a malicious test attempting network or file escape fails harmlessly.
8. **Acceptance criteria.** F2P evidence is produced for a real httpx PR with a regression test, and classified correctly by M27.
9. **Depends on.** M30
10. **Deferred.** Historical environment reconstruction for old SHAs (spec §22.4); multi-language runners.

---

#### M34 — Security, resilience, operational readiness

1. **Goal.** Close remaining gaps: the full security suite, timeout and retry review, performance baselines, runbooks.
2. **Why it exists.** Spec Phase 6 exit criteria.
3. **Spec requirements.** §14 (all), §19.3, §21 (security suite), ADR-004 Testing; D7 follow-up; success criteria 12–15.
4. **Files/modules.** `tests/security/` (completed), `docs/runbooks/{ingestion,rca-runs,validation-runs,incident-temporal-violation}.md`, performance notes in `docs/evaluation/`
5. **Domain models/interfaces.** None new.
6. **External dependencies.** Possibly a secret-detection library (D7), with justification.
7. **Tests.** Every ADR-004 security test present and green; timeouts on every external call; retry policy audit tests per adapter; load test of retrieval latency on the ingested httpx corpus.
8. **Acceptance criteria.** Security suite green; runbooks written; V1 success criteria 1–15 demonstrated. (Criterion 16 is completed by evaluation expansion.)
9. **Depends on.** M31, M32, M33
10. **Deferred.** Phase 7.

---

## 7. Not planned in detail: Phase 7 (evaluation expansion)

After M34: expand the benchmark beyond the seed set; compare baseline RAG, improved RAG, and LangGraph RCA; compare retrieval strategies and models (second LLM provider; local/open-weight `EmbeddingProvider` vs. `voyage-code-4` on Recall@K, MRR, NDCG, latency, indexing time, infrastructure cost); add a less-prominent or private repository (spec §22.2). This will be planned when M34 is complete.

## 8. Explicitly out of V1 (never in this plan)

Per spec §3.2: writing to GitHub (comments, approvals, merges, issue edits), generating or pushing fixes, releases or changelog updates, executing repository code in platform processes, bypassing CI, branch protection, or human approvals. Also excluded: the quality gate itself (spec §10.4), human-in-the-loop graph interrupts (spec §16.4, optional), `test_not_feasible` exemptions (spec Q1), and a runtime groundedness judge (spec Q4).

## 9. How to use this plan with Claude Code

1. Approve or amend §4 decisions and §5 proposed changes; update the spec, ADRs, and `CLAUDE.md` accordingly.
2. Set `CLAUDE.md` "Current milestone" to the next milestone.
3. Start a fresh session per milestone, in plan mode: *"Implement milestone MNN from docs/implementation-plan.md. Propose the plan first."*
4. Review, run the Definition of Done checks, commit, and advance the current milestone.
