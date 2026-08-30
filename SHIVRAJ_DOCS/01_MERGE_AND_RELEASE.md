# Merge, Protect, Freeze

Everything here is yours (Shivraj). Run top to bottom.

---

## 1. Make `main` the real trunk — do this first, tonight

`origin/main` is `95adfc6`: `LICENSE` and a one-line `README.md`. Every other
branch is ahead of it. **A judge cloning the default branch sees an empty
repository**, no matter how good the branches are.

```bash
cd ~/Desktop/Devops/Kubemedic

# Your local main still carries abe5672 -- the superseded full-archive import
# with the pre-consolidation agent/ and all of orchestrator/. Drop it; it is
# not pushed and it would undo the consolidation.
git checkout main
git reset --hard origin/main

# Ramana's consolidation becomes the trunk.
git merge --no-ff origin/ramana -m "Merge ramana: consolidated agent architecture

main held only LICENSE and a one-line README while every branch was ahead of
it. This makes the consolidated Track 2 architecture the trunk so the other
branches merge forwards rather than backwards."

python -m pytest        # expect 62 at this point -- ramana alone
git push origin main
```

> Recover the old task board first if you want it:
> `git show abe5672:SHIVRAJ_DOCS/TASK_BOARD.md > /tmp/old_board.md`
> It is superseded by `docs/16_TASK_BACKLOG.md`, so this is optional.

---

## 2. Open your PR

```bash
git checkout shivraj/mcp-repo-ci
git push -u origin shivraj/mcp-repo-ci     # already pushed; no-op if clean
```

Open `shivraj/mcp-repo-ci` → `main` at
<https://github.com/Edith-Stark06/Kubemedic/compare/main...shivraj/mcp-repo-ci>

**Title:** `MCP contract, live remediation, human review loop, API, CI`

**Body:**

```markdown
Brings the MCP, dashboard, workload and k8s layers onto the consolidated
architecture, then closes every integration gap outside the dashboard lane.

## The headline

The loop now runs against a real cluster. Before this branch the executor had
never mutated one and the verifier had never read one -- KubernetesClient and
EvidenceReader were Protocols with no implementation anywhere, satisfied only
by test fakes.

`bash scripts/validate.sh` against live k3s, ALL CHECKS PASSED:

    healthy 2/2 -> inject -> rollout stalled 2/3
      -> watcher filed 2 tickets -> re-poll filed 0 (dedup)
      -> both correlated into one incident, 0 excluded
      -> unapproved execute REFUSED, cluster unchanged
      -> rejection without a reason REFUSED
      -> rejection with a reason recorded, cluster still unchanged
      -> approve -> rollback revision 35 -> 34
      -> verified on two independent signals -> RESOLVED
      -> audit record written -> reset

## What changed

- **MCP**: three tool names aligned with the two consumers that already agreed
  on them; `--profile evidence` now actually enforced (it was passed by
  `.bob/mcp.json` and ignored -- no argparse existed); results are JSON rather
  than Python `repr`; `list_tools` returned raw dicts where the SDK expects
  `types.Tool`.
- **Tickets**: `update_ticket()` raised `NameError: name 'Enum' is not defined`
  on every scalar field, breaking `update_ticket_status` outright.
- **`orchestrator/` retired** -- `mcp_server` no longer depends on Track 1.
- **`agent/k8s_client.py`**: live rollback/restart/scale, RFC 1123 name
  validation, replica ceiling, no shell anywhere. The reader is a separate
  class so the verifier holds nothing that can change what it verifies.
- **`agent/adapters.py`**: joins the two type systems. Guards the quiet failure
  where a dropped `named_workload` or `created_at` silently excludes a ticket
  from its own incident.
- **Review loop**: rejection feedback reaches Bob's prompt and produces a
  revised plan, capped at 3 revisions. It was stored and never read before.
- **`agent/api.py`**: 8 routes. Rejection without a reason is
  `400 feedback_required`.
- **Watcher**: one ticket per anomaly signal, so many-to-one correlation has
  real input rather than the dashboard's fabricated three.
- **Repo**: dependencies declared, CI added, README written, `validate.sh`
  runs anywhere (it hardcoded a path to a venv on my machine).

## Tests

    python -m pytest  ->  206 passed   (was 62, all agent-only)

New suites: tickets 12, MCP contract 18, k8s client 29, adapters 25, review
loop 19, watcher 13, API 28.

## Not in this PR

`dashboard/` is untouched -- Verona's lane. It still fabricates verification
results and is the reason `docs/20_KNOWN_GAPS.md` ranks `DASH-001` as P0.

IBM Bob has still never returned a live analysis; no credentials are
configured. Every run above shows `analysis_source: "unavailable"`, and the
harness says so rather than substituting a fabricated one.
```

Then merge it. With hours left, do not let a PR sit waiting for a review that
is not coming.

```bash
git checkout main
git merge --no-ff shivraj/mcp-repo-ci
python -m pytest        # expect 206
git push origin main
```

---

## 3. Branch protection — only after the merges

Enable it *after* `main` has the code. Enabling it first blocks the merge that
fixes the trunk.

GitHub → Settings → Branches → Add rule for `main`:

- Require a pull request before merging (1 approval)
- Require status checks: `test (3.13)`, `hygiene`
- Do not allow force pushes or deletions

> With one day left this is a submission artifact more than a working process —
> it shows a judge the repository is run properly. Do not let it block a merge
> you need. You can enable it after the final merge and before the tag.

---

## 4. Secret sweep — full history, not just the tree

```bash
# Working tree
git grep -nEi '(api[_-]?key|secret|token|password)[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9_-]{16,}' -- ':!*.md' ':!docs/*'

# Every blob ever committed. The working tree being clean says nothing about
# history, and history is what gets published.
git log --all --full-history -p -- .env .env.local '*.pem' '*.key' kubeconfig | head -50

# Nothing that should be ignored is tracked
git ls-files | grep -E '(\.venv/|__pycache__/|\.pyc$|\.db$|^\.env$)'
```

All three should return nothing. `AGENTS.md` extends this to the exported Bob
report — check it for keys and absolute local paths before committing it.

---

## 5. Fresh-clone test

This is judging criterion "completeness and feasibility", measured directly.
Do it in a directory you have never worked in.

```bash
cd /tmp && rm -rf clonetest && git clone https://github.com/Edith-Stark06/Kubemedic.git clonetest
cd clonetest
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest                                    # expect 206 passed
python -c "import mcp_server.server, agent.api"     # expect no output
```

If any of that fails, fix it before anything else. A judge who cannot run the
repository will not score what is inside it.

---

## 6. Freeze

```bash
git checkout main
git pull
python -m pytest                       # paste output into the checklist
bash scripts/validate.sh               # paste output into the checklist

git tag -a v1.0-submission -m "IBM TechXchange 2026 Dev Day Hackathon submission

KubeMedic: evidence-driven Kubernetes incident response with a human in the
loop. IBM Bob correlates symptoms into one incident and reasons about cause;
MCP supplies evidence and can never change the cluster; remediation is
allowlisted, human-approved and independently verified.

206 tests pass. scripts/validate.sh passes every check against a live cluster.
Known limitations are documented in README.md and docs/20_KNOWN_GAPS.md rather
than hidden."

git push origin v1.0-submission
```

After the tag, **stop committing.** The rules state an entry may not be
enhanced once committed. Further commits create ambiguity about what was
actually submitted.
