# Workflow Update

Supported command form:

    codex_workflow --update

The prompt form is retained for compatibility, but external release updates
are disabled. The lifecycle CLI only accepts a deliberate local package source:
Resolve the Codex home from a non-empty `CODEX_HOME` environment variable when
it is set; otherwise use `~/.codex`.

```text
python3 <Codex home>/codex_workflow/workflow.py update \
  --source <repository>/codex_workflow \
  --project <project>
```

`--source` is the explicit local-source operation. Run the current repository's `workflow.py` or the
installed launcher as appropriate; if the incoming source is different from
the running launcher, the incoming source's CLI performs the update so its
migrations and validation rules are used. No network request or release lookup
is performed. Running `update` without `--source` fails closed with an
instruction to provide a local package root.

Before applying an update that enables Multi-Agent V2, verify the active
OpenCodex runtime remains at the tested version `2.21.0` and its effective
external configuration still provides `multiAgentMode = "v2"`,
`syncCodexSubagentDefaults = false`, and `agentTaskRecovery` enabled using model
`gpt-5.6-sol`, `timeoutMs` `45000`, and `cacheEntries` `200`. Stop if any part of
that prerequisite is absent. The workflow does not own or modify OpenCodex
configuration and does not update OpenCodex.

During materialization, `max_concurrent_workers` remains the child-worker
limit and V2 total session capacity is written as that value plus one under
`features.multi_agent_v2.max_concurrent_threads_per_session`. Exact
workflow-owned legacy `agents.max_threads` values are migrated; unowned legacy
values stop the update, and `agents.enabled` is never managed.

The update migrates and preserves the mutable workflow configuration, then
regenerates distributed worker TOMLs from the local source templates. It
preserves project personalization, project-local instructions, project
documents, unrelated Codex settings, source backups, and the project's
enabled/disabled state. Projects created from an earlier local source are
validated against their matching historical source identity instead of the
latest global template. It creates a verified timestamped backup and applies
the user/project state as one compensating transaction with rollback on failure.

If a legacy project entry point contains merged local edits, the update stops.
Review and extract only the project-local instructions into a temporary file,
then rerun with:

```text
--legacy-local-instructions <reviewed-file>
```

This is a one-time migration into the dedicated local region. Never infer the
content automatically. Local source identities are content hashes and have no
newer/older ordering or release-bump requirement.

Report the source identity, preserved state, backup location, and any failure.
Do not describe a partial or rolled-back update as successful.
