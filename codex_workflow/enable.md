# Enable the Project Workflow

Run the installed lifecycle CLI from the project directory, resolving the
Codex home from a non-empty `CODEX_HOME` environment variable when it is set;
otherwise use `~/.codex`:

```text
python3 <Codex home>/codex_workflow/workflow.py enable --project <project> --json
```

It atomically moves the recognized hidden entry point to `AGENTS.md`, updates
project state, and preserves its exact contents. An already enabled project is
a safe no-op; conflicted or unrecognized entry points are a hard error.
