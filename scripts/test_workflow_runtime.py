"""Regression tests for the lifecycle runtime."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "codex_workflow"
PACKAGE_VERSION = (PACKAGE / "VERSION").read_text(encoding="utf-8").strip()

import sys

sys.path.insert(0, str(PACKAGE))

import workflow as workflow_cli

from runtime._toml import tomllib
from runtime.config import (
    DEFAULT_EXECUTORS,
    WorkflowConfig,
    load_config,
    patch_codex_config,
    remove_workflow_owned_config,
    render_heavy_route,
    render_worker_template,
)
from runtime.backup import append_backup_mutations
from runtime.errors import TransactionError, ValidationError
from runtime.lifecycle import (
    PackageLayout,
    ProjectPaths,
    RuntimePaths,
    materialize_personalization,
    plan_bootstrap,
    plan_configure,
    plan_enable,
    plan_personalize,
    plan_project_install,
    plan_remove,
    plan_update,
)
from runtime.markers import (
    PROJECT_LOCAL,
    PROJECT_PERSONALIZATION,
    USER_MANAGED,
    extract,
    render_project_entry,
)
from runtime.migrations import migrate_config_resource
from runtime.plan import OperationPlan, read_string_list, resolve_owned_runtime_path
from runtime.release import parse_semver
from runtime.transaction import Mutation, apply


class MarkerTests(unittest.TestCase):
    def test_user_command_contract_has_no_external_update_surface(self) -> None:
        instructions = (PACKAGE / "user_AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("auto-check-update", instructions)
        self.assertNotIn("check-update", instructions)
        self.assertNotIn("auto_check_update", instructions)
        self.assertIn("codex_workflow --remove", instructions)

        personalization = (PACKAGE / "personalization_guide.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("resources/personalization.md", personalization)
        self.assertIn("missing or invalid", personalization)
        self.assertIn("copy that section's complete", personalization)

    def test_template_renders_independent_project_regions(self) -> None:
        template = (PACKAGE / "AGENTS.md").read_text(encoding="utf-8")
        rendered = render_project_entry(
            template,
            personalization="Personal rule.",
            local_instructions="# Existing\nKeep this.",
        )
        self.assertEqual(extract(rendered, PROJECT_PERSONALIZATION), "Personal rule.")
        self.assertEqual(extract(rendered, PROJECT_LOCAL), "# Existing\nKeep this.")

    def test_package_project_docs_are_neutral_bootstrap_templates(self) -> None:
        documents = (
            "project_overview.md",
            "project_core_tech.md",
            "project_structure.md",
            "project_progress.md",
            "project_diary.md",
            "latest_session_work.md",
        )
        for name in documents:
            text = (PACKAGE / "project_docs" / name).read_text(encoding="utf-8")
            self.assertIn("codex-workflow-bootstrap-template", text)
            self.assertNotIn("cleanup_20260822", text)
            if name != "latest_session_work.md":
                self.assertNotIn("No previous workflow session has been recorded.", text)

        handoff = (PACKAGE / "end_of_session.md").read_text(encoding="utf-8")
        self.assertIn("live `<project>/agent_docs/`", handoff)
        self.assertIn("bootstrap-marked", handoff)

    def test_operational_policies_are_compact_and_knowledge_aware(self) -> None:
        names = (
            "AGENTS.md",
            "medium_route.md",
            "heavy_route.md",
            "explorer_companion.md",
        )
        policies = {
            name: (PACKAGE / name).read_text(encoding="utf-8") for name in names
        }
        for name, text in policies.items():
            limit = 225 if name == "heavy_route.md" else 200
            self.assertLess(len(text.splitlines()), limit, name)

        heavy = policies["heavy_route.md"]
        self.assertIn("recommended approach", heavy.lower())
        self.assertIn("canonical task names", heavy)
        self.assertIn("Decision required: none", heavy)
        self.assertIn("knowledge-delta brief", heavy)
        self.assertIn("Only when the assigned worker is `executor_luna`", heavy)
        self.assertIn("ordered implementation sequence", heavy)
        self.assertIn("Do not add this Execution Guide requirement", heavy)
        self.assertIn("not spawn, message, or otherwise call subagents", heavy)
        self.assertIn("skips End-of-Session and worker statistics", heavy)
        self.assertIn("before the final response", heavy)
        self.assertIn("automatic handoff context fork", heavy)
        self.assertNotIn("compact ledger", heavy)
        heavy_contract = " ".join(heavy.split())
        self.assertIn("same Luna worker for repair #1", heavy_contract)
        self.assertIn("same Luna worker for repair #2", heavy_contract)
        self.assertIn("Never send a third routine Luna repair", heavy_contract)
        self.assertIn("focused `followup_task` defect packet", heavy_contract)
        self.assertIn("That executor repairs within its capsule, self-checks", heavy_contract)
        self.assertIn("completion evidence via `send_message`", heavy_contract)
        self.assertIn("not the executor's ordinary final", heavy_contract)
        self.assertIn("Parent is not the routine native-executor relay", heavy_contract)
        self.assertIn("communication-only `send_message`, `wait_agent`", heavy_contract)
        self.assertIn("failed delivery goes in the executor's parent-visible final", heavy_contract)
        self.assertIn("tester sends the parent", heavy)
        self.assertIn("Tester never creates Pro", heavy)
        self.assertIn('`executor_pro` with `fork_turns="none"`', heavy_contract)
        self.assertIn("parent retains Pro's canonical identity", heavy_contract)
        self.assertIn("Every Pro final returns to the parent", heavy_contract)
        self.assertIn("thin-relays it unchanged via `send_message`", heavy_contract)
        self.assertIn("same waiting tester", heavy_contract)
        self.assertIn("mailbox wakes tester to recheck", heavy_contract)
        self.assertIn("`followup_task` deltas to the same Pro", heavy_contract)
        self.assertIn("Never respawn Pro", heavy_contract)
        self.assertIn("return capsule/invariant conflict", heavy_contract)
        self.assertIn("same responsible worker", heavy_contract)
        self.assertIn("not the executor's ordinary final", heavy_contract)
        self.assertIn("manually selected Terra", heavy_contract)
        self.assertIn("one same-Terra `followup_task`", heavy_contract)
        self.assertIn("direct `send_message`, and recheck", heavy_contract)
        self.assertIn("returns evidence to Parent for its decision", heavy_contract)
        self.assertIn("does not inherit Luna's two-repair or automatic-Pro ladder", heavy_contract)
        self.assertIn("no Terra-to-Luna, second-Terra", heavy_contract)
        self.assertIn(
            "do not automatically invoke `executor_sol` or `reviewer_pro`",
            heavy_contract,
        )

        medium = policies["medium_route.md"]
        self.assertIn("direct main-agent fast path", medium)
        self.assertIn("do not call `end_of_session`", medium)
        self.assertIn("Before the final response", medium)
        self.assertIn("complete documentation framework", medium)
        self.assertNotIn("usage ledger", medium)

        agents_policy = policies["AGENTS.md"]
        self.assertIn("handoff is not a user command", agents_policy)

        explorer = policies["explorer_companion.md"]
        self.assertIn("planning brief", explorer)
        self.assertIn("knowledge-delta brief", explorer)
        self.assertIn("distinct task names", explorer)
        self.assertIn('agent_type="explorer"', explorer)
        self.assertEqual(explorer.count('task_name="explorer_companion"'), 1)
        self.assertIn('fork_turns="none"', explorer)
        self.assertIn("Reuse its thread", explorer)
        self.assertIn("Do not create a\n  second Explorer", explorer)

        handoff_contract = (PACKAGE / "end_of_session.md").read_text(
            encoding="utf-8"
        )
        handoff_worker = (PACKAGE / "agents" / "end_of_session.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn('task_name="end_of_session_<deployment_id>"', handoff_contract)
        self.assertIn('agent_type="end_of_session"', handoff_contract)
        self.assertIn("after every substantive Medium or Heavy", handoff_contract)
        self.assertIn("inherits the deployment context", handoff_contract)
        self.assertIn("complete `agent_docs/` framework", handoff_contract)
        self.assertIn("Do not call a second documentation worker", handoff_contract)
        self.assertNotIn('fork_turns="none"', handoff_contract)
        self.assertNotIn("compact usage ledger", handoff_contract)
        self.assertIn(
            "| Worker name | Quantity | Number of calls |", handoff_worker
        )
        self.assertIn(
            "`Quantity` is the number of distinct task names", handoff_worker
        )
        self.assertIn("turn-starting initial assignments", handoff_worker)
        self.assertIn("read the complete existing", handoff_worker)
        self.assertIn("Do not delegate or create another worker", handoff_worker)
        self.assertIn("the parent does not supply or maintain a ledger", handoff_worker)
        for framework_file in (
            "project_overview.md",
            "project_core_tech.md",
            "project_structure.md",
            "project_progress.md",
            "project_diary.md",
            "latest_session_work.md",
        ):
            self.assertIn(framework_file, handoff_worker)
        for policy in (
            heavy,
            medium,
            agents_policy,
            handoff_contract,
            handoff_worker,
        ):
            self.assertNotIn("end this session", policy.lower())

        tester = (PACKAGE / "agents" / "tester.toml").read_text(encoding="utf-8")
        executor = (PACKAGE / "agents" / "executor_luna.toml").read_text(
            encoding="utf-8"
        )
        terra = (PACKAGE / "agents" / "executor_terra.toml").read_text(
            encoding="utf-8"
        )
        executor_pro = (PACKAGE / "agents" / "executor_pro.toml").read_text(
            encoding="utf-8"
        )
        reviewer_pro = (PACKAGE / "agents" / "reviewer_pro.toml").read_text(
            encoding="utf-8"
        )
        doc_writer = (PACKAGE / "agents" / "doc-writer.toml").read_text(
            encoding="utf-8"
        )
        bootstrap = (PACKAGE / "bootstrap.md").read_text(encoding="utf-8")
        update = (PACKAGE / "update.md").read_text(encoding="utf-8")
        install = (PACKAGE / "install.md").read_text(encoding="utf-8")
        usage = (ROOT / "workflow_usage.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        recovery_contract = "\n".join((bootstrap, update, usage, readme))
        for required_recovery_value in (
            "2.21.0",
            "agentTaskRecovery",
            "gpt-5.6-sol",
            "45000",
            "200",
        ):
            self.assertIn(required_recovery_value, recovery_contract)
        bootstrap_contract = " ".join(bootstrap.split())
        update_contract = " ".join(update.split())
        self.assertIn("Stop before bootstrap", bootstrap_contract)
        self.assertIn(
            "does not own or modify OpenCodex configuration", bootstrap_contract
        )
        self.assertIn(
            "does not own or modify OpenCodex configuration", update_contract
        )
        self.assertIn("workflow-level read-only roles", usage)
        self.assertIn("permission inheritance", usage)
        self.assertIn("worker-policy violation", usage)
        self.assertIn("does not add or manage `agents.enabled`", usage)
        self.assertIn("at most two focused", tester)
        self.assertIn("same Luna worker", tester)
        self.assertIn("Never\n  request a third routine Luna repair", tester)
        self.assertIn("Never create or orchestrate `executor_pro`", tester)
        tester_contract = " ".join(tester.split())
        luna_contract = " ".join(executor.split())
        terra_contract = " ".join(terra.split())
        phase3_contract = " ".join(
            (heavy + "\n" + tester + "\n" + executor + "\n" + terra + "\n" + usage).split()
        )
        self.assertIn("same named responsible executor", tester_contract)
        self.assertIn("`executor_luna` or `executor_terra`", tester_contract)
        self.assertIn("Use `wait_agent` for that executor's direct", tester_contract)
        self.assertIn("`send_message` mailbox completion signal", tester_contract)
        self.assertIn("then rerun the failed criterion", tester_contract)
        self.assertIn("Parent is not the routine native-executor relay", tester_contract)
        self.assertIn("communication-only `send_message`, waiting", tester_contract)
        self.assertIn("scoped repair through `followup_task`", luna_contract)
        self.assertIn("run its focused self-check", luna_contract)
        self.assertIn("same tester with `send_message`", luna_contract)
        self.assertIn("direct message is tester's completion signal", luna_contract)
        self.assertIn("do not rely on your ordinary final", luna_contract)
        self.assertIn("communication failure in the parent-visible final", luna_contract)
        self.assertIn("do not stall, create a worker", luna_contract)
        self.assertIn("one scoped `followup_task` to that same Terra worker", tester_contract)
        self.assertIn("wait for Terra's direct `send_message`, and recheck", tester_contract)
        self.assertIn("send the evidence to the parent for a decision", tester_contract)
        self.assertIn("Do not inherit Luna's two-repair or automatic-Pro ladder", tester_contract)
        self.assertIn("never automatically start a second Terra, substitute Luna", tester_contract)
        self.assertIn("scoped repair through `followup_task`", terra_contract)
        self.assertIn("run its focused self-check", terra_contract)
        self.assertIn("same tester with `send_message`", terra_contract)
        self.assertIn("direct message is tester's completion signal", terra_contract)
        self.assertIn("do not rely on your ordinary final", terra_contract)
        self.assertIn("normal parent-visible final", terra_contract)
        self.assertIn("do not stall, create a worker", terra_contract)
        self.assertIn("communication failure in the parent-visible final", terra_contract)
        self.assertIn("Do not start another Terra", terra_contract)
        self.assertIn("Luna send_message completion wakes Tester", usage)
        self.assertIn("without a routine parent relay", usage)
        self.assertIn("When Terra is manually selected", usage)
        self.assertIn("`followup_task` to the same Terra worker", usage)
        self.assertIn(
            "directly\nsignals that waiting tester with `send_message` for recheck",
            usage,
        )
        self.assertIn("returns to the parent for a decision", usage)
        self.assertIn("no automatic second Terra", usage)
        self.assertIn("the parent creates or assigns one Pro", tester_contract)
        self.assertIn("scoped `followup_task` deltas to the same Pro", tester_contract)
        self.assertIn("Expect every Pro final at the parent", tester_contract)
        self.assertIn("thin `send_message` mailbox relay", tester_contract)
        self.assertIn("rerun the focused criterion", tester_contract)
        self.assertIn("target the same Pro", tester_contract)
        self.assertIn(
            "Pro final returns to Parent",
            usage,
        )
        self.assertIn(
            "Parent thin-relays result via send_message to the same waiting Tester",
            usage,
        )
        self.assertIn(
            "followup_task to same Pro",
            usage,
        )
        direct_completion_claim = " ".join(("pro final returns", "directly to tester"))
        luna_final_claim = " ".join(("luna final", "returns directly to tester"))
        read_only_claim = " ".join(("tester must be", "read-only"))
        self.assertNotIn(direct_completion_claim, phase3_contract.lower())
        self.assertNotIn(luna_final_claim, phase3_contract.lower())
        self.assertNotIn(read_only_claim, phase3_contract.lower())
        tester_config = tomllib.loads(tester)
        luna_config = tomllib.loads(executor)
        terra_config = tomllib.loads(terra)
        default_config = json.loads(
            (PACKAGE / "resources" / "workflow_config.default.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(default_config["default_executor"], "executor_luna")
        self.assertEqual(luna_config["model"], "gpt-5.6-luna")
        self.assertEqual(luna_config["model_reasoning_effort"], "xhigh")
        self.assertEqual(luna_config["sandbox_mode"], "workspace-write")
        self.assertEqual(terra_config["model"], "gpt-5.6-terra")
        self.assertEqual(terra_config["model_reasoning_effort"], "high")
        self.assertEqual(terra_config["sandbox_mode"], "workspace-write")
        self.assertEqual(tester_config["model"], "gpt-5.6-luna")
        self.assertEqual(tester_config["model_reasoning_effort"], "xhigh")
        self.assertEqual(tester_config["sandbox_mode"], "workspace-write")
        self.assertIn("Execution Guide as the primary work sequence", executor)
        self.assertIn("Track the completion checklist internally", executor)
        self.assertNotIn("Execution Guide as the primary work sequence", terra)
        self.assertNotIn("Execution Guide", executor_pro)
        self.assertNotIn("Execution Guide", reviewer_pro)
        self.assertIn("explicitly assigned difficult package", executor_pro)
        self.assertIn("independent serious reviewer", reviewer_pro)
        self.assertIn("always contains one required", bootstrap)
        self.assertIn("explicitly labeled bootstrap/project-install action", doc_writer)
        for required_context in (
            "project_structure.md",
            "project_overview.md",
            "project_core_tech.md",
        ):
            self.assertIn(required_context, bootstrap)
            self.assertIn(required_context, install)

    def test_reserved_marker_collision_is_rejected_during_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            (project / "AGENTS.md").write_text(PROJECT_LOCAL.start, encoding="utf-8")
            with self.assertRaises(ValidationError):
                plan_bootstrap(
                    PackageLayout.resolve(PACKAGE),
                    RuntimePaths(root / "home"),
                    ProjectPaths(project),
                )

    def test_package_requires_exact_user_managed_region(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "codex_workflow"
            shutil.copytree(
                PACKAGE,
                root,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            path = root / "user_AGENTS.md"
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace(USER_MANAGED.start, "", 1), encoding="utf-8"
            )
            with self.assertRaises(ValidationError):
                PackageLayout.resolve(root)

    def test_update_help_exposes_only_the_local_source_operation(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(PACKAGE / "workflow.py"), "update", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--source", completed.stdout)
        self.assertIn("local package root", completed.stdout)
        self.assertNotIn("--apply", completed.stdout)

    def test_top_level_help_omits_retired_update_commands(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(PACKAGE / "workflow.py"), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("check-update", completed.stdout)
        self.assertNotIn("auto-update", completed.stdout)

    def test_retired_update_commands_fail_closed_without_network(self) -> None:
        for command in (
            "auto-check-update",
            "check-update",
            "enable-auto-check-update",
            "disable-auto-check-update",
            "enable-auto-update",
            "disable-auto-update",
        ):
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(PACKAGE / "workflow.py"),
                    command,
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn("external release updates are disabled", completed.stdout)

    def test_configure_help_omits_handoff_context_option(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(PACKAGE / "workflow.py"),
                "configure",
                "--help",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("--handoff-context-turns", completed.stdout)

    def test_remove_help_hides_internal_confirmation_flag(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(PACKAGE / "workflow.py"), "remove", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("--confirm", completed.stdout)


class SafetyTests(unittest.TestCase):
    def test_owned_runtime_manifest_is_confined_and_typed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "runtime"
            with self.assertRaises(ValidationError):
                resolve_owned_runtime_path(runtime_root, "../../outside.txt")
            with self.assertRaises(ValidationError):
                resolve_owned_runtime_path(runtime_root, "/tmp/outside.txt")
        with self.assertRaises(ValidationError):
            read_string_list({"owned_runtime_files": None}, "owned_runtime_files")

    def test_heavy_initial_spawns_bind_installed_roles(self) -> None:
        heavy = " ".join(
            (PACKAGE / "heavy_route.md").read_text(encoding="utf-8").split()
        )
        self.assertIn(
            "Every initial `spawn_agent` call must pass both the installed `agent_type` and a stable `task_name`",
            heavy,
        )
        self.assertIn(
            'Required shape: `spawn_agent(agent_type="<role>", task_name="<stable identity>", ...)`',
            heavy,
        )
        for label, role in (
            ("Explorer", "explorer"),
            ("routine Luna", "executor_luna"),
            ("Tester", "tester"),
            ("serious Pro", "executor_pro"),
            ("closure", "end_of_session"),
        ):
            with self.subTest(label=label):
                self.assertIn(f'{label} `agent_type="{role}"`', heavy)
                definition = tomllib.loads(
                    (PACKAGE / "agents" / f"{role}.toml").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(definition["name"], role)
        self.assertIn("task identity does not select a role", heavy)
        self.assertIn(
            "the installed role TOML remains the model/provider authority", heavy
        )

    def test_end_of_session_contract_is_git_read_only(self) -> None:
        forbidden = re.compile(
            r"\bgit\s+(?:add|commit|push|reset|stash|checkout|clean)\b",
            re.IGNORECASE,
        )
        for relative in ("end_of_session.md", "agents/end_of_session.toml"):
            with self.subTest(relative=relative):
                text = (PACKAGE / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split()).lower()
                self.assertIn("read-only", normalized)
                self.assertIn("without changing", normalized)
                self.assertIsNone(forbidden.search(text), relative)
                for stale_phrase in (
                    "handles Git staging",
                    "handles the Git commit",
                    "commit identity",
                    "commit quietly",
                ):
                    self.assertNotIn(stale_phrase.lower(), normalized)
        handoff = (PACKAGE / "end_of_session.md").read_text(encoding="utf-8")
        self.assertIn("unwritable `.git` directory is not a handoff failure", handoff)

    def test_backup_skips_missing_optional_user_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            mutations: list[Mutation] = []
            append_backup_mutations(
                mutations,
                root / "backup",
                RuntimePaths(root / "home"),
                ProjectPaths(project),
            )
            self.assertEqual(mutations, [])


class ConfigTests(unittest.TestCase):
    def workflow_config(self, maximum: int = 20) -> WorkflowConfig:
        raw = json.loads(
            (PACKAGE / "resources" / "workflow_config.default.json").read_text(
                encoding="utf-8"
            )
        )
        raw["max_concurrent_workers"] = maximum
        return WorkflowConfig.from_mapping(raw)

    def test_package_default_disables_automatic_update_checks(self) -> None:
        raw = json.loads(
            (PACKAGE / "resources" / "workflow_config.default.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(raw["auto_check_update"])
        self.assertFalse(WorkflowConfig.from_mapping(raw).auto_check_update)

    def test_deepseek_worker_roles_have_fixed_models_effort_and_authority(self) -> None:
        workers = {
            name: tomllib.loads(
                (PACKAGE / "agents" / f"{name}.toml").read_text(encoding="utf-8")
            )
            for name in ("explorer", "executor_pro", "reviewer_pro")
        }
        self.assertEqual(workers["explorer"]["name"], "explorer")
        self.assertEqual(
            workers["explorer"]["model"], "deepseek/deepseek-v4-flash"
        )
        self.assertEqual(workers["explorer"]["model_reasoning_effort"], "max")
        self.assertEqual(workers["explorer"]["sandbox_mode"], "read-only")
        self.assertNotIn("service_tier", workers["explorer"])
        self.assertNotIn("model_provider", workers["explorer"])
        self.assertNotIn("wire_api", workers["explorer"])

        for role in ("executor_pro", "reviewer_pro"):
            self.assertEqual(workers[role]["name"], role)
            self.assertEqual(workers[role]["model"], "deepseek/deepseek-v4-pro")
            self.assertEqual(workers[role]["model_reasoning_effort"], "max")
        self.assertEqual(workers["executor_pro"]["sandbox_mode"], "workspace-write")
        self.assertEqual(workers["reviewer_pro"]["sandbox_mode"], "read-only")
        self.assertNotEqual(
            workers["executor_pro"]["developer_instructions"],
            workers["reviewer_pro"]["developer_instructions"],
        )

    def test_deepseek_worker_templates_render_deterministically_without_volatile_values(self) -> None:
        config = load_config(
            PACKAGE / "resources" / "workflow_config.default.json",
            templates=PACKAGE / "agents",
        )
        volatile_value_patterns = (
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}",
            r"\b[0-9a-f]{40}\b",
            r"\{\{[^}]+\}\}",
            r"<deployment[_ -]?id>",
            r"<run[_ -]?id>",
        )
        for worker in ("explorer", "executor_pro", "reviewer_pro"):
            source = (PACKAGE / "agents" / f"{worker}.toml").read_text(
                encoding="utf-8"
            )
            first = render_worker_template(source, worker=worker, config=config)
            second = render_worker_template(source, worker=worker, config=config)
            self.assertEqual(first.encode(), second.encode(), worker)
            for pattern in volatile_value_patterns:
                self.assertIsNone(re.search(pattern, first, re.IGNORECASE), (worker, pattern))

    def test_pro_roles_are_enabled_but_cannot_be_default_executors(self) -> None:
        raw = json.loads(
            (PACKAGE / "resources" / "workflow_config.default.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(raw["default_executor"], "executor_luna")
        self.assertEqual(DEFAULT_EXECUTORS, {"executor_luna", "executor_terra"})
        self.assertIn("executor_pro", raw["enabled_workers"])
        self.assertIn("reviewer_pro", raw["enabled_workers"])
        for role in ("executor_pro", "reviewer_pro"):
            invalid = dict(raw)
            invalid["default_executor"] = role
            with self.assertRaises(ValidationError):
                WorkflowConfig.from_mapping(invalid)

    def test_newer_persistent_schema_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            migrate_config_resource(
                {"schema_version": 6},
                {"schema_version": 5},
            )

    def test_v2_config_migration_enables_handoff_worker(self) -> None:
        migrated = migrate_config_resource(
            {
                "schema_version": 2,
                "enabled_workers": ["executor_luna", "doc-writer", "explorer"],
            },
            {"schema_version": 5},
        )
        self.assertEqual(migrated["schema_version"], 5)
        self.assertIn("end_of_session", migrated["enabled_workers"])
        self.assertIn("executor_pro", migrated["enabled_workers"])
        self.assertIn("reviewer_pro", migrated["enabled_workers"])
        self.assertNotIn("end_of_session_context_turns", migrated)

    def test_v3_config_migration_removes_handoff_context_setting(self) -> None:
        migrated = migrate_config_resource(
            {
                "schema_version": 3,
                "end_of_session_context_turns": 150,
            },
            {"schema_version": 5},
        )
        self.assertEqual(migrated["schema_version"], 5)
        self.assertNotIn("end_of_session_context_turns", migrated)

    def test_v4_config_migration_enables_pro_roles(self) -> None:
        migrated = migrate_config_resource(
            {
                "schema_version": 4,
                "enabled_workers": [
                    "executor_luna",
                    "executor_sol",
                    "tester",
                    "doc-writer",
                    "explorer",
                    "end_of_session",
                ],
            },
            {"schema_version": 5},
        )
        self.assertEqual(migrated["schema_version"], 5)
        self.assertEqual(migrated["enabled_workers"].count("executor_pro"), 1)
        self.assertEqual(migrated["enabled_workers"].count("reviewer_pro"), 1)

    def test_worker_limit_above_platform_limit_is_rejected(self) -> None:
        raw = json.loads(
            (PACKAGE / "resources" / "workflow_config.default.json").read_text(
                encoding="utf-8"
            )
        )
        raw["max_concurrent_workers"] = 21
        with self.assertRaises(ValidationError):
            WorkflowConfig.from_mapping(raw)

    def test_toml_patch_creates_owned_v2_capacity_without_agents_controls(self) -> None:
        rendered = patch_codex_config("", self.workflow_config())
        parsed = tomllib.loads(rendered)
        self.assertTrue(parsed["features"]["multi_agent_v2"]["enabled"])
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            21,
        )
        self.assertNotIn("agents", parsed)
        self.assertNotIn("agents.enabled", rendered)
        self.assertNotIn("agents.max_threads", rendered)
        self.assertIn(
            "[features.multi_agent_v2] "
            "# codex-workflow-custom-owned: V2 feature table",
            rendered,
        )
        self.assertEqual(remove_workflow_owned_config(rendered), "")

    def test_toml_patch_nondefault_child_limit_adds_parent_slot(self) -> None:
        rendered = patch_codex_config("", self.workflow_config(12))
        parsed = tomllib.loads(rendered)
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            13,
        )
        self.assertNotIn("max_threads", parsed.get("agents", {}))

    def test_toml_patch_fails_closed_on_multiline_basic_string_features_text(self) -> None:
        original = 'note = """\n[features]\nnot a real table\n"""\n'
        with self.assertRaisesRegex(ValidationError, "ambiguous \\[features]"):
            patch_codex_config(original, self.workflow_config())

    def test_toml_patch_fails_closed_on_multiline_literal_string_agents_text(self) -> None:
        original = "note = '''\n[agents]\nnot a real table\n'''\n"
        with self.assertRaisesRegex(ValidationError, "ambiguous \\[agents]"):
            patch_codex_config(original, self.workflow_config())

    def test_toml_patch_real_feature_and_agent_tables_round_trip(self) -> None:
        original = (
            "[features]\n"
            "unrelated_feature = true\n\n"
            "[agents]\n"
            "interrupt_message = true\n"
        )
        rendered = patch_codex_config(original, self.workflow_config())
        parsed = tomllib.loads(rendered)
        self.assertTrue(parsed["features"]["unrelated_feature"])
        self.assertTrue(parsed["features"]["multi_agent_v2"]["enabled"])
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            21,
        )
        self.assertTrue(parsed["agents"]["interrupt_message"])
        self.assertNotIn("max_threads", parsed["agents"])
        self.assertEqual(remove_workflow_owned_config(rendered), original)

    def test_toml_patch_migrates_owned_legacy_v1_capacity_and_v2_boolean(self) -> None:
        original = (
            'model = "custom"\n\n'
            "[features] # codex-workflow-custom-owned: features table\n"
            "multi_agent_v2 = true "
            "# codex-workflow-custom-owned: features.multi_agent_v2\n"
            "keep_feature = true\n\n"
            "[agents] # codex-workflow-custom-owned: agents table\n"
            "max_threads = 20 "
            "# codex-workflow-custom-owned: agents.max_threads\n"
            "keep_agent = true\n"
        )
        rendered = patch_codex_config(original, self.workflow_config())
        parsed = tomllib.loads(rendered)
        self.assertTrue(parsed["features"]["keep_feature"])
        self.assertTrue(parsed["agents"]["keep_agent"])
        self.assertNotIn("max_threads", parsed["agents"])
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            21,
        )
        self.assertNotIn("codex-workflow-custom-owned: agents", rendered)
        self.assertNotIn("codex-workflow-custom-owned: features table", rendered)
        self.assertEqual(
            remove_workflow_owned_config(rendered),
            'model = "custom"\n\n'
            "[features]\n"
            "keep_feature = true\n\n"
            "[agents]\n"
            "keep_agent = true\n",
        )

    def test_toml_patch_migrates_empty_owned_legacy_tables(self) -> None:
        original = (
            'model = "custom"\n'
            "[features] # codex-workflow-custom-owned: features table\n"
            "multi_agent_v2 = true "
            "# codex-workflow-custom-owned: features.multi_agent_v2\n"
            "[agents] # codex-workflow-custom-owned: agents table\n"
            "max_threads = 20 "
            "# codex-workflow-custom-owned: agents.max_threads\n"
        )
        rendered = patch_codex_config(original, self.workflow_config())
        parsed = tomllib.loads(rendered)
        self.assertNotIn("agents", parsed)
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            21,
        )
        self.assertEqual(remove_workflow_owned_config(rendered), 'model = "custom"\n')

    def test_toml_patch_rejects_any_unowned_legacy_v1_capacity(self) -> None:
        originals = (
            "[agents]\nmax_threads = 20 # user capacity\n",
            "[agents]\nmax_threads = 7 # user capacity\n",
            "agents.max_threads = 20 # user capacity\n",
            "agents.max_threads = 7 # user capacity\n",
            "agents = { max_threads = 20 } # user capacity\n",
            "agents = { max_threads = 7 } # user capacity\n",
        )
        for original in originals:
            with self.subTest(original=original):
                with self.assertRaisesRegex(ValidationError, "legacy V1 capacity field"):
                    patch_codex_config(original, self.workflow_config())

    def test_toml_patch_preserves_agents_content_without_managing_enabled(self) -> None:
        originals = (
            "[agents]\ninterrupt_message = true\n",
            "agents.interrupt_message = true\n",
            "agents = { interrupt_message = true }\n",
            '[agents.reviewer]\ndescription = "Reviewer"\n',
        )
        for original in originals:
            with self.subTest(original=original):
                rendered = patch_codex_config(original, self.workflow_config())
                parsed = tomllib.loads(rendered)
                self.assertNotIn("max_threads", parsed["agents"])
                self.assertNotIn("enabled", parsed["agents"])
                self.assertEqual(remove_workflow_owned_config(rendered), original)

    def test_toml_patch_adds_owned_capacity_to_user_v2_table(self) -> None:
        original = (
            "[features.multi_agent_v2]\n"
            "enabled = true # user enablement\n"
            'keep = "user"\n'
        )
        rendered = patch_codex_config(original, self.workflow_config())
        parsed = tomllib.loads(rendered)
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            21,
        )
        self.assertIn(
            "# codex-workflow-custom-owned: V2 "
            "max_concurrent_threads_per_session",
            rendered,
        )
        self.assertNotIn("enabled = true # codex-workflow-custom-owned", rendered)
        self.assertEqual(remove_workflow_owned_config(rendered), original)

    def test_toml_patch_preserves_fully_satisfied_unowned_v2_forms(self) -> None:
        originals = (
            "[features.multi_agent_v2]\n"
            "enabled = true\n"
            "max_concurrent_threads_per_session = 21\n",
            "features.multi_agent_v2 = { enabled = true, "
            "max_concurrent_threads_per_session = 21 }\n",
            "features = { multi_agent_v2 = { enabled = true, "
            "max_concurrent_threads_per_session = 21 }, unrelated = true }\n",
        )
        for original in originals:
            with self.subTest(original=original):
                rendered = patch_codex_config(original, self.workflow_config())
                self.assertEqual(rendered, original)
                self.assertNotIn("codex-workflow-custom-owned", rendered)
                self.assertEqual(remove_workflow_owned_config(rendered), original)

    def test_toml_patch_rejects_conflicting_unowned_v2_capacity(self) -> None:
        originals = (
            "[features.multi_agent_v2]\n"
            "enabled = true\n"
            "max_concurrent_threads_per_session = 20\n",
            "features.multi_agent_v2 = { enabled = true, "
            "max_concurrent_threads_per_session = 7 }\n",
        )
        for original in originals:
            with self.subTest(original=original):
                with self.assertRaisesRegex(
                    ValidationError, "max_concurrent_threads_per_session.*already set"
                ):
                    patch_codex_config(original, self.workflow_config())

    def test_toml_patch_rejects_capacityless_scalar_and_inline_v2(self) -> None:
        originals = (
            "[features]\nmulti_agent_v2 = true\n",
            "features.multi_agent_v2 = true\n",
            "features = { multi_agent_v2 = true }\n",
            "features.multi_agent_v2 = { enabled = true }\n",
        )
        for original in originals:
            with self.subTest(original=original):
                with self.assertRaisesRegex(ValidationError, "no V2 session capacity"):
                    patch_codex_config(original, self.workflow_config())

    def test_toml_patch_rejects_unowned_v2_false_without_mutation(self) -> None:
        originals = (
            "[features]\nmulti_agent_v2 = false\n",
            "[features.multi_agent_v2]\nenabled = false\nkeep = 7\n",
            "features.multi_agent_v2 = { enabled = false, "
            "max_concurrent_threads_per_session = 21 }\n",
            "features = { multi_agent_v2 = false }\n",
        )
        for original in originals:
            with self.subTest(original=original):
                with self.assertRaisesRegex(ValidationError, "explicitly disabled"):
                    patch_codex_config(original, self.workflow_config())

    def test_toml_patch_updates_owned_v2_capacity_without_duplicate(self) -> None:
        rendered = patch_codex_config("", self.workflow_config())
        updated = patch_codex_config(rendered, self.workflow_config(12))
        parsed = tomllib.loads(updated)
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            13,
        )
        self.assertEqual(updated.count("max_concurrent_threads_per_session ="), 1)
        self.assertNotIn("agents.max_threads", updated)
        self.assertEqual(remove_workflow_owned_config(updated), "")

    def test_toml_remove_preserves_foreign_content_added_to_created_v2_table(self) -> None:
        rendered = patch_codex_config("", self.workflow_config())
        rendered += 'keep_feature = "foreign"\n'
        removed = remove_workflow_owned_config(rendered)
        self.assertEqual(
            removed,
            "[features.multi_agent_v2]\n"
            'keep_feature = "foreign"\n',
        )

    def test_toml_remove_supports_exact_legacy_owned_markers(self) -> None:
        original = (
            'model = "custom"\n'
            "[features] # codex-workflow-custom-owned: features table\n"
            "multi_agent_v2 = true "
            "# codex-workflow-custom-owned: features.multi_agent_v2\n"
            "[agents] # codex-workflow-custom-owned: agents table\n"
            "max_threads = 20 "
            "# codex-workflow-custom-owned: agents.max_threads\n"
        )
        self.assertEqual(remove_workflow_owned_config(original), 'model = "custom"\n')

    def test_opencodex_shaped_v2_compatible_config_survives_round_trip(self) -> None:
        original = (
            'openai_base_url = "http://127.0.0.1:8765/v1"\n'
            'model = "synthetic/deep-model"\n'
            'model_catalog_json = "C:/synthetic/catalog.json"\n\n'
            "[features]\n"
            "unrelated_feature = true\n\n"
            "[agents]\n"
            "interrupt_message = true\n"
            "job_max_runtime_seconds = 900\n"
        )
        rendered = patch_codex_config(original, self.workflow_config())
        parsed = tomllib.loads(rendered)
        self.assertEqual(parsed["openai_base_url"], "http://127.0.0.1:8765/v1")
        self.assertTrue(parsed["features"]["unrelated_feature"])
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            21,
        )
        self.assertEqual(parsed["agents"]["job_max_runtime_seconds"], 900)
        self.assertNotIn("max_threads", parsed["agents"])
        self.assertEqual(remove_workflow_owned_config(rendered), original)

    def test_toml_patch_dotted_features_round_trip(self) -> None:
        original = "features.unrelated = true\n"
        rendered = patch_codex_config(original, self.workflow_config())
        parsed = tomllib.loads(rendered)
        self.assertTrue(parsed["features"]["unrelated"])
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            21,
        )
        self.assertEqual(remove_workflow_owned_config(rendered), original)

    def test_toml_patch_feature_subtable_round_trip(self) -> None:
        original = "[features.other]\nkeep = true\n"
        rendered = patch_codex_config(original, self.workflow_config())
        parsed = tomllib.loads(rendered)
        self.assertTrue(parsed["features"]["other"]["keep"])
        self.assertEqual(
            parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"],
            21,
        )
        self.assertEqual(remove_workflow_owned_config(rendered), original)

    def test_toml_patch_inline_features_without_v2_fails_closed(self) -> None:
        original = "features = { unrelated = true }\n"
        with self.assertRaisesRegex(
            ValidationError, "inline table without multi_agent_v2"
        ):
            patch_codex_config(original, self.workflow_config())

    def test_toml_patch_rejects_ownership_marker_drift(self) -> None:
        invalid_inputs = (
            "[agents] # codex-workflow-custom-owned: agents table\n"
            "max_threads = 20\n",
            "[features] # codex-workflow-custom-owned: features table\n"
            "multi_agent_v2 = true\n",
            "[features.multi_agent_v2] "
            "# codex-workflow-custom-owned: V2 feature table\n"
            "enabled = true "
            "# codex-workflow-custom-owned: features.multi_agent_v2\n",
            "[features.multi_agent_v2]\n"
            "enabled = true\n"
            "# codex-workflow-custom-owned: V2 "
            "max_concurrent_threads_per_session\n",
        )
        for original in invalid_inputs:
            with self.subTest(original=original):
                with self.assertRaises(ValidationError):
                    patch_codex_config(original, self.workflow_config())

    def test_toml_remove_rejects_malformed_v2_ownership_marker(self) -> None:
        rendered = patch_codex_config("", self.workflow_config())
        malformed = rendered.replace(
            "# codex-workflow-custom-owned: V2 "
            "max_concurrent_threads_per_session",
            "# codex-workflow-custom-owned: V2 "
            "max_concurrent_threads_per_session extra",
        )
        with self.assertRaisesRegex(ValidationError, "capacity ownership marker"):
            remove_workflow_owned_config(malformed)

    def test_toml_patch_is_idempotent(self) -> None:
        once = patch_codex_config("[agents]\nkeep = true\n", self.workflow_config())
        self.assertEqual(patch_codex_config(once, self.workflow_config()), once)

    def test_toml_remove_never_infers_legacy_key_ownership(self) -> None:
        original = (
            'model = "custom"\n\n'
            "[agents]\n"
            "enabled = true\n"
            "max_threads = 20\n"
            "keep_agent = true\n\n"
            "[features.multi_agent_v2]\n"
            "enabled = true\n"
            "max_concurrent_threads_per_session = 21\n"
            'keep_feature = "keep"\n'
        )
        self.assertEqual(remove_workflow_owned_config(original), original)

    def test_heavy_snapshot_is_rendered_from_config(self) -> None:
        config = WorkflowConfig.from_mapping(
            json.loads(
                (PACKAGE / "resources" / "workflow_config.default.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        rendered = render_heavy_route(
            (PACKAGE / "heavy_route.md").read_text(encoding="utf-8"), config
        )
        self.assertIn("Maximum concurrent child workers: `20`", rendered)
        self.assertIn("Default executor: `executor_luna` (`xhigh`", rendered)
        self.assertNotIn("End-of-Session context fork", rendered)
        self.assertIn(
            'fork_turns="200"',
            (PACKAGE / "end_of_session.md").read_text(encoding="utf-8"),
        )


class CodexHomeInstructionContractTests(unittest.TestCase):
    """CODEX_HOME-aware workflow-resource lookup for managed instructions."""

    MANAGED_INSTRUCTION_FILES = (
        "AGENTS.md",
        "user_AGENTS.md",
        "heavy_route.md",
        "medium_route.md",
        "install.md",
        "update.md",
        "remove.md",
        "enable.md",
        "disable.md",
        "configuration_guide.md",
        "personalization_guide.md",
    )

    RULE_CARRYING_FILES = tuple(
        name
        for name in MANAGED_INSTRUCTION_FILES
        if name not in {"heavy_route.md", "medium_route.md"}
    )

    @classmethod
    def instruction_text(cls, name: str) -> str:
        return (PACKAGE / name).read_text(encoding="utf-8")

    def test_default_home_contract_keeps_codex_fallback(self) -> None:
        for name in self.RULE_CARRYING_FILES:
            with self.subTest(name=name):
                self.assertIn(
                    "otherwise use `~/.codex`",
                    " ".join(self.instruction_text(name).split()),
                )

    def test_custom_codex_home_contract_requires_precedence(self) -> None:
        for name in self.RULE_CARRYING_FILES:
            with self.subTest(name=name):
                self.assertIn(
                    "non-empty `CODEX_HOME` environment variable",
                    " ".join(self.instruction_text(name).split()),
                )

    def test_managed_instructions_never_bind_lookup_to_default_home(self) -> None:
        for name in self.MANAGED_INSTRUCTION_FILES:
            with self.subTest(name=name):
                self.assertNotIn(
                    "~/.codex/codex_workflow/", self.instruction_text(name)
                )

    def test_route_lookups_use_resolved_runtime_directory(self) -> None:
        agents = self.instruction_text("AGENTS.md")
        self.assertNotIn("~/.codex/codex_workflow/heavy_route.md", agents)
        self.assertNotIn("~/.codex/codex_workflow/medium_route.md", agents)
        self.assertIn("<Codex home>/codex_workflow/heavy_route.md", agents)
        self.assertIn("<Codex home>/codex_workflow/medium_route.md", agents)

    def test_explorer_and_end_of_session_lookups_use_resolved_runtime(self) -> None:
        agents = self.instruction_text("AGENTS.md")
        self.assertIn("<Codex home>/codex_workflow/explorer_companion.md", agents)
        self.assertIn("<Codex home>/codex_workflow/end_of_session.md", agents)
        for route in ("heavy_route.md", "medium_route.md"):
            with self.subTest(route=route):
                text = self.instruction_text(route)
                self.assertNotIn(
                    "~/.codex/codex_workflow/end_of_session.md", text
                )
                self.assertIn(
                    "<Codex home>/codex_workflow/end_of_session.md", text
                )

    def test_user_command_guides_use_resolved_runtime_directory(self) -> None:
        user_agents = self.instruction_text("user_AGENTS.md")
        self.assertNotIn("~/.codex/codex_workflow/", user_agents)
        for guide in (
            "install.md",
            "update.md",
            "remove.md",
            "configuration_guide.md",
            "personalization_guide.md",
            "disable.md",
            "enable.md",
        ):
            with self.subTest(guide=guide):
                self.assertIn(
                    f"<Codex home>/codex_workflow/{guide}", user_agents
                )

    def test_cli_home_resolution_respects_codex_home_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            custom = Path(temporary) / "custom-codex-home"
            with mock.patch.dict(os.environ, {"CODEX_HOME": str(custom)}):
                self.assertEqual(workflow_cli._default_codex_home(), custom)
            with mock.patch.dict(os.environ, {"CODEX_HOME": ""}):
                self.assertEqual(
                    workflow_cli._default_codex_home(), Path.home() / ".codex"
                )
        with mock.patch.dict(os.environ):
            os.environ.pop("CODEX_HOME", None)
            self.assertEqual(
                workflow_cli._default_codex_home(), Path.home() / ".codex"
            )

    def test_custom_codex_home_materializes_resources_and_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_home = root / "isolated-codex-home"
            project_root = root / "project"
            project_root.mkdir()
            runtime = RuntimePaths(codex_home)
            project = ProjectPaths(project_root)
            package = PackageLayout.resolve(PACKAGE)
            plan_bootstrap(package, runtime, project).apply()
            self.assertTrue((runtime.runtime / "workflow.py").is_file())
            self.assertTrue((runtime.runtime / "heavy_route.md").is_file())
            self.assertTrue((runtime.agents / "executor_luna.toml").is_file())
            self.assertTrue(runtime.config_toml.is_file())
            self.assertTrue(runtime.user_agents.is_file())
            for relative in (
                "templates/AGENTS.md",
                "user_AGENTS.md",
                "heavy_route.md",
                "medium_route.md",
            ):
                with self.subTest(relative=relative):
                    text = (runtime.runtime / relative).read_text(
                        encoding="utf-8"
                    )
                    self.assertNotIn("~/.codex/codex_workflow/", text)
            installed = runtime.user_agents.read_text(encoding="utf-8")
            self.assertNotIn("~/.codex/codex_workflow/", installed)
            self.assertIn("otherwise use `~/.codex`", installed)
            entry = project.active.read_text(encoding="utf-8")
            self.assertIn("<Codex home>/codex_workflow/heavy_route.md", entry)
            self.assertIn("otherwise use `~/.codex`", entry)


class TransactionTests(unittest.TestCase):
    def test_failed_transaction_restores_all_targets(self) -> None:
        from runtime import transaction

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first.write_bytes(b"old")
            original_write = transaction._atomic_write
            calls = 0

            def fail_once(path: Path, content: bytes, mode: int) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected failure")
                original_write(path, content, mode)

            with mock.patch("runtime.transaction._atomic_write", side_effect=fail_once):
                with self.assertRaises(TransactionError):
                    apply([Mutation(first, b"new"), Mutation(second, b"created")])
            self.assertEqual(first.read_bytes(), b"old")
            self.assertFalse(second.exists())


class LifecycleIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.codex_home = self.root / "codex-home"
        self.project_root = self.root / "project"
        self.project_root.mkdir()
        self.runtime = RuntimePaths(self.codex_home)
        self.project = ProjectPaths(self.project_root)
        self.package = PackageLayout.resolve(PACKAGE)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def bootstrap(self, *, existing_agents: str | None = None) -> OperationPlan:
        if existing_agents is not None:
            self.project.active.write_text(existing_agents, encoding="utf-8")
        plan = plan_bootstrap(self.package, self.runtime, self.project)
        self.assertFalse(self.codex_home.exists())
        plan.apply()
        return plan

    def incoming_package(self, directory: str, version: str | None = None) -> PackageLayout:
        version = version or PACKAGE_VERSION
        incoming_root = self.root / directory / "codex_workflow"
        shutil.copytree(
            PACKAGE,
            incoming_root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (incoming_root / "VERSION").write_text(f"{version}\n", encoding="utf-8")
        user_agents = (incoming_root / "user_AGENTS.md").read_text(encoding="utf-8")
        (incoming_root / "user_AGENTS.md").write_text(
            user_agents.replace(
                f"codex-workflow-version: {PACKAGE_VERSION}",
                f"codex-workflow-version: {version}",
            ),
            encoding="utf-8",
        )
        return PackageLayout.resolve(incoming_root)

    def test_bootstrap_imports_existing_agents_and_materializes_runtime(self) -> None:
        plan = self.bootstrap(
            existing_agents="# Existing instructions\nKeep local policy.\n"
        )
        entry = self.project.active.read_text(encoding="utf-8")
        self.assertEqual(
            extract(entry, PROJECT_LOCAL),
            "# Existing instructions\nKeep local policy.",
        )
        self.assertTrue((self.runtime.runtime / "workflow.py").is_file())
        self.assertTrue((self.runtime.runtime / "templates" / "AGENTS.md").is_file())
        self.assertTrue((self.runtime.agents / "executor_luna.toml").is_file())
        self.assertTrue((self.runtime.agents / "executor_terra.toml").is_file())
        self.assertTrue((self.runtime.agents / "end_of_session.toml").is_file())
        materialized_heavy = (self.runtime.runtime / "heavy_route.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("agent_type", materialized_heavy)
        self.assertIn("task name alone is invalid role binding", materialized_heavy)
        materialized_handoff = (
            self.runtime.runtime / "end_of_session.md"
        ).read_text(encoding="utf-8")
        materialized_handoff_worker = (
            self.runtime.agents / "end_of_session.toml"
        ).read_text(encoding="utf-8")
        for text in (materialized_handoff, materialized_handoff_worker):
            self.assertIn("read-only", text.lower())
            self.assertNotRegex(
                text,
                r"\bgit\s+(?:add|commit|push|reset|stash|checkout|clean)\b",
            )
        materialized = self.runtime.config_toml.read_text(encoding="utf-8")
        parsed_config = tomllib.loads(materialized)
        self.assertTrue(parsed_config["features"]["multi_agent_v2"]["enabled"])
        self.assertEqual(
            parsed_config["features"]["multi_agent_v2"][
                "max_concurrent_threads_per_session"
            ],
            21,
        )
        self.assertNotIn("max_threads", parsed_config.get("agents", {}))
        self.assertNotIn("enabled", parsed_config.get("agents", {}))
        installed_user_agents = self.runtime.user_agents.read_text(encoding="utf-8")
        self.assertNotIn("auto-check-update", installed_user_agents)
        self.assertNotIn("check-update", installed_user_agents)
        self.assertEqual(len(plan.agent_actions), 1)
        action = plan.agent_actions[0]
        self.assertEqual(action["role"], "doc-writer")
        self.assertTrue(action["required"])
        self.assertEqual(set(action["files"]), set(action["framework"]))
        self.assertEqual(
            action["required_context_files"],
            [
                "project_structure.md",
                "project_overview.md",
                "project_core_tech.md",
            ],
        )

        repeated = plan_project_install(self.package, self.project)
        self.assertEqual(len(repeated.agent_actions), 1)
        self.assertTrue(repeated.agent_actions[0]["required"])
        self.assertEqual(
            set(repeated.agent_actions[0]["files"]),
            set(repeated.agent_actions[0]["framework"]),
        )
        self.assertEqual(repeated.agent_actions[0]["created_files"], [])
        self.assertEqual(
            set(repeated.agent_actions[0]["recovery_files"]),
            set(repeated.agent_actions[0]["framework"]),
        )

    def test_bootstrap_state_uses_content_identity_not_semantic_version(self) -> None:
        plan = self.bootstrap()
        state = json.loads(
            (self.runtime.runtime / "install_state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["source_id"], self.package.source_id)
        self.assertNotIn("version", state)
        self.assertEqual(plan.details["source_id"], self.package.source_id)
        self.assertTrue(
            (self.runtime.runtime / ".source_backup" / self.package.source_id).is_dir()
        )

    def test_changed_source_without_version_bump_gets_new_identity(self) -> None:
        self.bootstrap()
        unchanged = plan_update(self.package, self.runtime, self.project)
        self.assertEqual(unchanged.details["to_source_id"], self.package.source_id)
        unchanged.apply()

        incoming = self.incoming_package("same-version-change")
        incoming.project_template.write_text(
            incoming.project_template.read_text(encoding="utf-8").replace(
                "## Working State", "## Working State (local source change)"
            ),
            encoding="utf-8",
        )
        incoming = PackageLayout.resolve(incoming.root)
        self.assertEqual(incoming.legacy_version, self.package.legacy_version)
        self.assertNotEqual(incoming.source_id, self.package.source_id)
        plan_update(incoming, self.runtime, self.project).apply()

        state = json.loads(
            (self.runtime.runtime / "install_state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["source_id"], incoming.source_id)
        self.assertNotIn("version", state)
        self.assertTrue(
            (self.runtime.runtime / ".source_backup" / self.package.source_id).is_dir()
        )
        self.assertTrue(
            (self.runtime.runtime / ".source_backup" / incoming.source_id).is_dir()
        )

    def test_legacy_workflow_version_state_migrates_from_version_snapshot(self) -> None:
        self.bootstrap()
        current_snapshot = self.runtime.runtime / ".source_backup" / self.package.source_id
        legacy_snapshot = self.runtime.runtime / ".source_backup" / "1.1.2"
        shutil.copytree(current_snapshot, legacy_snapshot)
        (legacy_snapshot / "VERSION").write_text("1.1.2\n", encoding="utf-8")
        legacy_agents = (legacy_snapshot / "user_AGENTS.md").read_text(encoding="utf-8")
        (legacy_snapshot / "user_AGENTS.md").write_text(
            legacy_agents.replace("codex-workflow-version: 1.1.3", "codex-workflow-version: 1.1.2"),
            encoding="utf-8",
        )
        runtime_state_path = self.runtime.runtime / "install_state.json"
        runtime_state = json.loads(runtime_state_path.read_text(encoding="utf-8"))
        runtime_state.pop("source_id")
        runtime_state["version"] = "1.1.2"
        runtime_state_path.write_text(json.dumps(runtime_state) + "\n", encoding="utf-8")
        self.assertEqual(
            PackageLayout.resolve(self.runtime.runtime).source_id,
            PackageLayout.resolve(legacy_snapshot, allow_legacy=True).source_id,
        )
        state_path = self.project.state
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.pop("source_id")
        state["workflow_version"] = "1.1.2"
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

        incoming = self.incoming_package("legacy-state-incoming")
        plan_update(incoming, self.runtime, self.project).apply()
        migrated = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["source_id"], incoming.source_id)
        self.assertNotIn("workflow_version", migrated)

    def test_package_without_version_uses_source_identity(self) -> None:
        source_root = self.root / "versionless" / "codex_workflow"
        shutil.copytree(
            PACKAGE,
            source_root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (source_root / "VERSION").unlink()
        user_agents = (source_root / "user_AGENTS.md").read_text(encoding="utf-8")
        (source_root / "user_AGENTS.md").write_text(
            "\n".join(
                line
                for line in user_agents.splitlines()
                if "codex-workflow-version:" not in line
            )
            + "\n",
            encoding="utf-8",
        )
        package = PackageLayout.resolve(source_root)
        self.assertIsNone(package.legacy_version)
        self.assertTrue(PackageLayout.is_source_id(package.source_id))
        runtime = RuntimePaths(self.root / "versionless-home")
        project = ProjectPaths(self.root / "versionless-project")
        project.root.mkdir()
        plan = plan_bootstrap(package, runtime, project)
        self.assertEqual(plan.details["source_id"], package.source_id)
        plan.apply()
        state = json.loads((runtime.runtime / "install_state.json").read_text())
        self.assertEqual(state["source_id"], package.source_id)
        self.assertNotIn("version", state)

    def test_bootstrap_cleans_project_staging_and_updates_gitignore(self) -> None:
        staging = self.project_root / "Codex_Workflow"
        (staging / "nested").mkdir(parents=True)
        (staging / "nested" / "package.txt").write_text("staged", encoding="utf-8")
        (self.project_root / ".gitignore").write_text("# local rules\n", encoding="utf-8")

        self.bootstrap()

        self.assertFalse(staging.exists())
        gitignore = (self.project_root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("# local rules\n", gitignore)
        for entry in (
            "agent_docs/",
            ".codex_workflow_hidden_resources/",
            "AGENTS.md",
        ):
            self.assertEqual(gitignore.splitlines().count(entry), 1)

        # A repeated project install is idempotent and does not duplicate rules.
        plan_project_install(self.package, self.project).apply()
        repeated = (self.project_root / ".gitignore").read_text(encoding="utf-8")
        for entry in (
            "agent_docs/",
            ".codex_workflow_hidden_resources/",
            "AGENTS.md",
        ):
            self.assertEqual(repeated.splitlines().count(entry), 1)

    def test_unactivated_workers_are_materialized_for_codex(self) -> None:
        self.bootstrap()
        for worker in self.package.worker_names:
            self.assertTrue((self.runtime.agents / f"{worker}.toml").is_file())
            self.assertTrue(
                (self.runtime.runtime / "templates" / "agents" / f"{worker}.toml").is_file()
            )
        state = json.loads((self.runtime.runtime / "install_state.json").read_text())
        self.assertEqual(set(state["owned_workers"]), self.package.worker_names)

    def test_configure_switches_default_executor_without_touching_local_region(self) -> None:
        self.bootstrap(existing_agents="Local policy.\n")
        plan = plan_configure(
            self.runtime,
            {
                "default_executor": "executor_terra",
                "default_executor_reasoning_effort": "max",
                "max_concurrent_workers": 7,
            },
        )
        plan.apply()
        configured = json.loads(
            (self.runtime.runtime / "workflow_config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(configured["default_executor"], "executor_terra")
        self.assertEqual(configured["max_concurrent_workers"], 7)
        self.assertNotIn("end_of_session_context_turns", configured)
        self.assertIn(
            'fork_turns="200"',
            (self.runtime.runtime / "end_of_session.md").read_text(encoding="utf-8"),
        )
        self.assertTrue((self.runtime.agents / "executor_luna.toml").is_file())
        terra = (self.runtime.agents / "executor_terra.toml").read_text(encoding="utf-8")
        self.assertIn('model_reasoning_effort = "max"', terra)
        self.assertEqual(extract(self.project.active.read_text(), PROJECT_LOCAL), "Local policy.")

    def test_configure_keeps_unactivated_worker_definitions_materialized(self) -> None:
        self.bootstrap()
        current = json.loads(
            (self.runtime.runtime / "workflow_config.json").read_text(encoding="utf-8")
        )
        current["enabled_workers"].remove("explorer")
        plan_configure(self.runtime, {"enabled_workers": current["enabled_workers"]}).apply()
        self.assertTrue((self.runtime.agents / "explorer.toml").is_file())
        state = json.loads((self.runtime.runtime / "install_state.json").read_text())
        self.assertIn("explorer", state["owned_workers"])

    def test_configure_forces_legacy_auto_check_state_disabled(self) -> None:
        self.bootstrap()
        config_path = self.runtime.runtime / "workflow_config.json"
        current = json.loads(config_path.read_text(encoding="utf-8"))
        current["auto_check_update"] = True
        config_path.write_text(json.dumps(current) + "\n", encoding="utf-8")
        plan_configure(self.runtime, {"report_package_size": 251}).apply()
        configured = json.loads(
            config_path.read_text(encoding="utf-8")
        )
        self.assertFalse(configured["auto_check_update"])
        self.assertNotIn("auto-check-update", self.runtime.user_agents.read_text(encoding="utf-8"))

    def test_personalize_and_enable_disable_preserve_regions(self) -> None:
        self.bootstrap(existing_agents="Local policy.\n")
        customized = (PACKAGE / "resources" / "personalization.md").read_text(
            encoding="utf-8"
        ).replace(
            "Status: default\nDecision: Preserve the workflow-managed default Design Principles.",
            "Status: customized\nDecision: Prefer explicit ports and adapters.",
        )
        plan_personalize(self.project, customized).apply()
        entry = self.project.active.read_text(encoding="utf-8")
        self.assertEqual(extract(entry, PROJECT_PERSONALIZATION), "Prefer explicit ports and adapters.")
        self.assertEqual(extract(entry, PROJECT_LOCAL), "Local policy.")
        plan_enable(self.project, enable=False).apply()
        self.assertFalse(self.project.active.exists())
        self.assertTrue(self.project.disabled.exists())
        plan_enable(self.project, enable=True).apply()
        self.assertTrue(self.project.active.exists())
        self.assertFalse(self.project.disabled.exists())

        self.project.personalization.unlink()
        defaults = (PACKAGE / "resources" / "personalization.md").read_text(
            encoding="utf-8"
        )
        plan_personalize(self.project, defaults).apply()
        self.assertEqual(self.project.personalization.read_text(encoding="utf-8"), defaults)
        self.assertEqual(
            extract(self.project.active.read_text(encoding="utf-8"), PROJECT_PERSONALIZATION),
            "",
        )

    def test_install_rejects_personalization_resource_drift(self) -> None:
        self.bootstrap()
        resource = self.project.personalization.read_text(encoding="utf-8")
        self.project.personalization.write_text(
            resource.replace(
                "Status: default\nDecision: Preserve the workflow-managed default Design Principles.",
                "Status: customized\nDecision: Prefer explicit ports and adapters.",
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValidationError):
            plan_project_install(self.package, self.project)

    def test_update_preserves_configuration_managed_and_local_content(self) -> None:
        self.bootstrap(existing_agents="Local policy.\n")
        plan_configure(
            self.runtime,
            {
                "default_executor": "executor_terra",
                "default_executor_reasoning_effort": "high",
                "max_concurrent_workers": 7,
            },
        ).apply()
        installed_config_path = self.runtime.runtime / "workflow_config.json"
        (self.runtime.agents / "executor_luna.toml").write_text(
            "# local worker override\n", encoding="utf-8"
        )
        incoming_root = self.root / "incoming" / "codex_workflow"
        shutil.copytree(PACKAGE, incoming_root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (incoming_root / "VERSION").write_text("1.1.3\n", encoding="utf-8")
        user_agents = (incoming_root / "user_AGENTS.md").read_text(encoding="utf-8")
        (incoming_root / "user_AGENTS.md").write_text(
            user_agents.replace(
                f"codex-workflow-version: {PACKAGE_VERSION}",
                "codex-workflow-version: 1.1.3",
            ),
            encoding="utf-8",
        )
        incoming = PackageLayout.resolve(incoming_root)
        plan_update(incoming, self.runtime, self.project).apply()
        entry = self.project.active.read_text(encoding="utf-8")
        self.assertEqual(extract(entry, PROJECT_LOCAL), "Local policy.")
        self.assertEqual((self.runtime.runtime / "VERSION").read_text(), "1.1.3\n")
        updated_config = json.loads(installed_config_path.read_text(encoding="utf-8"))
        self.assertEqual(updated_config["default_executor"], "executor_terra")
        self.assertEqual(updated_config["max_concurrent_workers"], 7)
        self.assertEqual(updated_config["default_executor_reasoning_effort"], "high")
        self.assertFalse(updated_config["auto_check_update"])
        self.assertNotIn("auto-check-update", self.runtime.user_agents.read_text(encoding="utf-8"))
        self.assertNotIn(
            "local worker override",
            (self.runtime.agents / "executor_luna.toml").read_text(encoding="utf-8"),
        )
        self.assertTrue(any((self.runtime.runtime / ".backups").iterdir()))

    def test_projects_update_against_their_recorded_historical_sources(self) -> None:
        self.bootstrap()
        second_root = self.root / "second-project"
        second_root.mkdir()
        second = ProjectPaths(second_root)
        plan_project_install(self.package, second).apply()

        incoming = self.incoming_package("multi-project-incoming", "1.2.0")
        incoming_template = incoming.project_template.read_text(encoding="utf-8")
        incoming.project_template.write_text(
            incoming_template.replace("## Working State", "## Working State (1.2)"),
            encoding="utf-8",
        )
        incoming = PackageLayout.resolve(incoming.root)

        plan_update(incoming, self.runtime, self.project).apply()
        second_plan = plan_update(incoming, self.runtime, second)
        self.assertEqual(second_plan.details["from_source_id"], incoming.source_id)
        self.assertEqual(
            second_plan.details["project_from_source_id"], self.package.source_id
        )
        second_plan.apply()
        self.assertIn(
            "## Working State (1.2)", second.active.read_text(encoding="utf-8")
        )

    def test_same_legacy_version_projects_resolve_old_snapshot_after_first_update(self) -> None:
        self.bootstrap()
        second_root = self.root / "legacy-second-project"
        second_root.mkdir()
        second = ProjectPaths(second_root)
        plan_project_install(self.package, second).apply()

        legacy_snapshot = self.runtime.runtime / ".source_backup" / PACKAGE_VERSION
        shutil.copytree(
            self.runtime.runtime / ".source_backup" / self.package.source_id,
            legacy_snapshot,
        )
        old_workflow = (legacy_snapshot / "workflow.py").read_bytes()

        # Reconstruct the old install/project state: both projects were made
        # by VERSION 1.1.3 and retain only the legacy project field.
        runtime_state_path = self.runtime.runtime / "install_state.json"
        runtime_state = json.loads(runtime_state_path.read_text(encoding="utf-8"))
        runtime_state.pop("source_id")
        runtime_state["version"] = PACKAGE_VERSION
        runtime_state_path.write_text(json.dumps(runtime_state) + "\n", encoding="utf-8")
        for project in (self.project, second):
            state = json.loads(project.state.read_text(encoding="utf-8"))
            state.pop("source_id")
            state["workflow_version"] = PACKAGE_VERSION
            project.state.write_text(json.dumps(state) + "\n", encoding="utf-8")

        incoming = self.incoming_package("same-legacy-version-incoming")
        incoming.project_template.write_text(
            incoming.project_template.read_text(encoding="utf-8").replace(
                "## Working State", "## Working State (same legacy version)"
            ),
            encoding="utf-8",
        )
        incoming = PackageLayout.resolve(incoming.root)
        self.assertEqual(incoming.legacy_version, PACKAGE_VERSION)
        self.assertNotEqual(incoming.source_id, self.package.source_id)

        # Project A moves the global runtime to the changed source.
        plan_update(incoming, self.runtime, self.project).apply()
        self.assertEqual((legacy_snapshot / "workflow.py").read_bytes(), old_workflow)
        self.assertTrue(
            (self.runtime.runtime / ".source_backup" / incoming.source_id).is_dir()
        )

        # Project B still has only workflow_version=1.1.3. The resolver must
        # use the retained old snapshot, not the new global runtime with the
        # same legacy VERSION.
        second_plan = plan_update(incoming, self.runtime, second)
        self.assertEqual(
            second_plan.details["project_from_source_id"], self.package.source_id
        )
        self.assertNotEqual(
            second_plan.details["project_from_source_id"], incoming.source_id
        )
        second_plan.apply()
        self.assertIn(
            "## Working State (same legacy version)",
            second.active.read_text(encoding="utf-8"),
        )
        migrated = json.loads(second.state.read_text(encoding="utf-8"))
        self.assertEqual(migrated["source_id"], incoming.source_id)
        self.assertNotIn("workflow_version", migrated)
        self.assertEqual((legacy_snapshot / "workflow.py").read_bytes(), old_workflow)

    def test_update_applies_config_migration_without_resetting_user_values(self) -> None:
        self.bootstrap()
        config_path = self.runtime.runtime / "workflow_config.json"
        configured = json.loads(config_path.read_text(encoding="utf-8"))
        configured["schema_version"] = 3
        configured["default_executor_reasoning_effort"] = "max"
        configured["max_concurrent_workers"] = 9
        configured["end_of_session_context_turns"] = 150
        config_path.write_text(json.dumps(configured) + "\n", encoding="utf-8")

        incoming = self.incoming_package("config-migration-incoming", "1.2.0")
        plan_update(incoming, self.runtime, self.project).apply()
        migrated = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], 5)
        self.assertEqual(migrated["default_executor_reasoning_effort"], "max")
        self.assertEqual(migrated["max_concurrent_workers"], 9)
        self.assertIn("executor_pro", migrated["enabled_workers"])
        self.assertIn("reviewer_pro", migrated["enabled_workers"])
        self.assertNotIn("end_of_session_context_turns", migrated)

    def test_cli_install_reports_enabled_disabled_and_stale_states(self) -> None:
        self.bootstrap()
        command = [
            sys.executable,
            "-B",
            str(self.runtime.runtime / "workflow.py"),
            "install",
            "--codex-home",
            str(self.codex_home),
            "--project",
            str(self.project_root),
            "--json",
        ]
        recovery = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(recovery.returncode, 0, recovery.stderr)
        recovery_summary = json.loads(recovery.stdout)
        self.assertTrue(recovery_summary["applied"])
        self.assertEqual(
            set(recovery_summary["agent_actions"][0]["recovery_files"]),
            set(recovery_summary["agent_actions"][0]["framework"]),
        )
        for document in self.project.docs.glob("*.md"):
            document.write_text(
                document.read_text(encoding="utf-8").replace(
                    "<!-- codex-workflow-bootstrap-template -->\n", ""
                ),
                encoding="utf-8",
            )

        enabled = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertEqual(json.loads(enabled.stdout)["status"], "already enabled")
        self.assertEqual(json.loads(enabled.stdout)["instruction"], "No action is required.")

        plan_enable(self.project, enable=False).apply()
        disabled = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertEqual(json.loads(disabled.stdout)["status"], "already disabled")
        self.assertIn("--enable", json.loads(disabled.stdout)["instruction"])

        plan_enable(self.project, enable=True).apply()
        text = self.project.active.read_text(encoding="utf-8")
        self.project.active.write_text(
            text.replace("## Working State", "## Locally Changed Working State"),
            encoding="utf-8",
        )
        stale = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(stale.returncode, 1)
        self.assertIn("--update", json.loads(stale.stdout)["error"])

    def test_update_preserves_disabled_project_state(self) -> None:
        self.bootstrap()
        plan_enable(self.project, enable=False).apply()
        plan_update(
            self.incoming_package("disabled-incoming"),
            self.runtime,
            self.project,
        ).apply()
        self.assertFalse(self.project.active.exists())
        self.assertTrue(self.project.disabled.exists())
        state = json.loads(self.project.state.read_text(encoding="utf-8"))
        self.assertFalse(state["enabled"])

    def test_cli_install_applies_without_confirmation_flag(self) -> None:
        project_root = self.root / "cli-project"
        project_root.mkdir()
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(PACKAGE / "workflow.py"),
                "install",
                "--package-root",
                str(PACKAGE),
                "--codex-home",
                str(self.codex_home),
                "--project",
                str(project_root),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertTrue(summary["applied"])
        self.assertEqual(len(summary["agent_actions"]), 1)
        self.assertTrue(summary["agent_actions"][0]["required"])
        self.assertEqual(
            summary["agent_actions"][0]["required_context_files"],
            [
                "project_structure.md",
                "project_overview.md",
                "project_core_tech.md",
            ],
        )
        self.assertTrue((project_root / "AGENTS.md").is_file())

    def test_remove_requires_second_confirmation_and_cleans_owned_files(self) -> None:
        self.bootstrap(existing_agents="Local policy.\n")
        user_agents = self.runtime.user_agents.read_text(encoding="utf-8")
        self.runtime.user_agents.write_text(
            "# Keep this user policy.\n\n" + user_agents,
            encoding="utf-8",
        )
        config = self.runtime.config_toml.read_text(encoding="utf-8")
        config = config.replace(
            "max_concurrent_threads_per_session = 21 "
            "# codex-workflow-custom-owned: V2 "
            "max_concurrent_threads_per_session",
            "max_concurrent_threads_per_session = 21 "
            "# codex-workflow-custom-owned: V2 "
            "max_concurrent_threads_per_session\n"
            'keep_feature = "keep"',
        )
        config += (
            "[agents]\n"
            "keep_agent = true\n"
            "interrupt_message = true\n"
        )
        self.runtime.config_toml.write_text(
            'openai_base_url = "http://127.0.0.1:8765/v1"\n'
            'model_catalog_json = "C:/synthetic/catalog.json"\n'
            + config,
            encoding="utf-8",
        )
        unrelated_worker = self.runtime.agents / "unrelated.toml"
        unrelated_worker.write_text('model = "keep"\n', encoding="utf-8")

        command = [
            sys.executable,
            "-B",
            str(self.runtime.runtime / "workflow.py"),
            "remove",
            "--codex-home",
            str(self.codex_home),
            "--project",
            str(self.project_root),
            "--json",
        ]
        planned = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(planned.returncode, 0, planned.stderr)
        planned_summary = json.loads(planned.stdout)
        self.assertFalse(planned_summary["applied"])
        self.assertTrue(planned_summary["confirmation_required"])
        self.assertTrue(self.project.active.is_file())
        self.assertTrue(self.runtime.runtime.is_dir())

        confirmed = subprocess.run(
            [*command[:-1], "--confirm", "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
        self.assertTrue(json.loads(confirmed.stdout)["applied"])
        self.assertFalse(self.project.active.exists())
        self.assertFalse(self.project.hidden_dir.exists())
        self.assertTrue((self.project.docs / "project_overview.md").is_file())
        self.assertFalse(self.runtime.runtime.exists())
        self.assertTrue(unrelated_worker.is_file())
        self.assertEqual(
            self.runtime.user_agents.read_text(encoding="utf-8"),
            "# Keep this user policy.\n",
        )
        remaining_config = self.runtime.config_toml.read_text(encoding="utf-8")
        self.assertIn('openai_base_url = "http://127.0.0.1:8765/v1"', remaining_config)
        self.assertIn('model_catalog_json = "C:/synthetic/catalog.json"', remaining_config)
        self.assertIn("keep_agent = true", remaining_config)
        self.assertIn('keep_feature = "keep"', remaining_config)
        self.assertIn("interrupt_message = true", remaining_config)
        self.assertNotIn("max_threads", remaining_config)
        self.assertNotIn("codex-workflow-custom-owned", remaining_config)

    def test_bootstrap_and_remove_preserve_opencodex_shaped_config(self) -> None:
        original = (
            'openai_base_url = "http://127.0.0.1:8765/v1"\n'
            'model_catalog_json = "C:/synthetic/catalog.json"\n\n'
            "[features]\n"
            "unrelated_feature = true\n\n"
            "[agents]\n"
            "# Synthetic V2-compatible OpenCodex content.\n"
            "interrupt_message = true\n"
            "job_max_runtime_seconds = 900\n"
        )
        self.codex_home.mkdir()
        self.runtime.config_toml.write_text(original, encoding="utf-8")
        plan_bootstrap(self.package, self.runtime, self.project).apply()
        configured = self.runtime.config_toml.read_text(encoding="utf-8")
        parsed = tomllib.loads(configured)
        self.assertEqual(parsed["openai_base_url"], "http://127.0.0.1:8765/v1")
        self.assertTrue(parsed["features"]["unrelated_feature"])
        self.assertEqual(
            parsed["features"]["multi_agent_v2"][
                "max_concurrent_threads_per_session"
            ],
            21,
        )
        self.assertTrue(parsed["agents"]["interrupt_message"])
        self.assertEqual(parsed["agents"]["job_max_runtime_seconds"], 900)
        self.assertNotIn("max_threads", parsed["agents"])
        plan_remove(self.runtime, self.project).apply()
        self.assertEqual(self.runtime.config_toml.read_text(encoding="utf-8"), original)

    def test_update_allows_missing_optional_codex_config(self) -> None:
        self.bootstrap()
        self.runtime.config_toml.unlink()
        plan = plan_update(
            self.incoming_package("missing-config-incoming"),
            self.runtime,
            self.project,
        )
        self.assertEqual(plan.operation, "update")

    def test_update_rejects_unsafe_owned_runtime_state(self) -> None:
        self.bootstrap()
        outside = self.root / "outside.txt"
        outside.write_text("keep", encoding="utf-8")
        state_path = self.runtime.runtime / "install_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["owned_runtime_files"] = ["../../outside.txt"]
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
        with self.assertRaises(ValidationError):
            plan_update(
                self.incoming_package("unsafe-state-incoming"),
                self.runtime,
                self.project,
            )
        self.assertTrue(outside.is_file())

    def test_update_without_source_fails_closed(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(PACKAGE / "workflow.py"),
                "update",
                "--codex-home",
                str(self.codex_home),
                "--project",
                str(self.project_root),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("pass --source", json.loads(completed.stdout)["error"])

    def test_legacy_entry_with_edits_requires_reviewed_local_instructions(self) -> None:
        self.bootstrap()
        installed_template_path = self.runtime.runtime / "templates" / "AGENTS.md"
        legacy_template = installed_template_path.read_text(encoding="utf-8")
        legacy_template = legacy_template.replace(
            "<!-- codex-workflow-managed-start -->\n", ""
        ).replace("<!-- codex-workflow-managed-end -->\n\n", "")
        legacy_template = legacy_template.replace(
            "\n<!-- codex-workflow-project-local-instructions-start -->\n"
            "<!-- codex-workflow-project-local-instructions-end -->\n",
            "\n",
        )
        installed_template_path.write_text(legacy_template, encoding="utf-8")
        self.project.active.write_text(
            legacy_template + "\nLocal legacy addition.\n", encoding="utf-8"
        )
        incoming = self.incoming_package("legacy-incoming")
        with self.assertRaises(ValidationError):
            plan_update(incoming, self.runtime, self.project)
        plan_update(
            incoming,
            self.runtime,
            self.project,
            legacy_local_instructions="Local legacy addition.",
        ).apply()
        self.assertEqual(
            extract(self.project.active.read_text(encoding="utf-8"), PROJECT_LOCAL),
            "Local legacy addition.",
        )

    def test_update_rejects_drift_in_workflow_managed_region(self) -> None:
        self.bootstrap()
        entry = self.project.active.read_text(encoding="utf-8")
        self.project.active.write_text(
            entry.replace("## Working State", "## Locally Changed Working State"),
            encoding="utf-8",
        )
        incoming = self.incoming_package("drift-incoming")
        with self.assertRaises(ValidationError):
            plan_update(incoming, self.runtime, self.project)

    def test_installed_launcher_delegates_to_incoming_update_runtime(self) -> None:
        self.bootstrap()
        incoming_root = self.root / "delegated-incoming" / "codex_workflow"
        shutil.copytree(
            PACKAGE,
            incoming_root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (incoming_root / "VERSION").write_text("1.1.3\n", encoding="utf-8")
        user_agents = (incoming_root / "user_AGENTS.md").read_text(encoding="utf-8")
        (incoming_root / "user_AGENTS.md").write_text(
            user_agents.replace(
                f"codex-workflow-version: {PACKAGE_VERSION}",
                "codex-workflow-version: 1.1.3",
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(self.runtime.runtime / "workflow.py"),
                "update",
                "--source",
                str(incoming_root),
                "--codex-home",
                str(self.codex_home),
                "--project",
                str(self.project_root),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["details"]["to_source_id"], PackageLayout.resolve(incoming_root).source_id)
        self.assertTrue(summary["applied"])


class PersonalizationTests(unittest.TestCase):
    def test_only_customized_decisions_are_materialized(self) -> None:
        text = (PACKAGE / "resources" / "personalization.md").read_text(encoding="utf-8")
        self.assertEqual(materialize_personalization(text), "")
        customized = text.replace(
            "Status: default\nDecision: No additional frontend profile.",
            "Status: customized\nDecision: Use the frontend profile.",
        )
        self.assertEqual(materialize_personalization(customized), "Use the frontend profile.")


if __name__ == "__main__":
    unittest.main()
