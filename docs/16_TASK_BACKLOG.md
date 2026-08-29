# 16 — Task Backlog

> **Status 2026-08-30.** Everything outside the dashboard lane is complete:
> 206 tests pass and `bash scripts/validate.sh` passes every check against a
> live cluster. Two things remain, and neither is code I can finish alone:
> **BOB-001** needs credentials, and **DASH-001/002/003** are Verona's.
> The five **SUB-\*** deliverables are still unwritten and are what the entry
> is actually judged on.

Priorities: `P0` submission blocker · `P1` integration blocker ·
`P2` quality/reliability · `P3` polish.

> **Triage, given the deadline of 2026-08-30 10:00 ET.** If the full plan does
> not fit, the minimum credible submission is: **BOB-001** (a real Bob
> analysis), **DASH-001** (stop fabricating verification), and the five
> **SUB-\*** deliverables. Everything else is negotiable. A working repo with
> honest limitations scores better than a polished repo whose audit records
> assert checks that never ran.

---

## P0 — submission blockers

- [ ] **BOB-001** — Obtain IBM Bob credentials; observe one real analysis
  - *Reason:* the theme is "Build with purpose using IBM Bob 2.0". `analysis_source: "ibm-bob"` has never been produced. Judging criteria and the watsonx clause both bear on this.
  - *Owner:* Ramana · *Depends:* — · *Est:* 30 min (unbounded if the endpoint is wrong)
  - *Files:* `.env` (never committed)
  - *Done:* one record in `records/` with `analysis_source: "ibm-bob"` and a non-empty `root_cause`
  - *Test:* manual, evidenced by the record file
  - *Commit:* `docs: first live IBM Bob analysis record`

- [ ] **DASH-001** — Dashboard renders real incidents; delete every mock
  - *Reason:* `_decide()` writes audit records whose six verification checks report the value of the `approved` boolean. That is a false claim of success and contradicts `AGENTS.md` rule 3. It is also the only thing a judge will click.
  - *Owner:* Verona · *Depends:* API-001 · *Est:* 3 h
  - *Files:* `dashboard/app.py`, `dashboard/templates/index.html`
  - *Done:* `git grep -n '"passed": approved'` empty; no literal ticket/evidence data in `app.py`; `/api/status` reads the cluster
  - *Test:* `TestClient` tests; one manual run against a live incident
  - *Commit:* `refactor(dashboard): render real incidents from the agent API`

- [x] **API-001** — FastAPI layer over the agent stages
  - *Reason:* nothing can drive `agent/pipeline.py` from a UI. `run_full_pipeline()` takes the human decision up front, so it cannot pause at the gate.
  - *Owner:* Ramana · *Depends:* MCP-008 · *Est:* 2.5 h
  - *Files:* new `agent/api.py`
  - *Done:* endpoints in `11_API_CONTRACTS.md` exist; incident state survives between requests
  - *Test:* `TestClient` per endpoint
  - *Commit:* `feat(api): HTTP surface over the incident lifecycle`

- [ ] **SUB-001** — Written problem and solution statements *(Ramana, 45 min)*
- [ ] **SUB-002** — Written statement on how IBM Bob was utilised *(Ramana, 45 min)*
- [ ] **SUB-003** — Exported IBM Bob report of all relevant tasks/sessions *(Shivraj, 30 min)*
- [ ] **SUB-004** — Demo video including how IBM Bob was used, in English *(Verona, 2 h)*
- [ ] **SUB-005** — Full-history secret sweep, then tag `v1.0-submission` *(Shivraj, 30 min)*

`SUB-001` through `SUB-004` are the four deliverables named in ENTRY
REQUIREMENTS. Missing any one risks the entry.

---

## P1 — integration blockers

- [x] **MCP-005** — Import `Enum` in `mcp_server/tickets.py`
  - *Reason:* `update_ticket()` raises `NameError: name 'Enum' is not defined` on every scalar field. Reproduced directly. Breaks `update_ticket_status` entirely.
  - *Owner:* Shivraj · *Est:* 5 min · *Files:* `mcp_server/tickets.py`
  - *Done:* `update_ticket(id, status='investigating')` returns a `Ticket`
  - *Test:* new unit test · *Commit:* `fix(tickets): import Enum`

