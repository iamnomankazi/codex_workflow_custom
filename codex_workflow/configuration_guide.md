# Configure the Workflow

Run this procedure only when the user's trimmed message is exactly:

    codex_workflow --configure

The lifecycle CLI is:

    <Codex home>/codex_workflow/workflow.py

Resolve `<Codex home>` from a non-empty `CODEX_HOME` environment variable
when it is set; otherwise use `~/.codex`. It requires Python 3.11 or newer and
applies the validated configuration directly.

## Configuration menu

Read the current values from
`<Codex home>/codex_workflow/workflow_config.json`. Do not walk through every
setting sequentially. Instead, display this complete selectable menu, showing
the current value beside each setting and keeping **Exit** as the final option:

The installed file is mutable state. Package defaults and migration fallbacks
come from `<Codex home>/codex_workflow/resources/workflow_config.default.json`
and must not be edited as user configuration.

1. Default executor: `executor_luna` or `executor_terra`.
2. Default-executor reasoning effort: `high`, `xhigh`, or `max`.
3. Maximum concurrent workers, from 1 through the current platform limit of 20.
4. Maximum concurrent `executor_sol` instances.
5. Maximum worker final-report size in words.
6. Exit.

Ask the user to select one menu item. For a setting, ask only the follow-up
needed for a valid value, allow **Keep current**, and then return to the full
menu with refreshed current values. Continue until the user selects **Exit**.
If no setting changed, exit without running the lifecycle CLI.

External release updates and automatic upstream checks are disabled. They are
not configuration options and must not be re-enabled by editing the legacy
`auto_check_update` compatibility field.

## Plan and apply

After the user selects **Exit**, run
`python3 <Codex home>/codex_workflow/workflow.py configure` once with only the
changed flags:

```text
--default-executor <name>
--reasoning-effort <effort>
--max-workers <count>
--max-sol <count>
--report-size <words>
```

Run it with `--json` after collecting the requested values. The command
validates and applies the complete configuration in one operation.

The script validates the configuration, keeps `doc-writer` and
`end_of_session` enabled as required system roles, renders the Heavy route,
synchronizes all distributed worker TOMLs, removes only obsolete manifest-owned
workers, and patches only workflow-owned Codex settings. The configured maximum
remains child-worker capacity; required Multi-Agent V2 total session capacity
is materialized as `max_concurrent_workers + 1` (20 children becomes 21 total).
The workflow migrates exact workflow-owned legacy `agents.max_threads` values
and fails closed on unowned legacy values. It never adds `agents.enabled` or
modifies the external OpenCodex `agentTaskRecovery` prerequisite. The
End-of-Session handoff is integrated and automatic; it is not user-configurable.
Report the result and tell the user to restart Codex when worker definitions or
platform settings changed.
