"""DSH-owned bounded task loop."""

import time

from .observability.logger import record
from .planner import SimplePlanner
from .runtime.executor import Executor
from .runtime.plugin import ExecutionContext, PLUGIN_TIMEOUT_ERROR
from .runtime.registry import PluginRegistry
from .state import TaskState, TaskStatus


class DSHController:
    def __init__(self, registry: PluginRegistry, planner: SimplePlanner | None = None) -> None:
        self.executor = Executor(registry)
        self.planner = planner or SimplePlanner()

    async def run(self, task: TaskState) -> TaskState:
        started = time.perf_counter()
        task.status = TaskStatus.RUNNING
        record("task_started", task_id=task.task_id, workspace_id=task.workspace_id)

        # DSH owns the loop. This milestone intentionally completes after one
        # bounded action; future continuation must be decided by DSH Controller
        # / Planner, not by a Plugin or by adding control fields to PluginResult.
        while task.iteration < task.max_iterations:
            decision = self.planner.next_action(task)
            result = await self.executor.execute(
                decision.plugin,
                ExecutionContext(task.task_id, task.workspace_id, task.goal),
                decision.params,
                task.timeout_seconds,
            )
            task.iteration += 1
            record("plugin_executed", task_id=task.task_id, plugin=decision.plugin,
                   iteration=task.iteration, success=result.success)
            if result.success:
                task.apply_success(result.output)
                record(
                    "task_completed",
                    task_id=task.task_id,
                    workspace_id=task.workspace_id,
                    iteration=task.iteration,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            else:
                error = result.error or "plugin execution failed"
                if error == PLUGIN_TIMEOUT_ERROR:
                    task.status = TaskStatus.TIMED_OUT
                    task.error = error
                    record(
                        "task_timed_out",
                        task_id=task.task_id,
                        workspace_id=task.workspace_id,
                        iteration=task.iteration,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        error=error,
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
                    )
            return task

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
