# Code Repository

The [README](../README.md) is the authoritative description. This is a map of
where the judged material is.

| Question | Where |
|---|---|
| Where does IBM Bob run? | `agent/providers/ibm_bob.py`, `agent/providers/bob_workspace/.bob/custom_modes.yaml` |
| What does Bob receive? | `agent/providers/prompt.py` |
| What is Bob's output held to? | `agent/models.py` (`BobAnalysis.from_raw`), `agent/reasoning.py`, `agent/pipeline.py` |
| What can change the cluster? | `agent/executor.py`, `agent/k8s_client.py` — three allowlisted actions, after a recorded human approval |
| What can Bob's tools see? | `.bob/mcp.json`, `mcp_server/server.py` — read-only evidence profile, asserted in CI |
| How is recovery verified? | `agent/verification.py` — rollout health and application health, re-read |
| Who may act, and who is recorded? | `agent/auth.py` |
| What is durable and tamper-evident? | `agent/store.py` |
| How is it deployed? | `Dockerfile`, `deploy/kubemedic.yaml` |
| How was Bob configured for development? | `.bob/`, `AGENTS.md` |
| Tests | `tests/` — run `python -m pytest`; no cluster or credentials needed |
| Executed evidence | `submission/evidence/` |

Statements about what Bob did, and what it did not, are in
[`HOW_WE_USED_IBM_BOB.md`](HOW_WE_USED_IBM_BOB.md) and
[`bob-report/README.md`](bob-report/README.md).
