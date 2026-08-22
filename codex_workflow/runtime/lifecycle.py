"""Composition layer for user-level and project lifecycle plans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import RUNTIME_SCHEMA_VERSION
from .backup import append_backup_mutations
from .config import WorkflowConfig, load_config, load_migrated_config
from .errors import ValidationError
from .layout import USER_STATE, PackageLayout, ProjectPaths, RuntimePaths
from .personalization import materialize_personalization
from .plan import (
    OperationPlan,
    deduplicate,
    json_mutation,
    read_json,
    read_string_list,
    resolve_owned_runtime_path,
)
from .project_ops import (
    plan_enable,
    plan_personalize,
    plan_project_install,
    plan_project_remove,
    plan_project_update,
)
from .release import parse_semver
from .runtime_ops import (
    plan_materialized_config,
    plan_runtime_files,
    plan_runtime_remove,
)
from .transaction import Mutation


def plan_bootstrap(
    package: PackageLayout, runtime: RuntimePaths, project: ProjectPaths
) -> OperationPlan:
    config = load_config(package.default_config, templates=package.agent_templates)
    mutations, owned_runtime = plan_runtime_files(
        package, runtime, config, config.to_json().encode()
    )
    project_plan = plan_project_install(package, project)
    mutations.extend(project_plan.mutations)
    state = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "source_id": package.source_id,
        "owned_runtime_files": sorted(owned_runtime),
        "owned_workers": sorted(package.worker_names),
    }
    mutations.append(json_mutation(runtime.runtime / USER_STATE, state))
    return OperationPlan(
        "bootstrap",
        deduplicate(mutations),
        project_plan.warnings,
        project_plan.agent_actions,
        {"source_id": package.source_id},
        cleanup_dirs=project_plan.cleanup_dirs,
    )


def plan_configure(
    runtime: RuntimePaths,
    changes: dict[str, Any],
) -> OperationPlan:
    templates = runtime.runtime / "templates" / "agents"
    current = load_config(runtime.runtime / "workflow_config.json", templates=templates)
    raw = current.to_mapping()
    raw.update({key: value for key, value in changes.items() if value is not None})
    if "enabled_workers" not in changes and changes.get("default_executor"):
        other = ({"executor_luna", "executor_terra"} - {changes["default_executor"]}).pop()
        raw["enabled_workers"] = [
            worker for worker in raw["enabled_workers"] if worker != other
        ]
        if changes["default_executor"] not in raw["enabled_workers"]:
            raw["enabled_workers"].insert(0, changes["default_executor"])
    available = {path.stem for path in templates.glob("*.toml")}
    proposed = WorkflowConfig.from_mapping(raw, available_workers=available)
    mutations = plan_materialized_config(runtime, proposed)
    mutations.append(
        Mutation(runtime.runtime / "workflow_config.json", proposed.to_json().encode())
    )
    state = read_json(runtime.runtime / USER_STATE, default={})
    source_id = state.get("source_id")
    if not PackageLayout.is_source_id(source_id):
        source_id = PackageLayout.resolve(runtime.runtime, allow_legacy=True).source_id
    state.update(
        {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "source_id": source_id,
            "owned_workers": sorted(available),
        }
    )
    # Old state used VERSION as its identity.  Once a local operation touches
    # it, migrate to the content identity and stop carrying the legacy field.
    state.pop("version", None)
    mutations.append(json_mutation(runtime.runtime / USER_STATE, state))
    return OperationPlan(
        "configure",
        deduplicate(mutations),
        [],
        [],
        {"configuration": proposed.to_mapping()},
    )


def plan_remove(
    runtime: RuntimePaths,
    project: ProjectPaths,
) -> OperationPlan:
    runtime_mutations, runtime_dirs, runtime_warnings = plan_runtime_remove(runtime)
    project_mutations, project_dirs, project_warnings = plan_project_remove(project)
    return OperationPlan(
        "remove",
        deduplicate(runtime_mutations + project_mutations),
        runtime_warnings + project_warnings,
        [],
        {
            "confirmation_required": True,
            "preserves": [
                "project agent_docs/ files",
                "unrelated user AGENTS.md content",
                "unrelated Codex config.toml keys",
                "unrelated worker TOMLs",
            ],
        },
        cleanup_dirs=runtime_dirs + project_dirs,
    )


def plan_update(
    incoming: PackageLayout,
    runtime: RuntimePaths,
    project: ProjectPaths,
    *,
    legacy_local_instructions: str | None = None,
) -> OperationPlan:
    installed = PackageLayout.resolve(runtime.runtime, allow_legacy=True)
    project_installed = _project_installed_package(installed, runtime, project)
    config = load_migrated_config(
        runtime.runtime / "workflow_config.json",
        defaults=incoming.default_config,
        templates=incoming.agent_templates,
    )
    backup_root = (
        runtime.runtime
        / ".backups"
        / f"{installed.source_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    mutations: list[Mutation] = []
    append_backup_mutations(mutations, backup_root, runtime, project)
    runtime_mutations, owned_runtime = plan_runtime_files(
        incoming, runtime, config, config.to_json().encode()
    )
    mutations.extend(runtime_mutations)
    project_mutations, warnings = plan_project_update(
        project_installed,
        incoming,
        project,
        legacy_local_instructions=legacy_local_instructions,
    )
    mutations.extend(project_mutations)
    previous_state = read_json(runtime.runtime / USER_STATE, default={})
    incoming_targets = {
        mutation.path.resolve(strict=False) for mutation in runtime_mutations
    }
    for relative in read_string_list(previous_state, "owned_runtime_files"):
        obsolete = resolve_owned_runtime_path(runtime.runtime, relative)
        if obsolete not in incoming_targets and obsolete.exists():
            mutations.append(Mutation(obsolete, None))
    state = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "source_id": incoming.source_id,
        "owned_runtime_files": sorted(owned_runtime),
        "owned_workers": sorted(incoming.worker_names),
    }
    mutations.append(json_mutation(runtime.runtime / USER_STATE, state))
    return OperationPlan(
        "update",
        deduplicate(mutations),
        warnings,
        [],
        {
            "from_source_id": installed.source_id,
            "to_source_id": incoming.source_id,
            "project_from_source_id": project_installed.source_id,
            "backup": str(backup_root),
        },
    )


def _project_installed_package(
    installed: PackageLayout,
    runtime: RuntimePaths,
    project: ProjectPaths,
) -> PackageLayout:
    """Resolve the local source that produced this project's entry point.

    New project state uses a deterministic source identity.  The semantic
    ``workflow_version`` field is read only as a narrowly-scoped migration path
    for installations created before source identities existed.
    """

    if not project.active.exists() and not project.disabled.exists():
        return installed
    state = read_json(project.state, default={})
    source_id = state.get("source_id")
    if source_id is not None:
        if not PackageLayout.is_source_id(source_id):
            raise ValidationError("project source_id state must be a valid sha256 identity")
        if source_id == installed.source_id:
            return installed
        source_backups = (runtime.runtime / ".source_backup").resolve()
        historical_root = (source_backups / source_id).resolve()
        try:
            historical_root.relative_to(source_backups)
        except ValueError as error:
            raise ValidationError("project source_id resolves outside source backups") from error
        if not historical_root.is_dir():
            raise ValidationError(
                "the historical workflow source for this project is missing: "
                f"{historical_root}; restore it from backup before updating the project"
            )
        historical = PackageLayout.resolve(historical_root, allow_legacy=True)
        if historical.source_id != source_id:
            raise ValidationError(
                "project source state and historical source backup identities disagree"
            )
        return historical

    version = state.get("workflow_version")
    if version is None:
        # Pre-state installations can only be associated with the currently
        # installed source; the next update writes a source_id.
        return installed
    if not isinstance(version, str) or not version:
        raise ValidationError("project workflow_version state must be a non-empty string")
    # Legacy migration is the only remaining semantic-version read.  It is
    # never used to decide whether an incoming local source is newer or older.
    parse_semver(version)
    source_backups = (runtime.runtime / ".source_backup").resolve()
    historical_root = (source_backups / version).resolve()
    try:
        historical_root.relative_to(source_backups)
    except ValueError as error:
        raise ValidationError("project workflow_version resolves outside source backups") from error
    if not historical_root.is_dir():
        raise ValidationError(
            "the historical workflow source required for this legacy project is missing: "
            f"{historical_root}; restore it from backup before updating the project"
        )
    historical = PackageLayout.resolve(historical_root, allow_legacy=True)
    if historical.legacy_version != version:
        raise ValidationError(
            "project workflow state and historical source backup versions disagree"
        )
    return historical
