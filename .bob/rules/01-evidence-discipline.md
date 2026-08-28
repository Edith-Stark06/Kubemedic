# Evidence discipline

Applies to every mode and every conversation in this repository.

1. **Cite or don't claim.** Any statement about cluster state carries its
   source: a pod name, an event reason plus timestamp, a revision number, or
   an HTTP status. A claim without a citation is an inference and must be
   labelled as one.

2. **Confidence is stated with a reason.** "High confidence" alone is noise.
   "High — corroborated by rollout history, pod readiness and events, with no
   contradicting signal" is a claim a reviewer can check.

3. **Contradicting evidence is a required field, not an optional one.** If
   there genuinely is none, write "none found in available evidence". Silently
   omitting it reads as an argument rather than an analysis.

4. **Temporal proximity is not proof of causation.** State this whenever the
   reasoning leans on ordering, and name what would distinguish coincidence
   from cause.

5. **Name the missing signal.** When evidence is insufficient, say which
   specific signal is absent and what it would have told you. Do not reason
   around a gap.

6. **Two equally supported causes are two hypotheses.** Present both, ranked,
   with the cheapest check that would separate them. Do not pick one to make
   the output tidier.

7. **No action without a stated blast radius.** Any proposed change carries
   what it affects, for how long, and how to undo it — before it is proposed,
   not after it is questioned.
