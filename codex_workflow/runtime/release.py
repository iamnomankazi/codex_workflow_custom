"""Legacy semantic-version parsing for old local installation state.

The active lifecycle identifies source trees by deterministic content hashes.
This module remains only so an existing ``workflow_version`` or historical
``.source_backup/<version>`` can be read and migrated without reintroducing
release lookup, network acquisition, or version ordering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import ValidationError


@dataclass(frozen=True)
class SemVer:
    core: tuple[int, int, int]
    prerelease: tuple[str, ...] = ()


_SEMVER = re.compile(
    r"^(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def parse_semver(value: str) -> SemVer:
    """Validate a legacy workflow version while migrating old state."""

    match = _SEMVER.fullmatch(value.strip())
    if match is None:
        raise ValidationError(f"invalid semantic version: {value!r}")
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
    for identifier in prerelease:
        if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
            raise ValidationError(f"invalid semantic version: {value!r}")
    return SemVer(tuple(int(match.group(index)) for index in range(1, 4)), prerelease)
