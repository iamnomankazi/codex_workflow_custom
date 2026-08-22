# Lifecycle Runtime Architecture

The lifecycle runtime separates immutable local source inputs, mutable
installed state, generated outputs, and project-owned content.

## Data ownership

- `codex_workflow/resources/`: immutable defaults from the checked-out source.
- `<Codex home>/codex_workflow/workflow_config.json`: mutable installed state,
  where `<Codex home>` is the non-empty `CODEX_HOME` environment variable when
  set, otherwise `~/.codex`.
- Heavy snapshots, all worker TOMLs, and workflow-owned Codex settings:
  generated outputs; never sources of truth.
- Project personalization: structured project state materialized into its own
  marker region.
- Project-local instructions: opaque preserved content in a separate marker
  region.

## Module boundaries

- `layout.py`: package and target path contracts.
- `config.py`: configuration schema and rendering.
- `migrations.py`: ordered persistent-resource migrations.
- `markers.py`: strict text-region parsing and rendering.
- `project_ops.py`: project entry point, personalization, and documents.
- `runtime_ops.py`: user-level runtime and generated outputs.
- `backup.py`: persistent local-source update backups.
- `transaction.py`: atomic file writes and compensating rollback.
- `plan.py`: validated mutation plans and compact summaries.
- `lifecycle.py`: composition only; it owns no low-level transformation.
- `release.py`: legacy semantic-version parsing used only to migrate old
  installation state; active lifecycle identity is content based and the module
  performs no network or release acquisition.
- `workflow.py`: CLI parsing, local-source update delegation, direct
  application, and two-phase removal.

The removal plan deletes the recognized project entry point and private
workflow resource, strips only the marked workflow region from the user-level
`AGENTS.md`, removes workflow-owned Codex settings and worker files, and cleans
the dedicated runtime directory. It deliberately preserves `agent_docs/` and
unrelated user-level content.

## Local-source update contract

1. The caller validates a deliberate package directory with `workflow.py
   validate` and passes it to `update --source`.
2. If the incoming source differs from the running launcher, the incoming CLI
   performs the update so its migrations and validation rules are used.
3. The mutable installed configuration is migrated into the incoming schema;
   package defaults supply only newly introduced fields. Generated worker
   surfaces are rendered from that preserved configuration.
4. Each project entry point is validated against the source backup for the
   content identity recorded in its project state. Project-local regions,
   personalization, unrelated user files, and enabled/disabled state are
   preserved as opaque data.
5. Marker drift or ambiguous legacy content stops before live writes.
6. Every write command validates and applies one mutation plan with rollback.

No command contacts an upstream repository or installs a downloaded release.
Every new source state is keyed by a deterministic `sha256-...` identity;
legacy `VERSION` and `workflow_version` values are read only for migration.

Add a new migration without changing callers: register the transformation from
schema `N` to `N+1`, add fixtures for both versions, and keep the incoming
default at the new schema.
