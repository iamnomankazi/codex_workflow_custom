# End-of-Session Handoff

Use this automatic closure once after every substantive Medium or Heavy
deployment, immediately before the main agent's final response. It also applies
when a deployment pauses or blocks. Questions and small or odd bounded tasks on
the direct fast path do not use this handoff and produce no worker statistics.

Spawn one fresh worker with:

- `agent_type="end_of_session"`
- `task_name="end_of_session_<deployment_id>"`, where the suffix is a unique,
  lowercase, underscore-safe deployment identifier
- `fork_turns="200"`

Reconcile the live `<project>/agent_docs/` framework only. The repository's
`codex_workflow/project_docs/` files and an installed
`<Codex home>/codex_workflow/templates/project_docs/` copy are bootstrap-marked
templates and must never receive session-specific content; if no live project
surface exists, report that limitation.

Pass only the active route, deployment ID, and closure state (`complete`,
`paused`, or `blocked`). Do not summarize the session, build a task capsule, or
maintain a usage ledger. The automatic finite fork passes recent main-agent
turns so the worker inherits the deployment context while retaining its Luna
xhigh model; its TOML contains the full procedure.

The worker alone reconciles the complete `agent_docs/` framework, performs
compact closing checks, inspects and reports Git state read-only without
changing it, and returns the final handoff report and statistics table. Git
staging, committing, pushing, resetting, stashing, or any equivalent mutation is
forbidden; an unwritable `.git` directory is not a handoff failure. Do not call a second documentation worker or duplicate these steps. Wait for the
worker, then relay its result. Create a fresh uniquely named worker for every
later substantive deployment in the same session.

If the worker cannot be created or is blocked, report that limitation. Do not
silently transfer the handoff to Explorer or another role.
