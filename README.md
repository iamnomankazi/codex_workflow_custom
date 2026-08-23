# Codex Workflow Custom

A local workflow layer for Codex with three execution routes: **Light**, **Medium**, and **Heavy**.

Small tasks stay with the main agent. Larger tasks can use a persistent read-only Explorer for project context, and Heavy work can be split between specialized executors, independent verification, and a bounded repair path.

More agents are useful only when the task benefits from them. The workflow keeps the direct path cheap and adds orchestration only when there is a clear reason to do so.

---

## Workflow routes

### Light

Light is the default.

The main agent handles the task directly. No Explorer, executor, Tester, or End-of-Session worker is created.

It is intended for things such as:

- questions;
- small code changes;
- quick debugging;
- narrow repository inspection;
- simple documentation or configuration work.

There is no reason to initialize a multi-agent workflow for work the main agent can finish cleanly on its own.

### Medium

Medium is for substantive work where additional project context is useful, but delegating implementation would add unnecessary overhead.

The main agent still owns:

- planning;
- implementation;
- verification;
- acceptance;
- the final response.

For a substantive Medium deployment, two supporting workers are used:

**Explorer**  
Reads relevant project material and returns a compact planning or knowledge-delta brief. Explorer is read-only and is reused during the deployment.

**End-of-Session (EOS)**  
Runs once when the deployment finishes, pauses, or blocks. EOS reconciles the live project documentation and reports Git state without modifying it.

Medium also has a direct fast path. If the current request is small or oddly bounded, no workers are created even if Medium is already selected.

### Heavy

Heavy is the full Multi-Agent V2 route.

The Parent owns architecture, scope, package boundaries, task allocation, integration decisions, acceptance, and the final outcome.

Operational work is delegated to the appropriate role:

```text
Explorer
   ↓
Parent / Orchestrator
   ↓
Executor
   ↓
Tester
   ↓
Acceptance
   ↓
End-of-Session
```

Heavy is intended for work where separation of responsibilities actually helps: larger features, difficult bugs, multi-module changes, migrations, architecture-heavy work, or changes that need meaningful independent verification.

Workers are not spawned simply because they are available.

---

## Model topology

Worker models are defined by their installed role TOMLs. The Parent model belongs to the active Codex session rather than being hard-coded by this workflow.

The current tested setup is:

| Role | Model | Effort | Responsibility |
| --- | --- | --- | --- |
| Parent / Orchestrator | GPT-5.6 Sol | High | Planning, architecture, orchestration, final decisions |
| Explorer | DeepSeek V4 Flash | Max | Read-only project and repository discovery |
| Executor Luna | GPT-5.6 Luna | xhigh | Default implementation and routine repair |
| Tester | GPT-5.6 Luna | xhigh | Independent verification and defect diagnosis |
| Executor Pro | DeepSeek V4 Pro | Max | Serious or persistent repair |
| End-of-Session | GPT-5.6 Luna | xhigh | Documentation reconciliation and Git-state handoff |

Additional roles are available when there is a reason to use them:

| Role | Model | Effort | Use |
| --- | --- | --- | --- |
| Executor Terra | GPT-5.6 Terra | High | Alternate default implementation executor |
| Executor Sol | GPT-5.6 Sol | Medium | Difficult mathematical, logical, or cross-cutting work |
| Reviewer Pro | DeepSeek V4 Pro | Max | Independent read-only deep review |
| Doc-writer | GPT-5.6 Luna | xhigh | Targeted durable documentation and installation-time project-doc initialization |

These specialist roles are not automatic stages in every Heavy deployment.

---

## Heavy repair path

Heavy separates implementation from independent verification.

For the normal Luna path:

```text
Parent
   ↓
Executor Luna
   ↓
Tester
```

If Tester finds a production defect, it sends a focused `followup_task` back to the **same Luna worker**.

```text
Tester
   │
   │ followup_task
   ▼
same Executor Luna
   │
   │ repair + self-check
   │ send_message
   ▼
same Tester
   │
   ▼
re-verification
```

The Parent does not relay routine Luna repair traffic.

Tester can request at most **two routine Luna repairs for the same failed criterion**. The existing worker is reused so its implementation context is preserved.

### Serious repair

If the criterion still fails after Luna repair #2, Tester sends the failure evidence to the Parent.

The Parent can then assign one `executor_pro`:

```text
Tester
   │
   │ serious failure packet
   ▼
Parent
   │
   ▼
Executor Pro
   │
   │ diagnosis + repair
   ▼
Parent
   │
   │ result relay
   ▼
same Tester
   │
   ▼
re-verification
```

Pro is not a routine first-line executor.

Its result returns to the Parent, which relays it to the same waiting Tester for independent verification. If another bounded repair is needed, the same Pro worker is reused rather than creating a replacement.

### Terra repair

Terra follows a different rule.

When `executor_terra` is manually selected as the responsible executor, Tester gets one same-Terra repair and recheck.

