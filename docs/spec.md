# GitHub Issue RCA Platform — Product Specification

| Field | Value |
|---|---|
| Status | Draft |
| Specification version | 0.3 |
| Reference repository | `encode/httpx` |
| Related ADRs | [001](adr/001-ports-and-adapters.md) · [002](adr/002-temporal-indexing.md) · [003](adr/003-validation-verdicts.md) · [004](adr/004-untrusted-code-execution.md) · [005](adr/005-observability.md) |

Normative language: **MUST**, **MUST NOT**, **SHOULD**, **MAY** follow RFC 2119.

---

## 1. Purpose

The GitHub Issue RCA Platform is an evidence-driven agentic system that investigates software defects and validates proposed fixes.

It has two independent but connected agent workflows:

1. **RCA Agent** — investigates a reported GitHub issue, gathers evidence from the repository and its history, determines the probable root cause, and recommends a fix approach.
2. **RCA Validation Agent** — runs after an RCA is approved and a developer opens a pull request; determines whether the proposed implementation addresses the diagnosed root cause, using claim-level analysis and deterministic test evidence.

The platform prioritizes, in order:

1. evidence over plausibility;
2. temporal correctness;
3. deterministic decisions where possible;
4. secure handling of untrusted repository content;
5. traceability and reproducibility;
6. model independence;
7. explicit human and policy control over merge and release.

### 1.1 Guiding principle

The platform MUST prefer *"There is insufficient evidence to establish the root cause"* over a plausible but unsupported explanation, and *"There is insufficient evidence that this PR addresses the RCA"* over an unsupported `pass`.

The system exists to improve engineering decisions through evidence, not to maximize the number of confident AI answers.

---

## 2. Business workflow

```text
GitHub Issue
   │
   ▼
RCA Agent ──────────► RCARecord (draft)
   │
   ▼
Human Review ──── rejected ──► new RCA version (draft)
   │
   ▼
Approved RCA
   │
   ▼
Developer implements fix ──► Pull Request
   │
   ▼
Deterministic CI / Sandbox ──► TestEvidence
   │
   ▼
RCA Validation Agent ──► ValidationResult (verdict computed in code)
   │
   ▼
Deterministic Quality Gate  (validation + CI + security + policy + human approval)
   │
   ▼
Merge ──► Changelog ──► Release        (outside platform authority)
```

Benchmark construction and evaluation are separate engineering-quality capabilities and MUST NOT be mixed into production agent behavior.

---

## 3. Scope

### 3.1 V1 in scope

- Public GitHub repositories: issues, source, docs, tests, historical issues/PRs/commits, releases and changelogs.
- RCA generation, RCA lifecycle management, PR-based validation.
- Deterministic test evidence from CI or an isolated sandbox.
- Evidence citations and citation verification.
- Temporal isolation, historical replay, evaluation.
- PostgreSQL persistence, pgvector, hybrid retrieval.
- LangGraph orchestration, OpenTelemetry instrumentation, self-hosted Arize Phoenix.

The architecture MUST NOT assume HTTPX-specific behavior.

### 3.2 V1 out of scope

V1 MUST NOT:

- modify repository code, or generate/push fixes;
- approve, merge, or comment on pull requests; modify issues;
- publish releases or update changelogs;
- execute repository code inside any platform process (see ADR-004);
- make production changes;
- bypass branch protection, deterministic CI, or required human approvals.

These capabilities require a separately reviewed specification and security design.

---

## 4. Architecture principles

### 4.1 Ports and adapters

Domain and application logic depend on interfaces (ports). Vendor implementations live in adapters. See **ADR-001**.

Core ports:

```text
LLMProvider          EmbeddingProvider     TelemetryProvider
RepoSource           Retriever             TestEvidenceSource
SecretRedactor       Clock
Store (a family of narrow repositories: artifacts, runs, RCAs, validations, idempotency)
```

Vendor SDK types MUST NOT appear in domain or application models.

### 4.2 Model independence

- Runtime logic MUST NOT depend on a specific provider (Anthropic, OpenAI, Google, local models).
- Model selection is configuration-driven, per graph node where useful.
- Claude Code may be used to develop the platform without creating runtime dependence on Claude.

### 4.3 Model definitions added during implementation

`IssueSnapshot`, `PullRequestSnapshot`, `RetrievedChunk`, and `LLMRequest` are specified in this document when they are built (implementation plan milestones M07, M08, M28).

### 4.4 Determinism boundary

