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
CONFIG_SCHEMA_VERSION = 5
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
            # Retain the legacy field for schema/migration compatibility, but
            # never carry an enabled upstream-check state forward.
            False,
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

    lines = text.splitlines()
    agents = parsed.get("agents")
    if agents is not None and not isinstance(agents, dict):
        raise ValidationError("[agents] must be a TOML table")
    bounds = _section_bounds(lines, "agents")
    if bounds is not None and agents is None:
        raise ValidationError(
            "existing Codex config contains an ambiguous [agents] representation; "
            "cannot verify that agents.max_threads is absent safely"
        )
    _validate_ownership_markers(lines, bounds)
    has_existing = isinstance(agents, dict) and "max_threads" in agents
    if has_existing:
        owned_lines = _owned_max_threads_lines(lines, bounds)
        if len(owned_lines) > 1:
            raise ValidationError("ambiguous workflow-owned agents.max_threads definition")
        if not owned_lines:
            raise ValidationError(
                "agents.max_threads is a user/OpenCodex-owned legacy V1 capacity "
                "field and cannot coexist with required Multi-Agent V2; remove it "
                "explicitly before configuring this workflow"
            )
        lines = _remove_owned_agents(lines)

    features = parsed.get("features")
    if features is not None and not isinstance(features, dict):
        raise ValidationError("[features] must be a TOML table")
    feature_bounds = _section_bounds(lines, "features")
    if feature_bounds is not None and features is None:
        raise ValidationError(
            "existing Codex config contains an ambiguous [features] representation; "
            "cannot materialize the required Multi-Agent V2 setting safely"
        )
    v2_bounds = _section_bounds(lines, "features.multi_agent_v2")
    if v2_bounds is not None and (
        not isinstance(features, dict)
        or not isinstance(features.get("multi_agent_v2"), dict)
    ):
        raise ValidationError(
            "existing Codex config contains an ambiguous "
            "[features.multi_agent_v2] representation; cannot materialize the "
            "required V2 session capacity safely"
        )
    _validate_v2_ownership_markers(lines, feature_bounds, v2_bounds)
    _patch_required_multi_agent_v2(
        lines,
        features,
        feature_bounds,
        v2_bounds,
        config.max_concurrent_workers + 1,
    )

    rendered = _render_lines(lines, text)
    try:
        generated = tomllib.loads(rendered)
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"generated Codex config is invalid TOML: {error}") from error
    _validate_generated_config_postconditions(generated, config)
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
WORKFLOW_OWNED_MULTI_AGENT_V2_MARKER = (
    "# codex-workflow-custom-owned: features.multi_agent_v2"
)
WORKFLOW_CREATED_FEATURES_MARKER = (
    "# codex-workflow-custom-owned: features table"
)
WORKFLOW_OWNED_V2_CAPACITY_MARKER = (
    "# codex-workflow-custom-owned: V2 max_concurrent_threads_per_session"
)
WORKFLOW_CREATED_V2_TABLE_MARKER = (
    "# codex-workflow-custom-owned: V2 feature table"
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
_OWNED_MULTI_AGENT_V2 = re.compile(
    r"^\s*multi_agent_v2\s*=\s*(true|false)\s+"
    + re.escape(WORKFLOW_OWNED_MULTI_AGENT_V2_MARKER)
    + r"\s*$"
)
_ROOT_DOTTED_FEATURES = re.compile(r"^\s*features\.[A-Za-z0-9_-]+\s*=")
_ROOT_INLINE_FEATURES = re.compile(r"^\s*features\s*=")
_OWNED_DOTTED_MULTI_AGENT_V2 = re.compile(
    r"^\s*features\.multi_agent_v2\s*=\s*(true|false)\s+"
    + re.escape(WORKFLOW_OWNED_MULTI_AGENT_V2_MARKER)
    + r"\s*$"
)
_OWNED_V2_ENABLED = re.compile(
    r"^\s*enabled\s*=\s*(true|false)\s+"
    + re.escape(WORKFLOW_OWNED_MULTI_AGENT_V2_MARKER)
    + r"\s*$"
)
_OWNED_V2_CAPACITY = re.compile(
    r"^\s*max_concurrent_threads_per_session\s*=\s*([0-9]+)\s+"
    + re.escape(WORKFLOW_OWNED_V2_CAPACITY_MARKER)
    + r"\s*$"
)
_OWNED_FEATURES_HEADER = re.compile(
    r"^\s*\[features]\s+"
    + re.escape(WORKFLOW_CREATED_FEATURES_MARKER)
    + r"\s*$"
)
_OWNED_V2_TABLE_HEADER = re.compile(
    r"^\s*\[features\.multi_agent_v2]\s+"
    + re.escape(WORKFLOW_CREATED_V2_TABLE_MARKER)
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


def _root_dotted_features_lines(lines: list[str]) -> list[int]:
    end = _root_table_end(lines)
    return [
        index
        for index in range(end)
        if _ROOT_DOTTED_FEATURES.match(lines[index])
    ]


def _root_inline_features_lines(lines: list[str]) -> list[int]:
    end = _root_table_end(lines)
    return [
        index
        for index in range(end)
        if _ROOT_INLINE_FEATURES.match(lines[index])
    ]


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


def _multi_agent_v2_enabled(setting: Any) -> bool:
    if isinstance(setting, bool):
        return setting
    elif isinstance(setting, dict):
        if "enabled" not in setting or not isinstance(setting["enabled"], bool):
            raise ValidationError(
                "features.multi_agent_v2 must explicitly use a boolean enabled value"
            )
        return setting["enabled"]
    else:
        raise ValidationError("features.multi_agent_v2 must be a boolean or table")


def _multi_agent_v2_capacity(setting: Any) -> Any:
    if not isinstance(setting, dict):
        return None
    return setting.get("max_concurrent_threads_per_session")


def _validate_generated_config_postconditions(
    generated: dict[str, Any], config: WorkflowConfig
) -> None:
    features = generated.get("features")
    setting = (
        features.get("multi_agent_v2")
        if isinstance(features, dict)
        else None
    )
    try:
        v2_enabled = _multi_agent_v2_enabled(setting)
    except ValidationError:
        v2_enabled = False
    if setting is None or not v2_enabled:
        raise ValidationError(
            "generated Codex configuration did not materialize the required "
            "Multi-Agent V2 setting safely"
        )

    required = config.max_concurrent_workers + 1
    capacity = _multi_agent_v2_capacity(setting)
    if (
        not isinstance(capacity, int)
        or isinstance(capacity, bool)
        or capacity != required
    ):
        raise ValidationError(
            "generated Codex configuration did not materialize the required "
            "features.multi_agent_v2.max_concurrent_threads_per_session "
            "capacity safely"
        )

    agents = generated.get("agents")
    if isinstance(agents, dict) and "max_threads" in agents:
        raise ValidationError(
            "generated Codex configuration retained legacy agents.max_threads "
            "while Multi-Agent V2 is enabled"
        )


def _owned_multi_agent_v2_lines(
    lines: list[str], bounds: tuple[int, int] | None
) -> list[int]:
    explicit = [
        index
        for index in _key_lines(lines, bounds, "multi_agent_v2")
        if _OWNED_MULTI_AGENT_V2.fullmatch(lines[index])
    ]
    dotted = [
        index
        for index in _root_dotted_features_lines(lines)
        if _OWNED_DOTTED_MULTI_AGENT_V2.fullmatch(lines[index])
    ]
    return explicit + dotted


def _owned_v2_enabled_lines(
    lines: list[str], bounds: tuple[int, int] | None
) -> list[int]:
    return [
        index
        for index in _key_lines(lines, bounds, "enabled")
        if _OWNED_V2_ENABLED.fullmatch(lines[index])
    ]


def _owned_v2_capacity_lines(
    lines: list[str], bounds: tuple[int, int] | None
) -> list[int]:
    return [
        index
        for index in _key_lines(
            lines, bounds, "max_concurrent_threads_per_session"
        )
        if _OWNED_V2_CAPACITY.fullmatch(lines[index])
    ]


def _patch_required_multi_agent_v2(
    lines: list[str],
    features: dict[str, Any] | None,
    feature_bounds: tuple[int, int] | None,
    v2_bounds: tuple[int, int] | None,
    required_capacity: int,
) -> None:
    legacy_owned_lines = _owned_multi_agent_v2_lines(lines, feature_bounds)
    if legacy_owned_lines:
        lines[:] = _remove_owned_legacy_v2(lines)
        _append_owned_v2_table(lines, required_capacity)
        return

    has_existing = isinstance(features, dict) and "multi_agent_v2" in features
    if not has_existing:
        if _root_inline_features_lines(lines):
            raise ValidationError(
                "features is an inline table without multi_agent_v2; "
                "codex-workflow-custom cannot enable V2 without restructuring "
                "the user-owned inline table"
            )
        _append_owned_v2_table(lines, required_capacity)
        return

    setting = features["multi_agent_v2"]
    if isinstance(setting, bool):
        if not setting:
            raise ValidationError(
                "features.multi_agent_v2 is explicitly disabled by a "
                "user/OpenCodex-owned value, but codex-workflow-custom requires "
                "Multi-Agent V2; enable or remove that value explicitly"
            )
        raise ValidationError(
            "user/OpenCodex-owned scalar features.multi_agent_v2=true has no V2 "
            "session capacity; use a table with enabled=true and "
            "max_concurrent_threads_per_session, or remove it explicitly"
        )

    enabled = _multi_agent_v2_enabled(setting)
    owned_enabled = _owned_v2_enabled_lines(lines, v2_bounds)
    if not enabled:
        if not owned_enabled:
            raise ValidationError(
                "features.multi_agent_v2 is explicitly disabled by a "
                "user/OpenCodex-owned value, but codex-workflow-custom requires "
                "Multi-Agent V2; enable or remove that value explicitly"
            )
        lines[owned_enabled[0]] = _owned_v2_enabled_line()

    capacity = _multi_agent_v2_capacity(setting)
    has_capacity = "max_concurrent_threads_per_session" in setting
    owned_capacity = _owned_v2_capacity_lines(lines, v2_bounds)
    if has_capacity:
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise ValidationError(
                "features.multi_agent_v2.max_concurrent_threads_per_session "
                "must be an integer"
            )
        if owned_capacity:
            lines[owned_capacity[0]] = _owned_v2_capacity_line(required_capacity)
        elif capacity != required_capacity:
            raise ValidationError(
                "features.multi_agent_v2.max_concurrent_threads_per_session is "
                f"already set to {capacity}, but codex-workflow-custom requires "
                f"{required_capacity}; change or remove the user/OpenCodex-owned "
                "value explicitly"
            )
        return

    if v2_bounds is None:
        raise ValidationError(
            "user/OpenCodex-owned inline features.multi_agent_v2 has no V2 "
            "session capacity; use an explicit [features.multi_agent_v2] table "
            "or add max_concurrent_threads_per_session explicitly"
        )
    _, end = v2_bounds
    lines.insert(end, _owned_v2_capacity_line(required_capacity))


def _owned_v2_table_header() -> str:
    return f"[features.multi_agent_v2] {WORKFLOW_CREATED_V2_TABLE_MARKER}"


def _owned_v2_enabled_line() -> str:
    return f"enabled = true {WORKFLOW_OWNED_MULTI_AGENT_V2_MARKER}"


def _owned_v2_capacity_line(value: int) -> str:
    return (
        f"max_concurrent_threads_per_session = {value} "
        f"{WORKFLOW_OWNED_V2_CAPACITY_MARKER}"
    )


def _append_owned_v2_table(lines: list[str], required_capacity: int) -> None:
    lines.append(_owned_v2_table_header())
    lines.append(_owned_v2_enabled_line())
    lines.append(_owned_v2_capacity_line(required_capacity))


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
    valid_explicit_setting_lines = {
        index for index in max_lines if _OWNED_MAX_THREADS.fullmatch(lines[index])
    }
    valid_setting_lines = set(valid_explicit_setting_lines)
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
    if valid_header_lines and len(valid_explicit_setting_lines) != 1:
        raise ValidationError(
            "workflow-created [agents] table ownership drift: expected one "
            "workflow-owned agents.max_threads setting"
        )


def _validate_v2_ownership_markers(
    lines: list[str],
    feature_bounds: tuple[int, int] | None,
    v2_bounds: tuple[int, int] | None,
) -> None:
    setting_lines = _key_lines(lines, feature_bounds, "multi_agent_v2")
    valid_explicit_legacy_lines = {
        index
        for index in setting_lines
        if _OWNED_MULTI_AGENT_V2.fullmatch(lines[index])
    }
    valid_legacy_lines = set(valid_explicit_legacy_lines)
    valid_legacy_lines.update(
        index
        for index in _root_dotted_features_lines(lines)
        if _OWNED_DOTTED_MULTI_AGENT_V2.fullmatch(lines[index])
    )
    valid_enabled_lines = set(_owned_v2_enabled_lines(lines, v2_bounds))
    valid_setting_lines = valid_legacy_lines | valid_enabled_lines
    marker_lines = {
        index
        for index, line in enumerate(lines)
        if WORKFLOW_OWNED_MULTI_AGENT_V2_MARKER in line
    }
    if marker_lines != valid_setting_lines:
        raise ValidationError("malformed codex-workflow-custom V2 ownership marker")

    valid_capacity_lines = set(_owned_v2_capacity_lines(lines, v2_bounds))
    capacity_marker_lines = {
        index
        for index, line in enumerate(lines)
        if WORKFLOW_OWNED_V2_CAPACITY_MARKER in line
    }
    if capacity_marker_lines != valid_capacity_lines:
        raise ValidationError(
            "malformed codex-workflow-custom V2 capacity ownership marker"
        )

    valid_feature_header_lines: set[int] = set()
    if (
        feature_bounds is not None
        and _OWNED_FEATURES_HEADER.fullmatch(lines[feature_bounds[0]])
    ):
        valid_feature_header_lines.add(feature_bounds[0])
    feature_header_marker_lines = {
        index
        for index, line in enumerate(lines)
        if WORKFLOW_CREATED_FEATURES_MARKER in line
    }
    if feature_header_marker_lines != valid_feature_header_lines:
        raise ValidationError("malformed codex-workflow-custom features-table marker")
    if valid_feature_header_lines and len(valid_explicit_legacy_lines) != 1:
        raise ValidationError(
            "workflow-created [features] table ownership drift: expected one "
            "workflow-owned features.multi_agent_v2 setting"
        )

    valid_v2_header_lines: set[int] = set()
    if (
        v2_bounds is not None
        and _OWNED_V2_TABLE_HEADER.fullmatch(lines[v2_bounds[0]])
    ):
        valid_v2_header_lines.add(v2_bounds[0])
    v2_header_marker_lines = {
        index
        for index, line in enumerate(lines)
        if WORKFLOW_CREATED_V2_TABLE_MARKER in line
    }
    if v2_header_marker_lines != valid_v2_header_lines:
        raise ValidationError(
            "malformed codex-workflow-custom V2 feature-table marker"
        )
    if valid_v2_header_lines:
        if len(valid_enabled_lines) != 1 or len(valid_capacity_lines) != 1:
            raise ValidationError(
                "workflow-created [features.multi_agent_v2] table ownership "
                "drift: expected owned enabled and capacity settings"
            )
    elif valid_enabled_lines:
        raise ValidationError(
            "workflow-owned V2 enabled setting requires a workflow-created "
            "[features.multi_agent_v2] table"
        )


def remove_workflow_owned_config(text: str) -> str:
    """Remove only the Codex settings owned by this workflow."""
    if not text.strip():
        return ""
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"existing Codex config is invalid TOML: {error}") from error

    ownership_markers = (
        WORKFLOW_OWNED_MAX_THREADS_MARKER,
        WORKFLOW_CREATED_AGENTS_MARKER,
        WORKFLOW_OWNED_MULTI_AGENT_V2_MARKER,
        WORKFLOW_CREATED_FEATURES_MARKER,
        WORKFLOW_OWNED_V2_CAPACITY_MARKER,
        WORKFLOW_CREATED_V2_TABLE_MARKER,
    )
    if not any(marker in text for marker in ownership_markers):
        return text

    lines = text.splitlines()
    lines = _remove_owned_v2(lines)
    lines = _remove_owned_agents(lines)

    rendered = _render_lines(lines, text) if lines else ""
    try:
        tomllib.loads(rendered)
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"generated Codex config is invalid TOML: {error}") from error
    return rendered


