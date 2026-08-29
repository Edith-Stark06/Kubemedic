# 13 — Test Matrix

**Command executed:** `python -m pytest -q`
**Result:** `62 passed in 0.28s` — 2026-08-29, branch `shivraj/mcp-repo-ci` @ `1448908`

Legend: `PASS` = executed and passed · `FAIL` = executed and failed ·
`MISSING` = no test exists · `UNVERIFIED` = code exists, not executed here.

---

## Agent — executed

| ID | Module | Scenario | Expected | Current | Test |
|---|---|---|---|---|---|
| A-01 | models | Allowlist enum has exactly 3 actions | closed set | PASS | `test_allowed_action_enum` |
| A-02 | models | Arbitrary action string rejected | `ValueError` | PASS | `test_action_enum_rejects_arbitrary_string` |
| A-03 | models | `kubectl ...` rejected as an action | `ValueError` | PASS | `test_action_enum_rejects_kubectl_string` |
| A-04 | models | Action without target rejected | `ValueError` | PASS | `test_action_without_target_rejected` |
| A-05 | models | Null recommendation is valid | accepted | PASS | `test_null_action_is_valid` |
| A-06 | models | Rejection without feedback refused | `ValidationError` | PASS | `test_human_decision_rejected_requires_feedback` |
| A-07 | models | Empty-string feedback refused | `ValidationError` | PASS | `test_empty_feedback_on_reject_raises_422_equivalent` |
| A-08 | models | Approval needs no feedback | accepted | PASS | `test_human_decision_approved_no_feedback_ok` |
| A-09 | models | `REJECTED -> EXECUTING` refused | `ValueError` | PASS | `test_illegal_transition_rejected_to_executing` |
| A-10 | models | `require_approval` raises when not approved | `ValueError` | PASS | `test_require_approval_raises_when_not_approved` |
| A-11 | models | `requires_human_approval` always true | `True` | PASS | `test_requires_human_approval_always_true` |
| A-12 | models | Invalid confidence value rejected | `ValidationError` | PASS | `test_invalid_confidence_rejected` |
| A-13 | models | Missing `hypotheses` defaults to `[]` | `[]` | PASS | `test_missing_hypotheses_field_defaults_empty` |
| A-14 | models | Plan built from analysis | `RemediationPlan` | PASS | `test_from_analysis` |
| A-15 | models | Plan from null action raises | `ValueError` | PASS | `test_from_analysis_null_action_raises` |
| A-16 | models | `IncidentRecord` shape | valid | PASS | `test_incident_record_from_incident` |
| A-17 | correlation | 3 related tickets to 1 incident | 3 members | PASS | `test_three_tickets_one_incident` |
| A-18 | correlation | Unrelated ticket excluded | in `excluded` | PASS | `test_unrelated_ticket_excluded` |
| A-19 | correlation | Ticket outside the 2h window excluded | in `excluded` | PASS | `test_old_ticket_excluded` |
| A-20 | correlation | Empty ticket list | empty incident | PASS | `test_empty_tickets_list` |
| A-21 | correlation | Ticket refs preserved | identity kept | PASS | `test_correlation_preserves_ticket_refs` |
| A-22 | bob | No API key returns unavailable | `bob_unavailable` | PASS | `test_analyze_no_key_returns_unavailable` |
| A-23 | reasoning | Bob down does not fabricate | `analysis_source="unavailable"` | PASS | `test_reasoning_on_bob_unavailable_does_not_fabricate` |
| A-24 | reasoning | Malformed output does not fabricate | `analysis_source="unavailable"` | PASS | `test_reasoning_on_malformed_output_does_not_fabricate` |
| A-25 | executor | Approved execution succeeds | `ExecutionResult.success` | PASS | `test_execute_approved_succeeds` |
| A-26 | executor | Unapproved execution raises | `ValueError` | PASS | `test_execute_without_approval_raises` |
| A-27 | executor | Rejected to executing unreachable | `ValueError` | PASS | `test_rejected_to_executing_is_unreachable` |
| A-28 | executor | Second execute is idempotent | same result | PASS | `test_second_execute_returns_existing_state` |
| A-29 | executor | All 3 actions dispatch | correct method | PASS | `test_all_three_actions_dispatched` |
| A-30 | executor | Unknown action raises | `ValueError` | PASS | `test_unknown_action_rejected` |
| A-31 | executor | Cluster failure captured not raised | `success=False` | PASS | `test_cluster_failure_captured_not_raised` |
| A-32 | verification | Both signals pass resolves | `RESOLVED` | PASS | `test_both_signals_pass_resolves` |
| A-33 | verification | Rollout fail does not resolve | `VERIFICATION_FAILED` | PASS | `test_rollout_fail_does_not_resolve` |
| A-34 | verification | Health fail does not resolve | `VERIFICATION_FAILED` | PASS | `test_health_fail_does_not_resolve` |
| A-35 | verification | Tool error is inconclusive | `INCONCLUSIVE` | PASS | `test_tool_error_inconclusive` |
| A-36 | verification | Verify on wrong state raises | `ValueError` | PASS | `test_verify_on_wrong_state_raises` |
| A-37 | verification | Verification written to audit log | entry present | PASS | `test_verification_written_to_audit_log` |
| A-38 | audit | Rejection feedback in audit log | present | PASS | `test_rejection_feedback_persisted_in_audit_log` |
| A-39 | audit | Rejected record carries feedback | present | PASS | `test_rejected_record_contains_feedback` |
| A-40 | audit | Rejection sets `executed=false` | `false` | PASS | `test_rejection_sets_executed_false_in_record` |
| A-41 | audit | Feedback transitions to `FEEDBACK_RECORDED` | state set | PASS | `test_valid_feedback_transitions_to_feedback_recorded` |
| A-42 | audit | Decision on wrong state raises | `ValueError` | PASS | `test_decision_on_wrong_state_raises` |
| A-43 | audit | Record file created | file exists | PASS | `test_write_record_creates_file` |
| A-44 | audit | No overwrite on duplicate | suffixed file | PASS | `test_no_overwrite_on_duplicate` |
| A-45 | pipeline | Happy path resolves | `RESOLVED` | PASS | `test_happy_path_resolves` |
| A-46 | pipeline | Bob unavailable stops pipeline | no plan | PASS | `test_bob_unavailable_stops_pipeline` |
| A-47 | pipeline | Rejection stops before execution | `execution is None` | PASS | `test_rejection_stops_before_execution` |

