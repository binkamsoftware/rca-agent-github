# ADR-001: Ports and Adapters

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-27 |
| Spec sections | §4, §19, §20 |

## Context

The platform depends on several external systems that will change over time: LLM providers, embedding models, GitHub, PostgreSQL/pgvector, CI/sandbox runners, and telemetry backends. The spec requires model independence, testability with fakes, and no vendor types in domain models.

LangGraph and `langchain-core` are already project dependencies. `langchain-core` offers its own model abstraction, but adopting it as *our* domain interface would couple domain and application code to LangChain's message and tool types.

## Decision

Use a hexagonal (ports and adapters) architecture with four layers and one-way dependencies.

```text
src/rca_platform/
├── domain/        # pure models + rules. No I/O, no frameworks except Pydantic.
├── ports/         # typing.Protocol interfaces. Depend only on domain.
├── application/   # use-case services + LangGraph graphs. Depend on domain + ports.
├── adapters/      # vendor implementations of ports. Depend on ports + domain + vendor SDKs.
├── api/           # FastAPI entrypoints (webhooks, review actions). Thin.
├── config/        # pydantic-settings.
├── bootstrap.py   # composition root: builds adapters, injects into services.
└── evaluation/    # separate subsystem; production code never imports it.
```

### Dependency rules

| Layer | May import | Must not import |
|---|---|---|
| domain | stdlib, pydantic | everything else in the project; any vendor SDK |
| ports | domain | application, adapters, vendor SDKs |
| application | domain, ports, langgraph | adapters, vendor SDKs (incl. langchain chat models, httpx clients, SQLAlchemy) |
| adapters | domain, ports, vendor SDKs | application, api |
| api | application, domain, config | adapters (except via bootstrap) |
| bootstrap | everything | — |
| any production module | — | evaluation |

These rules are enforced in CI with `import-linter` contracts, not by convention.

LangGraph is permitted in `application/graphs/` because it is the orchestration framework, not an external service. Graph nodes call application services and ports; they never call vendor SDKs directly.

`langchain-core` chat-model classes MAY be used **inside** `adapters/llm/` as an implementation convenience. Their types never cross the port boundary.

### Core ports

Signatures are indicative; the code is authoritative once written.

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self, request: LLMRequest, schema: type[T]
    ) -> LLMResponse[T]: ...
    # LLMRequest: system instructions, trusted/untrusted content blocks (ADR-004),
    #             model_ref, params. LLMResponse: parsed output, usage, model_id.

class EmbeddingProvider(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[Embedding]: ...
    @property
    def model_ref(self) -> ModelRef: ...

class RepoSource(Protocol):
    # Read-only access to repository artifacts. Live mode: GitHub adapter.
    # Replay mode: Store-backed adapter (ADR-002).
    async def get_issue_snapshot(self, issue: IssueRef, scope: TemporalScope) -> IssueSnapshot: ...
    async def get_file(self, path: str, sha: GitSha) -> FileContent: ...
    async def get_pull_request(self, pr: PullRequestRef) -> PullRequestSnapshot: ...

class Retriever(Protocol):
    async def search(self, query: RetrievalQuery, scope: RetrievalScope) -> list[RetrievedChunk]: ...
    # scope is REQUIRED; there is no unscoped search method.

class TestEvidenceSource(Protocol):
    async def get_evidence(self, pr: PullRequestRef, base_sha: GitSha, head_sha: GitSha) -> TestEvidence | None: ...

class TelemetryProvider(Protocol):
    def span(self, name: str, kind: SpanKind, attributes: SafeAttributes) -> ContextManager[Span]: ...

class Clock(Protocol):
    # Injected time source; keeps domain rules and budgets deterministic in tests.
    def now(self) -> datetime: ...

class SecretRedactor(Protocol):
    # Infrastructure sanitation (ADR-004 Addendum B). Applied by application services at boundaries.
    def redact(self, text: str) -> RedactionResult: ...
```

`Store` is a **family of narrow repository protocols**, not one god-interface:

```text
ArtifactRepository      # artifacts, revisions, chunks, validity ranges
RunRepository           # RunManifest, usage
RCARepository           # RCARecord, transitions (enforces append-only)
ValidationRepository    # ValidationResult, TestEvidence
IdempotencyRepository   # execution keys
UnitOfWork              # transaction boundary across repositories
```

### Dependency injection

- Services receive ports through constructors. No service instantiates infrastructure, reads environment variables, or uses module-level singletons.
- `bootstrap.py` is the only place that reads settings and constructs adapters.
- Model selection is configuration: `ModelRef(provider, model_id, params)` per graph role (e.g., `planner`, `analyst`, `validator`), resolved by an `LLMProvider` router adapter.

### Provider differences

Adapters absorb provider differences (native JSON-schema output vs. tool calling vs. JSON mode, token accounting, error mapping). Every adapter maps vendor errors onto the typed hierarchy in spec §19.2 and performs transport retries internally (spec §19.3). Structured-output repair (spec §16.3) is implemented once in the application layer, not per adapter.

### Fakes

Every port has an in-memory fake in `tests/fakes/`, used by unit and graph tests. A shared **contract test suite** per port runs against both the fake and the real adapter (the latter marked `integration`) so fakes cannot drift from reality.

## Consequences

**Positive**
- Providers and backends can be swapped by configuration.
- Domain rules (citations, lifecycle, verdict) are unit-testable with zero I/O.
- The temporal-scope requirement is visible in the `Retriever` signature and impossible to omit.

**Negative**
- More types and mapping code than calling SDKs directly.
- LangChain ecosystem conveniences (tool decorators, prebuilt agents) are unavailable to application code.
- Contract tests must be maintained per port.

## Alternatives considered

- **Use `langchain-core` `BaseChatModel` as the LLM port.** Rejected: leaks LangChain message/tool types into application code and ties upgrades to LangChain's release cadence.
- **Single `Store` interface.** Rejected: becomes a god-object; narrow repositories make fakes and transaction boundaries clearer.
- **Convention-only layering.** Rejected: erodes silently; `import-linter` makes violations fail CI.
