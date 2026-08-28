# Build discipline

## Never fake a success

- If the Bob call fails, the result is `analysis_source: "unavailable"` and the
  dashboard shows "IBM Bob unavailable". Never synthesize an analysis locally
  and present it as Bob's. That is both a correctness bug and a contest
  compliance problem.
- If evidence collection fails, the incident stops at
  `EVIDENCE_COLLECTION_FAILED`. Never diagnose from gaps.
- If verification fails, the incident does not reach RESOLVED. There is no
  partial pass.

## The executor takes an enum, not a string

```python
# Never, under any circumstance:
subprocess.run(model_output)          # no
kubectl(f"kubectl {model_suggestion}") # no

# Always:
action = AllowedAction(analysis.recommended_action)  # raises on anything else
target = validate_target(analysis.action_target)     # raises if not in allowlist
require_approval(incident)                           # raises unless APPROVED
perform(action, target)                              # named k8s API call
```

There is no force flag, no override parameter, no `skip_approval=True`. If you
find yourself adding one to make a test easier, write the test differently.

## Typed boundaries

Pydantic models between every stage: `Incident`, `EvidenceSnapshot`,
`CorrelationResult`, `BobAnalysis`, `RemediationPlan`, `HumanDecision`,
`ExecutionResult`, `VerificationResult`, `IncidentRecord`. Bare dicts crossing
a stage boundary are a bug.

Validate rejection feedback server-side. A required-field check that lives only
in JavaScript is not a check.

## Idempotency

An already-executed remediation does not execute again on a second request.
Return the existing state. Repeated approval does not trigger repeated
execution.

## Report real test output

Run the tests and paste what they printed. Never describe a test as passing
that you did not execute in this session. If something fails, say what failed.

## Small changes

One subsystem per commit, tests run after each. Do not remove working
functionality without a replacement landing in the same change.