Remaining passing tests cover model defaults and shapes
(`test_direct_construction`, `test_evidence_snapshot_defaults`,
`test_incident_defaults`, `test_ticket_reference_minimal`,
`test_parse_success_shape`, `test_parse_all_three_actions`,
`test_evidence_unavailable_shape`, `test_bob_unavailable_shape`,
`test_is_unavailable_false_for_success`, `test_incident_state_evidence_collected`,
`test_verification_result_inconclusive`, `test_require_approval_passes_when_approved`,
`test_record_is_valid_incident_record`).

---

## Non-agent — findings from direct execution, not from a test suite

| ID | Module | Scenario | Expected | Current | Test |
|---|---|---|---|---|---|
| M-01 | `mcp_server/tickets.py` | `update_ticket(id, status='investigating')` | ticket updated | **FAIL** — `NameError: name 'Enum' is not defined` (reproduced directly) | MISSING |
| M-02 | `mcp_server/tickets.py` | create / get / list | works | UNVERIFIED — create succeeded during the probe | MISSING |
| M-03 | `mcp_server/server.py` | `import mcp_server.server` | imports | **PASS** — `python -c "import mcp_server.server"` (also creates `data/kubemedic.db` as a side effect) | MISSING |
| M-04 | `mcp_server/server.py` | `--profile evidence` limits tools to 7 | 7 read tools | **FAIL** — no argparse; flag ignored | MISSING |
| M-05 | `mcp_server/server.py` | No mutation tool under evidence profile | absent | **FAIL** — `create_ticket`, `update_ticket_status` always listed | MISSING |
| M-06 | `mcp_server/tools.py` | Tool names match `.bob/mcp.json` | match | **FAIL** — 3 mismatches | MISSING |
| M-07 | `mcp_server/watcher.py` | Anomaly to ticket | ticket created | UNVERIFIED — needs a cluster | MISSING |
| D-01 | `dashboard/app.py` | `import dashboard.app` | imports | **PASS** — `python -c "import dashboard.app"` | MISSING |
| D-02 | `dashboard/app.py` | `agent.bob.BobAgent` importable | yes | **FAIL** — does not exist; swallowed by `except ImportError` | MISSING |
| D-03 | `dashboard/app.py` | `/api/reject` accepts feedback | accepted, stored | **FAIL** — no field on the model | MISSING |
| D-04 | `dashboard/app.py` | Verification reflects the cluster | real check | **FAIL** — derived from the `approved` boolean | MISSING |
| D-05 | `dashboard/app.py` | `/api/records` reads agent records | lists them | **FAIL** — reads `agent/records`, agent writes `records/` | MISSING |
| O-01 | `orchestrator/evidence.py` | Evidence functions against a cluster | typed results | UNVERIFIED — needs a cluster | MISSING |
| E-01 | end-to-end | reject, feedback, revise, approve, execute, verify | full loop | **MISSING** — the revise stage does not exist | MISSING |
| E-02 | `scripts/validate.sh` | E2E harness runs | exit 0 | **FAIL** — hardcoded `/c/Users/shivraj/...` paths; calls a file absent from this repo | — |
| B-01 | `agent/bob.py` | Live Bob returns a valid analysis | `analysis_source="ibm-bob"` | **UNVERIFIED — never observed** | MISSING |

---

## Honest one-line summary

**The agent is well tested. Nothing else is tested at all. The single most
important behaviour in the project — IBM Bob returning a real analysis — has
never been observed.**