If the criterion still fails, the evidence returns to the Parent for a decision. The workflow does not automatically start another Terra, substitute Luna, or escalate to Pro, Sol, or Reviewer.

---

## Explorer and project context

Explorer is the context gateway for substantive Medium and Heavy deployments.

It is a persistent, read-only worker for the current deployment session.

Explorer can inspect relevant:

- source files;
- repository structure;
- architecture;
- dependencies;
- configuration;
- project documentation;
- logs and artifacts;
- external information when required by the task.

Instead of sending raw repository dumps back to the Parent, Explorer returns a smaller brief containing the parts that matter to the current decision.

At the beginning of a deployment, that is normally a **planning brief**.

Later, if implementation results change contracts, assumptions, risks, or architecture, the same Explorer can return a **knowledge-delta brief**.

Explorer retains its working context during the deployment, so unchanged material does not need to be rediscovered on every request.

It cannot modify source, configuration, dependencies, Git state, or the environment.

---

## Bounded worker context

Heavy workers do not receive the Parent's complete conversation by default.

Each initial worker receives a task capsule containing the context needed for its package:

- required outcome;
- ownership and expected edit surface;
- protected areas;
- relevant decisions;
- interfaces and dependencies;
- important invariants;
- likely integration risks;
- acceptance criteria;
- required verification;
- escalation conditions.

The Parent keeps the broader project view while each worker maintains the detailed operational context for its own package.

Follow-up work is sent to the existing worker as a delta rather than recreating its original context from scratch.

---

## Project memory

Persistent project knowledge lives in:

```text
<project>/agent_docs/
```

The core framework is:

```text
project_overview.md
project_core_tech.md
project_structure.md
project_progress.md
project_diary.md
latest_session_work.md
```

These files carry useful project context across Codex sessions.

They are separate from:

```text
codex_workflow/project_docs/
```

The files under `codex_workflow/project_docs/` are bootstrap templates. They are not live project documentation and must not receive project-specific session content.

---

## End-of-Session

Every substantive Medium or Heavy deployment creates one fresh End-of-Session worker immediately before the Parent's final response.

EOS reconciles the live `<project>/agent_docs/` framework using the verified deployment context.

Depending on what changed, it records:

- implementation outcome;
- architecture or contract changes;
- verification evidence;
- current project state;
- completed work;
- blockers or remaining work;
- the next continuation point.

EOS also inspects the final Git state for the handoff.

That Git access is read-only. EOS must not stage, commit, push, reset, stash, checkout, clean, amend, or rewrite history.

Small direct-path tasks skip EOS entirely.

---

## Installation

### Requirements

The lifecycle runtime requires **Python 3.11 or newer**.

The current Heavy setup also depends on Multi-Agent V2 and the tested OpenCodex environment.

The bootstrap currently requires the active OpenCodex runtime to be:

```text
2.21.0
```

with effective `agentTaskRecovery` configuration equivalent to:

```json
{
  "agentTaskRecovery": {
    "enabled": true,
    "model": "gpt-5.6-sol",
    "timeoutMs": 45000,
    "cacheEntries": 200
  }
}
```

This recovery path is required for the current DeepSeek V4 Flash/Pro Multi-Agent V2 workers.

The workflow does not install, modify, or update OpenCodex configuration itself. If the required runtime or recovery configuration cannot be verified, bootstrap stops.

### First installation

Clone or check out this repository locally.

Open Codex from the project where the workflow should be installed and send:

```text
From a checkout of this repository, read `codex_workflow/bootstrap.md` and
follow its local-source validation and bootstrap procedure.
```

Bootstrap validates the checked-out package, installs the shared workflow runtime, materializes the worker definitions and workflow-owned Codex settings, and initializes the current project's workflow files.

It also returns one required `doc-writer` action to initialize or verify the project's documentation framework.

Installation is complete only after bootstrap and that documentation action both succeed.

Restart Codex afterward so the installed instructions and worker definitions are loaded.

### Installing into another project

The shared user-level runtime only needs to be bootstrapped once.

For another project, open Codex in that project and send:

```text
codex_workflow --install
```

This installs the project-level workflow entry point, hidden state, personalization resource, Git ignore entries, and documentation framework using the existing shared runtime.

---

## Commands

Commands are sent from the relevant project.

| Command | Purpose |
| --- | --- |
| `codex_workflow --install` | Install the existing shared workflow into the current project |
| `codex_workflow --configure` | Change the executor, reasoning effort, or worker limits |
| `codex_workflow --personal` | Set project-specific workflow preferences |
| `codex_workflow --update` | Materialize a deliberate local source revision |
| `codex_workflow --disable` | Disable the workflow for the current project |
| `codex_workflow --enable` | Re-enable a disabled project |
| `codex_workflow --remove` | Remove workflow-owned installation state after confirmation |

---

## Configuration

The current default configuration uses:

```json
{
  "default_executor": "executor_luna",
  "default_executor_reasoning_effort": "xhigh",
  "max_concurrent_workers": 20,
  "max_executor_sol_instances": 1,
  "report_package_size": 250
}
```

