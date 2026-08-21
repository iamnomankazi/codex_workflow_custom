# Workflow Update

Supported command forms:

    codex_workflow --update

Python 3.11 or newer is required. The lifecycle CLI applies a validated update
directly.

Before applying an update that enables Multi-Agent V2, verify the active
OpenCodex runtime remains at the tested version `2.21.0` with
`agentTaskRecovery` enabled using model `gpt-5.6-sol`, `timeoutMs` `45000`, and
`cacheEntries` `200`. Stop if that prerequisite is absent. The workflow does
not own or modify OpenCodex configuration and does not update OpenCodex.

During materialization, `max_concurrent_workers` remains the child-worker
limit and V2 total session capacity is written as that value plus one under
`features.multi_agent_v2.max_concurrent_threads_per_session`. Exact
workflow-owned legacy `agents.max_threads` values are migrated; unowned legacy
values stop the update, and `agents.enabled` is never managed.

## Source

The script queries GitHub Releases, selects the highest
non-draft SemVer release containing both the universal ZIP and `SHA256SUMS`,
verifies the checksum, and extracts it safely. It includes prereleases and
never clones the repository. The installed launcher delegates planning and
application to the verified incoming CLI so new migrations ship with the new
release.

## Update

Run the lifecycle CLI, resolving the Codex home from a non-empty
`CODEX_HOME` environment variable when it is set; otherwise use `~/.codex`:

```text
python3 <Codex home>/codex_workflow/workflow.py update --project <project>
```

For migration from a pre-script installation, run the incoming package's
`workflow.py` instead of an older installed launcher.

The script migrates and preserves the mutable workflow configuration, then
regenerates distributed worker TOMLs from the incoming package templates. It
preserves unrelated Codex settings, project documents, personalization,
project-local instructions, source backups, the automatic-check preference,
and the project's enabled/disabled state. For projects that still use an older
workflow version, it validates their managed region against that version's
source backup instead of the latest global template. It creates a verified
timestamped backup and applies the user/project state as one compensating
transaction.

If a legacy project entry point contains merged local edits, the update stops.
Review and extract only the project-local instructions into a temporary file,
then rerun with:

```text
--legacy-local-instructions <reviewed-file>
```

This is a one-time migration into the dedicated local region. Never infer the
content automatically. A downgrade additionally requires `--allow-downgrade`.

Report the installed version, preserved state, backup location, and any failure.
Do not describe a partial or rolled-back update as successful.