| Decided by LLM | Decided by application code |
|---|---|
| Hypotheses, claims, rationale | Citation verification |
| Claim coverage assessment | Temporal scope enforcement |
| Findings, recommendations | Test outcomes and fail-to-pass classification |
| Evidence-sufficiency *proposal* | Final validation verdict |
| | Budget enforcement, termination |
| | Lifecycle transitions, staleness |

---

## 5. RCA Agent

### 5.1 Responsibility

Given an issue, answer: *What is the most probable root cause, what evidence supports it, and what should probably change?*

The RCA Agent stops after producing an evidence-backed RCA. It does not implement or validate a fix.

### 5.2 Inputs

- repository identifier, issue identifier;
- an **IssueSnapshot** — the issue as it existed at the cutoff (title, body revision, labels, comments), see §13.3;
- cutoff time and repository SHA;
- run configuration and budgets.

It may investigate, within the temporal scope: source code, tests, documentation, historical issues, historical PRs, commits, changelogs, and release metadata.

### 5.3 Investigation flow

```text
Load IssueSnapshot → Triage → Plan Investigation
   → Retrieve → Analyze / Generate & Test Hypotheses
   → Evidence sufficient? ── no, budget remains ──► Refine plan → Retrieve …
                         └─ yes, or budget/termination reached
   → Build RCA → Verify Citations → Assess Sufficiency → Persist
```

The loop is bounded (§16). Termination conditions are listed in §16.2.

---

## 6. Evidence model

Evidence is a first-class domain concept. All repository and GitHub content is untrusted data (§14).

### 6.1 Citation

```text
Citation
├── citation_id
├── kind: file | issue | issue_comment | pr | pr_comment | commit | release | ci_run
├── ref                       # human-readable reference (examples below)
├── sha | None                # git SHA for file/commit kinds
├── line_start | None
├── line_end | None
├── content_hash              # hash of the cited artifact revision (immutability for mutable artifacts)
├── excerpt                   # verbatim text the claim relies on
├── content_trust: system | untrusted
├── verification_status: verified | failed | not_verified
├── verification_error | None
├── verified_at | None
└── retrieved_at
```

`content_trust = system` applies only to structured data produced by trusted platform components (e.g., CI outcome codes parsed by the TestEvidenceSource adapter). Everything originating from repository or GitHub content — including test output text — is `untrusted`.

Reference examples:

```text
httpx/_client.py@abc1234#L120-L147
issue#123
issue#123/comment/987654321
PR#456
PR#456/comment/987654321
commit:abc1234
release:0.27.0
ci_run#789
```

Reference format rules:

- File references take a line range `#L120-L147`, a single line `#L120`, or no fragment (whole file). A range whose start equals its end is written as a single line.
- SHAs are lowercase hex, 7–40 characters. Numbers are positive integers without leading zeros.
- `content_hash` is written `sha256:<64 lowercase hex>`.

Issues, comments, and PR bodies are mutable; a citation to them MUST include `content_hash` of the revision used so it can be verified after later edits.

### 6.2 Citation verification

Performed by application code, never by trusting the LLM. A citation is `verified` only if:

1. the referenced artifact exists in the Store within the run's temporal scope;
2. the SHA or `content_hash` matches;
3. the line range exists (where applicable);
4. `excerpt` is an exact substring of the referenced content after whitespace normalization (collapse runs of whitespace, strip line ends).

> **Verification proves existence and fidelity, not support.** A verified citation proves the quoted text exists at the stated location. It does not prove the text supports the claim. Support is measured by groundedness evaluation (§22.3) and MAY later be enforced at runtime by an independent judge.

A citation with status other than `verified` MUST NOT support a fact, coverage, or finding.

### 6.3 Claims

```text
Claim
├── claim_id                  # stable within an RCA version
├── type: fact | hypothesis
├── role: root_cause | contributing_factor | symptom | context
├── statement
├── evidence[]: Citation
└── resolution: supported | unresolved | None   # hypotheses only
```

Rules:

- A **fact** MUST have ≥ 1 verified citation. A fact failing this is **downgraded to `hypothesis / unresolved`** before output — never removed silently and never kept as a fact.
- A **hypothesis** in the final RCA MUST be `supported` (≥ 1 verified citation) or `unresolved`. Unsupported hypotheses may exist during investigation but are discarded or labeled before output.
- A hypothesis MUST NOT be converted into a fact without new verified evidence.
- An RCA with `evidence_sufficiency = sufficient` MUST contain ≥ 1 `root_cause` claim that is a fact or a supported hypothesis.

### 6.4 Recommended fix

