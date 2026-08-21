# Medium Route

Use after Medium is selected under `AGENTS.md`.

## Role and Context

You are the main agent.

The main agent performs planning, implementation, and verification. Do not
delegate those tasks. For a substantive deployment, the only subagents are the
persistent Explorer defined by `<Codex home>/codex_workflow/explorer_companion.md` and one fresh
`end_of_session` worker that reconciles the complete documentation framework
during automatic closure.

Use Explorer as the context gateway: request a planning brief before broad
inspection and focused follow-up briefs for peripheral, unfamiliar, external,
or newly discovered context. The main agent remains responsible for source it
edits, acceptance decisions, critical evidence, and final claims. Inspect
underlying evidence when a brief is uncertain, contradictory, decision-relevant,
or insufficient for safe implementation.

Questions and small or odd bounded tasks use the direct main-agent fast path:
do not initialize or call Explorer, do not call `end_of_session`, and omit
worker statistics. Keep process proportional; this path does not become a
deployment merely because Medium remains selected.

## Execution

- Work in bounded context, inspection, implementation, verification, and review
  stages.
- Batch independent, already-known reads, searches, metadata checks, and
  isolated validation. Keep dependent or overlapping edits sequential.
- Run checks concurrently only when they share no mutable build output,
  generated files, fixtures, databases, ports, devices, or processes.
- Keep detailed logs in artifacts and retain only the claim, result, exact
  command or method, artifact path, critical excerpt if needed, and confidence.
- Reinspect after a change, failure, contradiction, or newly discovered
  dependency—not as routine repetition.
- Preserve unrelated work, verify in proportion to risk, and never claim an
  unrun check passed.

## Plans and Durable Status

When the user asks to plan an implementation, persist and begin it unless they
request planning only. Record the goal, major milestones, overall progress,
current position, and next milestone.

For durable or multi-session work, the main agent may update
`agent_docs/project_progress.md` once to activate the bounded plan. The
automatic closure worker owns final reconciliation and replaces
`agent_docs/latest_session_work.md`; the main must not use it as scratch space.

Leave the end-of-deployment documentation reconciliation to the single
`end_of_session` worker. Do not create a separate doc-writer for that process.

For a blocker, preserve a clear continuation point and record the failed step,
evidence, suspected cause, completed state, affected criterion, and required
input. Never present partial work as complete.

## Automatic Deployment Handoff

Before the final response that completes, pauses, or blocks the deployment,
follow `<Codex home>/codex_workflow/end_of_session.md` exactly once and wait for its
fresh worker. Pass only the route, a unique deployment ID, and closure state;
the automatic handoff context fork supplies the main-agent history. Relay its
result; do not duplicate its documentation, status, Git, or statistics work. A
later substantive deployment receives a new ID and handoff, even in the same
session.
