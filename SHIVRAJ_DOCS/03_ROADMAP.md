# Roadmap

Remaining engineering work, in dependency order. Single owner — the per-person
allocation is gone with the hackathon.

Two horizons. **Part 1 is today, before 19:30 IST.** Part 2 is the
provider/vault architecture we discussed — a real workstream, and deliberately
*not* a today workstream.

---

# Part 1 — before the deadline (~4 hours)

## P0 · Still required

- [ ] **Run the IBM Bob incident session.** `08_BOB_RUNBOOK.md` session 1.
  **Needs no credentials** — the desktop app is already signed in and Bob
  launches our MCP server from the workspace. ~45 min. It closes the two
  remaining integration gaps at once: the MCP protocol path (never driven by
  any client) and a real Bob analysis (never produced).
  Then `scripts/ingest_bob_analysis.py --approve` turns Bob's JSON into an
  audit record reading `analysis_source: "ibm-bob"`.

- [ ] **Record the video.** `06_DEMO_SCRIPT.md`. Version A is viable — the
  dashboard is wired and verified. Must be English and must state how Bob was
  used.

- [ ] **Confirm the portal, the deadline, and whether the repo must be public.**

- [ ] **Tag `v1.0-submission` and submit.** Target 18:00 IST, not 19:25.

## P1 · If session 1 succeeds

- [ ] Copy the record into `submission/evidence/`
- [ ] `submission/HOW_WE_USED_IBM_BOB.md` section 4 → switch to Variant A
- [ ] `submission/README.md` → the "What we are not claiming" section is
      written for Bob *not* having run; it needs rewriting
- [ ] `submission/bob-report/README.md` → add the session

## Do not do today

Provider abstraction, vault, health/usage endpoints. Everything in Part 2.
None of it produces evidence a judge can see, and all of it risks the working
tree with hours left.

---

# Part 2 — after the deadline

## The architecture, in one picture

```
                    ┌─────────────────────────────┐
                    │  agent/pipeline.py + api.py │   the coordinator
                    │  correlate → reason → plan  │   (not MCP)
                    │  → review → execute → verify│
                    └───────────┬─────────────────┘
                                │
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                  ▼
      ┌───────────────┐  ┌─────────────┐  ┌────────────────┐
      │  MCP server   │  │  Reasoning  │  │  K8s client    │
      │  READ-ONLY    │  │  provider   │  │  3 allowlisted │
      │  8 tools      │  │  registry   │  │  actions       │
      └───────────────┘  └──────┬──────┘  └────────────────┘
                                │
                ┌───────────────┼───────────────┬─────────────┐
                ▼               ▼               ▼             ▼
            ibm-bob         watsonx         anthropic       manual
```

**The rule that must not bend:** MCP stays passive. It answers questions; it
never plans, never mutates, never holds state. The safety claim — *Bob has no
tool that can change the cluster* — is true only because mutation lives in
`agent/executor.py` behind the approval gate and is never registered as an MCP
tool. If MCP ever coordinates, that property is gone.

---

## PROV-001 · Reasoning provider abstraction · ~2h

`agent/reasoning.py:12` is the only production import of `agent/bob.py` — one
import, one call site. That is why this is small.

```
agent/providers/
├── __init__.py      registry, get_provider(), config errors
├── base.py          ReasoningProvider protocol + ProviderResult
├── prompt.py        build_prompt / FEEDBACK_BLOCK   (extracted from bob.py)
├── parsing.py       _extract_json / _last_object    (extracted from bob.py)
├── ibm_bob.py       IBM Bob RemoteAgent REST        (moved)
├── watsonx.py       IBM watsonx.ai                  NEW
├── anthropic.py     Claude Messages API             NEW
└── manual.py        interactive session / file ingest
```

```python
class ReasoningProvider(Protocol):
    id: str                  # "ibm-bob" | "watsonx" | "anthropic" | "manual"
    display_name: str
    def is_configured(self) -> tuple[bool, str]: ...
    def analyze(self, evidence, tickets, feedback=None) -> ProviderResult: ...
```

**The failure policy lives in the base class, not per provider.** Every failure
mode — no credentials, 401, timeout, unparseable output, schema violation —
must converge on `analysis_source: "unavailable"` with no plan built. That is
the single most valuable property in the system, and re-implementing it four
times guarantees provider #3 gets it subtly wrong.

**Blocker:** `agent/models.py:100` is
`analysis_source: Literal["ibm-bob", "unavailable"]`. It has to widen to a
provider-id union, and it is a frozen contract field — so
`.bob/skills/incident-correlation/references/evidence-schema.md` changes in the
same commit.

**Keep 238 tests green:** ~25 tests monkeypatch the string
`"agent.reasoning.bob_analyze"`. Keep a module-level `bob_analyze` in
`reasoning.py` that resolves through the registry, and none of them need
touching.

## PROV-002 · Config surface · ~30 min

DB-config shape — one switch, per-provider namespaces:

