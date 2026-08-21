# Legacy Alias: Disable Automatic Update Checks

Run this procedure only for the exact command:

    codex_workflow --disable_auto_update

Use the canonical prompt `codex_workflow --disable_auto_check_update`. This
guide is retained for compatibility with installations that used the older,
misleading “auto update” name.

The command itself is explicit authorization to disable the session-start
check; do not request another confirmation.

Run the lifecycle CLI directly, resolving the Codex home from a non-empty
`CODEX_HOME` environment variable when it is set; otherwise use `~/.codex`:

```text
python3 <Codex home>/codex_workflow/workflow.py \
  disable-auto-check-update --json
```

Report the final `auto_check_update` value. The script sets the mutable installed
configuration and removes the session-start check instruction from the
workflow's managed region in `<Codex home>/AGENTS.md`. It preserves unrelated user
content and does not rewrite routes, workers, project files, or package defaults.

The setting is enabled again through
`codex_workflow --enable_auto_check_update`.
