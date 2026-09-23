# Heavy Route

Use after Heavy is selected under `AGENTS.md`.

<!-- codex-workflow-effective-config-start -->
## Effective Workflow Configuration

- Default executor: `executor_luna` (`max` reasoning effort).
- Enabled workers: `executor_luna`, `executor_pro`, `reviewer_pro`, `executor_sol`, `tester`, `doc-writer`, `explorer`, `end_of_session`.
- Maximum concurrent child workers: `20`.
- Maximum `executor_sol` workers: `1`.
- Maximum worker final-report package: `250` words.

Create only enabled workers and obey these limits.
<!-- codex-workflow-effective-config-end -->

## Heavy launch boundary

For ChatGPT/Codexless Heavy launches, the caller selects the parent before the
turn starts. Plain Heavy explicitly uses `gpt-6-sol` with `high` effort;
never rely on a catalog default. GPT-6 Astra is opt-in only at exactly the
user-requested supported effort. A parent cannot change its own already-running
model. Immediately after start, the caller verifies requested versus resolved
model and effort; any mismatch stops before worker spawning. Worker role TOMLs
remain the separate authority for child models.

## Role-aware spawning (mandatory)

Every initial `spawn_agent` call must pass both the installed `agent_type` and a stable `task_name`; a task name alone is invalid role binding.
Required shape: `spawn_agent(agent_type="<role>", task_name="<stable identity>", ...)`.
Use exact bindings: Explorer `agent_type="explorer"`; routine Luna `agent_type="executor_luna"`; Tester `agent_type="tester"`; serious Pro `agent_type="executor_pro"`; closure `agent_type="end_of_session"`.
Follow-ups use `followup_task` on the same canonical worker and never respawn; task identity does not select a role.
Do not pass `model` or `reasoning_effort` for normal Heavy workers; the installed role TOML remains the model/provider authority.

## Main Agent: Knowledge Plane

You are the main agent.

The main agent is the knowledge architect, decision maker, and guidance-rich
allocator. It owns task direction, architecture, scope, acceptance, package
boundaries, cross-package decisions, integration gates, official status, and
user communication.

Workers own operational context: Explorer gathers and refines discovery;
executors own package-local investigation, implementation, self-check, and
repair; testers own test evidence and failure diagnosis; doc-writers own
assigned durable documentation. The End-of-Session worker owns final Git-state
inspection/reporting and complete documentation-framework reconciliation during
automatic deployment closure.

The main agent's default tool use should be coordination, planning/status,
compact commands, and critical source or evidence inspection. Delegate routine
discovery, implementation, diagnostics, full logs, large diffs, external
research, and deployment diagnostics to the role that owns that context. The
main agent opens critical evidence only for a material decision, uncertainty,
contradiction, missing proof, or high-risk boundary.

Questions and small or odd bounded tasks use a direct main-agent fast path: do
not spawn, message, or otherwise call subagents and do not create work merely
to use a worker. This fast path also skips End-of-Session and worker statistics.

When the active Heavy parent is GPT-6 Astra, read and follow `<Codex home>/codex_workflow/astra_orchestration.md` as an additional route policy.
## Planning and Context Gateway

Initialize Explorer as required by `<Codex home>/codex_workflow/explorer_companion.md`. Before allocating
packages, give it the investigation questions and request a planning brief.
Use that brief to form the architecture, acceptance matrix, dependency order,
ownership map, and package guidance; do not repeat Explorer's raw discovery.

After a coherent group of worker completions, request a knowledge-delta brief
when contracts, assumptions, risks, or cross-package understanding may have
changed. Give Explorer compact worker outcomes and artifact references, not raw
logs. If no decision is required and evidence is coherent, absorb the brief
without reopening its sources.

When the user asks to plan an implementation, persist and begin it unless they
request planning only. For durable work, the main agent may update
`agent_docs/project_progress.md` once for plan activation. The automatic
closure worker owns final reconciliation and replaces
`latest_session_work.md`; no other worker may edit either file.

## Packages and Knowledge Distribution

Delegate coherent, independently completable packages large enough for one
executor to perform local discovery, implementation, self-check, and routine
repair. Run packages concurrently only when outcomes and mutable ownership are
independent. Keep one child slot available for End-of-Session.

Every initial task-worker uses `fork_turns="none"`. A capsule is the worker's
local slice of the main agent's global understanding and must contain:

- Task ID and iteration; required outcome.
- Ownership, expected edit surface, and protected areas.
- Relevant upstream decisions, exact references, interfaces, dependencies, and
  authorized contract changes.
