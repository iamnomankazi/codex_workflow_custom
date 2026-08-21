# Check for Updates

Run the installed lifecycle CLI, resolving the Codex home from a non-empty
`CODEX_HOME` environment variable when it is set; otherwise use `~/.codex`:

```text
python3 <Codex home>/codex_workflow/workflow.py check-update --json
```

This is an explicit, read-only check and runs regardless of the automatic
update-check setting. It compares the installed version with all available
release assets, reports every newer version, and includes a compact summary of
each version's GitHub release notes. It does not download, install, or change
any workflow files.

If an update is available, review the reported summaries and then send
`codex_workflow --update` when you are ready to install the latest release.
