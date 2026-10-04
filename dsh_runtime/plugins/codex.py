"""One-shot bounded Codex app-server capability.

Codex-specific process and JSON-RPC details intentionally stay in this module.
The Runtime only sees the existing Plugin/PluginResult boundary.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..runtime.plugin import ExecutionContext, PluginResult


class _CodexProtocolError(Exception):
    pass


_QUALIFICATION_OBSERVABILITY_FAILURE = "QUALIFICATION OBSERVABILITY FAILURE"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _trace_plugin_result(result: PluginResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "stop_reason": result.stop_reason.value if result.stop_reason else None,
        "cleanup_error": result.cleanup_error,
    }


def _find_protocol_value(value: Any, keys: set[str]) -> str | None:
    if isinstance(value, Mapping):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for child in value.values():
            found = _find_protocol_value(child, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_protocol_value(child, keys)
            if found is not None:
                return found
    return None


class _CodexQualificationTrace:
    """Opt-in, qualification-only evidence sink for one Codex child."""

    def __init__(
        self,
        path: Path,
        *,
        task_id: str,
        workspace_id: str,
        cwd: str,
        argv: Sequence[str],
        goal: str,
        model: str | None,
        reasoning: str | None,
        allow_workspace_write: bool,
    ) -> None:
        self.path = path
        self.trace_id = path.stem.removeprefix("codex-worker-")
        self.started_at = _utc_timestamp()
        self.task_id = task_id
        self.workspace_id = workspace_id
        self.cwd = cwd
        self.argv = list(argv)
        self.goal = goal
        self.model = model
        self.reasoning = reasoning
        self.allow_workspace_write = allow_workspace_write
        self.events: list[dict[str, Any]] = []
        self.protocol_frames: list[dict[str, Any]] = []
        self.stderr = b""

    def event(self, name: str, **fields: Any) -> None:
        self.events.append(
            {"timestamp": _utc_timestamp(), "event": name, **fields}
        )

    def outgoing(self, raw: bytes, message: Mapping[str, Any]) -> None:
        self.protocol_frames.append(
            {
                "timestamp": _utc_timestamp(),
                "direction": "outbound",
                "raw_base64": base64.b64encode(raw).decode("ascii"),
                "message": dict(message),
            }
        )

    def incoming(
        self,
        raw: bytes,
        message: Mapping[str, Any] | None = None,
        *,
        parse_error: str | None = None,
    ) -> None:
        frame: dict[str, Any] = {
            "timestamp": _utc_timestamp(),
            "direction": "inbound",
            "raw_base64": base64.b64encode(raw).decode("ascii"),
            "message": dict(message) if message is not None else None,
            "parse_error": parse_error,
        }
        self.protocol_frames.append(frame)

    def persist(
        self,
        *,
        process: subprocess.Popen[bytes] | None,
        result: PluginResult | None,
        cancelled: bool,
    ) -> None:
        returncode = process.returncode if process is not None else None
        self.event("process_exit", returncode=returncode)
        received = [
            frame
            for frame in self.protocol_frames
            if frame["direction"] == "inbound"
        ]
        valid_received = [frame for frame in received if frame["message"] is not None]
        last_valid = valid_received[-1] if valid_received else None
        observed_model = _find_protocol_value(
            self.protocol_frames,
            {"model", "modelId", "model_id"},
        )
        observed_reasoning = _find_protocol_value(
            self.protocol_frames,
            {"reasoning", "reasoningEffort", "reasoning_effort"},
        )
        payload = {
            "schema_version": 1,
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "settled_at": _utc_timestamp(),
            "pid": process.pid if process is not None else None,
            "executable": self.argv[0] if self.argv else None,
            "argv": self.argv,
            "cwd": self.cwd,
            "task_id": self.task_id,
            "workspace_id": self.workspace_id,
            "goal": self.goal,
            "model": self.model or observed_model,
            "reasoning": self.reasoning or observed_reasoning,
            "requested_model": self.model,
            "requested_reasoning": self.reasoning,
            "observed_model": observed_model,
            "observed_reasoning": observed_reasoning,
            "allow_workspace_write": self.allow_workspace_write,
            "events": self.events,
            "protocol_frames": self.protocol_frames,
            "last_valid_inbound_frame": last_valid,
            "turn_completed_observed": any(
                isinstance(frame.get("message"), Mapping)
                and frame["message"].get("method") == "turn/completed"
                for frame in valid_received
            ),
            "stderr": self.stderr.decode("utf-8", errors="replace"),
            "stderr_base64": base64.b64encode(self.stderr).decode("ascii"),
            "terminal": {
                "returncode": returncode,
                "signal": returncode if isinstance(returncode, int) and returncode < 0 else None,
                "cancelled": cancelled,
            },
            "plugin_result": _trace_plugin_result(result),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class _CodexSession:
    def __init__(
        self,
        process: subprocess.Popen[bytes],
        *,
        cwd: str,
        allow_workspace_write: bool,
        model: str | None,
        max_output_chars: int,
        trace: _CodexQualificationTrace | None = None,
    ) -> None:
        self.process = process
        self.cwd = cwd
        self.allow_workspace_write = allow_workspace_write
        self.model = model
        self.max_output_chars = max_output_chars
        self.trace = trace
        self._next_id = 1
        self.thread_id: str | None = None
        self.turn_id: str | None = None
        self.final_answer: str | None = None
        self.unphased_answer: str | None = None

    @property
    def permission_params(self) -> dict[str, Any]:
        if self.allow_workspace_write:
            # This is the evidence-backed unattended mapping. Full access is
            # intentionally not exposed by this first capability.
            return {
                "approvalPolicy": "on-request",
                "approvalsReviewer": "auto_review",
                "sandbox": "workspace-write",
            }
        return {
            "approvalPolicy": "never",
            "sandbox": "read-only",
        }

    async def send(self, method: str, params: Mapping[str, Any] | None = None) -> int:
        if self.process.stdin is None:
            raise _CodexProtocolError("stdin unavailable")
        request_id = self._next_id
        self._next_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": dict(params or {}),
        }
        try:
            raw = (json.dumps(message) + "\n").encode()
            if self.trace is not None:
                self.trace.outgoing(raw, message)
            await asyncio.to_thread(
                _write_pipe,
                self.process.stdin,
                raw,
            )
        except (BrokenPipeError, ConnectionError) as exc:
            if self.trace is not None:
                self.trace.event("stdin_write_error", error=f"{type(exc).__name__}: {exc}")
            raise _CodexProtocolError("stdin write failed") from exc
        return request_id

    async def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        if self.process.stdin is None:
            raise _CodexProtocolError("stdin unavailable")
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": dict(params or {}),
        }
        try:
            raw = (json.dumps(message) + "\n").encode()
            if self.trace is not None:
                self.trace.outgoing(raw, message)
            await asyncio.to_thread(
                _write_pipe,
                self.process.stdin,
                raw,
            )
        except (BrokenPipeError, ConnectionError) as exc:
            if self.trace is not None:
                self.trace.event("stdin_write_error", error=f"{type(exc).__name__}: {exc}")
            raise _CodexProtocolError("stdin write failed") from exc

    async def read_message(self) -> dict[str, Any]:
        if self.process.stdout is None:
            raise _CodexProtocolError("stdout unavailable")
        line = await asyncio.to_thread(self.process.stdout.readline)
        if not line:
            if self.trace is not None:
                self.trace.event(
                    "stdout_eof", returncode_at_eof=self.process.poll()
                )
            raise _CodexProtocolError("app-server stream ended")
        try:
            message = json.loads(line.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if self.trace is not None:
                self.trace.incoming(
                    line, parse_error=f"{type(exc).__name__}: {exc}"
                )
            raise _CodexProtocolError("invalid app-server JSON-RPC frame") from exc
        if not isinstance(message, dict):
            if self.trace is not None:
                self.trace.incoming(line, parse_error="JSON frame was not an object")
            raise _CodexProtocolError("invalid app-server JSON-RPC message")
        if self.trace is not None:
            self.trace.incoming(line, message)
        return message

    async def respond_to_server_request(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params")
        if not isinstance(request_id, (str, int)) or not isinstance(method, str):
            raise _CodexProtocolError("invalid app-server request")
        if not isinstance(params, dict):
            params = {}

        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        }:
            available = params.get("availableDecisions")
            decision = "decline"
            if isinstance(available, list) and "cancel" in available:
                decision = "cancel"
            result: dict[str, Any] = {"decision": decision}
        elif method == "item/permissions/requestApproval":
            result = {"permissions": {}, "scope": "turn"}
        elif method == "item/tool/requestUserInput":
            result = {"answers": {}}
        elif method == "mcpServer/elicitation/request":
            result = {"action": "decline", "content": None, "_meta": None}
        else:
            await self._send_response(
                request_id,
                error={"code": -32601, "message": "unsupported app-server request"},
            )
            raise _CodexProtocolError("unsupported app-server request")
        await self._send_response(request_id, result=result)

    async def _send_response(
        self,
        request_id: str | int,
        *,
        result: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> None:
        if self.process.stdin is None:
            raise _CodexProtocolError("stdin unavailable")
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
        if error is not None:
            message["error"] = dict(error)
        else:
            message["result"] = dict(result or {})
        raw = (json.dumps(message) + "\n").encode()
        if self.trace is not None:
            self.trace.outgoing(raw, message)
        await asyncio.to_thread(
            _write_pipe,
            self.process.stdin,
            raw,
        )

    async def await_response(self, request_id: int) -> dict[str, Any]:
        while True:
            message = await self.read_message()
            if "method" in message and "id" in message:
                await self.respond_to_server_request(message)
                continue
            if message.get("id") != request_id:
                self.handle_notification(message)
                continue
            if "error" in message:
                raise _CodexProtocolError("app-server request failed")
            result = message.get("result")
            if not isinstance(result, dict):
                raise _CodexProtocolError("invalid app-server response")
            return result

    def handle_notification(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            return
        if method != "item/completed":
            return
        if params.get("threadId") != self.thread_id:
            return
        if self.turn_id is not None and params.get("turnId") != self.turn_id:
            return
        item = params.get("item")
        if not isinstance(item, dict) or item.get("type") != "agentMessage":
            return
        text = item.get("text")
        if not isinstance(text, str):
            raise _CodexProtocolError("invalid agent message")
        if len(text) > self.max_output_chars:
            raise _CodexProtocolError("final answer exceeded output bound")
        phase = item.get("phase")
        if phase == "final_answer":
            self.final_answer = text
        elif phase is None:
            self.unphased_answer = text
        elif phase != "commentary":
            raise _CodexProtocolError("invalid agent message phase")

    async def initialize(self) -> None:
        request_id = await self.send(
            "initialize",
            {
                "clientInfo": {
                    "name": "dsh-runtime",
                    "title": "DSH Runtime",
                    "version": "0.1.0",
                },
                "capabilities": {
                    "experimentalApi": False,
                    "requestAttestation": False,
                },
            },
        )
        await self.await_response(request_id)
        if self.trace is not None:
            self.trace.event("initialize_response", request_id=request_id)
        await self.notify("initialized")

    async def start_thread(self) -> None:
        params: dict[str, Any] = {
            "cwd": self.cwd,
            "ephemeral": True,
            **self.permission_params,
        }
        if self.model is not None:
            params["model"] = self.model
        request_id = await self.send("thread/start", params)
        result = await self.await_response(request_id)
        thread = result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise _CodexProtocolError("invalid thread/start result")
        if thread.get("ephemeral") is not True:
            raise _CodexProtocolError("Codex thread was not ephemeral")
        self.thread_id = thread["id"]
        if self.trace is not None:
            self.trace.event(
                "thread_start_response",
                request_id=request_id,
                thread_id=self.thread_id,
            )

    async def run_turn(self, prompt: str) -> str:
        if self.thread_id is None:
            raise _CodexProtocolError("turn started before thread")
        request_id = await self.send(
            "turn/start",
            {
                "threadId": self.thread_id,
                "input": [{"type": "text", "text": prompt, "text_elements": []}],
            },
        )
        result = await self.await_response(request_id)
        turn = result.get("turn")
        if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
            raise _CodexProtocolError("invalid turn/start result")
        self.turn_id = turn["id"]
        if self.trace is not None:
            self.trace.event(
                "turn_start_response",
                request_id=request_id,
                thread_id=self.thread_id,
                turn_id=self.turn_id,
            )

        while True:
            message = await self.read_message()
            if "method" in message and "id" in message:
                await self.respond_to_server_request(message)
                continue
            if "method" in message:
                self.handle_notification(message)
                if message.get("method") != "turn/completed":
                    continue
                params = message.get("params")
                if not isinstance(params, dict) or params.get("threadId") != self.thread_id:
                    continue
                terminal = params.get("turn")
                if not isinstance(terminal, dict) or terminal.get("id") != self.turn_id:
                    continue
                status = terminal.get("status")
                if status != "completed":
                    raise _CodexProtocolError("Codex turn did not complete")
                output = self.final_answer or self.unphased_answer
                if not output:
                    raise _CodexProtocolError("Codex completed without a final answer")
                if self.trace is not None:
                    self.trace.event(
                        "turn_completed",
                        thread_id=self.thread_id,
                        turn_id=self.turn_id,
                    )
                return output

    async def interrupt(self) -> None:
        if self.thread_id is None or self.turn_id is None:
            return
        try:
            await self.send(
                "turn/interrupt",
                {"threadId": self.thread_id, "turnId": self.turn_id},
            )
        except Exception:
            # Protocol interrupt is best effort; process teardown is authoritative.
            return

    async def dispose(self, grace_seconds: float) -> None:
        if self.trace is not None:
            self.trace.event(
                "dispose_started", returncode=self.process.poll()
            )
        if self.process.stdin is not None:
            self.process.stdin.close()
            if self.trace is not None:
                self.trace.event("stdin_closed")
        await _terminate_process_tree(self.process, grace_seconds)
        if self.trace is not None:
            self.trace.event(
                "dispose_finished", returncode=self.process.returncode
            )


def _write_pipe(pipe: Any, data: bytes) -> None:
    pipe.write(data)
    pipe.flush()


async def _terminate_process_tree(
    process: subprocess.Popen[bytes],
    grace_seconds: float,
) -> None:
    if process.poll() is not None:
        await asyncio.to_thread(process.wait)
        return

    if os.name == "nt" and process.pid is not None:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ),
                timeout=grace_seconds,
            )
        except (asyncio.TimeoutError, OSError):
            process.kill()
    else:
        process.terminate()

    try:
        await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=grace_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=grace_seconds)


def _default_command() -> tuple[str, ...]:
    codex = shutil.which("codex") or "codex"
    return (codex, "app-server", "--stdio")


class CodexPlugin:
    """Concrete one-shot Codex app-server Plugin."""

    name = "codex"

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        node_executable: str | Path | None = None,
        codex_wrapper: str | Path | None = None,
        environment: Mapping[str, str] | None = None,
        cleanup_grace_seconds: float = 2.0,
        max_output_chars: int = 100_000,
        qualification_trace_dir: str | Path | None = None,
    ) -> None:
        if command is not None and (node_executable is not None or codex_wrapper is not None):
            raise ValueError("command cannot be combined with node_executable/codex_wrapper")
        if node_executable is not None or codex_wrapper is not None:
            if node_executable is None or codex_wrapper is None:
                raise ValueError("both node_executable and codex_wrapper are required")
            self._command = (
                str(node_executable),
                str(codex_wrapper),
                "app-server",
                "--stdio",
            )
        else:
            self._command = tuple(command) if command is not None else _default_command()
        if not self._command:
            raise ValueError("Codex command cannot be empty")
        self.cleanup_grace_seconds = cleanup_grace_seconds
        self.max_output_chars = max_output_chars
        self.qualification_trace_dir = (
            Path(qualification_trace_dir)
            if qualification_trace_dir is not None
            else None
        )
        self._environment_overlay = dict(environment or {})

    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        for key in list(environment):
            upper = key.upper()
            if key.startswith("DSH_") or re.search(
                r"(?:KEY|PASSWORD|SECRET|TOKEN)", upper
            ):
                environment.pop(key, None)
        environment.update(self._environment_overlay)
        return environment

    async def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> PluginResult:
        cwd = ctx.cwd
        if cwd is None:
            return PluginResult(success=False, error="Codex workspace cwd is missing")
        cwd_path = Path(cwd)
        if not cwd_path.exists() or not cwd_path.is_dir():
            return PluginResult(success=False, error="Codex workspace cwd is invalid")

        prompt = params.get("prompt", ctx.goal)
        if not isinstance(prompt, str) or not prompt.strip():
            return PluginResult(success=False, error="Codex prompt must be non-empty text")
        model = params.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            return PluginResult(success=False, error="Codex model must be non-empty text")

        process: subprocess.Popen[bytes] | None = None
        session: _CodexSession | None = None
        stderr_task: asyncio.Task[bytes] | None = None
        trace: _CodexQualificationTrace | None = None
        trace_error: str | None = None
        trace_capture_error: str | None = None
        cancelled = False
        result: PluginResult | None = None
        reasoning = params.get("reasoning")
        if not isinstance(reasoning, str):
            reasoning = None

        if self.qualification_trace_dir is not None:
            try:
                self.qualification_trace_dir.mkdir(parents=True, exist_ok=True)
                trace_path = self.qualification_trace_dir / (
                    f"codex-worker-{uuid4().hex}.json"
                )
                trace_path.touch(exist_ok=False)
                trace = _CodexQualificationTrace(
                    trace_path,
                    task_id=ctx.task_id,
                    workspace_id=ctx.workspace_id,
                    cwd=str(cwd_path),
                    argv=self._command,
                    goal=ctx.goal,
                    model=model,
                    reasoning=reasoning,
                    allow_workspace_write=ctx.allow_workspace_write,
                )
            except OSError as exc:
                return PluginResult(
                    success=False,
                    error=(
                        f"{_QUALIFICATION_OBSERVABILITY_FAILURE}: "
                        f"cannot prepare trace sink: {type(exc).__name__}: {exc}"
                    ),
                )

        try:
            try:
                # Popen itself is synchronous and short-lived. Keeping it in
                # this coroutine avoids a cancellable worker thread creating a
                # process after the Plugin has already lost its handle.
                process = subprocess.Popen(
                    self._command,
                    cwd=str(cwd_path),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE if trace is not None else subprocess.DEVNULL,
                    env=self._environment(),
                )
            except (FileNotFoundError, OSError) as exc:
                raise _CodexProtocolError("Codex app-server startup failed") from exc

            if trace is not None:
                trace.event(
                    "process_spawned",
                    pid=process.pid,
                    executable=self._command[0],
                    argv=list(self._command),
                    cwd=str(cwd_path),
                )
                if process.stderr is None:
                    raise RuntimeError(
                        f"{_QUALIFICATION_OBSERVABILITY_FAILURE}: stderr pipe unavailable"
                    )
                stderr_task = asyncio.create_task(
                    asyncio.to_thread(process.stderr.read)
                )

            session = _CodexSession(
                process,
                cwd=str(cwd_path),
                allow_workspace_write=ctx.allow_workspace_write,
                model=model,
                max_output_chars=self.max_output_chars,
                trace=trace,
            )
            await session.initialize()
            await session.start_thread()
            output = await session.run_turn(prompt.strip())
            result = PluginResult(success=True, output=output)
        except asyncio.CancelledError:
            cancelled = True
            if trace is not None:
                trace.event("plugin_cancelled")
            if session is not None:
                await session.interrupt()
            raise
        except _CodexProtocolError as exc:
            # Only bounded stage-level diagnostics cross the Plugin boundary.
            diagnostic = str(exc)
            if diagnostic not in {
                "Codex workspace cwd is missing",
                "Codex workspace cwd is invalid",
            }:
                diagnostic = f"Codex bounded invocation failed: {diagnostic}"
            result = PluginResult(success=False, error=diagnostic)
        finally:
            if session is not None:
                await session.dispose(self.cleanup_grace_seconds)
            elif process is not None:
                await _terminate_process_tree(process, self.cleanup_grace_seconds)

            if stderr_task is not None:
                try:
                    stderr = await asyncio.shield(stderr_task)
                    if trace is not None:
                        trace.stderr = stderr
                except (OSError, asyncio.CancelledError) as exc:
                    trace_capture_error = (
                        f"stderr capture failed: {type(exc).__name__}: {exc}"
                    )

            if trace is not None:
                trace.event(
                    "plugin_terminal",
                    cancelled=cancelled,
                    result=_trace_plugin_result(result),
                )
                if trace_capture_error is not None:
                    trace_error = (
                        f"{_QUALIFICATION_OBSERVABILITY_FAILURE}: "
                        f"{trace_capture_error}"
                    )
                else:
                    try:
                        trace.persist(
                            process=process,
                            result=result,
                            cancelled=cancelled,
                        )
                    except (OSError, TypeError, ValueError) as exc:
                        trace_error = (
                            f"{_QUALIFICATION_OBSERVABILITY_FAILURE}: "
                            f"cannot persist trace: {type(exc).__name__}: {exc}"
                        )

            if trace_error is not None:
                if cancelled:
                    raise RuntimeError(trace_error)
                result = PluginResult(
                    success=False,
                    error=trace_error,
                    cleanup_error=trace_error,
                )

        return result or PluginResult(
            success=False, error="Codex invocation produced no result"
        )
