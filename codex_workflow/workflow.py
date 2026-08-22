#!/usr/bin/env python3
"""Deterministic codex_workflow lifecycle CLI.

Lifecycle commands validate and apply their mutations directly. The destructive
``remove`` command is the exception: it plans first and applies only with its
hidden confirmation flag. The hidden ``--apply`` option remains accepted for
compatibility with older launchers.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    raise SystemExit("codex_workflow requires Python 3.11 or newer")

from runtime.errors import WorkflowError
from runtime.layout import PROJECT_ID
from runtime.lifecycle import (
    OperationPlan,
    PackageLayout,
    ProjectPaths,
    RuntimePaths,
    plan_bootstrap,
    plan_configure,
    plan_enable,
    plan_personalize,
    plan_project_install,
    plan_remove,
    plan_update,
)

RETIRED_EXTERNAL_UPDATE_COMMANDS = frozenset(
    {
        "auto-check-update",
        "check-update",
        "enable-auto-check-update",
        "disable-auto-check-update",
        "enable-auto-update",
        "disable-auto-update",
    }
)
EXTERNAL_UPDATE_DISABLED = (
    "external release updates are disabled; no network request was made. "
    "Use `update --source <local package root>` for a deliberate working-tree update."
)


def _default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _add_common(parser: argparse.ArgumentParser, *, project: bool = True) -> None:
    parser.add_argument("--codex-home", type=Path, default=_default_codex_home())
    if project:
        parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true", default=True, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="emit compact JSON")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    install = commands.add_parser("install")
    _add_common(install)
    # Retained for callers that have an extracted package available. This is
    # a read-only project-install source; install never bootstraps user files.
    install.add_argument("--package-root", type=Path, help=argparse.SUPPRESS)

    bootstrap = commands.add_parser("bootstrap", help=argparse.SUPPRESS)
    _add_common(bootstrap)
    bootstrap.add_argument(
        "--package-root", type=Path, default=Path(__file__).resolve().parent
    )

    update = commands.add_parser("update")
    _add_common(update)
    # Deliberate local-source materialization. An installed launcher may also
    # delegate here when the incoming source contains the newer CLI.
    update.add_argument(
        "--source",
        type=Path,
        help="local package root to materialize into the Codex home",
    )
    # Accepted as a no-op compatibility flag for older local launchers. Local
    # source identities are not ordered, so there is no downgrade decision.
    update.add_argument("--allow-downgrade", action="store_true", help=argparse.SUPPRESS)
    update.add_argument(
        "--legacy-local-instructions",
        type=Path,
        help="reviewed local instructions extracted from a legacy merged entry point",
    )

    remove = commands.add_parser("remove")
    _add_common(remove)
    remove.add_argument("--confirm", action="store_true", help=argparse.SUPPRESS)

    configure = commands.add_parser("configure")
    _add_common(configure, project=False)
    configure.add_argument("--default-executor", choices=["executor_luna", "executor_terra"])
    configure.add_argument("--reasoning-effort", choices=["high", "xhigh", "max"])
    configure.add_argument("--max-workers", type=int)
    configure.add_argument("--max-sol", type=int)
    configure.add_argument("--report-size", type=int)
    personalize = commands.add_parser("personalize")
    _add_common(personalize)
    personalize.add_argument("--resource", type=Path, required=True)

    for name in ("enable", "disable"):
        command = commands.add_parser(name)
        _add_common(command)

    validate = commands.add_parser("validate")
    _add_common(validate, project=False)
    validate.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parent)
    return parser.parse_args()


def _paths(args: argparse.Namespace) -> tuple[RuntimePaths, ProjectPaths | None]:
    runtime = RuntimePaths(args.codex_home.expanduser().resolve())
    project = ProjectPaths(args.project.resolve()) if hasattr(args, "project") else None
    return runtime, project


def _emit(value: dict[str, object], *, compact: bool) -> None:
    if compact:
        print(json.dumps(value, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def _retired_external_update_command(argv: list[str]) -> int | None:
    if len(argv) < 2 or argv[1] not in RETIRED_EXTERNAL_UPDATE_COMMANDS:
        return None
    _emit(
        {"error": EXTERNAL_UPDATE_DISABLED, "applied": False},
        compact="--json" in argv[2:],
    )
    return 1


def _finish(plan: OperationPlan, args: argparse.Namespace) -> int:
    summary = plan.summary()
    summary["applied"] = True
    plan.apply()
    _emit(summary, compact=args.json)
    return 0


def _project_workflow_entry(project: ProjectPaths) -> Path | None:
    """Return an existing recognized active or disabled project entry point."""

    for path in (project.active, project.disabled):
        if path.is_file() and PROJECT_ID in path.read_text(encoding="utf-8"):
            return path
    return None


def _delegate_update(incoming: PackageLayout, args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        "-B",
        str(incoming.root / "workflow.py"),
        "update",
        "--source",
        str(incoming.root),
        "--codex-home",
        str(args.codex_home),
        "--project",
        str(args.project),
    ]
    if args.legacy_local_instructions:
        command.extend(
            ["--legacy-local-instructions", str(args.legacy_local_instructions)]
        )
    if args.apply:
        command.append("--apply")
    if args.json:
        command.append("--json")
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> int:
    retired = _retired_external_update_command(sys.argv)
    if retired is not None:
        return retired
    args = parse_args()
    temporary = None
    try:
        runtime, project = _paths(args)
        if args.command == "validate":
            package = PackageLayout.resolve(args.package_root)
            result = {
                "valid": True,
                "source_id": package.source_id,
                "workers": sorted(package.worker_names),
            }
            if package.legacy_version is not None:
                result["legacy_version"] = package.legacy_version
            _emit(result, compact=args.json)
            return 0
        if args.command == "remove":
            assert project is not None
            plan = plan_remove(runtime, project)
            if not args.confirm:
                summary = plan.summary()
                summary["applied"] = False
                summary["confirmation_required"] = True
                _emit(summary, compact=args.json)
                return 0
            return _finish(plan, args)
        if args.command == "bootstrap":
            assert project is not None
            package = PackageLayout.resolve(args.package_root)
            return _finish(plan_bootstrap(package, runtime, project), args)
        if args.command == "install":
            assert project is not None
            if project.active.exists() and project.disabled.exists():
                raise WorkflowError("both active and disabled project entry points exist")
            if (runtime.runtime / "workflow.py").is_file():
                package = PackageLayout.resolve(runtime.runtime)
            elif args.package_root is not None:
                package = PackageLayout.resolve(args.package_root)
            else:
                raise WorkflowError(
                    "the user-level workflow bootstrap is not installed; "
                    "complete the initial bootstrap before installing a project"
                )
            existing = _project_workflow_entry(project)
            if existing is not None:
                # Validate the recognized entry before reporting a no-op. This
                # turns stale, malformed, or personalization-drifted installs
                # into actionable errors instead of misreporting them as merely
                # disabled.
                existing_plan = plan_project_install(package, project)
                if existing_plan.agent_actions[0]["files"]:
                    return _finish(existing_plan, args)
                enabled = existing == project.active
                _emit(
                    {
                        "applied": False,
                        "status": "already enabled" if enabled else "already disabled",
                        "instruction": (
                            "No action is required."
                            if enabled
                            else "Run `codex_workflow --enable` to reactivate it."
                        ),
                    },
                    compact=args.json,
                )
                return 0
            return _finish(plan_project_install(package, project), args)
        if args.command == "update":
            assert project is not None
            if not args.source:
                raise WorkflowError(
                    "external release updates are disabled; pass --source <local "
                    "package root> to update from deliberate local source"
                )
            incoming = PackageLayout.resolve(args.source)
            if incoming.root != Path(__file__).resolve().parent:
                return _delegate_update(incoming, args)
            legacy_local = (
                args.legacy_local_instructions.read_text(encoding="utf-8")
                if args.legacy_local_instructions
                else None
            )
            return _finish(
                plan_update(
                    incoming,
                    runtime,
                    project,
                    legacy_local_instructions=legacy_local,
                ),
                args,
            )
        if args.command == "configure":
            changes = {
                "default_executor": args.default_executor,
                "default_executor_reasoning_effort": args.reasoning_effort,
                "max_concurrent_workers": args.max_workers,
                "max_executor_sol_instances": args.max_sol,
                "report_package_size": args.report_size,
            }
            return _finish(plan_configure(runtime, changes), args)
        if args.command == "personalize":
            assert project is not None
            resource = args.resource.read_text(encoding="utf-8")
            return _finish(plan_personalize(project, resource), args)
        if args.command in {"enable", "disable"}:
            assert project is not None
            return _finish(plan_enable(project, enable=args.command == "enable"), args)
        raise WorkflowError(f"unsupported command: {args.command}")
    except (OSError, WorkflowError) as error:
        _emit({"error": str(error), "applied": False}, compact=getattr(args, "json", False))
        return 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
