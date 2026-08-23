# Initial Workflow Bootstrap

Use this guide for the first installation from a deliberate checkout of the
personal workflow repository. Python 3.11 or newer is required. On Windows,
use the equivalent `py -3.11` invocation and native paths.

## Multi-Agent V2 prerequisite

Before validating or installing the package, verify that the active OpenCodex
runtime is the empirically tested version `2.21.0` and that its effective
external configuration already contains:

```json
{
  "multiAgentMode": "v2",
  "syncCodexSubagentDefaults": false,
  "agentTaskRecovery": {
    "enabled": true,
    "model": "gpt-5.6-sol",
    "timeoutMs": 45000,
    "cacheEntries": 200
  }
}
```

`multiAgentMode = "v2"` is required for the intended V2 worker behavior,
`syncCodexSubagentDefaults = false` avoids incompatible default-subagent writes,
and `agentTaskRecovery` is required for the current DeepSeek V4 Flash/Pro
workers. The workflow does not own or modify OpenCodex configuration and must
not update OpenCodex during installation. Stop before bootstrap and report
the missing prerequisite if the active version or effective external
configuration cannot be verified.

The installed workflow keeps `max_concurrent_workers` as child-worker
capacity. Its V2 config materialization adds one Parent slot, so the default 20
children produce
`features.multi_agent_v2.max_concurrent_threads_per_session = 21`.
`agents.max_threads` is legacy V1 capacity: exact workflow-owned values are
migrated, unowned values fail closed, and `agents.enabled` remains unmanaged.

From the repository checkout, validate the source package first:

```text
python3 <repository>/codex_workflow/workflow.py validate \
  --package-root <repository>/codex_workflow --json
```

Stop on any validation error. From the project being bootstrapped, run:

```text
python3 <repository>/codex_workflow/workflow.py bootstrap \
  --package-root <repository>/codex_workflow \
  --project <project>
```

The bootstrap installs the shared runtime, templates, source backup, user
command block, package-default configuration, distributed worker TOMLs, and
workflow-owned Codex settings. It also initializes the current project's
workflow entry point, documentation scaffold, personalization and state
files, and other project-level assets in one compensating transaction.

## Required documentation action

Read the command's `agent_actions` result. It always contains one required
`doc-writer` action for the Project Documentation Framework. Spawn it with
`agent_type="doc-writer"`, `task_name="bootstrap_docs"`, and
`fork_turns="none"`. Its capsule must include the project root and the returned
`files`, `created_files`, `recovery_files`, `framework`, and
`required_context_files` lists, with these requirements:

- Inspect only enough project evidence to record verified initial context;
  source-less projects are valid.
- Initialize only documents listed in `files`—newly created or
  still-template-marked recovery documents—and remove their
  `codex-workflow-bootstrap-template` markers.
- Populate listed `project_structure.md`, `project_overview.md`, and
  `project_core_tech.md` recovery or new files with verified project structure,
  purpose/architecture, and technology context. If relevant source is absent,
  explicitly record that fact instead of leaving template-only content.
- Preserve every pre-existing project document not listed for recovery. If
  `files` is empty, perform a read-only completeness check of all documents in
  `framework`.
- This action may initialize listed new or recovery `project_progress.md` and
  `latest_session_work.md` files; leave deployment status empty when no plan
  exists.
- Do not edit source, entry points, personalization, Git state, or user-level
  files.

Verify that every framework file exists, no file listed in `files` retains the
bootstrap marker, and every listed file in `required_context_files` has been
populated. Installation is incomplete if the required worker cannot run or
fails; do not silently perform its work in the main thread.

Restart Codex only after the bootstrap and required documentation action both
succeed.