- Recommended approach and why it fits the architecture.
- The most important invariant and likely integration pitfall.
- Acceptance criteria, required verification, and regression boundary.
- Escalation conditions, repair counterpart when applicable, and expected
  return format.

Keep capsules concise through exact references and omission of irrelevant
history. Never remove recommendation, rationale, invariants, or pitfalls merely
to meet an arbitrary length when doing so risks clarification or repair work.
Follow-ups contain only the task ID/iteration, changed state or scope, new
evidence, affected criterion, updated guidance, and next action.

Only when the assigned worker is `executor_luna`, make the capsule compact but
execution-complete by adding an **Execution Guide** with:

1. Starting state, relevant current behavior, and prerequisites.
2. An ordered implementation sequence. Name the exact file or symbol, required
   change, rationale, and affected interface or invariant. Group related edits
   into coherent stages; for each stage, state the smallest focused check that
   materially de-risks the next stage. Do not prescribe a full gate after each
   small edit.
3. Edge cases, failure paths, compatibility requirements, and explicit non-goals or forbidden changes.
4. A validation ladder from focused checks through package tests to the
   required integration gate, plus the build/output-cache strategy for expensive
   or stateful toolchains. Prefer the project's reusable cache; when isolation is
   required, assign one deterministic package-level path shared by executor and
   tester. Finish with a concrete completion checklist.
5. Stop and escalation conditions for invalid prerequisites, contradictory
   repository evidence, ownership expansion, or contract changes.

Do not add this Execution Guide requirement to packets for `executor_terra`,
`executor_sol`, or any non-Luna role. Use exact references instead of embedding
source, logs, or repeated project history; resolve known choices in the guide so
Luna does not rediscover settled decisions.

Adapt the knowledge supplied by role:

| Role | Required guidance |
| --- | --- |
| Explorer | Questions, boundaries, authoritative sources, evidence format |
| `executor_luna` | Approach, rationale, invariants, interfaces, pitfalls, and the ordered Execution Guide above |
| Any other selected default executor | Approach, rationale, invariants, interfaces, pitfalls; no Luna Execution Guide requirement |
| `executor_pro` | Difficult-package evidence, constraints, invariants, authorized repair scope, acceptance criteria; no Luna Execution Guide requirement |
| `reviewer_pro` | Review questions, claims and evidence, contracts or invariants, risk areas, read-only boundaries |
| `executor_sol` | Decision context, constraints, invariants, unresolved problem; do not prescribe the solution |
| Tester | Acceptance matrix, risks, public contracts, regression boundaries, independence requirements |
| Doc-writer | Verified facts, changed behavior, audience, terminology, limitations |
| Executor handling deployment | Release manifest, health criteria, smoke cases, rollback and escalation conditions |

Use the selected default executor for production work. Reserve `executor_sol`
for substantial mathematical or logical reasoning or exceptionally difficult
cross-cutting work. Pro roles are not defaults, first-line repair, or automatic
review stages. The parent explicitly assigns them, including bounded serious
`executor_pro` escalation after Luna exhausts routine repair. Start the tester
after executor self-check unless separate test research is independent. Delegate documentation
only after the relevant behavior is verified. Do not create a separate
doc-writer for the automatic end-of-deployment framework reconciliation; the
End-of-Session worker owns it.

## Verification, Repair, and Build Economy

Verification proves assigned behavior without multiplying equivalent builds or repair turns. Parent includes the build/output strategy in executor/tester capsules for expensive or stateful toolchains.
- Reuse the project's normal build cache when safe. If isolation is required, Parent assigns exactly one deterministic package-level path shared by every executor/tester turn. For Cargo use normal `target` by default or one assigned `CARGO_TARGET_DIR`; never create numbered/per-attempt targets merely for fresh verification. Commands sharing mutable build output run sequentially.
- Cold/clean rebuilds require concrete cache-corruption/staleness evidence or an explicit clean-build acceptance gate. Use focused checks during implementation/repair; run broad build, lint, typecheck, or full-suite gates at coherent integration points and rerun only when later edits could invalidate their evidence.
- For any workflow-only isolated build path, Parent assigns cleanup ownership in the capsule; default to Tester when executor and tester share it. The cleanup owner removes it only after the final required verification/repair consumer when clearly safe. Never delete the project's normal build cache as workflow cleanup; if temporary output must remain, report its exact path and purpose for closure.
- Tester completes one verification pass before routine repair when practical and consolidates all material same-scope failures into one packet. Material means an assigned acceptance failure, existing public-contract/established-invariant violation, security/data-integrity issue, or regression directly touched by the change. Adjacent robustness, exhaustive-enumeration, style, or nice-to-have findings below that threshold are residual observations, not automatic production scope.

