"""Deterministic, non-live tests for the M6 real-host qualification boundary."""

import asyncio
import time
from dataclasses import fields
from pathlib import Path

import pytest

from dsh_runtime.qualification import (
    CODEBUDDY_PROBE_TIMEOUT_SECONDS,
    CODEX_PROBE_TIMEOUT_SECONDS,
    QualificationStatus,
    RealHostQualifier,
)
from dsh_runtime.runtime.plugin import ExecutionContext, PluginResult


ARTIFACT = Path(".m6_qualification") / "codebuddy_probe.txt"
EXPECTED_CONTENT = "DSH_M6_CODEBUDDY_PROBE"


def write_artifact(content: str = EXPECTED_CONTENT):
    def action(ctx: ExecutionContext) -> None:
        path = Path(ctx.cwd) / ARTIFACT
        path.write_text(content, encoding="utf-8")

    return action


def write_extra_file(name: str = "unexpected.txt"):
    def action(ctx: ExecutionContext) -> None:
        (Path(ctx.cwd) / name).write_text("unexpected", encoding="utf-8")

    return action


class FakePlugin:
    def __init__(
        self,
        name: str,
        *,
        action=None,
        success: bool = True,
        output: str | None = None,
        error: str | None = None,
        delay: float = 0.0,
    ) -> None:
        self.name = name
        self.action = action
        self.success = success
        self.output = output
        self.error = error
        self.delay = delay
        self.calls = 0
        self.contexts: list[ExecutionContext] = []

    async def execute(self, ctx: ExecutionContext, params: dict) -> PluginResult:
        self.calls += 1
        self.contexts.append(ctx)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.action is not None:
            self.action(ctx)
        return PluginResult(
            success=self.success,
            output=self.output,
            error=self.error,
        )


def exact_codebuddy(**kwargs) -> FakePlugin:
    return FakePlugin("codebuddy", action=write_artifact(), **kwargs)


def passing_codex(**kwargs) -> FakePlugin:
    kwargs.setdefault("output", "DSH_VERIFICATION: PASS")
    return FakePlugin("codex", **kwargs)


def qualify(
    codebuddy: FakePlugin | None = None,
    codex: FakePlugin | None = None,
    *,
    target_resolver=None,
):
    return asyncio.run(
        RealHostQualifier(
            codebuddy=codebuddy,
            codex=codex,
            target_resolver=target_resolver or (lambda target: target),
        ).qualify()
    )


def test_m6_qf_d001_targets_available() -> None:
    report = qualify(exact_codebuddy(), passing_codex())

    discovery = [item for item in report.evidence if item.stage == "target_discovery"]
    assert [item.classification for item in discovery] == [
        QualificationStatus.AVAILABLE,
        QualificationStatus.AVAILABLE,
    ]


def test_m6_qf_d002_codebuddy_target_missing() -> None:
    codex = passing_codex()

    def resolver(target: str) -> str | None:
        return None if target == "codebuddy.cmd" else "codex"

    report = qualify(None, codex, target_resolver=resolver)

    assert report.classification is QualificationStatus.ENVIRONMENT_BLOCKED
    assert codex.calls == 0


def test_m6_qf_d003_codex_target_missing() -> None:
    codebuddy = exact_codebuddy()

    def resolver(target: str) -> str | None:
        return "codebuddy.cmd" if target == "codebuddy.cmd" else None

    report = qualify(codebuddy, None, target_resolver=resolver)

    assert report.classification is QualificationStatus.ENVIRONMENT_BLOCKED
    assert codebuddy.calls == 0


def test_m6_qf_d004_target_discovery_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        "dsh_runtime.qualification.TARGET_DISCOVERY_TIMEOUT_SECONDS", 0.01
    )
    codex = passing_codex()

    def resolver(target: str) -> str | None:
        if target == "codebuddy.cmd":
            time.sleep(0.1)
        return target

    report = qualify(None, codex, target_resolver=resolver)

    assert report.classification is QualificationStatus.ENVIRONMENT_BLOCKED
    assert any(
        item.reason and "discovery timed out" in item.reason
        for item in report.evidence
    )
    assert codex.calls == 0


