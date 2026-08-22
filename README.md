<h3 align="center"><big><big><strong>SIMPLE&emsp;&emsp;───&emsp;&emsp;EASY&emsp;&emsp;───&emsp;&emsp;EFFICIENT</strong></big></big></h3>
<p align="center"><small>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;(to use)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;(to install)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;(token consumption)</small></p>
<hr>

![Workflow illustration](illustration.png)

Built for maximum token efficiency: swarm execution with the main agent as the
knowledge distributor, companion assistants that preserve operational context,
and built-in context and implementation-progress management across sessions.

> ⭐ For lightweight tasks, it won’t overdo things. Light route is default.

## 1. Quick installation ⚙️

Requires Python 3.11 or newer for deterministic lifecycle operations. The
Multi-Agent V2 workflow also requires the tested OpenCodex `2.21.0` runtime
with effective external configuration `multiAgentMode` = `"v2"`,
`syncCodexSubagentDefaults` = `false`, and `agentTaskRecovery` enabled through
`gpt-5.6-sol` (`timeoutMs`: `45000`, `cacheEntries`: `200`). V2 mode is
required for the intended V2 worker behavior; `syncCodexSubagentDefaults =
false` avoids incompatible default-subagent writes; recovery is required
because DeepSeek workers cannot directly consume encrypted V2 task content.
The workflow does not configure or update OpenCodex; the bundled bootstrap
stops if this prerequisite cannot be verified.
The persistent worker limit counts children; generated V2 session capacity adds
one Parent slot (20 children becomes 21 total), never emits
`agents.max_threads`, and leaves `agents.enabled` unmanaged.

### Open Codex CLI / Codex app from your project directory 

▶️ Send:

```text
From a checkout of this repository, read `codex_workflow/bootstrap.md` and
follow its local-source validation and bootstrap procedure. The workflow does
not download public release packages or contact an upstream repository.
```
> ⭐ Recommended: use 5.6 Luna xhigh for installation. 

🔄 Restart Codex after installation

After this initial installation, the current project is ready to use. Whenever you need to install this workflow for a new project, simply open the codex and send: `codex_workflow --install`

## 2. Workflow usage 

### This workflow has 3 routes:
- Light route : No subagents, no workflow, minimal context.
- Heavy route : Deploy subagents, full workflow mode.
- Medium route: No subagents, full workflow mode.

> Full workflow mode : Activate `explorer companion` and the ability to automatically manage context and processes.

Note that the `medium route` doesn't call subagents; it completes the task itself. It only applies `full workflow mode` to automatically manage context & progress. It's suitable for moderately sized or narrow tasks, where the main agent can do everything itself faster and more efficiently than calling a small number of workers.

### How to use
- Normally, for simple work, general Q&A, you don't need to do anything. `light route` is the default route.

--------------------------------
- When starting or continuing a plan in progress, just tell Codex in the prompt: "

```text
use medium/heavy route. [your task description]".
```
Or continue a task that was already underway in the previous session: 
```text
use medium/heavy route. Continue ongoing work.
```
> Codex stays on the selected route until you change it, so you don’t need to repeat it in every prompt.
---------------
> **⭐ Recommendation:** Assign very large and complex tasks to the `heavy route` to make the most of its capabilities and maximize token usage savings.

## Light benchmark

![Light benchmark analysis](light_benchmark/analysis.png)

## 3. More details 

Send these exact commands to Codex from the relevant project directory:

| Command | Purpose |
| --- | --- |
| `codex_workflow --install` | Install workflow in the current project and initialize its documentation framework. |
| `codex_workflow --configure` | Configure the default executor, reasoning effort, and worker limits. |
| `codex_workflow --personal` | Add or update project-specific workflow preferences. |
| `codex_workflow --update` | Apply a deliberate local-source update; external release updates are disabled. |
| `codex_workflow --disable` / `codex_workflow --enable` | Disable or re-enable the workflow for the current project. |
| `codex_workflow --remove` | Remove the installed workflow after a destructive dry-run and confirmation. |

For the complete command reference, installed-file map, scripted customization
guide, and Heavy-route design, see [workflow_usage.md](workflow_usage.md).