def _remove_owned_v2(lines: list[str]) -> list[str]:
    feature_bounds = _section_bounds(lines, "features")
    v2_bounds = _section_bounds(lines, "features.multi_agent_v2")
    _validate_v2_ownership_markers(lines, feature_bounds, v2_bounds)

    lines = _remove_owned_legacy_v2(lines)
    v2_bounds = _section_bounds(lines, "features.multi_agent_v2")
    has_new_markers = any(
        marker in line
        for line in lines
        for marker in (
            WORKFLOW_OWNED_V2_CAPACITY_MARKER,
            WORKFLOW_CREATED_V2_TABLE_MARKER,
        )
    )
    if not has_new_markers:
        return lines
    if v2_bounds is None:
        raise ValidationError(
            "workflow-owned V2 capacity requires a [features.multi_agent_v2] table"
        )

    owned_enabled = _owned_v2_enabled_lines(lines, v2_bounds)
    owned_capacity = _owned_v2_capacity_lines(lines, v2_bounds)
    start, end = v2_bounds
    created_table = WORKFLOW_CREATED_V2_TABLE_MARKER in lines[start]
    if not created_table:
        if owned_enabled or len(owned_capacity) != 1:
            raise ValidationError(
                "expected one workflow-owned V2 capacity setting in the "
                "user-owned [features.multi_agent_v2] table"
            )
        return [
            line
            for index, line in enumerate(lines)
            if index != owned_capacity[0]
        ]

    owned_lines = set(owned_enabled + owned_capacity)
    retained_body = [
        line
        for index, line in enumerate(lines[start + 1 : end], start + 1)
        if index not in owned_lines
    ]
    if created_table and not any(line.strip() for line in retained_body):
        return lines[:start] + lines[end:]
    header = "[features.multi_agent_v2]"
    return lines[:start] + [header] + retained_body + lines[end:]