```bash
KUBEMEDIC_REASONING_PROVIDER=ibm-bob

KUBEMEDIC_BOB_API_KEY= / _AGENT_ID= / _API_BASE= / _MODE=
KUBEMEDIC_WATSONX_API_KEY= / _PROJECT_ID= / _URL= / _MODEL_ID=
KUBEMEDIC_ANTHROPIC_API_KEY= / _MODEL=
```

Unknown provider name → hard exit, same as the MCP `--profile` guard. Silently
falling back to a default because someone typo'd is the failure that guard
exists to prevent.

## PROV-003 · watsonx provider · ~1.5h

Two calls. **Verify both against IBM's current docs — do not trust this from
memory:**

1. IAM token exchange — `POST https://iam.cloud.ibm.com/identity/token`,
   `grant_type=urn:ibm:params:oauth:grant-type:apikey`. Bearer token, ~1h
   lifetime, cache it with its expiry.
2. Inference — `POST {url}/ml/v1/text/chat?version=2023-05-29` with
   `model_id`, `project_id`, `messages`.

Granite models wrap JSON in prose or fences. `parsing.py` already handles that
— which is exactly why extracting it comes before adding a provider.

## SEC-001 · Secret provider seam · ~1h

The seam matters more than the backend:

```python
class SecretProvider(Protocol):
    def get(self, name: str) -> str | None: ...
    def describe(self) -> str: ...   # "env" | "k8s:kubemedic-secrets" — never values
```

`KUBEMEDIC_SECRETS_BACKEND=env|dotenv|file|k8s|vault`

| Backend | Use |
|---|---|
| `env` | default, dev |
| `file` | `/run/secrets/*` — Docker/K8s mounted |
| `k8s` | read a `Secret` through the client we already have |
| `vault` | HashiCorp / IBM Cloud Secrets Manager |

Two rules regardless of backend: **never log a value**, and **redact in every
health output** — a health endpoint that echoes config is the classic leak.

**Proportionality:** hygiene is already clean — nothing in git history, `.env`
ignored, CI checks for committed credentials. This is an upgrade, not a fix.
Ship `env` + `k8s`; leave `vault` as a documented adapter until something runs
in a cluster that needs it.

## HEALTH-001 · Provider health and usage · ~1h

Three distinct things, deliberately not conflated:

| Check | Cost | Where |
|---|---|---|
| **Configured?** required vars present | free | startup, `/api/provider` |
| **Reachable?** auth works, endpoint answers | network + token exchange | cached with TTL, on demand |
| **Usage** calls, failures by reason, latency, tokens | free counters | `/api/provider` |

Rules:

- **`/api/health` stays cheap.** It is liveness. Do not make it call watsonx, or
  the dashboard goes red because a model API is slow.
- **A provider health check must never block incident creation.** If the
  provider hangs, the incident still collects evidence and reports
  `BOB_UNAVAILABLE`. That is today's behaviour; keep it.
- **Budget guard**, in the spirit of `MAX_REVISIONS`: max provider calls per
  incident. An agent loop retrying a failing provider burns money fast.

`duration_ms` per call already lands in the audit log — usage extends that
rather than inventing a second path.

## MCP-010 · Read-only incident tools · ~1h

So Bob can see the state it reasons about: `list_incidents`, `get_incident`,
`get_plan`. All on the evidence profile, all reads.

**`approve_plan` and `execute_plan` must never exist.** That is the line.

## ADR-007 · Decide who owns correlation · ~30 min

Still open. `agent/correlation.py` correlates deterministically *and* Bob is
asked to correlate; the two results are never reconciled. Matters because the
headline claim is "Bob understood that three symptoms were one problem".
Options in `docs/21_DECISIONS.md`.

---

## Credentials — what each provider actually needs

**Email and password will not suffice for any of them.** A console login is how
you *create* a credential; it is not the credential. A server process cannot
log in as a human.

| Provider | Needs | Note |
|---|---|---|
| **IBM Bob — interactive** | **nothing** | app already signed in; this is today's path |
| **IBM Bob — REST** | API key + agent id + base URL | endpoint still unverified |
| **watsonx** | IAM API key + project id + region URL + model id | needs a project with watsonx.ai runtime |
| **Claude** | `sk-ant-...` from console.anthropic.com | **not a Claude Code / Claude.ai login** — different product, separate billing |

## One recommendation on scope

I would ship `ibm-bob` (default), `watsonx` and `manual`, and keep `anthropic`
on a branch or behind a clearly-labelled dev section.

There is a `gemini-audit` skill in this repo whose whole purpose is proving no
Google SDK is present, and `docs/19_HACKATHON_COMPLIANCE.md` leans on it. A
`providers/gemini.py` would reverse that story for no gain, and a reader
scanning the tree for "is this really an IBM Bob project" sees filenames before
framing.

---

## Suggested order

```
SEC-001  →  PROV-001  →  PROV-002  →  PROV-003  →  HEALTH-001  →  MCP-010
  1h          2h           30m          1.5h          1h            1h
```

Secrets first, so no provider is ever written against raw `os.getenv`.
About 7 hours, comfortably two sessions.
