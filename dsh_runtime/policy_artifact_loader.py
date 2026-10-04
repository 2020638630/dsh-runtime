"""Loading boundary for validated canonical policy artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import json
from os import PathLike
from pathlib import Path
from typing import Protocol

from .policy_artifact import (
    CanonicalPolicyArtifact,
    PolicyArtifactValidationError,
    compute_policy_hash,
    validate_policy_artifact,
)


class PolicyArtifactLoadError(Exception):
    """A policy artifact could not be loaded as a trusted artifact."""


class PolicyArtifactSourceError(PolicyArtifactLoadError):
    """An artifact source could not provide a JSON document."""


class PolicyArtifactParseError(PolicyArtifactLoadError):
    """An artifact source did not contain valid JSON."""


class PolicyArtifactLoadValidationError(PolicyArtifactLoadError):
    """A parsed artifact failed canonical artifact validation."""


class PolicyArtifactHashMismatchError(PolicyArtifactLoadError):
    """A loaded artifact did not match its expected canonical hash."""


class PolicyArtifactSource(Protocol):
    """Replaceable source contract for one policy artifact JSON document."""

    def read_text(self) -> str:
        """Return the source document as text."""


@dataclass(frozen=True)
class FilePolicyArtifactSource:
    """Read one UTF-8 JSON artifact from the local filesystem."""

    path: str | PathLike[str]

    def read_text(self) -> str:
        return Path(self.path).read_text(encoding="utf-8")


@dataclass(frozen=True)
class PolicyArtifactIdentity:
    """Stable identity established by canonical artifact loading."""

    policy_id: str
    policy_version: str
    artifact_schema_version: str
    policy_hash: str


@dataclass(frozen=True)
class LoadedPolicyArtifact:
    """A validated immutable artifact together with its verified identity."""

    artifact: CanonicalPolicyArtifact
    identity: PolicyArtifactIdentity


def load_policy_artifact(
    source: PolicyArtifactSource,
    *,
    expected_policy_hash: str | None = None,
) -> LoadedPolicyArtifact:
    """Read, parse, validate, hash, and optionally verify one artifact."""

    try:
        document = source.read_text()
    except Exception as exc:
        raise PolicyArtifactSourceError(
            "policy artifact source could not be read"
        ) from exc

    if not isinstance(document, str):
        raise PolicyArtifactSourceError(
            "policy artifact source must return text"
        )

    try:
        parsed = json.loads(document)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PolicyArtifactParseError(
            "policy artifact source does not contain valid JSON"
        ) from exc

    try:
        artifact = validate_policy_artifact(parsed)
    except PolicyArtifactValidationError as exc:
        raise PolicyArtifactLoadValidationError(str(exc)) from exc

    policy_hash = compute_policy_hash(artifact)
    if expected_policy_hash is not None:
        if not isinstance(expected_policy_hash, str) or not hmac.compare_digest(
            policy_hash, expected_policy_hash
        ):
            raise PolicyArtifactHashMismatchError(
                "loaded policy artifact does not match expected policy hash"
            )

    return LoadedPolicyArtifact(
        artifact=artifact,
        identity=PolicyArtifactIdentity(
            policy_id=artifact.policy_id,
            policy_version=artifact.policy_version,
            artifact_schema_version=artifact.artifact_schema_version,
            policy_hash=policy_hash,
        ),
    )
