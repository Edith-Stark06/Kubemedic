---
name: verification-review
description: >-
  Independently assesses whether a remediation actually restored service, using
  at least two signals re-read from the cluster after the action. Activates on
  verifying recovery, confirming a fix worked, checking whether an incident is
  resolved, or reviewing a verification result.
user-invocable: true
---

# Independent verification

The single most common failure in automated remediation is declaring victory
because the mutation call returned success. That is evidence the API accepted
the request. It is not evidence the service recovered.

## The rule

Verification **re-reads the cluster after the action**, through the same
read-only evidence tools, with no reference to what the action returned. If
the only thing you can say is "the rollback succeeded", you have not verified
anything.

## Required signals

Both of these must pass. Not one.

1. **Kubernetes rollout healthy** — rollout complete, required replicas Ready,
   and no pod running the suspect image.
2. **Application health** — `/health` returns 200 on a fresh request made
   after the rollout settled.

Where the evidence supports it, also check that the specific symptom in the
originating tickets is gone. A ticket said checkout was throwing 500s; ideally
you can say checkout now answers.

## Handling asynchrony

Kubernetes is eventually consistent and terminating pods linger in listings.

- Poll for the desired state with a timeout. Do not read once.
- Treat a terminating pod as neither pass nor fail — wait for it to go.
- If the timeout expires with the state still unsettled, that is `FAIL` with
  reason `timeout`, not `PASS`. Ambiguity is not success.

## Reporting the result

Three outcomes only:

- **PASS** — both signals green, re-read after the action. The incident may be
  marked RESOLVED.
- **FAIL** — either signal red, or the timeout expired. The incident is **not**
  resolved. Name which signal failed and what you observed. Do not
  automatically retry the same remediation.
- **INCONCLUSIVE** — a verification tool itself errored. Say the verification
  could not be performed. This is not a pass.

Never soften a FAIL into a partial pass. A verification that can never fail is
not a verification, and a reviewer will test exactly this.

## The failure case is a feature, not an embarrassment

If a remediation goes through and verification fails, that is the system
working correctly — it caught a bad fix. Report it plainly, keep the incident
open, and record it in the audit trail. Demonstrating a caught failure is more
persuasive than three clean passes.