def _remove_owned_legacy_v2(lines: list[str]) -> list[str]:
    bounds = _section_bounds(lines, "features")
    owned_lines = _owned_multi_agent_v2_lines(lines, bounds)
    if not owned_lines:
        return lines
    if len(owned_lines) != 1:
        raise ValidationError(
            "expected one legacy workflow-owned features.multi_agent_v2 setting"
        )
    if _OWNED_DOTTED_MULTI_AGENT_V2.fullmatch(lines[owned_lines[0]]):
        return [
            line for index, line in enumerate(lines) if index != owned_lines[0]
        ]

    if bounds is None:
        raise ValidationError(
            "legacy workflow-owned V2 setting requires a [features] table"
        )
    start, end = bounds
    created_table = WORKFLOW_CREATED_FEATURES_MARKER in lines[start]
    retained_body = [
        line
        for index, line in enumerate(lines[start + 1 : end], start + 1)
        if index not in owned_lines
    ]
    if created_table and not any(line.strip() for line in retained_body):
        return lines[:start] + lines[end:]
    header = "[features]" if created_table else lines[start]
    return lines[:start] + [header] + retained_body + lines[end:]


def _remove_owned_agents(lines: list[str]) -> list[str]:
    bounds = _section_bounds(lines, "agents")
    _validate_ownership_markers(lines, bounds)
    has_markers = any(
        marker in line
        for line in lines
        for marker in (
            WORKFLOW_OWNED_MAX_THREADS_MARKER,
            WORKFLOW_CREATED_AGENTS_MARKER,
        )
    )
    if not has_markers:
        return lines

    owned_lines = _owned_max_threads_lines(lines, bounds)
    if len(owned_lines) != 1:
        raise ValidationError("expected one workflow-owned agents.max_threads setting")
    if _OWNED_DOTTED_MAX_THREADS.fullmatch(lines[owned_lines[0]]):
        return [line for index, line in enumerate(lines) if index != owned_lines[0]]

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
    return result
