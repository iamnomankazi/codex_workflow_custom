"""Workflow configuration validation and materialization."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ._toml import tomllib
from .errors import ValidationError
from .markers import EFFECTIVE_CONFIG, replace
from .migrations import migrate_config_resource


DEFAULT_EXECUTORS = {"executor_luna", "executor_terra"}
REASONING_EFFORTS = {"high", "xhigh", "max"}
CONFIG_SCHEMA_VERSION = 4
REQUIRED_WORKERS = {"doc-writer", "end_of_session"}
PLATFORM_MAX_WORKERS = 20


@dataclass(frozen=True)
class WorkflowConfig:
    schema_version: int
    default_executor: str
    default_executor_reasoning_effort: str
    auto_check_update: bool
    max_concurrent_workers: int
    max_executor_sol_instances: int
    report_package_size: int
    enabled_workers: tuple[str, ...]

    @classmethod
    def from_mapping(
        cls, raw: dict[str, Any], *, available_workers: set[str] | None = None
    ) -> "WorkflowConfig":
        expected = {
            "schema_version",
            "default_executor",
            "default_executor_reasoning_effort",
            "auto_check_update",
            "max_concurrent_workers",
            "max_executor_sol_instances",
            "report_package_size",
            "enabled_workers",
        }
        unknown = set(raw) - expected
        missing = expected - set(raw)
        if unknown or missing:
            raise ValidationError(
                f"invalid workflow config keys; missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        if raw["schema_version"] != CONFIG_SCHEMA_VERSION:
            raise ValidationError("unsupported workflow_config schema_version")
        workers_raw = raw["enabled_workers"]
        if not isinstance(workers_raw, list) or not all(
            isinstance(item, str) and item for item in workers_raw
        ):
            raise ValidationError("enabled_workers must be a list of names")
        workers = tuple(workers_raw)
        if len(workers) != len(set(workers)):
            raise ValidationError("enabled_workers contains duplicates")
        default = raw["default_executor"]
        if default not in DEFAULT_EXECUTORS or default not in workers:
            raise ValidationError("default_executor must be enabled luna or terra")
        enabled_defaults = DEFAULT_EXECUTORS.intersection(workers)
        if enabled_defaults != {default}:
            raise ValidationError("exactly the selected default executor must be enabled")
        missing_required = REQUIRED_WORKERS - set(workers)
        if missing_required:
            raise ValidationError(
                f"required workers must remain enabled: {sorted(missing_required)}"
            )
        effort = raw["default_executor_reasoning_effort"]
        if effort not in REASONING_EFFORTS:
            raise ValidationError("invalid default_executor_reasoning_effort")
        auto_check = raw["auto_check_update"]
        if not isinstance(auto_check, bool):
            raise ValidationError("auto_check_update must be a boolean")
        maximum = _positive_int(raw["max_concurrent_workers"], "max_concurrent_workers")
        if maximum > PLATFORM_MAX_WORKERS:
            raise ValidationError(
                f"max_concurrent_workers exceeds platform limit {PLATFORM_MAX_WORKERS}"
            )
        sol_maximum = raw["max_executor_sol_instances"]
        if not isinstance(sol_maximum, int) or isinstance(sol_maximum, bool):
            raise ValidationError("max_executor_sol_instances must be an integer")
        if sol_maximum < 0 or sol_maximum > maximum:
            raise ValidationError("max_executor_sol_instances is outside worker limit")
        if "executor_sol" not in workers and sol_maximum != 0:
            raise ValidationError(
                "max_executor_sol_instances must be zero when executor_sol is disabled"
            )
        report_size = _positive_int(raw["report_package_size"], "report_package_size")
        if available_workers is not None:
            unavailable = set(workers) - available_workers
            if unavailable:
                raise ValidationError(f"missing worker templates: {sorted(unavailable)}")
        return cls(
            CONFIG_SCHEMA_VERSION,
            default,
            effort,
            auto_check,
            maximum,
            sol_maximum,
            report_size,
            workers,
        )

    def to_mapping(self) -> dict[str, Any]:
        value = asdict(self)
        value["enabled_workers"] = list(self.enabled_workers)
        return value

    def to_json(self) -> str:
        return json.dumps(self.to_mapping(), indent=2) + "\n"


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValidationError(f"{name} must be a positive integer")
    return value


def load_config(path: Path, *, templates: Path | None = None) -> WorkflowConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"cannot read workflow config {path}: {error}") from error
    if not isinstance(raw, dict):
        raise ValidationError("workflow config root must be an object")
    available = None
    if templates is not None:
        available = {path.stem for path in templates.glob("*.toml") if path.is_file()}
    return WorkflowConfig.from_mapping(raw, available_workers=available)


def load_migrated_config(
    path: Path, *, defaults: Path, templates: Path
) -> WorkflowConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        default_raw = json.loads(defaults.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"cannot load configuration migration inputs: {error}") from error
    if not isinstance(raw, dict) or not isinstance(default_raw, dict):
        raise ValidationError("configuration migration inputs must be JSON objects")
    migrated = migrate_config_resource(raw, default_raw)
    available = {item.stem for item in templates.glob("*.toml") if item.is_file()}
    return WorkflowConfig.from_mapping(migrated, available_workers=available)


def effective_config_body(config: WorkflowConfig) -> str:
    workers = ", ".join(f"`{name}`" for name in config.enabled_workers)
    return "\n".join(
        [
            "## Effective Workflow Configuration",
            "",
            f"- Default executor: `{config.default_executor}` "
            f"(`{config.default_executor_reasoning_effort}` reasoning effort).",
            f"- Enabled workers: {workers}.",
            f"- Maximum concurrent child workers: `{config.max_concurrent_workers}`.",
            f"- Maximum `executor_sol` workers: `{config.max_executor_sol_instances}`.",
            f"- Maximum worker final-report package: `{config.report_package_size}` words.",
            "",
            "Create only enabled workers and obey these limits.",
        ]
    )


def render_heavy_route(text: str, config: WorkflowConfig) -> str:
    return replace(text, EFFECTIVE_CONFIG, effective_config_body(config))


_EFFORT_LINE = re.compile(
    r'(?m)^model_reasoning_effort\s*=\s*"[^"]+"\s*$'
)


def render_worker_template(text: str, *, worker: str, config: WorkflowConfig) -> str:
    marker = f"# codex-workflow-worker: {worker}"
    if not text.startswith(marker + "\n"):
        raise ValidationError(f"worker template ownership marker mismatch: {worker}")
    if worker == config.default_executor:
        matches = list(_EFFORT_LINE.finditer(text))
        if len(matches) != 1:
            raise ValidationError(f"expected one reasoning effort field in {worker}")
        text = _EFFORT_LINE.sub(
            f'model_reasoning_effort = "{config.default_executor_reasoning_effort}"',
            text,
        )
    tomllib.loads(text)
    return text


def patch_codex_config(text: str, config: WorkflowConfig) -> str:
    parsed: dict[str, Any] = {}
    if text.strip():
        try:
            parsed = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            raise ValidationError(f"existing Codex config is invalid TOML: {error}") from error
    _reject_enabled_multi_agent_v2(parsed)

    lines = text.splitlines()
    agents = parsed.get("agents")
    if agents is not None and not isinstance(agents, dict):
        raise ValidationError("[agents] must be a TOML table")

    bounds = _section_bounds(lines, "agents")
    _validate_ownership_markers(lines, bounds)
    existing = agents.get("max_threads") if isinstance(agents, dict) else None
    has_existing = isinstance(agents, dict) and "max_threads" in agents

    required = config.max_concurrent_workers
    if has_existing:
        if not isinstance(existing, int) or isinstance(existing, bool):
            raise ValidationError("agents.max_threads must be an integer")
        owned_lines = _owned_max_threads_lines(lines, bounds)
        if len(owned_lines) > 1:
            raise ValidationError("ambiguous workflow-owned agents.max_threads definition")
        if not owned_lines:
            if existing != required:
                raise ValidationError(
                    "agents.max_threads is already set to "
                    f"{existing}, but codex-workflow-custom requires {required}; "
                    "change or remove the user/OpenCodex-owned value explicitly"
                )
            return text
        line_index = owned_lines[0]
        replacement = (
            _owned_dotted_max_threads_line(required)
            if _OWNED_DOTTED_MAX_THREADS.fullmatch(lines[line_index])
            else _owned_max_threads_line(required)
        )
        if lines[line_index] == replacement:
            return text
        lines[line_index] = replacement
    elif bounds is not None:
        _, end = bounds
        lines.insert(end, _owned_max_threads_line(required))
    elif _root_inline_agents_lines(lines):
        raise ValidationError(
            "agents is an inline table without max_threads; "
            "codex-workflow-custom cannot add capacity without restructuring "
            "the user-owned inline table"
        )
    elif _root_dotted_agents_lines(lines):
        lines.insert(_root_table_end(lines), _owned_dotted_max_threads_line(required))
    elif isinstance(agents, dict) and _has_agents_subtable(lines):
        lines.append(_owned_agents_header())
        lines.append(_owned_max_threads_line(required))
    elif agents is None:
        lines.append(_owned_agents_header())
        lines.append(_owned_max_threads_line(required))
    else:
        if agents is not None:
            raise ValidationError(
                "agents uses an unsupported TOML representation without max_threads; "
                "codex-workflow-custom cannot add capacity safely"
            )

    rendered = _render_lines(lines, text)
    try:
        tomllib.loads(rendered)
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"generated Codex config is invalid TOML: {error}") from error
    return rendered


_SECTION = re.compile(r"^\s*\[([^]]+)]\s*(?:#.*)?$")
_TABLE_BOUNDARY = re.compile(r"^\s*(?:\[[^]]+]\]|\[[^]]+])\s*(?:#.*)?$")
_KEY = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")
WORKFLOW_OWNED_MAX_THREADS_MARKER = (
    "# codex-workflow-custom-owned: agents.max_threads"
)
WORKFLOW_CREATED_AGENTS_MARKER = (
    "# codex-workflow-custom-owned: agents table"
)
_OWNED_MAX_THREADS = re.compile(
    r"^\s*max_threads\s*=\s*([0-9]+)\s+"
    + re.escape(WORKFLOW_OWNED_MAX_THREADS_MARKER)
    + r"\s*$"
)
_ROOT_DOTTED_AGENTS = re.compile(r"^\s*agents\.[A-Za-z0-9_-]+\s*=")
_ROOT_INLINE_AGENTS = re.compile(r"^\s*agents\s*=")
_OWNED_DOTTED_MAX_THREADS = re.compile(
    r"^\s*agents\.max_threads\s*=\s*([0-9]+)\s+"
    + re.escape(WORKFLOW_OWNED_MAX_THREADS_MARKER)
    + r"\s*$"
)
_OWNED_AGENTS_HEADER = re.compile(
    r"^\s*\[agents]\s+"
    + re.escape(WORKFLOW_CREATED_AGENTS_MARKER)
    + r"\s*$"
)


def _section_bounds(lines: list[str], section: str) -> tuple[int, int] | None:
    headers = [
        index
        for index, line in enumerate(lines)
        if (_SECTION.match(line) and _SECTION.match(line).group(1) == section)
    ]
    if len(headers) > 1:
        raise ValidationError(f"duplicate TOML section [{section}]")
    if not headers:
        return None
    start = headers[0]
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if _TABLE_BOUNDARY.match(lines[index])
        ),
        len(lines),
    )
    return start, end


def _key_lines(
    lines: list[str], bounds: tuple[int, int] | None, key: str
) -> list[int]:
    if bounds is None:
        return []
    start, end = bounds
    matches: list[int] = []
    for index in range(start + 1, end):
        match = _KEY.match(lines[index])
        if match and match.group(1) == key:
            matches.append(index)
    return matches


def _root_table_end(lines: list[str]) -> int:
    return next(
        (index for index, line in enumerate(lines) if _TABLE_BOUNDARY.match(line)),
        len(lines),
    )


def _root_dotted_agents_lines(lines: list[str]) -> list[int]:
    end = _root_table_end(lines)
    return [
        index
        for index in range(end)
        if _ROOT_DOTTED_AGENTS.match(lines[index])
    ]


def _root_inline_agents_lines(lines: list[str]) -> list[int]:
    end = _root_table_end(lines)
    return [
        index
        for index in range(end)
        if _ROOT_INLINE_AGENTS.match(lines[index])
    ]


def _has_agents_subtable(lines: list[str]) -> bool:
    return any(
        match and match.group(1).startswith("agents.")
        for line in lines
        if (match := _SECTION.match(line))
    )


def _owned_max_threads_lines(
    lines: list[str], bounds: tuple[int, int] | None
) -> list[int]:
    explicit = [
        index
        for index in _key_lines(lines, bounds, "max_threads")
        if _OWNED_MAX_THREADS.fullmatch(lines[index])
    ]
    dotted = [
        index
        for index in _root_dotted_agents_lines(lines)
        if _OWNED_DOTTED_MAX_THREADS.fullmatch(lines[index])
    ]
    return explicit + dotted


def _reject_enabled_multi_agent_v2(parsed: dict[str, Any]) -> None:
    features = parsed.get("features")
    if not isinstance(features, dict) or "multi_agent_v2" not in features:
        return
    setting = features["multi_agent_v2"]
    if isinstance(setting, bool):
        enabled = setting
    elif isinstance(setting, dict):
        if "enabled" not in setting or not isinstance(setting["enabled"], bool):
            raise ValidationError(
                "features.multi_agent_v2 must explicitly use a boolean enabled value"
            )
        enabled = setting["enabled"]
    else:
        raise ValidationError("features.multi_agent_v2 must be a boolean or table")
    if enabled:
        raise ValidationError(
            "codex-workflow-custom targets Codex 0.144 V1 and cannot set "
            "agents.max_threads while multi-agent V2 is explicitly enabled; "
            "disable V2 explicitly before configuring this workflow"
        )


def _owned_agents_header() -> str:
    return f"[agents] {WORKFLOW_CREATED_AGENTS_MARKER}"


def _owned_max_threads_line(value: int) -> str:
    return f"max_threads = {value} {WORKFLOW_OWNED_MAX_THREADS_MARKER}"


def _owned_dotted_max_threads_line(value: int) -> str:
    return f"agents.max_threads = {value} {WORKFLOW_OWNED_MAX_THREADS_MARKER}"


def _render_lines(lines: list[str], original: str) -> str:
    newline = "\r\n" if "\r\n" in original else "\n"
    rendered = newline.join(lines)
    if original.endswith(("\n", "\r")) or not original:
        rendered += newline
    return rendered


def _validate_ownership_markers(
    lines: list[str], bounds: tuple[int, int] | None
) -> None:
    max_lines = _key_lines(lines, bounds, "max_threads")
    valid_setting_lines = {
        index for index in max_lines if _OWNED_MAX_THREADS.fullmatch(lines[index])
    }
    valid_setting_lines.update(
        index
        for index in _root_dotted_agents_lines(lines)
        if _OWNED_DOTTED_MAX_THREADS.fullmatch(lines[index])
    )
    marker_lines = {
        index
        for index, line in enumerate(lines)
        if WORKFLOW_OWNED_MAX_THREADS_MARKER in line
    }
    if marker_lines != valid_setting_lines:
        raise ValidationError("malformed codex-workflow-custom max_threads ownership marker")

    valid_header_lines: set[int] = set()
    if bounds is not None and _OWNED_AGENTS_HEADER.fullmatch(lines[bounds[0]]):
        valid_header_lines.add(bounds[0])
    header_marker_lines = {
        index
        for index, line in enumerate(lines)
        if WORKFLOW_CREATED_AGENTS_MARKER in line
    }
    if header_marker_lines != valid_header_lines:
        raise ValidationError("malformed codex-workflow-custom agents-table marker")


def remove_workflow_owned_config(text: str) -> str:
    """Remove only the Codex settings owned by this workflow."""
    if not text.strip():
        return ""
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"existing Codex config is invalid TOML: {error}") from error

    if (
        WORKFLOW_OWNED_MAX_THREADS_MARKER not in text
        and WORKFLOW_CREATED_AGENTS_MARKER not in text
    ):
        return text

    lines = text.splitlines()
    bounds = _section_bounds(lines, "agents")
    _validate_ownership_markers(lines, bounds)
    owned_lines = _owned_max_threads_lines(lines, bounds)
    if len(owned_lines) != 1:
        raise ValidationError("expected one workflow-owned agents.max_threads setting")
    if _OWNED_DOTTED_MAX_THREADS.fullmatch(lines[owned_lines[0]]):
        result = [
            line for index, line in enumerate(lines) if index != owned_lines[0]
        ]
        rendered = _render_lines(result, text) if result else ""
        try:
            tomllib.loads(rendered)
        except tomllib.TOMLDecodeError as error:
            raise ValidationError(
                f"generated Codex config is invalid TOML: {error}"
            ) from error
        return rendered

    if bounds is None:
        raise ValidationError("workflow-owned max_threads requires an [agents] table")
    start, end = bounds
    created_table = WORKFLOW_CREATED_AGENTS_MARKER in lines[start]
    retained_body = [
        line for index, line in enumerate(lines[start + 1 : end], start + 1)
        if index not in owned_lines
    ]
    if created_table and not any(line.strip() for line in retained_body):
        result = lines[:start] + lines[end:]
    else:
        header = "[agents]" if created_table else lines[start]
        result = lines[:start] + [header] + retained_body + lines[end:]

    rendered = _render_lines(result, text) if result else ""
    try:
        tomllib.loads(rendered)
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"generated Codex config is invalid TOML: {error}") from error
    return rendered
