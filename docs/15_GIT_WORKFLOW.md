# 15 — Git Workflow

## Actual state (observed 2026-08-29)

Remote: `https://github.com/Edith-Stark06/Kubemedic.git`

| Branch | Head | Contents |
|---|---|---|
| `main` | `95adfc6` | `LICENSE` + a one-line `README.md`. **Effectively empty** |
| `ramana` | `5e1743f` | The consolidated `agent/` + `tests/` + `.bob/` + `AGENTS.md`. 6 commits |
| `verona` | `aaf2741` | Not audited |
| `shivraj/mcp-repo-ci` | `1448908` | `ramana` + `mcp_server/`, `dashboard/`, `k8s/`, `workload/`, `scripts/` |

There is also an unpushed local commit on `main` (`abe5672`) importing the full
OpsPilot archive. It is **superseded** by `shivraj/mcp-repo-ci` and should be
dropped, not pushed — it reintroduces the pre-consolidation `agent/` and all of
`orchestrator/`.

### Branch naming is inconsistent

`ramana` and `verona` are flat; `shivraj/mcp-repo-ci` uses `owner/topic`.
Git cannot hold both `ramana` and `ramana/anything` — a ref cannot be a file
and a directory. **Decide now, before more branches exist.** Recommendation:
adopt the flat form (`shivraj`), because renaming one branch with no PR
against it is cheaper than renaming two.

### `main` is not the trunk

Every other branch is ahead of `main`, and `main` has no code. The real trunk
today is `ramana`. This must be fixed before any PR flow makes sense —
otherwise "merge to main" means merging into an empty repository.

---

## Target structure

```
main  (protected, always green, always demoable)
  |
  +-- ramana    orchestration, agent, Bob, API
  +-- verona    dashboard, workload, demo assets
  +-- shivraj   MCP, CI, repository hygiene
```

---

## Merge order

```
1. ramana -> main            establish the real trunk
2. shivraj -> main           MCP fixes, hygiene, CI
3. verona -> main            dashboard against the real API
4. integration testing on main
5. freeze, tag v1.0-submission
```

Step 1 is a prerequisite for everything. Until it lands, nobody can branch
from a `main` that contains the architecture.

> **Given the deadline, do not open PRs that sit waiting.** With under a day
> left, the review requirement below is aspirational. The realistic protocol
> is: small commits, push often to your own branch, merge to `main` as soon as
> tests are green, and tell the team in chat. A blocked PR at 3am costs more
> than an unreviewed merge.

---

## Branch naming

`<owner>` for the three long-lived branches. For anything short-lived off
those: `<owner>/<type>-<slug>`, e.g. `shivraj/fix-ticket-enum`.

## Commit conventions

`<type>(<scope>): <imperative summary>`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`.
Scopes: `agent`, `mcp`, `dashboard`, `bob`, `tickets`, `api`, `k8s`, `repo`.

The body should say **why**, and name the task id from `16_TASK_BACKLOG.md`.
A commit that changes a safety property must change its test in the same
commit.

Example, matching the existing history style:

```
fix(mcp): align tool names with .bob/mcp.json and EvidenceReader

server.py registered get_workload_state, get_app_health and
get_full_snapshot. Both consumers -- .bob/mcp.json alwaysAllow and
agent/verification.py:EvidenceReader -- expect get_workload_status,
get_application_health and get_workload_snapshot. Two independent
consumers agree, so the server was the outlier.

MCP-001. Refs docs/handoffs.md.
```

## PR requirements (target)

- Green CI.
- One approval.
- Description names the task id and states what was tested, with the command.
- No `git add .` — stage the files you meant to change.

## Branch protection (target)

On `main`: require a PR, require CI, require one approval, no direct push, no
force push. **Set this only after `ramana` has merged to `main`** — enabling
it first would block the merge that fixes the trunk.

## Rollback

- Bad commit on a branch: `git revert <sha>`. Do not rewrite pushed history —
  three people are working from these branches.
- Bad merge to `main`: `git revert -m 1 <merge-sha>`.
- Broken demo during the recording window: check out the last tag
  (`v1.0-submission` once it exists) and re-record.
- Working tree confusion: `git stash`, verify `git status` is clean, then
  reapply.

## Secret hygiene

`.gitignore` covers `.env`, `.env.*` (with `!.env.example`), `*.pem`, `*.key`,
`kubeconfig`, `.kube/`. Before the freeze run a full-history sweep, not just a
working-tree grep — see `SUB-005`. `AGENTS.md` extends this to the exported
Bob report: check it for credentials and absolute local paths before
committing it.

**Currently violated:** `data/kubemedic.db` is tracked, and
`scripts/validate.sh` contains `/c/Users/shivraj/...` absolute paths. Both are
in `16_TASK_BACKLOG.md`.
