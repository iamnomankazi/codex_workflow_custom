"""Package, user-runtime, and project path contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ._toml import tomllib
from .config import load_config, render_heavy_route
from .errors import ValidationError
from .markers import (
    USER_MANAGED,
    extract,
    validate_project_template,
)
from .personalization import materialize_personalization


PROJECT_ID = "<!-- codex-workflow-id: viettran-edgeAI/codex_workflow -->"
USER_ID = "<!-- codex-workflow-user-id: viettran-edgeAI/codex_workflow -->"
WORKER_MARKER = re.compile(r"^# codex-workflow-worker: ([A-Za-z0-9_-]+)$", re.MULTILINE)
LEGACY_VERSION = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
SOURCE_ID = re.compile(r"sha256-[0-9a-f]{64}")
PROJECT_STATE = "state.json"
USER_STATE = "install_state.json"


@dataclass(frozen=True)
class PackageLayout:
    root: Path
    project_template: Path
    agent_templates: Path
    project_docs: Path

    @classmethod
    def resolve(cls, root: Path, *, allow_legacy: bool = False) -> "PackageLayout":
        root = root.resolve()
        if not (root / "workflow.py").is_file():
            nested = root / "codex_workflow"
            if nested.is_dir() and (nested / "workflow.py").is_file():
                root = nested
            else:
                raise ValidationError(f"package root does not contain workflow.py: {root}")
        if (root / "templates" / "AGENTS.md").is_file():
            layout = cls(
                root,
                root / "templates" / "AGENTS.md",
                root / "templates" / "agents",
                root / "templates" / "project_docs",
            )
        else:
            layout = cls(root, root / "AGENTS.md", root / "agents", root / "project_docs")
        layout.validate(allow_legacy=allow_legacy)
        return layout

    def validate(self, *, allow_legacy: bool = False) -> None:
        symlinks = [
            path
            for path in self.root.rglob("*")
            if path.is_symlink()
            and ".backups" not in path.parts
            and ".source_backup" not in path.parts
        ]
        if symlinks:
            raise ValidationError(f"package contains symlinks: {symlinks[:3]}")
        version = self.legacy_version
        if version is not None and not LEGACY_VERSION.fullmatch(version):
            raise ValidationError(f"invalid legacy package VERSION: {version!r}")
        user_agents = self.root / "user_AGENTS.md"
        if not user_agents.is_file():
            raise ValidationError("package user_AGENTS.md marker is missing")
        user_agents_text = user_agents.read_text(encoding="utf-8")
        if USER_ID not in user_agents_text:
            raise ValidationError("package user_AGENTS.md marker is missing")
        if version is not None and f"<!-- codex-workflow-version: {version} -->" not in user_agents_text:
            raise ValidationError("package version and user marker disagree")
        extract(user_agents_text, USER_MANAGED)
        if not allow_legacy:
            required = [
                "workflow.py",
                "resources/workflow_config.default.json",
                "heavy_route.md",
                "medium_route.md",
                "explorer_companion.md",
                "end_of_session.md",
                "install.md",
                "bootstrap.md",
                "update.md",
                "remove.md",
                "configuration_guide.md",
                "personalization_guide.md",
                "enable.md",
                "disable.md",
                "runtime/__init__.py",
                "runtime/_toml.py",
                "runtime/backup.py",
                "runtime/config.py",
                "runtime/layout.py",
                "runtime/lifecycle.py",
                "runtime/markers.py",
                "runtime/migrations.py",
                "runtime/personalization.py",
                "runtime/plan.py",
                "runtime/project_ops.py",
                "runtime/release.py",
                "runtime/runtime_ops.py",
                "runtime/transaction.py",
                "resources/personalization.md",
            ]
            missing = [relative for relative in required if not (self.root / relative).is_file()]
            if missing:
                raise ValidationError(f"package runtime files missing: {missing}")
            validate_project_template(self.project_template.read_text(encoding="utf-8"))
        required_docs = {
            "project_overview.md",
            "project_core_tech.md",
            "project_structure.md",
            "project_progress.md",
            "project_diary.md",
            "latest_session_work.md",
        }
        present_docs = {path.name for path in self.project_docs.glob("*.md")}
        if not required_docs.issubset(present_docs):
            raise ValidationError(
                f"package project document templates missing: {sorted(required_docs - present_docs)}"
            )
        templates = self.worker_names
        if not templates:
            raise ValidationError("package has no worker templates")
        for worker in templates:
            text = (self.agent_templates / f"{worker}.toml").read_text(encoding="utf-8")
            match = WORKER_MARKER.search(text)
            if not allow_legacy and (match is None or match.group(1) != worker):
                raise ValidationError(f"worker ownership marker missing or wrong: {worker}")
            try:
                tomllib.loads(text)
            except tomllib.TOMLDecodeError as error:
                raise ValidationError(f"invalid worker TOML {worker}: {error}") from error
        if not allow_legacy:
            config = load_config(
                self.default_config, templates=self.agent_templates
            )
            render_heavy_route(
                (self.root / "heavy_route.md").read_text(encoding="utf-8"), config
            )
            materialize_personalization(
                (self.root / "resources" / "personalization.md").read_text(
                    encoding="utf-8"
                )
            )

    @property
    def legacy_version(self) -> str | None:
        version_path = self.root / "VERSION"
        if not version_path.is_file():
            return None
        lines = version_path.read_text(encoding="utf-8").splitlines()
        if len(lines) != 1 or not lines[0]:
            raise ValidationError("VERSION must contain exactly one non-empty line")
        return lines[0]

    @property
    def version(self) -> str:
        """Return the legacy VERSION value for migration compatibility only."""

        version = self.legacy_version
        if version is None:
            raise ValidationError("package has no legacy VERSION")
        return version

    @property
    def source_id(self) -> str:
        """Return a deterministic identity for this local source tree.

        The identity is content based and intentionally independent of semantic
        release numbers. Template files are normalized to their installed
        ``templates/`` paths so a source checkout and its materialized runtime
        produce the same identity.
        """

        # Materialized runtimes render a few source files (notably the Heavy
        # route and user prompt block). Their install manifest records the
        # source identity before rendering, so use that verified identity when
        # resolving an installed runtime rather than hashing generated output.
        if self.project_template.parent.name == "templates":
            state_path = self.root / USER_STATE
            if state_path.is_file():
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    state = None
                recorded = state.get("source_id") if isinstance(state, dict) else None
                if self.is_source_id(recorded):
                    return recorded
                legacy = state.get("version") if isinstance(state, dict) else None
                if isinstance(legacy, str) and LEGACY_VERSION.fullmatch(legacy):
                    snapshot = self.root / ".source_backup" / legacy
                    if snapshot.is_dir():
                        try:
                            return PackageLayout.resolve(
                                snapshot, allow_legacy=True
                            ).source_id
                        except (OSError, ValidationError):
                            pass

        entries: dict[str, Path] = {
            "templates/AGENTS.md": self.project_template,
        }
        entries.update(
            {
                f"templates/agents/{path.name}": path
                for path in self.agent_templates.glob("*")
                if path.is_file()
            }
        )
        entries.update(
            {
                f"templates/project_docs/{path.name}": path
                for path in self.project_docs.glob("*")
                if path.is_file()
            }
        )
        ignored_roots = {
            "agents",
            "project_docs",
            "templates",
            ".source_backup",
            ".backups",
            "__pycache__",
        }
        ignored_files = {"AGENTS.md", "workflow_config.json", USER_STATE}
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root)
            if (
                relative.parts[0] in ignored_roots
                or relative.as_posix() in ignored_files
                or "__pycache__" in relative.parts
                or path.suffix == ".pyc"
            ):
                continue
            entries[relative.as_posix()] = path

        digest = hashlib.sha256()
        for relative, path in sorted(entries.items()):
            relative_bytes = relative.encode("utf-8")
            content = path.read_bytes()
            digest.update(len(relative_bytes).to_bytes(8, "big"))
            digest.update(relative_bytes)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
        return f"sha256-{digest.hexdigest()}"

    @staticmethod
    def is_source_id(value: object) -> bool:
        return isinstance(value, str) and SOURCE_ID.fullmatch(value) is not None

    @property
    def worker_names(self) -> set[str]:
        return {path.stem for path in self.agent_templates.glob("*.toml") if path.is_file()}

    @property
    def default_config(self) -> Path:
        return self.root / "resources" / "workflow_config.default.json"

    @property
    def default_personalization(self) -> Path:
        return self.root / "resources" / "personalization.md"


@dataclass(frozen=True)
class RuntimePaths:
    codex_home: Path

    @property
    def runtime(self) -> Path:
        return self.codex_home / "codex_workflow"

    @property
    def agents(self) -> Path:
        return self.codex_home / "agents"

    @property
    def config_toml(self) -> Path:
        return self.codex_home / "config.toml"

    @property
    def user_agents(self) -> Path:
        return self.codex_home / "AGENTS.md"


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @property
    def active(self) -> Path:
        return self.root / "AGENTS.md"

    @property
    def hidden_dir(self) -> Path:
        return self.root / ".codex_workflow_hidden_resources"

    @property
    def legacy_hidden_dir(self) -> Path:
        """Previous singular resource name retained for existing projects."""
        return self.root / ".codex_workflow_hidden_resource"

    @property
    def workflow_dir(self) -> Path:
        """Select the canonical resource directory, or an existing legacy one."""
        if self.hidden_dir.exists() or not self.legacy_hidden_dir.exists():
            return self.hidden_dir
        return self.legacy_hidden_dir

    @property
    def source_dir(self) -> Path:
        """Project-local package staging directory removed after installation."""
        return self.root / "Codex_Workflow"

    @property
    def gitignore(self) -> Path:
        return self.root / ".gitignore"

    @property
    def disabled(self) -> Path:
        return self.workflow_dir / ".AGENTS.md"

    @property
    def personalization(self) -> Path:
        return self.workflow_dir / "personalization.md"

    @property
    def state(self) -> Path:
        return self.workflow_dir / PROJECT_STATE

    @property
    def docs(self) -> Path:
        return self.root / "agent_docs"
