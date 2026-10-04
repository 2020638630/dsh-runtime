"""DSH-owned bounded task loop."""

import time

from .observability.logger import record
from .planner import SimplePlanner
from .runtime.executor import Executor
from .runtime.plugin import ExecutionContext, StopReason
from .runtime.registry import PluginRegistry
from .state import TaskState, TaskStatus
from .workspace.manager import WorkspaceManager, WorkspaceResolutionError


class DSHController:
    def __init__(
        self,
        registry: PluginRegistry,
        planner: SimplePlanner | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        self.executor = Executor(registry)
        self.planner = planner or SimplePlanner()
        self.workspace_manager = workspace_manager or WorkspaceManager()

    async def run(self, task: TaskState) -> TaskState:
        started = time.perf_counter()
        task.status = TaskStatus.RUNNING
        record("task_started", task_id=task.task_id, workspace_id=task.workspace_id)

        # Invocation budget is checked before the initial Planner evaluation.
        if task.iteration >= task.max_iterations:
            return self._max_iterations(task, started)

        decision = self.planner.next_action(task)
        if decision.is_terminal:
            task.error = "planner returned terminal decision before invocation"
            task.status = TaskStatus.FAILED
            record(
                "task_failed",
                task_id=task.task_id,
                workspace_id=task.workspace_id,
                error=task.error,
                stop_reason=StopReason.FAILED.value,
            )
            return task

        while True:
            try:
                cwd = self.workspace_manager.resolve_cwd(task.workspace_id)
            except WorkspaceResolutionError as exc:
                task.error = str(exc)
                task.status = TaskStatus.FAILED
                record(
                    "task_failed",
                    task_id=task.task_id,
                    workspace_id=task.workspace_id,
                    error=task.error,
                    stop_reason=StopReason.FAILED.value,
                )
                return task
            if decision.allow_workspace_write is None:
                allow_workspace_write = task.allow_workspace_write
            else:
                allow_workspace_write = (
                    task.allow_workspace_write
                    and decision.allow_workspace_write
                )
            result = await self.executor.execute(
                decision.plugin,
                ExecutionContext(
                    task.task_id,
                    task.workspace_id,
                    task.goal,
                    cwd=str(cwd),
                    allow_workspace_write=allow_workspace_write,
                ),
                decision.params,
                task.timeout_seconds,
            )
            task.iteration += 1
            record("plugin_executed", task_id=task.task_id, plugin=decision.plugin,
                   iteration=task.iteration, success=result.success)
            if result.stop_reason is StopReason.COMPLETED and result.success:
                task.last_invocation_result = result.output
            else:
                error = result.error or "plugin execution failed"
                if result.stop_reason is StopReason.TIMED_OUT:
                    task.status = TaskStatus.TIMED_OUT
                    task.error = error
                    record(
                        "task_timed_out",
                        task_id=task.task_id,
                        workspace_id=task.workspace_id,
                        iteration=task.iteration,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        error=error,
                        cleanup_error=result.cleanup_error,
                        stop_reason=result.stop_reason.value,
                    )
                else:
                    task.apply_failure(error)
                    record(
                        "task_failed",
                        task_id=task.task_id,
                        workspace_id=task.workspace_id,
                        iteration=task.iteration,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        error=error,
                        cleanup_error=result.cleanup_error,
                        stop_reason=(
                            result.stop_reason.value
                            if result.stop_reason is not None
                            else StopReason.FAILED.value
                        ),
                    )

                return task

            next_decision = self.planner.next_action(task)
            if next_decision.is_terminal:
                if next_decision.terminal_success:
                    task.apply_success(task.last_invocation_result)
                    record(
                        "task_completed",
                        task_id=task.task_id,
                        workspace_id=task.workspace_id,
                        iteration=task.iteration,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                else:
                    task.apply_failure(
                        next_decision.terminal_error
                        or "planner returned terminal failure"
                    )
                    record(
                        "task_failed",
                        task_id=task.task_id,
                        workspace_id=task.workspace_id,
                        iteration=task.iteration,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        error=task.error,
                        stop_reason=StopReason.FAILED.value,
                    )
                return task

            if task.iteration >= task.max_iterations:
                return self._max_iterations(task, started)

            decision = next_decision

    @staticmethod
    def _max_iterations(task: TaskState, started: float) -> TaskState:
        task.status = TaskStatus.MAX_ITERATIONS
        task.error = "maximum iterations reached"
        record(
            "task_failed",
            task_id=task.task_id,
            workspace_id=task.workspace_id,
            iteration=task.iteration,
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=task.error,
        )
        return task