Pair each verification package with its responsible executor and both canonical task names. Tester sends one consolidated `followup_task` packet containing every material same-scope failure from the pass, minimal reproductions, observed/expected behavior, affected contracts, focused evidence, and scope/risk. The executor repairs the packet, self-checks affected surfaces, and signals the waiting tester with `send_message`; Tester reruns packet criteria and directly affected regressions. Parent is not the routine relay.
For Luna, the repair budget is package-level: repair round #1 and, if material assigned failures remain or a newly exposed material same-scope failure appears, one consolidated repair round #2 on the same Luna worker. Never split known failures to gain rounds or send a third routine production-repair round for that package/iteration. Original implementation, self-check, tester-owned corrections, wrong-test reruns, evidence-only contact, `send_message`, waiting, early escalation, and parent-created materially re-scoped work do not consume the budget.
Before either Luna round, return capsule/invariant conflict, cross-package contract or architecture change, expanded ownership, security risk, or migration risk to Parent. After round #2, any remaining material assigned failure returns as one serious packet with remaining criteria, evidence, affected contracts, and both repair outcomes; Tester never creates Pro.
For manually selected Terra, Tester sends one consolidated same-Terra `followup_task`; Terra repairs, self-checks, directly signals Tester, and gets one recheck. Any remaining material failure or structural condition returns to Parent; there is no automatic second Terra, Terra-to-Luna substitution, or Pro/Sol/Reviewer fallback.
After Luna's serious packet, Parent may create one `executor_pro` with `fork_turns="none"`, retaining canonical identity/spawn ownership. Its capsule carries authority, decisions/invariants, current implementation, remaining material failures, both Luna outcomes, tester evidence, affected contracts, repair surface, regression boundary, and verification—not Luna's Guide or raw history. Pro finals return to Parent, which thin-relays them with `send_message` to the same waiting Tester; bounded material follow-ups reuse the same Pro. Never respawn Pro or extend escalation for non-material adjacent findings. If Pro is unavailable, conflicted, or fails, return evidence to Parent; do not automatically invoke `executor_sol` or `reviewer_pro`.

## Layered Evidence and Reports

Workers keep full logs, large diffs, reports, API responses, screenshots,
diagnostics, and source inventories in referenced artifacts or their retained
thread context. Evidence returned upward is layered:

```text
Claim | Result | Exact command or method | Artifact location
Critical excerpt (only if needed) | Confidence
```

Each final report is within the configured package size and describes the
knowledge delta:

```text
Status | Outcome | Contract changes | New facts discovered
Assumptions invalidated | Verification evidence | Residual risks
Decision required | Exact references
```

Use `Decision required: none` explicitly. The main agent normally integrates
such a report without opening artifacts unless evidence conflicts, uncertainty
is material, or integration risk requires inspection. Reject intent-only or
evidence-free reports; do not rerun evidenced checks unless later changes or
conflicting evidence invalidate them.

## Gates, Failure, and Waiting

- Executor self-check precedes independent tester verification. Require
  meaningful tests for behavior changes, bug fixes, important modules, and
  public contracts. Prefer deterministic local fixtures; never weaken
  validation, claim unrun checks passed, accept unrelated scope, or allow
  silent error suppression or unplanned public API/schema breaks.
- After one evidence-free response, send one focused retry. Replace the worker
  after a second; if replacement also lacks evidence, report the limitation and
  take over only the smallest critical step transparently.
- Wait for lifecycle events. Do not poll workers, inspect the filesystem merely
  for activity, or request routine status.
- Update the user only at meaningful assignment, handoff, knowledge-changing
  defect, replacement, blocker, or completion transitions.
- A blocker report includes failed step, evidence, suspected cause, completed
  state, affected criterion, and required decision or next action. Never present
  partial work as complete.

## Automatic Handoff and Worker Statistics

After all package workers reach a terminal state, and before the final response
that completes, pauses, or blocks the deployment, follow
`<Codex home>/codex_workflow/end_of_session.md` exactly once, passing only the route, a
unique deployment ID, and closure state; the automatic handoff context fork
supplies the main-agent history. Wait and relay the fresh worker's report
without duplicating its work; a later substantive deployment gets a new ID and
handoff. The direct fast path calls no worker and emits no statistics.
