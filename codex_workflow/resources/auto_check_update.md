Once at the start of every new session, before normal task work, run
`python3 <Codex home>/codex_workflow/workflow.py auto-check-update --json`,
resolving the Codex home from a non-empty `CODEX_HOME` environment variable
when it is set; otherwise use `~/.codex`. Use the equivalent Python 3.11+
invocation and native paths for the current platform. Run it at most once per
session.

If it reports `update available`, notify the user briefly with the installed
and available versions. Stay quiet for `current` or `installed newer`. Treat a
check failure as a non-blocking warning and continue the user's task.
