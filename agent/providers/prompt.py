"""
The reasoning prompt. One copy, shared by every provider.

A provider that writes its own prompt is a provider that drifts from
.bob/skills/incident-correlation/references/evidence-schema.md, and the drift
shows up as a validation failure at the worst moment. The allowlist is stated
literally here because it is also enforced in BobAnalysis.from_raw -- the model
is told the constraint it will be held to.
"""
from __future__ import annotations

import json
from typing import Any

PROMPT_TEMPLATE = """\
Analyze this Kubernetes incident using the incident-correlation skill.

The evidence below was collected by the KubeMedic evidence MCP server. Treat it
as the complete set of observed facts. Do not assume anything not present here.

<evidence>
{evidence}
</evidence>

<open_tickets>
{tickets}
</open_tickets>
{feedback_block}
Allowlisted actions: rollback_deployment, restart_deployment, scale_workload.
No other action exists. If none fits, recommend null and say what a human
should do instead.

Return exactly one JSON object with exactly these field names. A hosted model
cannot open a file in this repository, so the shape is stated here rather than
referenced -- naming a schema path it cannot read is how a model ends up
inventing its own field names.

{{
  "hypotheses": [
    {{
      "rank": 1,
      "statement": "what you think happened",
      "confidence": "high" | "medium" | "low",
      "confidence_reason": "why that confidence",
      "supporting_evidence": ["facts from the evidence above"],
      "contradicting_evidence": ["facts that argue against, or 'none found'"]
    }}
  ],
  "root_cause": {{
    "statement": "the underlying cause",
    "confidence": "high" | "medium" | "low",
    "is_inference": true
  }},
  "dual_signal_note": "optional: where two signals disagree and why",
  "recommended_action": "rollback_deployment" | "restart_deployment" | "scale_workload" | null,
  "action_target": "the deployment name",
  "action_parameters": {{"to_revision": 11}},
  "reason": "why this action",
  "requires_human_approval": true
}}

recommended_action MUST be one of those three strings or null -- never an
object. action_target is required whenever recommended_action is not null.
No prose, no markdown fences, no extra top-level fields.
"""

FEEDBACK_BLOCK = """
A human reviewer rejected your previous remediation plan for this incident and
gave the reasons below, oldest first. This is operator knowledge you do not
have from the evidence alone -- treat it as authoritative context, not as a
suggestion to restate.

<human_feedback>
{feedback}
</human_feedback>

Produce a revised plan that answers these objections. If they mean no
allowlisted action is appropriate, recommend null and say what the human should
do instead. Do not repeat the rejected recommendation unchanged.
"""

SYSTEM_PROMPT = """\
You are the KubeMedic incident analyst. You reason over Kubernetes evidence
collected by a read-only MCP server. You never claim a fact the evidence does
not contain, you label inference as inference, and you recommend only from the
stated allowlist. You return one JSON object and nothing else.
"""


def build_prompt(
    evidence: dict[str, Any],
    tickets: list[dict[str, Any]],
    feedback: list[str] | None = None,
) -> str:
    """
    Assemble the reasoning prompt.

    When a reviewer has rejected a previous plan, their reasons go in verbatim.
    That is the whole point of requiring a reason on rejection: it is operator
    knowledge the evidence does not contain, and it is worthless if it is
    stored and never read back.
    """
    feedback_block = ""
    if feedback:
        numbered = "\n".join(
            f"{i}. {reason}" for i, reason in enumerate(feedback, start=1)
        )
        feedback_block = FEEDBACK_BLOCK.format(feedback=numbered)

    return PROMPT_TEMPLATE.format(
        evidence=json.dumps(evidence, indent=2, default=str),
        tickets=json.dumps(tickets, indent=2, default=str),
        feedback_block=feedback_block,
    )