`max_concurrent_workers` counts child workers.

The Parent occupies another Multi-Agent V2 slot, so the default session capacity is:

```text
20 children + 1 Parent = 21 total
```

The workflow does not add or manage `agents.enabled`.

`agents.max_threads` belongs to the older V1 capacity model. Known workflow-owned legacy values can be migrated; an unowned value causes configuration to stop rather than silently taking ownership of it.

---

## Local-source updates

This repository does not use a GitHub Release-based update system.

There is no:

- automatic release check;
- release downloader;
- automatic updater;
- semantic-version ordering for local source revisions;
- runtime fetch from an upstream repository.

`codex_workflow --update` means that a specific local source tree should be materialized into the installed workflow.

The lifecycle operation uses an explicit source:

```text
workflow.py update --source <local-package-root>
```

Calling the lifecycle update without `--source` fails closed.

### Source identity

Local source revisions use deterministic SHA-256 content identities:

```text
sha256-...
```

The source identity is based on package contents rather than semantic version ordering.

That also allows an uncommitted local working tree to have an exact installation identity.

New historical source snapshots are stored under:

```text
<Codex home>/codex_workflow/.source_backup/<source-id>/
```

Update transactions create timestamped recovery backups under:

```text
<Codex home>/codex_workflow/.backups/
```

The existing `VERSION` file remains only for compatibility with older installations and historical version-based state.

Normal local changes do not require a version bump.

---

## Ownership and safety

Lifecycle operations keep explicit boundaries between workflow-owned and user-owned state.

The workflow preserves unrelated:

- `AGENTS.md` content;
- Codex configuration;
- worker TOMLs;
- project-local instructions;
- personalization;
- project documentation.

Managed regions and worker files carry ownership markers so update and removal operations can determine what they are allowed to change.

When ownership cannot be established safely, the lifecycle code stops instead of assuming that a file or setting belongs to the workflow.

Project workflow paths, including `agent_docs/`, are added to the project's `.gitignore` during installation.

Workers are also given explicit Git boundaries. Executors, Tester, Doc-writer, and EOS do not own normal Git operations; EOS only reports Git state during closure.

---

## Verification

Heavy keeps implementation and verification separate.

An executor implements the assigned package and performs its own focused checks.

Tester then independently verifies the assigned acceptance criteria and regression boundary.

Workers return compact evidence to the Parent instead of copying full logs into the main context.

A typical evidence package contains:

```text
Claim
Result
Exact command or method
Artifact/reference
Confidence
```

Large diffs, logs, screenshots, diagnostics, and other detailed artifacts remain with the responsible worker unless the Parent needs them for a decision.

---

## Benchmarks

The repository currently contains the existing Light-route benchmark:

![Light benchmark analysis](light_benchmark/analysis.png)

It should be read as the result of the scenario it measured, not as a universal token-saving figure for every task or route.

Medium and Heavy have also been functionally validated, including Multi-Agent V2 role binding and the Heavy repair path. Functional acceptance, however, is different from an efficiency benchmark.

Future measurements can compare:

- direct Light work;
- Medium with Explorer-assisted context discovery;
- Heavy on work large enough to justify delegation;
- Parent context growth;
- worker usage;
- elapsed time;
- repair/rework;
- final result quality.

Until there is comparable data across those cases, the README does not claim a fixed percentage of savings.

---

## Repository layout

The workflow source lives under:

```text
codex_workflow/
```

The main pieces are:

```text
codex_workflow/
├── AGENTS.md
├── bootstrap.md
├── install.md
├── update.md
├── medium_route.md
├── heavy_route.md
├── explorer_companion.md
├── end_of_session.md
├── workflow.py
├── runtime/
├── agents/
├── resources/
└── project_docs/
```

Worker role definitions are under:

```text
codex_workflow/agents/
```

Lifecycle, migration, ownership, configuration, and transaction code is under:

```text
codex_workflow/runtime/
```

The model-free regression suite is:

```text
scripts/test_workflow_runtime.py
```

---

## More detail

This README is the overview.

For the complete command behavior, installed-file map, worker contracts, configuration rules, Heavy routing, repair semantics, Multi-Agent V2 setup, and lifecycle ownership model, see:

**[workflow_usage.md](workflow_usage.md)**

Runtime internals are documented in:

**[docs/runtime_architecture.md](docs/runtime_architecture.md)**

---

## Why it is structured this way

Light does not use workers because many tasks do not need orchestration.

Medium adds project context without handing implementation away from the main agent.

Heavy separates discovery, implementation, verification, difficult repair, and closure because larger changes benefit from those boundaries.

Explorer keeps broad repository discovery out of the Parent's working context. Existing executor threads are reused for repair instead of discarding useful local context. EOS leaves the project documentation in a usable state for the next session.

The workflow is not trying to use as many agents as possible.

It uses them when separating the work is useful.
