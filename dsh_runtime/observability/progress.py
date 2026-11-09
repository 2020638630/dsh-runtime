"""Optional live phase metadata for a Harness-owned run."""

import json
import os
import re
import time
from pathlib import Path


def _progress_target() -> tuple[Path, str] | None:
    path = os.environ.get("DSH_RUNTIME_PROGRESS_PATH")
    run_id = os.environ.get("DSH_RUNTIME_RUN_ID", "")
    if not path or not re.fullmatch(r"dsh-runtime-[a-f0-9-]{36}", run_id):
        return
    target = Path(path)
    if (not target.is_absolute() or target.name != "runtime-progress.jsonl"
        or target.parent.name != run_id or target.is_symlink()):
        return
    return target, run_id


def record_phase(workspace_id: str, role: str, adapter: str | None) -> None:
    if (role, adapter) not in {
        ("worker", "codex"), ("worker", "codebuddy"), ("reviewer", "codex"),
        ("reviewer", "api_agent"), ("inspector", "codex"), ("inspector", "api_agent"),
    }:
        return
    progress = _progress_target()
    if progress is None:
        return
    target, run_id = progress
    data = {"schema_version": 1, "run_id": run_id, "workspace_id": workspace_id,
            "role": role, "adapter": adapter, "started_at_ms": time.time_ns() // 1_000_000}
    try:
        with target.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(data, ensure_ascii=True, separators=(",", ":")) + "\n")
    except OSError:
        # Progress is optional. A write failure must not change task settlement.
        return


def record_codex_tool(workspace_id: str, name: str, status: str) -> None:
    if name not in {"commandExecution", "fileChange"} or status not in {"called", "completed", "failed"}:
        return
    progress = _progress_target()
    if progress is None:
        return
    phases, run_id = progress
    target = phases.with_name("runtime-codex-activity.jsonl")
    pending = target.with_suffix(".pending")
    data = {"schema_version": 1, "run_id": run_id, "workspace_id": workspace_id,
            "tool": name, "status": status, "at_ms": time.time_ns() // 1_000_000}
    try:
        file = pending.open("x", encoding="utf-8", newline="\n")
        try:
            with file:
                file.write(json.dumps(data, ensure_ascii=True, separators=(",", ":")) + "\n")
            os.replace(pending, target)
        finally:
            pending.unlink(missing_ok=True)
    except OSError:
        # Live-observation failures must not propagate into the execution protocol.
        return