```text
RecommendedFix
├── summary
├── rationale
├── affected_components[]
└── evidence[]: Citation
```

The recommended fix is evidence-backed and describes an implementation direction. V1 does not generate code.

---

## 7. RCA result and record

### 7.1 RCAResult

```text
RCAResult
├── status: completed | budget_exhausted
├── evidence_sufficiency: sufficient | partial | insufficient
├── root_cause_summary
├── reasoning_summary
├── claims[]: Claim
├── affected_components[]
├── recommended_fix: RecommendedFix | None
├── missing_evidence[]         # REQUIRED non-empty when sufficiency != sufficient
└── unresolved_questions[]
```

`status` (did the run finish?) and `evidence_sufficiency` (how strong are the findings?) are independent. `completed` + `insufficient` is a valid, honest outcome.

`evidence_sufficiency` is proposed by the LLM and then **capped by application code**: it cannot be `sufficient` if the §6.3 root-cause rule fails, and cannot exceed `partial` if any root-cause claim has only unverified evidence.

A `failed` run produces no RCAResult; the failure is recorded on the RunManifest only.

### 7.2 RCARecord

```text
RCARecord
├── rca_id
├── version                    # monotonically increasing per rca_id
├── issue_id
├── repo_id
├── run_id → RunManifest       # source of cutoff_time / repository_sha
├── result: RCAResult
├── lifecycle_state: draft | under_review | approved | rejected | superseded
├── transitions[]: LifecycleTransition
└── created_at

LifecycleTransition
├── from_state
├── to_state
├── actor                      # human identity or "system"
├── at
└── reason
```

A persisted RCA version is immutable (content). Only `lifecycle_state` and `transitions` change, append-only. Any content change creates a new version.

`cutoff_time` and `repository_sha` live only on the RunManifest; RCARecord references it by `run_id`.

### 7.3 Lifecycle

```text
          ┌────────────── (new version) ◄──────────────┐
          ▼                                             │
        draft ──► under_review ──► approved ──► superseded
          ▲            │
          │            ├──► rejected ──► (new version) draft
          └────────────┘   (returned for revision)
```

Allowed transitions:

| From | To | Actor |
|---|---|---|
| draft | under_review | system or human |
| under_review | draft | human (returned for revision) |
| under_review | approved | human only |
| under_review | rejected | human only |
| approved | superseded | system (when a newer version is approved) |

Approval preconditions (enforced in code):

- `result.status = completed`;
- `evidence_sufficiency = sufficient`, **or** `partial` with the approval transition `reason` explicitly recording the override;
- ≥ 1 `root_cause` claim that is a fact or supported hypothesis.

At most one version per `rca_id` is `approved` at a time. Only an approved, non-superseded version may be the input to validation.

---

## 8. RCA Validation Agent

### 8.1 Responsibility

Given an approved RCA, the original issue, a proposed PR, and deterministic test evidence, determine whether the implementation adequately addresses the diagnosed root cause.

The Validation Agent does not redo the RCA. If it finds evidence contradicting an RCA claim, it records `contradicted` coverage and a finding.

### 8.2 Inputs

- original issue; approved RCA version;
- PR metadata, `base_sha`, `pr_head_sha`, diff, changed files, commits;
- relevant repository code at `pr_head_sha` and `base_sha`;
- new/modified tests and relevant existing tests;
- TestEvidence from the TestEvidenceSource.

The Validation Agent MAY inspect post-RCA information; temporal isolation does not apply to it.

### 8.3 Trace requirement

Every coverage decision traces: `Issue → RCA claim → Evidence → Code change → Test`.

### 8.4 Flow

```text
Load Approved RCA → Load PR Snapshot → Load TestEvidence
  → Map RCA Claims → Changes → Evaluate Claim Coverage
  → Inspect Scope / Risks → Verify Citations
  → Normalize (code) → Compute Verdict (code) → Persist
```

`Normalize` and `Compute Verdict` are application code, not LLM nodes.

### 8.5 Binding and staleness

Every validation is immutably bound to `(rca_id, rca_version, base_sha, pr_head_sha)`.

A validation is **current** only if, at the time it is read:

- the PR's head SHA equals `pr_head_sha`; and
- `rca_version` is still the approved, non-superseded version.

Staleness is derived at read time by the quality gate, not stored as a boolean. A stale validation MUST NOT be used by the quality gate; a new validation must run.

---

## 9. Test evidence

Repository and PR code is untrusted and MUST execute only in CI or an isolated sandbox (ADR-004). The Validation Agent consumes structured results; it never infers test success from source code or PR descriptions.

