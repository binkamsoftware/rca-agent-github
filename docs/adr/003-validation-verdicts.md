# ADR-003: Deterministic Validation Verdicts

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-27 |
| Rule version | `verdict-v1` |
| Spec sections | §8, §9, §10 |

## Context

The Validation Agent's output feeds a merge-quality gate. If an LLM picks the final verdict, that verdict is non-reproducible, open to prompt injection from PR content, and hard to audit. The LLM is good at judging *whether a change addresses a claim*. It should not decide *what that judgment implies for merge readiness*, and it should not decide *whether tests passed*.

## Decision

The final verdict is computed by a pure function in `domain/verdict.py`:

```python
def compute_verdict(
    rca: RCAResult,                     # the approved RCA version
    coverage: Sequence[ClaimCoverage],  # normalized
    test_evidence: TestEvidence | None,
    findings: Sequence[Finding],        # normalized
) -> VerdictDecision: ...
```

It performs no I/O, reads no clock, and calls no LLM. Every rule that fires is recorded in `VerdictDecision.reasons`. The rule set is versioned (`rule_version = "verdict-v1"`), and any change to the rules requires a new version and an update to this ADR.

### 1. Required claims

```text
required_claims = claims where role = root_cause
                  and (type = fact or resolution = supported)
```

Unresolved hypotheses and non-root-cause claims are **not required**. Coverage gaps on them surface as advisory findings only. An approved RCA always has ≥ 1 required claim (spec §7.3). If `required_claims` is empty anyway, the verdict is `insufficient_evidence` (rule `R0`).

### 2. Normalization (before rules)

| Input | Normalized to |
|---|---|
| `addressed` with no verified citation | `insufficient_evidence` |
| `blocking` finding with no verified citation | `advisory` |
| `linked_tests` entry not present in TestEvidence | dropped |
| duplicate coverage entries for one `claim_id` | worst coverage wins (order below) |
| `TestEvidence.head_sha ≠ pr_head_sha` or `base_sha` mismatch | TestEvidence treated as absent + reason recorded |

Coverage severity order (worst first): `contradicted` > `symptom_only` > `partial` > `insufficient_evidence` > `addressed`.

### 3. Test classification

**Fail-to-pass** (base = `base_sha` with the PR's test files overlaid; head = `pr_head_sha`):

| base \ head | passed | failed | error / timeout / skipped |
|---|---|---|---|
| **failed** | `DEMONSTRATED` | `NOT_FIXED` | `INCONCLUSIVE` |
| **passed** | `NOT_REPRODUCING` | `NOT_REPRODUCING` | `NOT_REPRODUCING` |
| **error / timeout / skipped** | `INCONCLUSIVE` | `INCONCLUSIVE` | `INCONCLUSIVE` |

- `NOT_FIXED`: the defect is reproduced and is still present after the change.
- `NOT_REPRODUCING`: the regression test does not capture the defect, so it cannot prove anything.
- `base = error` is common when a new test imports a symbol introduced by the PR. It is `INCONCLUSIVE`, not proof.

**Pass-to-pass:** head `passed` → `OK`; `failed` → `BROKEN`; `error / timeout / skipped` → `INCONCLUSIVE`.

### 4. Rules (first match wins; all matching rules are still recorded as reasons)

| ID | Condition | Verdict |
|---|---|---|
| R0 | no required claims | insufficient_evidence |
| R1 | any `blocking` finding | needs_changes |
| R2 | any required claim coverage ∈ {contradicted, symptom_only} | needs_changes |
| R3 | any F2P test linked to a required claim is `NOT_FIXED` | needs_changes |
| R4 | any P2P test is `BROKEN` | needs_changes |
| R5 | any F2P test linked to a required claim is `NOT_REPRODUCING` | needs_changes |
| R6 | any required claim coverage = partial | needs_changes |
| R7 | any required claim has no coverage entry | insufficient_evidence |
| R8 | any required claim coverage = insufficient_evidence | insufficient_evidence |
| R9 | TestEvidence absent (or rejected in normalization) | insufficient_evidence |
| R10 | any required claim has no linked F2P test that is `DEMONSTRATED` | insufficient_evidence |
| R11 | any linked F2P or any P2P is `INCONCLUSIVE` | insufficient_evidence |
| R12 | otherwise | **pass** |

Precedence rationale:

- **`needs_changes` before `insufficient_evidence`.** Concrete evidence of a problem is actionable even when other evidence is missing.
- **R5 (`NOT_REPRODUCING`) is `needs_changes`.** A regression test that passes on the unfixed code is a defect in the PR's tests, and the developer can fix it.
- **R10 requires a demonstrated F2P test for every required claim.** Coverage asserted by the LLM alone is never enough for `pass`.
- **`pass` is only reachable when every positive condition holds.** It is never the fall-through of missing data.

### 5. Staleness (separate from the verdict)

The verdict does not encode staleness. `is_current(validation, current_pr_head_sha, current_approved_rca_version) -> bool` is a separate pure function. The quality gate MUST call it at read time. A stale validation is never used, whatever its verdict.

### 6. What the LLM supplies vs. what code supplies

| LLM | Code |
|---|---|
| per-claim coverage + rationale + citations | citation verification |
| findings + severity proposal | normalization (downgrades) |
| `linked_tests` mapping | F2P / P2P classification |
| recommendations | rule evaluation, verdict, reasons |

## Testing

`tests/unit/domain/test_verdict.py` MUST be **table-driven**, with at least one case per rule, plus:

- precedence cases (e.g., R1 and R9 both true → `needs_changes`, with both reasons recorded);
- every cell of the F2P classification table;
- normalization cases (unverified `addressed`, unverified `blocking`, SHA-mismatched evidence);
- property test: adding a `blocking` finding never changes a verdict *to* `pass`; removing evidence never changes a verdict *to* `pass`.

## Consequences

**Positive**
- Reproducible, auditable verdicts; `reasons` explain every outcome.
- Prompt injection in a PR cannot produce `pass` without real test evidence.
- Rules can be changed deliberately and versioned.

**Negative**
- Root causes that are hard to test (races, environment-specific, infrastructure) will usually get `insufficient_evidence` under R10. This is intentional in V1: a human decides at the quality gate. See spec Q1.
- F2P on base needs test-file overlay tooling in the sandbox (ADR-004).

## Alternatives considered

- **LLM chooses the verdict.** Rejected: non-deterministic, injectable, unauditable.
- **Weighted score with threshold.** Rejected for V1: harder to explain, and it invites threshold tuning that hides failures.
- **`test_not_feasible` exemption.** Deferred (spec Q1); it would need a human-approved justification recorded on the RCA to avoid becoming a loophole.
