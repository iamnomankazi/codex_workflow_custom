# Enable Automatic Update Checks

Run this procedure only for the exact command:

    codex_workflow --enable_auto_check_update

The command itself is explicit authorization to enable the session-start
check; do not request another confirmation. This enables only a read-only
release check and notification. It never downloads or installs an update.

Run the lifecycle CLI directly, resolving the Codex home from a non-empty
`CODEX_HOME` environment variable when it is set; otherwise use `~/.codex`:

```text
python3 <Codex home>/codex_workflow/workflow.py \
  enable-auto-check-update --json
```

Report the final `auto_check_update` value. The script sets the mutable installed
configuration and adds the session-start check instruction to the workflow's
managed region in `<Codex home>/AGENTS.md`. It preserves unrelated user content and
does not rewrite routes, workers, project files, or package defaults.

The setting is disabled again through
`codex_workflow --disable_auto_check_update`. The former
`codex_workflow --enable_auto_update` form remains a compatibility alias.
