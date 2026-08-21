# Remove codex_workflow

Run this procedure only for the exact command:

    codex_workflow --remove

This is a destructive operation. It uses two phases: the first phase is a
read-only plan, and the second phase is allowed only after one clear second
confirmation from the user. Do not ask any other questions.

First run the lifecycle CLI without `--confirm`, resolving the Codex home
from a non-empty `CODEX_HOME` environment variable when it is set; otherwise
use `~/.codex`:

```text
python3 <Codex home>/codex_workflow/workflow.py \
  remove --project <project> --json
```

Use the equivalent `py -3.11` invocation and native paths on Windows. Report the
plan and explicitly warn that the confirmed phase will permanently delete:

- the recognized project-level `AGENTS.md` (active or disabled), project
  personalization, and project workflow state;
- the workflow-managed region in the user-level `<Codex home>/AGENTS.md` (the
  user file itself is deleted only when no unrelated content remains);
- workflow-owned Multi-Agent V2 enablement and
  `max_concurrent_threads_per_session` capacity in `<Codex home>/config.toml`,
  plus recognized legacy workflow-owned `agents.max_threads` markers;
- worker TOMLs carrying a matching `codex-workflow-worker` ownership marker;
- every file under `<Codex home>/codex_workflow/`, including source and update
  backups.

Also report that `agent_docs/`, unrelated user-level AGENTS/config content,
and unrelated worker TOMLs are preserved. Do not claim that anything has been
removed during this first phase.

Then ask exactly one confirmation, for example:

    This will permanently remove codex_workflow and its workflow-owned files. Confirm removal? (yes/no)

If the reply is not an explicit affirmative, stop without running the second
phase. After an affirmative reply, run:

```text
python3 <Codex home>/codex_workflow/workflow.py \
  remove --project <project> --confirm --json
```

Report the final JSON result. If the command fails, reports an error, or rolls
back, do not describe the removal as successful.