def test_m6_qf_d005_exact_controlled_mutation_succeeds() -> None:
    codebuddy = exact_codebuddy()
    report = qualify(codebuddy, passing_codex())

    evidence = report.evidence[2]
    assert evidence.classification is QualificationStatus.AVAILABLE
    assert evidence.authority is not None
    assert (evidence.authority.caller_ceiling, evidence.authority.invocation_request, evidence.authority.effective) == (True, True, True)
    assert evidence.attempt_count == 1
    assert evidence.workspace_delta == ("+.m6_qualification/codebuddy_probe.txt",)
    assert report.classification is QualificationStatus.AVAILABLE
    assert report.classification is not QualificationStatus.QUALIFICATION_PASS


def test_m6_qf_d006_codebuddy_native_failure_without_mutation() -> None:
    codebuddy = FakePlugin(
        "codebuddy", success=False, error="bounded native failure"
    )
    codex = passing_codex()

    report = qualify(codebuddy, codex)

    assert report.classification is QualificationStatus.ENVIRONMENT_BLOCKED
    assert report.evidence[2].reason == "bounded native failure"
    assert codex.calls == 0


def test_m6_qf_d007_codebuddy_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        "dsh_runtime.qualification.CODEBUDDY_PROBE_TIMEOUT_SECONDS", 0.01
    )
    codebuddy = FakePlugin("codebuddy", delay=0.1)
    codex = passing_codex()

    report = qualify(codebuddy, codex)

    assert report.classification is QualificationStatus.ENVIRONMENT_BLOCKED
    assert report.evidence[2].attempt_count == 1
    assert codebuddy.calls == 1
    assert codex.calls == 0


def test_m6_qf_d008_successful_codebuddy_result_but_artifact_absent() -> None:
    codebuddy = FakePlugin("codebuddy")

    report = qualify(codebuddy, passing_codex())

    assert report.classification is QualificationStatus.QUALIFICATION_FAIL


def test_m6_qf_d009_wrong_artifact_content() -> None:
    codebuddy = FakePlugin("codebuddy", action=write_artifact("WRONG"))

    report = qualify(codebuddy, passing_codex())

    assert report.classification is QualificationStatus.QUALIFICATION_FAIL


def test_m6_qf_d010_unexpected_extra_mutation() -> None:
    def mutate(ctx: ExecutionContext) -> None:
        write_artifact()(ctx)
        write_extra_file()(ctx)

    report = qualify(FakePlugin("codebuddy", action=mutate), passing_codex())

    assert report.classification is QualificationStatus.QUALIFICATION_FAIL
    assert "+unexpected.txt" in report.evidence[2].workspace_delta


def test_m6_qf_d011_failed_codebuddy_after_wrong_mutation() -> None:
    def mutate(ctx: ExecutionContext) -> None:
        write_artifact("WRONG")(ctx)
        write_extra_file()(ctx)

    codebuddy = FakePlugin(
        "codebuddy",
        action=mutate,
        success=False,
        error="native failure after mutation",
    )

    report = qualify(codebuddy, passing_codex())

    assert report.classification is QualificationStatus.QUALIFICATION_FAIL
    assert report.classification is not QualificationStatus.ENVIRONMENT_BLOCKED


def test_m6_qf_d012_readonly_codex_pass() -> None:
    codex = passing_codex()
    report = qualify(exact_codebuddy(), codex)

    evidence = report.evidence[3]
    assert evidence.classification is QualificationStatus.AVAILABLE
    assert evidence.authority is not None
    assert (evidence.authority.caller_ceiling, evidence.authority.invocation_request, evidence.authority.effective) == (True, False, False)
    assert evidence.workspace_delta == ()
    assert report.classification is QualificationStatus.AVAILABLE


def test_m6_qf_d013_codex_native_failure_without_mutation() -> None:
    codex = FakePlugin("codex", success=False, error="codex unavailable")

    report = qualify(exact_codebuddy(), codex)

    assert report.classification is QualificationStatus.ENVIRONMENT_BLOCKED


