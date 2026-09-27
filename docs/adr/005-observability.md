# ADR-005: Observability

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-27 |
| Spec sections | §11, §14.4, §17 |

## Context

Agent runs are multi-step and non-deterministic. Debugging an RCA means seeing which queries ran, what was retrieved, which citations failed, and how budgets were spent. At the same time, prompts contain untrusted repository content and potentially sensitive data. The spec requires OpenTelemetry for vendor neutrality and self-hosted Arize Phoenix for AI observability.

## Decision

### 1. Stack

- **Instrumentation:** OpenTelemetry SDK (traces, metrics) behind the `TelemetryProvider` port. Application code never imports OTel directly.
- **LLM span semantics:** OpenInference semantic conventions (native to Phoenix), set by the telemetry adapter. Only the adapter changes if we move to OTel GenAI conventions later.
- **Export:** OTLP to self-hosted Phoenix. An OpenTelemetry Collector MAY be inserted later (for tail sampling, extra redaction, or a second backend) without code changes.
- **Logs:** structured JSON logging with `trace_id` and `span_id` injected into every record.
- **System of record:** PostgreSQL remains authoritative for runs, RCAs, and validations. Phoenix is diagnostic and may be wiped without data loss.

### 2. Span hierarchy

```text
agent.run (rca | validation)                 run_id, mode, repo_id, issue_id|pr_number, repository_sha
├── graph.node.<name>                        iteration
│   ├── llm.call                             model_provider, model_id, prompt_version, tokens_in/out, cost
│   ├── retrieval.search                     retrieval_version, k, scope.cutoff_seq, result_count, latency
│   │   ├── retrieval.lexical
│   │   ├── retrieval.vector
│   │   └── retrieval.rerank
│   ├── tool.<name>                          tool args (validated, non-sensitive subset)
│   └── embedding.call
├── citations.verify                         total, verified, failed
├── verdict.compute                          rule_version, verdict, fired_rules
└── persist
```

### 3. Required correlation attributes

On the root span, propagated to children as resource or span attributes where relevant: `run_id`, `agent_type`, `mode`, `repo_id`, `issue_id`, `pr_number`, `repository_sha`, `rca_id`, `rca_version`, `code_version`, `prompt_version`, `retrieval_version`.

### 4. Content policy

| Mode | Prompt / completion content in spans |
|---|---|
| `evaluation`, `replay`, local dev | allowed, after secret redaction, size-capped |
| `live` (production) | **off by default**; spans carry content hashes, sizes, and references to persisted artifacts |

Controlled by configuration (`TELEMETRY_CAPTURE_CONTENT`), default `false`. Regardless of mode, telemetry MUST NOT contain credentials, tokens, authorization headers, or detected secrets (spec §14.4). Attributes pass through a `SafeAttributes` allowlist builder. Arbitrary dicts cannot be attached.

### 5. Metrics

| Metric | Type | Notes |
|---|---|---|
| `rca.run.duration`, `validation.run.duration` | histogram | by outcome |
| `llm.tokens`, `llm.cost` | counter | by model, node |
| `retrieval.latency` | histogram | by branch |
| `citations.verification.failed` | counter | by reason |
| `temporal.isolation.violations` | counter | **alert on > 0** |
| `budget.exhausted` | counter | by budget type |
| `validation.verdict` | counter | by verdict, fired rule |
| `structured_output.repair` | counter | repair attempts and failures |

### 6. Sampling and reliability

- Agent runs are low-volume and high-value: sample 100% of runs.
- Exporters are asynchronous and batched. Export failures are logged and counted, never raised. A telemetry outage MUST NOT fail or slow a run beyond a bounded flush timeout.

### 7. Evaluation linkage

Evaluation results MAY be pushed to Phoenix as annotations keyed by `run_id` for visual inspection. The evaluation schema in PostgreSQL remains authoritative.

## Testing

- Unit: an in-memory span exporter asserts the span tree shape and required attributes for a fake RCA run and a fake validation run.
- Security: with planted secrets and `TELEMETRY_CAPTURE_CONTENT=false`, no span attribute or log line contains prompt content or secrets. With `true`, secrets are still redacted.
- Resilience: an exporter that raises does not fail the run.
- Integration (marked): traces arrive in a Phoenix container.

## Consequences

**Positive**
- Full trace of every run with consistent correlation IDs.
- Backend-neutral: Phoenix can be replaced or supplemented by changing the adapter or adding a Collector.
- Production prompt privacy by default.

**Negative**
- Production debugging without content capture needs a join from span references to persisted artifacts.
- OpenInference and OTel GenAI conventions may diverge; the adapter absorbs this.

## Alternatives considered

- **Phoenix/OpenInference auto-instrumentation only.** Useful in dev, but not relied on: it bypasses the `SafeAttributes` policy and couples application code to instrumentor behavior. It MAY be enabled in non-production modes.
- **Capture full content everywhere.** Rejected: untrusted content and sensitive data would end up in a diagnostic system with weaker controls.
