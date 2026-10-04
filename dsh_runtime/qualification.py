"""Opt-in real-host qualification boundary for the M6 probes.

This module is deliberately outside the production Planner/Controller loop.
It composes the existing Plugin and Executor seams, owns only qualification
repository setup and evidence, and never exposes either plugin's private
native lifecycle.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .plugins.codebuddy import CodeBuddyPlugin
from .plugins.codex import CodexPlugin
from .runtime.executor import Executor
from .runtime.plugin import ExecutionContext, Plugin, PluginResult, StopReason
from .runtime.registry import PluginRegistry


TARGET_DISCOVERY_TIMEOUT_SECONDS = 5.0
CODEBUDDY_PROBE_TIMEOUT_SECONDS = 120.0
CODEX_PROBE_TIMEOUT_SECONDS = 120.0
QUALIFICATION_ATTEMPTS_PER_PROBE = 1
QUALIFICATION_AUTOMATIC_RETRIES = 0
QUALIFICATION_MANDATORY_PASS_THRESHOLD = 1.0

_CODEBUDDY_TARGET = "codebuddy.cmd"
_CODEX_TARGET = "codex"
_QUALIFICATION_WORKSPACE_ID = "dsh.m6.qualification"
_PROBE_ARTIFACT = Path(".m6_qualification") / "codebuddy_probe.txt"
_PROBE_CONTENT = "DSH_M6_CODEBUDDY_PROBE"
_MAX_REASON_CHARS = 1_000


class QualificationStatus(str, Enum):
    """Minimal classification vocabulary for one qualification run."""

    AVAILABLE = "AVAILABLE"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
    QUALIFICATION_FAIL = "QUALIFICATION_FAIL"
    CONTRACT_CONTRADICTION = "CONTRACT_CONTRADICTION"
    QUALIFICATION_PASS = "QUALIFICATION_PASS"


@dataclass(frozen=True)
class AuthorityExpectation:
    """Authority facts expected at one native invocation boundary."""

    caller_ceiling: bool
    invocation_request: bool
    effective: bool


@dataclass(frozen=True)
class QualificationEvidence:
    """Bounded evidence for one discovery or native qualification stage."""

    service: str
    stage: str
    classification: QualificationStatus
    attempt_count: int
    elapsed_seconds: float
    settled: bool
    native_result: str
    reason: str | None = None
    authority: AuthorityExpectation | None = None
    workspace_delta: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualificationReport:
    """Structured result returned by the opt-in qualification boundary."""

    classification: QualificationStatus
    evidence: tuple[QualificationEvidence, ...]
    workspace: str | None = None


TargetResolver = Callable[[str], str | None]


def _bounded(value: Any) -> str:
    text = str(value).strip()
    if len(text) <= _MAX_REASON_CHARS:
        return text
    return text[: _MAX_REASON_CHARS - 3] + "..."


def _command_target(
    command: Sequence[str] | None,
    target: str,
    resolver: TargetResolver,
    suffix: Sequence[str] = (),
) -> tuple[str, ...] | None:
    """Resolve a configured command or the same default target as its plugin."""

    if command is not None:
        resolved = tuple(command)
        if not resolved:
            return None
        executable = resolved[0]
        if Path(executable).exists() or resolver(executable) is not None:
            return resolved
        return None

    executable = resolver(target)
    if executable is None:
        return None
    return (executable, *suffix)


def _snapshot(root: Path) -> dict[str, bytes]:
    """Snapshot files, symlinks, and directories in the disposable workspace."""

    snapshot: dict[str, bytes] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = b"symlink:" + os.readlink(path).encode(
                "utf-8", errors="replace"
            )
        elif path.is_dir():
            snapshot[relative] = b"directory"
        elif path.is_file():
            snapshot[relative] = b"file:" + path.read_bytes()
    return snapshot


def _delta(before: Mapping[str, bytes], after: Mapping[str, bytes]) -> tuple[str, ...]:
    changes: list[str] = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            changes.append(f"+{path}")
        elif path not in after:
            changes.append(f"-{path}")
        elif before[path] != after[path]:
            changes.append(f"~{path}")
    return tuple(changes)


def _native_result(result: PluginResult) -> tuple[str, bool]:
    stop_reason = result.stop_reason
    if stop_reason is StopReason.COMPLETED:
        return "success/completed", True
    if stop_reason is StopReason.TIMED_OUT:
        return "timeout", True
    if stop_reason is StopReason.FAILED:
        return "failure/failed", True
    return "unclassified", False


def _result_reason(result: PluginResult) -> str | None:
    details = [value for value in (result.error, result.cleanup_error) if value]
    return _bounded("; ".join(details)) if details else None


class RealHostQualifier:
    """Run one bounded, opt-in CodeBuddy-then-Codex host qualification."""

    def __init__(
        self,
        *,
        codebuddy: Plugin | None = None,
        codex: Plugin | None = None,
        codebuddy_command: Sequence[str] | None = None,
        codex_command: Sequence[str] | None = None,
        target_resolver: TargetResolver = shutil.which,
        executor: Executor | None = None,
    ) -> None:
        if codebuddy is not None and codebuddy_command is not None:
            raise ValueError("codebuddy cannot be combined with codebuddy_command")
        if codex is not None and codex_command is not None:
            raise ValueError("codex cannot be combined with codex_command")
        self._codebuddy = codebuddy
        self._codex = codex
        self._codebuddy_command = (
            tuple(codebuddy_command) if codebuddy_command is not None else None
        )
        self._codex_command = tuple(codex_command) if codex_command is not None else None
        self._target_resolver = target_resolver
        self._executor = executor

    async def qualify(self) -> QualificationReport:
        """Perform discovery and, only when both targets resolve, both probes."""

        evidence: list[QualificationEvidence] = []
        codebuddy_command = await self._discover(
            "codebuddy", _CODEBUDDY_TARGET, self._codebuddy_command, evidence
        )
        codex_command = await self._discover(
            "codex", _CODEX_TARGET, self._codex_command, evidence
        )
        if codebuddy_command is None or codex_command is None:
            return QualificationReport(
                classification=QualificationStatus.ENVIRONMENT_BLOCKED,
                evidence=tuple(evidence),
            )

        codebuddy = self._codebuddy or CodeBuddyPlugin(command=codebuddy_command)
        codex = self._codex or CodexPlugin(command=codex_command)

        registry = PluginRegistry()
        registry.register(codebuddy)
        registry.register(codex)
        executor = self._executor or Executor(registry)

        with tempfile.TemporaryDirectory(prefix="dsh-m6-qualification-") as raw_workspace:
            workspace = Path(raw_workspace)
            (workspace / _PROBE_ARTIFACT.parent).mkdir(parents=True, exist_ok=True)

            codebuddy_evidence = await self._run_codebuddy(
                executor, codebuddy, workspace
            )
            evidence.append(codebuddy_evidence)
            if codebuddy_evidence.classification is not QualificationStatus.AVAILABLE:
                return QualificationReport(
                    classification=codebuddy_evidence.classification,
                    evidence=tuple(evidence),
                )

            codex_evidence = await self._run_codex(executor, codex, workspace)
            evidence.append(codex_evidence)
            if codex_evidence.classification is QualificationStatus.AVAILABLE:
                classification = QualificationStatus.AVAILABLE
            else:
                classification = codex_evidence.classification
            return QualificationReport(
                classification=classification,
                evidence=tuple(evidence),
            )

    async def _discover(
        self,
        service: str,
        target: str,
        configured_command: Sequence[str] | None,
        evidence: list[QualificationEvidence],
    ) -> tuple[str, ...] | None:
        started = time.monotonic()
        if (self._codebuddy if service == "codebuddy" else self._codex) is not None:
            elapsed = time.monotonic() - started
            evidence.append(
                QualificationEvidence(
                    service=service,
                    stage="target_discovery",
                    classification=QualificationStatus.AVAILABLE,
                    attempt_count=QUALIFICATION_ATTEMPTS_PER_PROBE,
                    elapsed_seconds=elapsed,
                    settled=True,
                    native_result="configured plugin",
                    reason="target supplied by caller",
                )
            )
            return ("configured",)

        try:
            resolved = await asyncio.wait_for(
                asyncio.to_thread(
                    _command_target,
                    configured_command,
                    target,
                    self._target_resolver,
                    ("app-server", "--stdio") if service == "codex" else (),
                ),
                timeout=TARGET_DISCOVERY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            resolved = None
            reason = "target discovery timed out"
        except (OSError, TypeError, ValueError) as exc:
            resolved = None
            reason = f"target discovery failed: {_bounded(exc)}"
        else:
            reason = None if resolved is not None else f"target not found: {target}"

        elapsed = time.monotonic() - started
        evidence.append(
            QualificationEvidence(
                service=service,
                stage="target_discovery",
                classification=(
                    QualificationStatus.AVAILABLE
                    if resolved is not None
                    else QualificationStatus.ENVIRONMENT_BLOCKED
                ),
                attempt_count=QUALIFICATION_ATTEMPTS_PER_PROBE,
                elapsed_seconds=elapsed,
                settled=True,
                native_result="target resolved" if resolved is not None else "target unavailable",
                reason=reason,
            )
        )
        return resolved

    async def _run_codebuddy(
        self, executor: Executor, plugin: Plugin, workspace: Path
    ) -> QualificationEvidence:
        started = time.monotonic()
        before = _snapshot(workspace)
        context = ExecutionContext(
            task_id="m6-qualification-codebuddy",
            workspace_id=_QUALIFICATION_WORKSPACE_ID,
            goal="Create the controlled M6 CodeBuddy probe artifact.",
            cwd=str(workspace),
            allow_workspace_write=True,
        )
        prompt = (
            "Use Python only. In the qualification repository, create exactly "
            ".m6_qualification/codebuddy_probe.txt with exactly this content: "
            "DSH_M6_CODEBUDDY_PROBE. Do not modify, create, or delete any other "
            "file. Report only after the file has been written."
        )
        result = await executor.execute(
            plugin.name,
            context,
            {"prompt": prompt},
            CODEBUDDY_PROBE_TIMEOUT_SECONDS,
        )
        after = _snapshot(workspace)
        delta = _delta(before, after)
        native_result, settled = _native_result(result)
        artifact = workspace / _PROBE_ARTIFACT
        try:
            content = artifact.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            content = None
            artifact_reason = f"probe artifact unreadable: {_bounded(exc)}"
        else:
            artifact_reason = None
        expected_delta = (f"+{_PROBE_ARTIFACT.as_posix()}",)
        mutation_conflict = bool(delta) and (
            delta != expected_delta or content != _PROBE_CONTENT
        )
        if mutation_conflict:
            classification = QualificationStatus.QUALIFICATION_FAIL
            reason = (
                "unexpected qualification-repository mutation"
                if delta != expected_delta
                else artifact_reason or "controlled mutation mismatch"
            )
        elif not settled or not result.success:
            classification = QualificationStatus.ENVIRONMENT_BLOCKED
            reason = _result_reason(result) or "CodeBuddy probe did not settle successfully"
        elif content != _PROBE_CONTENT or delta != expected_delta:
            classification = QualificationStatus.QUALIFICATION_FAIL
            reason = artifact_reason or "controlled mutation mismatch"
        else:
            classification = QualificationStatus.AVAILABLE
            reason = None
        return QualificationEvidence(
            service="codebuddy",
            stage="native_probe",
            classification=classification,
            attempt_count=QUALIFICATION_ATTEMPTS_PER_PROBE,
            elapsed_seconds=time.monotonic() - started,
            settled=settled,
            native_result=native_result,
            reason=reason,
            authority=AuthorityExpectation(True, True, True),
            workspace_delta=delta,
        )

    async def _run_codex(
        self, executor: Executor, plugin: Plugin, workspace: Path
    ) -> QualificationEvidence:
        started = time.monotonic()
        before = _snapshot(workspace)
        context = ExecutionContext(
            task_id="m6-qualification-codex",
            workspace_id=_QUALIFICATION_WORKSPACE_ID,
            goal="Verify the controlled M6 CodeBuddy probe artifact.",
            cwd=str(workspace),
            allow_workspace_write=False,
        )
        prompt = (
            "Read .m6_qualification/codebuddy_probe.txt without changing the "
            "qualification repository. Verify that its exact content is "
            "DSH_M6_CODEBUDDY_PROBE. If and only if it matches, include the exact "
            "standalone line DSH_VERIFICATION: PASS in the final answer; otherwise "
            "include DSH_VERIFICATION: FAIL. Do not create, edit, or delete files."
        )
        result = await executor.execute(
            plugin.name,
            context,
            {"prompt": prompt},
            CODEX_PROBE_TIMEOUT_SECONDS,
        )
        after = _snapshot(workspace)
        delta = _delta(before, after)
        native_result, settled = _native_result(result)
        if delta:
            classification = QualificationStatus.CONTRACT_CONTRADICTION
            reason = "Codex mutated the qualification repository under read-only authority"
        elif not settled or not result.success:
            classification = QualificationStatus.ENVIRONMENT_BLOCKED
            reason = _result_reason(result) or "Codex probe did not settle successfully"
        elif not _has_pass_marker(result.output):
            classification = QualificationStatus.QUALIFICATION_FAIL
            reason = "Codex output did not contain DSH_VERIFICATION: PASS"
        else:
            classification = QualificationStatus.AVAILABLE
            reason = None
        return QualificationEvidence(
            service="codex",
            stage="native_probe",
            classification=classification,
            attempt_count=QUALIFICATION_ATTEMPTS_PER_PROBE,
            elapsed_seconds=time.monotonic() - started,
            settled=settled,
            native_result=native_result,
            reason=reason,
            authority=AuthorityExpectation(True, False, False),
            workspace_delta=delta,
        )


def _has_pass_marker(output: Any) -> bool:
    if not isinstance(output, str):
        return False
    markers = {line.strip() for line in output.splitlines()}
    return "DSH_VERIFICATION: PASS" in markers and "DSH_VERIFICATION: FAIL" not in markers


async def qualify_real_host(**kwargs: Any) -> QualificationReport:
    """Run one opt-in real-host qualification using the existing plugin seams."""

    return await RealHostQualifier(**kwargs).qualify()