### 9.1 Patterns

- **Fail-to-pass (F2P)** — a regression test for the defect fails on `base_sha` (with the PR's test files overlaid) and passes on `pr_head_sha`.
- **Pass-to-pass (P2P)** — relevant existing tests pass on `pr_head_sha`.

### 9.2 Models

```text
TestResult
├── outcome: passed | failed | skipped | error | timeout
├── duration_ms
└── output_ref | None          # pointer to stored, untrusted output

FailToPassEvidence
├── test_id
├── base: TestResult
└── head: TestResult

PassToPassEvidence
├── test_id
└── head: TestResult

TestEvidence
├── source: ci | sandbox
├── base_sha
├── head_sha
├── environment_ref            # image digest, Python version, lockfile hash, runner config
├── fail_to_pass[]: FailToPassEvidence
├── pass_to_pass[]: PassToPassEvidence
├── ci_run_ref: Citation
└── captured_at
```

`failed` (assertion failure) and `error` (collection/setup/import failure) are distinct. Only `base = failed, head = passed` demonstrates fail-to-pass. The full classification is in ADR-003.

`TestEvidence.head_sha` MUST equal the validation's `pr_head_sha`, else the evidence is rejected.

---

## 10. Claim coverage and findings

### 10.1 ClaimCoverage

```text
ClaimCoverage
├── claim_id → RCA Claim
├── coverage: addressed | symptom_only | partial | contradicted | insufficient_evidence
├── rationale
├── evidence[]: Citation       # diff hunks, files at head/base, CI runs
└── linked_tests[]             # test_ids from TestEvidence
```

| Coverage | Meaning |
|---|---|
| addressed | Evidence shows the claim's root cause is corrected. |
| symptom_only | Visible symptom mitigated; diagnosed cause remains. |
| partial | Only part of the claim or its required scope is addressed. |
| contradicted | Implementation or test evidence conflicts with the claim or expected fix behavior. |
| insufficient_evidence | Coverage cannot be established reliably. |

Application code **normalizes** coverage before the verdict: `addressed` without ≥ 1 verified citation becomes `insufficient_evidence`; `linked_tests` referencing unknown test IDs are dropped.

### 10.2 Finding

```text
Finding
├── finding_id
├── kind: out_of_scope_change | suspicious_change | regression_risk
│         | missing_edge_case | missing_regression_test | rca_discrepancy
├── severity: blocking | advisory
├── description
└── evidence[]: Citation       # blocking findings REQUIRE ≥ 1 verified citation
```

A `blocking` finding without a verified citation is downgraded to `advisory` by normalization.

### 10.3 ValidationResult

```text
ValidationResult
├── validation_id
├── run_id → RunManifest
├── rca_id
├── rca_version
├── pr_number
├── base_sha
├── pr_head_sha
├── claim_coverage[]: ClaimCoverage
├── test_evidence: TestEvidence | None
├── findings[]: Finding
├── recommendations[]
├── verdict: VerdictDecision   # computed
└── created_at

VerdictDecision
├── overall_verdict: pass | needs_changes | insufficient_evidence
├── rule_version
└── reasons[]: { rule_id, detail, refs[] }
```

The LLM MUST NOT choose `overall_verdict`. It is derived by `compute_verdict` as specified in **ADR-003**. `reasons` records every rule that fired, for auditability.

### 10.4 Quality gate

A ValidationResult is advisory input to a deterministic quality gate that also considers CI results, security scans, coverage rules, repository policy, and human approval. An LLM never independently authorizes merge or release. The quality gate itself is outside V1 scope; V1 exposes the verdict and staleness check for it to consume.

---

## 11. Run manifest and reproducibility

### 11.1 RunManifest

```text
RunManifest
├── run_id
├── execution_key              # idempotency key, §12
├── agent_type: rca | validation
├── mode: live | replay | evaluation
├── repo_id
├── issue_id | None
├── pr_number | None
├── cutoff_time | None         # RCA: required; validation: None
├── repository_sha             # RCA: cutoff SHA; validation: pr_head_sha
├── code_version               # git SHA of this platform
├── prompt_version
├── model_provider
├── model_id
├── model_config               # temperature, max tokens, etc. (no secrets)
├── retrieval_version          # chunkers + embedding model + fusion/rerank config
├── pricing_version            # price table used to compute cost
├── environment_version        # container image digest / dependency lock hash
├── config_hash                # hash of the effective, secret-free configuration
├── budgets: Budgets           # §16.1
├── usage: Usage               # below
├── started_at
├── ended_at | None
├── outcome: running | completed | budget_exhausted | failed | aborted
└── error | None               # typed error code + message, sanitized
```

```text
Usage
├── iterations
├── tool_calls
├── llm_calls
├── tokens_in
├── tokens_out
└── cost_usd                   # computed with pricing_version
```

### 11.2 Reproducibility guarantee

A run MUST be explainable from its manifest: code, prompts, model identity and configuration, retrieval version, configuration hash, repository SHA, temporal cutoff, and execution environment.

Byte-identical LLM output is **not** guaranteed. The guarantee is *configuration and evidence reproducibility*: the system can reconstruct exactly what inputs, repository state, retrieval strategy, and model configuration produced a run.

Prompt templates are versioned files in the repository; `prompt_version` identifies the bundle.

---

## 12. Idempotency

GitHub webhooks are delivered at least once. Runs MUST be idempotent.

- `execution_key = hash(agent_type, repo_id, issue_id | pr_number, trigger_type, repository_sha | pr_head_sha, rca_version?)`.
- A unique constraint on `execution_key` among non-terminal and completed runs prevents duplicates.
- A duplicate trigger for a `running` or `completed` key returns the existing run.
- A duplicate for a `failed` key MAY start a new attempt; attempts are linked.
- Idempotency state is persisted in PostgreSQL.

---

## 13. Temporal integrity

Temporal integrity applies to all RCA runs. Full design: **ADR-002**.

### 13.1 Live RCA

Every live RCA records `cutoff_time` (investigation start) and `repository_sha` (default-branch head at that time). The RCA uses only artifacts visible at that snapshot.

### 13.2 Historical replay

Replay defines `cutoff_time` and `cutoff_sha`. The RCA Agent MUST NOT access anything created or modified after the cutoff, including:

- the fixing PR and fixing commits;
- post-cutoff code, tests, documentation, changelog entries, releases;
- post-cutoff issues, PRs, and comments;
- **post-cutoff edits** to pre-cutoff issues, comments, and PR bodies;
- post-cutoff metadata of the target issue: labels, state, `closed_by`, milestones, assignees, cross-references, linked PRs.

In replay mode, the RCA graph reads only from the ingested Store; live GitHub calls are not wired (ADR-002).

### 13.3 IssueSnapshot

The target issue is presented as it existed at the cutoff: body revision at cutoff, labels reconstructed from timeline events, state `open`, and only comments created at or before the cutoff (at their revision at cutoff). If the historical revision of any included content cannot be determined, that content is excluded; if the target issue body itself cannot be reconstructed, the replay case is ineligible.

### 13.4 Enforcement

Temporal isolation MUST be enforced by data-access code, not prompts. Every retrieval call requires a `RetrievalScope`; for RCA runs its `temporal_scope` MUST be set; the Store applies it in SQL and the application re-checks every result. Any violation raises `TemporalIsolationError`, fails the run, and is never retried.

### 13.5 Leakage tests

CI MUST include leakage tests (ADR-002 §Testing), including canary tokens planted in post-cutoff fixtures that must never reach any LLM prompt.

---

## 14. Untrusted content and security

Full design: **ADR-004**.

### 14.1 Untrusted content

All repository and GitHub content is untrusted data: issue/PR titles and bodies, comments, reviews, commit messages, source, code comments, docs, test names, test output, changelogs.

Untrusted content MUST NEVER: change system policy, tool permissions, budgets, validation rules, or evidence requirements; enable tools; or authorize actions.

Prompts MUST separate trusted instructions from untrusted content using delimited data blocks (ADR-004). Validation MUST NOT rely on a PR's self-description (title, body, commit messages) as evidence that it fixes anything.

### 14.2 GitHub permissions

V1 credentials are read-only **by construction** (fine-grained token with read-only scopes). Policy restrictions alone are insufficient.

### 14.3 Code execution

Repository and PR code MUST NOT execute in the API, LangGraph, LLM-adapter, retrieval, or ingestion processes. Static parsing (e.g., `ast.parse`, tree-sitter) is permitted; importing, executing, or unpickling repository content is not.

### 14.4 Sensitive data

Sensitive data: API keys, GitHub tokens, model credentials, database credentials, authorization headers, session tokens, secrets discovered in repository content, and any configured sensitive field.

Sensitive data MUST NEVER be hard-coded, committed, logged, stored in telemetry attributes, included in RCA/validation output, or sent to an LLM unnecessarily. Secrets detected in repository content are redacted before prompting, persistence of excerpts, and telemetry.

All other sections (configuration, logging, telemetry) reference this section rather than restating it.

---

## 15. Retrieval

### 15.1 Artifact types

Source code, tests, documentation, issues, issue comments, PRs, PR comments, commits, changelogs, release metadata.

### 15.2 Filtering

Retrieval supports filtering by repository, artifact type, path, temporal scope (mandatory for RCA), repository version, and issue/PR identifiers.

```text
RetrievalScope
├── repo_id
├── artifact_types[]
├── path_prefixes[]
└── temporal_scope: TemporalScope | None   # required for RCA runs

TemporalScope
├── repo_id
├── cutoff_time
├── cutoff_sha
├── cutoff_seq                 # first-parent ordinal of cutoff_sha (ADR-002)
├── mode: live | replay | evaluation
└── cutoff_policy: at_creation | before_first_fix_signal
```

Validation runs use a `RetrievalScope` pinned to `base_sha` / `pr_head_sha` with `temporal_scope = None`.

### 15.3 Hybrid retrieval

```text
Query ──┬── Lexical (PostgreSQL full-text) ──┐
        └── Vector (pgvector) ───────────────┴── Fusion (RRF) ── Rerank (optional) ── Evidence set
```

The temporal/scope filter is applied **before** ranking in both branches. The exact implementation evolves through experiments and is versioned by `retrieval_version`. A future ADR (006) will fix the lexical implementation.

### 15.4 Chunking

| Artifact | Strategy |
|---|---|
| Source code | function/class/module-aware (AST) |
| Tests | test-function/class-aware |
| Documentation | heading/section-aware |
| Issues | body + individual comments, each with metadata |
| PRs | metadata + discussion + per-file diff hunks |
| Commits | message + changed-file summary |

Chunking strategy is part of `retrieval_version`. Embeddings are stored once per unique content hash and shared across repository versions (ADR-002).

---

## 16. Agent control

### 16.1 Budgets

```text
Budgets
├── max_iterations
├── max_tool_calls
├── max_llm_calls
├── max_tokens
├── max_cost_usd
└── timeout_s
```

Budgets are hard limits enforced by application code before each LLM or tool call. On exhaustion, the graph routes to a finalize node that produces the best evidence-backed partial result, with `status = budget_exhausted`. A budget-exhausted RCA MUST NOT present itself as complete, and its `evidence_sufficiency` is capped at `partial`.

### 16.2 Termination

Every graph terminates on the first of: sufficient evidence; no productive path remains (no new evidence in N consecutive iterations, configurable); iteration/tool/LLM-call/token/cost budget reached; timeout; unrecoverable infrastructure error; human interruption. Unbounded loops are prohibited.

### 16.3 Structured output

All LLM outputs consumed by code are schema-validated Pydantic models. On validation failure, the node MAY perform **one** repair attempt that includes the validation error; the attempt counts against budgets. A second failure raises `StructuredOutputError`. This bounded repair is distinct from transport retries (§19).

### 16.4 Human-in-the-loop

Graphs MAY interrupt for human input (e.g., clarifying reproduction details). Interrupts are checkpointed; resumption preserves budgets consumed so far.

---

## 17. Observability

Full design: **ADR-005**.

- OpenTelemetry is the instrumentation layer; self-hosted Arize Phoenix is the initial AI-observability backend.
- Instrument: runs, graph nodes, LLM calls, embeddings, retrieval, reranking, GitHub/tool calls, citation verification, verdict computation, errors, latency, tokens, estimated cost.
- Correlation attributes: `run_id`, `agent_type`, `mode`, `repo_id`, `issue_id`, `pr_number`, `repository_sha`, `rca_id`, `rca_version`.
- Prompt and completion content is not exported from production by default (ADR-005). §14.4 applies to all telemetry.
- Telemetry failures MUST NOT fail a run.

---

## 18. Persistence

PostgreSQL is the system of record; pgvector provides vector search.

Persisted: artifact metadata and revisions; chunk contents, validity ranges, and embeddings; run manifests; RCA records and transitions; validation results; citations; test evidence; idempotency state; evaluation cases and results (separate schema, §22).

Access occurs only through Store ports. Schema changes are made through versioned migrations.

---

## 19. Configuration, errors, retries

### 19.1 Configuration

Environment-based settings via `pydantic-settings`, grouped: Application, Database, GitHub, LLM, Embeddings, Retrieval, Budgets, Telemetry/Phoenix, TestEvidence (CI/sandbox). A committed `.env.example` documents names only. `.env` is never committed. §14.4 applies.

### 19.2 Errors

Typed by responsibility, carrying diagnostic context without sensitive data:

```text
PlatformError
├── RepositoryAccessError
├── RetrievalError
├── TemporalIsolationError        # never retried; fails run
├── CitationVerificationError
├── LLMProviderError
│   └── LLMTransientError
├── StructuredOutputError
├── BudgetExceededError
├── TestEvidenceError
├── LifecycleError                # illegal transition / precondition
├── StaleValidationError
└── PersistenceError
```

Exceptions MUST NOT be silently swallowed.

### 19.3 Retries

Retry only transient failures (HTTP 429, retryable 5xx, network timeouts, temporary unavailability) with capped exponential backoff and jitter, honoring `Retry-After`. Retries happen in adapters.

Never retry: authentication/authorization failures, schema validation failures (see §16.3 for bounded repair), temporal-isolation violations, or deterministic domain errors.

---

## 20. Orchestration

RCA and Validation are separate LangGraph graphs with explicitly typed state, focused nodes, conditional routing, bounded loops, deterministic termination, and optional interrupts. The whole workflow MUST NOT live in a single agent node. Graph nodes call application services; they do not contain vendor calls directly.

Pydantic is used at external boundaries, persisted models, configuration, and structured LLM outputs. Internal graph state uses the simplest adequate typed representation (e.g., `TypedDict` or dataclass).

---

## 21. Testing strategy

| Suite | Scope | External services |
|---|---|---|
| Unit | domain rules, lifecycle, citation rules, verdict, budgets, idempotency | none (fakes) |
| Graph | routing, loops, termination, budget exhaustion, insufficient-evidence and error paths | none (fake LLM) |
| Temporal | post-cutoff code/comments/edits/labels/fix PR/releases never retrievable; canary tokens | PostgreSQL (container) |
| Security | prompt injection in issues, source comments, PR descriptions, test output; tool-permission boundaries; redaction | none |
| Validation | F2P/P2P classification, missing tests, stale head, superseded RCA, symptom-only, partial, blocking findings, verdict table | none |
| Integration | each adapter: GitHub, PostgreSQL/pgvector, LLM providers, embeddings, OTel/Phoenix, CI/sandbox | marked `integration` |
| Evaluation | benchmark harness runs; not part of default CI | marked `evaluation` |

Tests MUST NOT depend on live external services unless marked `integration` or `e2e`.

---

## 22. Evaluation

Evaluation is a separate subsystem with its own schema and package. Production code MUST NOT import evaluation code.

### 22.1 Historical evaluation case

```text
HistoricalEvaluationCase
├── case_id
├── repo_id
├── issue_id
├── cutoff_time
├── cutoff_sha
├── eligibility: eligible | ineligible
├── ineligibility_reason | None      # e.g., issue body not reconstructable
├── contamination_risk: likely_seen | likely_unseen | unknown
├── tests_available: bool            # can F2P be executed at historical SHAs
├── hidden_ground_truth              # accessible to evaluation subsystem only
│   ├── fixing_pr
│   ├── fixing_commits[]
│   ├── affected_files[]
│   ├── regression_tests[]
│   ├── known_root_cause
│   └── expected_fix
└── metadata
```

Benchmark construction may inspect future artifacts to build ground truth. Ground truth MUST NEVER be reachable from the RCA Agent's Store scope or prompts.

### 22.2 Contamination policy

Public repositories such as `encode/httpx` are likely present in model training data. Temporal isolation controls retrieval, not model memory. Therefore:

- each case is tagged `contamination_risk` relative to each evaluated model's training cutoff (issue fixed after cutoff → `likely_unseen`);
- metrics are reported separately for `likely_seen` and `likely_unseen` cases;
- a **no-retrieval baseline** is run per model; cases the model solves without evidence are flagged as probable memorization;
- the benchmark SHOULD later include at least one less-prominent or private repository.

### 22.3 Metrics

- **Retrieval:** Recall@K, Precision@K, MRR, NDCG against ground-truth affected files/artifacts.
- **RCA:** root-cause correctness, affected-component correctness, groundedness (does cited evidence support each claim), unsupported-claim rate, citation correctness, recommended-fix alignment, evidence-sufficiency calibration.
- **Validation:** claim-coverage accuracy, incomplete-fix and symptom-only detection, regression-risk and missing-test detection, false-positive and false-negative rates, evidence quality.

Retrieval and reasoning are evaluated separately so a wrong RCA can be attributed to retrieval failure vs. reasoning failure.

### 22.4 Known risk: historical test execution

F2P at historical SHAs requires reconstructing old dependency and Python environments, which may be infeasible. Such cases are marked `tests_available = false` and excluded from validation-verdict metrics rather than failing silently.

---

## 23. Reference dataset

Dataset #1 is `encode/httpx`, used for ingestion, retrieval experiments, replay cases, RCA measurement, and validation testing. No HTTPX-specific rules may enter the domain layer.

---

## 24. Delivery phases

| Phase | Deliverables | Exit criteria |
|---|---|---|
| 0 — Foundation | project layout, domain models, config, ports, fakes, test infrastructure, lint/type/import-layer checks (DB schema moved to Phase 1, milestone M14) | unit suite green; import contracts enforced |
| 1 — Repository knowledge | GitHub read adapter, ingestion with revisions + validity ranges, chunking, embeddings, lexical + vector + hybrid retrieval; **seed eval set of 20–30 hand-checked httpx replay cases**; leakage tests | leakage tests green; Recall@K baseline recorded |
| 2 — Baseline RCA | single-pass `Issue → Retrieve → LLM → RCAResult` with citation verification | baseline RCA metrics recorded on seed set |
| 3 — LangGraph RCA | planning, iterative retrieval, hypotheses, routing, sufficiency checks, budgets | measurable improvement vs. baseline on `likely_unseen` cases |
| 4 — RCA lifecycle | versioning, review, approval preconditions, rejection, supersession | lifecycle rules unit-tested |
| 5 — Validation | PR snapshot ingestion, TestEvidenceSource, claim→change mapping, coverage, findings, `compute_verdict` | verdict table tests green; stale detection tested |
| 6 — Hardening | idempotent webhooks, sandbox integration, retries/timeouts, full OTel/Phoenix, security suite, performance | security suite green; runbooks written |
| 7 — Evaluation expansion | larger benchmark; compare baseline RAG, improved RAG, LangGraph RCA, retrieval strategies, models | comparison report |

Milestone-level ordering is defined in `docs/implementation-plan.md`. Phase-2 baseline RCA *logic* is built on fakes before Phase-1 infrastructure; Phase-2 exit criteria are still measured on real data.

Do not implement later-phase features early.

---

## 25. Success criteria (V1)

The system can:

1. ingest a public GitHub repository with revision history for mutable artifacts;
2. receive an issue and build a temporally correct IssueSnapshot;
3. investigate only temporally valid evidence;
4. produce an evidence-backed RCA with verified citations;
5. explicitly report insufficient evidence when appropriate;
6. persist, version, review, and approve RCAs under enforced preconditions;
7. bind validation to an immutable RCA version and PR SHA;
8. consume deterministic test evidence and classify F2P/P2P correctly;
9. determine claim-level fix coverage;
10. compute a deterministic, explained validation verdict;
11. detect stale validations (PR head moved or RCA superseded);
12. prevent post-cutoff leakage in replay, proven by leakage and canary tests;
13. resist repository-content prompt injection, proven by the security suite;
14. trace execution through OpenTelemetry/Phoenix without leaking sensitive data;
15. reconstruct the configuration and repository state of any run;
16. evaluate retrieval, RCA, and validation independently, with contamination-split reporting.

---

## 26. Open questions

| # | Question | Owner / resolution path |
|---|---|---|
| Q1 | Should validation allow a documented `test_not_feasible` exemption for untestable root causes (races, infra)? V1: no — verdict is `insufficient_evidence`; humans decide at the quality gate. | ADR-003 revisit after Phase 5 |
| Q2 | Replay cutoff policy: at issue creation only, or up to the first fix signal to include early reproduction comments? V1 default: `at_creation`. | ADR-002 revisit after Phase 3 |
| Q3 | Lexical retrieval: PostgreSQL `tsvector` vs. a BM25 extension. | ADR-006 (Phase 1) |
| Q4 | Runtime groundedness judge for claim support. | Evaluate after Phase 3 metrics |

---

## 27. Change log

| Version | Date | Changes |
|---|---|---|
| 0.3 | 2026-09-27 | Applied implementation-plan C1–C2, S1–S7: removed `failed` from `RCAResult.status`; `max_cost_usd`/`cost_usd`; defined `Usage`, `RetrievalScope`, `TemporalScope`; facts failing verification are always downgraded; added `Clock` and `SecretRedactor` ports; DB schema moved out of Phase 0. |
| 0.2 | 2026-09-27 | Initial full specification with ADR-001…005. |