- [x] **MCP-001** — Rename 3 MCP tools to the names both consumers expect
  - *Reason:* `.bob/mcp.json` and `agent/verification.py:EvidenceReader` independently agree on `get_workload_status` / `get_application_health` / `get_workload_snapshot`. The server is the outlier, so the server changes.
  - *Owner:* Shivraj · *Est:* 20 min · *Commit:* `fix(mcp): align tool names`

- [x] **MCP-002** — Implement `--profile evidence` *(handoff #1, BLOCKING)*
  - *Reason:* `.bob/mcp.json` passes the flag; `server.py` has no argparse and ignores it. `create_ticket` and `update_ticket_status` are exposed on a profile documented as read-only.
  - *Owner:* Shivraj · *Depends:* MCP-001 · *Est:* 45 min
  - *Done:* 7 read tools listed under the profile; mutation calls refused
  - *Test:* two new tests · *Commit:* `feat(mcp): enforce the read-only evidence profile`

- [x] **MCP-003** — Move `evidence.py` into `mcp_server/`; delete `orchestrator/`
  - *Owner:* Shivraj · *Est:* 20 min · *Done:* `git grep "from orchestrator"` empty
  - *Commit:* `refactor: retire orchestrator/`

- [x] **MCP-008** — Adapter: MCP evidence + SQLite tickets to agent contracts
  - *Reason:* two incompatible `EvidenceSnapshot` types and no `Ticket` to `TicketReference` mapping. **This is the main integration gap.**
  - *Risk:* dropping `named_workload` or `created_at` silently breaks correlation — a ticket then scores at most 1 of 3 signals and is excluded from its own incident.
  - *Owner:* Shivraj + Ramana · *Est:* 1.5 h · *Files:* new `agent/adapters.py`
  - *Commit:* `feat(agent): adapt MCP evidence and tickets to agent contracts`

- [x] **REVIEW-001** — `/incidents/{id}/review` with `400 feedback_required`
  - *Owner:* Ramana · *Depends:* API-001 · *Est:* 45 min
  - *Commit:* `feat(api): human review gate; rejection requires a reason`

- [x] **REVIEW-002** — Human feedback becomes reasoning context; revised plan
  - *Reason:* feedback is stored and never read. `PROMPT_TEMPLATE` has no slot for it. The reject-revise-review loop is the differentiating feature and does not exist.
  - *Owner:* Ramana · *Depends:* REVIEW-001 · *Est:* 2 h
  - *Done:* rejecting with a reason produces a different plan; feedback visible in the revised analysis's audit entry; a revision cap prevents spinning
  - *Safety:* do not weaken `_ILLEGAL_TRANSITIONS`
  - *Commit:* `feat(agent): human feedback becomes reasoning context`

- [x] **EXEC-001** — Real `KubernetesClient`
  - *Reason:* no concrete implementation exists. The executor has never mutated a cluster.
  - *Owner:* Ramana · *Est:* 1.5 h · *Files:* new `agent/k8s_client.py`
  - *Safety:* typed `AppsV1Api` calls only. No shell, no `kubectl` subprocess.

- [x] **VER-001** — Real `EvidenceReader`
  - *Decision:* map `ready` to `WorkloadState.rollout_complete`, not `healthy`.
  - *Owner:* Ramana · *Est:* 45 min

- [x] **TICKET-001** — Watcher emits one ticket per anomaly signal
  - *Reason:* today one real failure produces exactly one ticket. Correlating one ticket into one incident demonstrates nothing, which is why the dashboard fabricates three.
  - *Owner:* Shivraj · *Est:* 1 h

- [ ] **DASH-002** — Reject dialog requiring a reason *(Verona, 1 h)*

---

## P2 — quality and reliability

- [x] **REPO-001** — Untrack `data/kubemedic.db`; ignore `data/*.db`, `records/*.json` *(Shivraj, 10 min)*
  - *Reason:* the runtime database is committed. It was picked up because the branch's `.gitignore` (from `ramana`) lacks the `data/` rules the archive's had.
- [x] **REPO-002** — Root `requirements.txt` and `requirements-dev.txt` *(Shivraj, 15 min)*
  - *Reason:* `agent/` declares no dependencies at all; pydantic and pytest are undeclared.
- [x] **REPO-003** — README with real setup steps *(Shivraj, 45 min)* — currently one line
- [x] **REPO-004** — Fix `scripts/validate.sh` absolute paths *(Shivraj, 30 min)*
  - *Reason:* hardcodes `/c/Users/shivraj/Desktop/Devops/opspilot/...` and calls `orchestrator/validate_incident.py`, absent from this repo. `AGENTS.md` forbids committing absolute local paths.
- [x] **CI-001** — GitHub Actions: install, compile, pytest, import checks *(Shivraj, 45 min)*
- [ ] **CI-002** — Branch protection on `main`, **after** `ramana` merges *(Shivraj, 15 min)*
- [x] **MCP-006** — `json.dumps` tool results instead of `str()` *(Shivraj, 10 min)*
- [x] **MCP-007** — Tool errors surface as errors, not as successful text *(Shivraj, 20 min)*
- [x] **MCP-004** — Add `get_recent_changes` to the `alwaysAllow` list *(Shivraj, 5 min)*
  - *Reason:* rollout history is the most diagnostic signal for a bad-deploy incident, and Bob is not allowed to read it without asking.
- [x] **TEST-001** — Ticket store unit tests on a temp database *(Shivraj, 45 min)*
- [x] **TEST-002** — MCP profile tests *(Shivraj, 30 min)* — folded into MCP-002
- [ ] **TEST-003** — `_extract_json` parsing tests *(Ramana, 30 min)*
- [ ] **TICKET-002** — Incident state propagates to member tickets *(Shivraj, 45 min)*
- [x] **E2E-001** — Rewrite `scripts/validate.sh` as a real harness *(Shivraj, 1.5 h)*
- [ ] **DASH-003** — Remove Gemini strings from user-visible surfaces *(Verona, 15 min)*
  - `dashboard/app.py:202,299,389`, `templates/index.html:263,834`. Note `.bob/skills/gemini-audit/` and `.bob/agents/gemini-auditor.md` are the *auditor* and should stay.
- [ ] **DOC-001** — Update `docs/consolidation-inventory.md` *(Shivraj, 10 min)*
  - It states no dashboard template contains a Gemini reference. That was true when written, before the dashboard was on this branch. It is now inaccurate.

---

## P3 — polish

- [ ] **NAME-001** — Choose OpsPilot or KubeMedic; apply everywhere *(30 min)*
- [ ] **NAME-002** — Reconcile namespace `kubemedic` (`.env.example`) vs `opspilot` (manifests, evidence defaults, scripts) *(15 min)*
- [ ] **MODEL-001** — Wire or delete the dead `EVIDENCE_FAILED` and `VERIFIED` states *(20 min)*
- [ ] **MODEL-002** — Map `TicketStatus` to `IncidentState`, or document why they differ *(20 min)*
- [ ] **MODEL-003** — Incident id generation is a module global; not thread-safe, resets per process *(20 min)*
- [ ] **ADR-007** — Decide who owns correlation: Python, Bob, or both *(see `21_DECISIONS.md`)*
- [ ] **CLEAN-001** — Remove the unused `subprocess`/`shutil` imports in `agent/bob.py` *(5 min)*

---

## Ownership summary

| Owner | P0 | P1 | P2 | P3 |
|---|---|---|---|---|
| Ramana | BOB-001, API-001, SUB-001, SUB-002 | REVIEW-001, REVIEW-002, EXEC-001, VER-001 | TEST-003 | MODEL-* |
| Verona | DASH-001, SUB-004 | DASH-002 | DASH-003 | NAME-001 |
| Shivraj | SUB-003, SUB-005 | MCP-001/002/003/005/008, TICKET-001 | REPO-*, CI-*, TEST-001/002, E2E-001, DOC-001 | NAME-002 |