def test_m6_qf_d014_codex_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        "dsh_runtime.qualification.CODEX_PROBE_TIMEOUT_SECONDS", 0.01
    )
    codex = FakePlugin("codex", delay=0.1)

    report = qualify(exact_codebuddy(), codex)

    assert report.classification is QualificationStatus.ENVIRONMENT_BLOCKED
    assert report.evidence[3].attempt_count == 1
    assert codex.calls == 1


@pytest.mark.parametrize(
    "output",
    ["ordinary prose", "DSH_VERIFICATION: FAIL"],
)
def test_m6_qf_d015_codex_success_without_pass_evidence(output: str) -> None:
    codex = passing_codex(output=output)

    report = qualify(exact_codebuddy(), codex)

    assert report.classification is QualificationStatus.QUALIFICATION_FAIL


def test_m6_qf_d016_pass_text_not_standalone() -> None:
    codex = passing_codex(output="result: DSH_VERIFICATION: PASS")

    report = qualify(exact_codebuddy(), codex)

    assert report.classification is QualificationStatus.QUALIFICATION_FAIL


def test_m6_qf_d017_codex_mutation_under_readonly_authority() -> None:
    codex = passing_codex(action=write_extra_file("codex.txt"))

    report = qualify(exact_codebuddy(), codex)

    assert report.classification is QualificationStatus.CONTRACT_CONTRADICTION
    assert "+codex.txt" in report.evidence[3].workspace_delta


def test_m6_qf_d018_codex_mutation_plus_native_failure() -> None:
    codex = FakePlugin(
        "codex",
        action=write_extra_file("codex.txt"),
        success=False,
        error="codex failed after mutation",
    )

    report = qualify(exact_codebuddy(), codex)

    assert report.classification is QualificationStatus.CONTRACT_CONTRADICTION
    assert report.classification is not QualificationStatus.ENVIRONMENT_BLOCKED


def test_m6_qf_d019_authority_matrix() -> None:
    codebuddy = exact_codebuddy()
    codex = passing_codex()

    report = qualify(codebuddy, codex)

    assert codebuddy.contexts[0].allow_workspace_write is True
    assert codex.contexts[0].allow_workspace_write is False
    assert report.evidence[2].authority is not None
    assert report.evidence[3].authority is not None
    assert report.evidence[2].authority.effective is True
    assert report.evidence[3].authority.effective is False


def test_m6_qf_d020_exactly_one_invocation_per_service() -> None:
    codebuddy = exact_codebuddy()
    codex = passing_codex()

    qualify(codebuddy, codex)

    assert codebuddy.calls == 1
    assert codex.calls == 1


def test_m6_qf_d021_failed_codebuddy_prevents_codex() -> None:
    codebuddy = FakePlugin("codebuddy", success=False, error="stop here")
    codex = passing_codex()

    report = qualify(codebuddy, codex)

    assert report.classification is QualificationStatus.ENVIRONMENT_BLOCKED
    assert codex.calls == 0


def test_m6_qf_d022_no_dead_workspace_locator() -> None:
    report = qualify(exact_codebuddy(), passing_codex())

    assert report.workspace is None
    assert report.evidence[2].workspace_delta


def test_m6_qf_d023_bounded_evidence_shape() -> None:
    report = qualify(exact_codebuddy(), passing_codex())
    evidence = report.evidence[2]

    assert {field.name for field in fields(evidence)} == {
        "service",
        "stage",
        "classification",
        "attempt_count",
        "elapsed_seconds",
        "settled",
        "native_result",
        "reason",
        "authority",
        "workspace_delta",
    }
    assert evidence.service == "codebuddy"
    assert evidence.stage == "native_probe"
    assert evidence.attempt_count == 1
    assert evidence.elapsed_seconds >= 0
    assert evidence.settled is True
    assert evidence.native_result == "success/completed"
    assert evidence.reason is None
    assert evidence.authority is not None
    assert isinstance(evidence.workspace_delta, tuple)


def test_m6_qf_d024_conflicting_pass_and_fail_evidence() -> None:
    codex = passing_codex(
        output="DSH_VERIFICATION: PASS\nDSH_VERIFICATION: FAIL"
    )

    report = qualify(exact_codebuddy(), codex)

    assert report.classification is QualificationStatus.QUALIFICATION_FAIL
