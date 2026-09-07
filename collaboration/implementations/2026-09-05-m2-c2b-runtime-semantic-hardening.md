# Milestone 2-C.2b：Runtime Semantic Hardening

日期：2026-09-05  
状态：完成  
结果：PASS

## 1. Scope

本 milestone 只修复 2-C.2a 通过测试暴露的 Runtime semantic ambiguity：

- 让 invocation 的 governing stop reason 结构化表达；
- 保留 timeout 与 cleanup failure 两个独立事实；
- 让 Executor 明确拥有 timeout、取消与 invocation settlement；
- 让 Controller 依据结构化 stop reason 做 TaskState mapping；
- 保持 `Plugin.execute(ctx, params) -> PluginResult` 不变。

本 milestone 没有实现 CodexPlugin、app-server JSON-RPC、workspace resolver 或 permission mapping。

## 2. Production files changed

### `dsh_runtime/runtime/plugin.py`

- 新增最小 `StopReason`：`COMPLETED`、`FAILED`、`TIMED_OUT`；
- `PluginResult` 保留原有 `success/output/error` 字段；
- 新增 `stop_reason`，默认 `None` 以保持现有 Plugin 构造兼容；
- 新增 `cleanup_error`，只承载 bounded cleanup failure 的可观察诊断；
- 新增 invalid result 的安全错误常量。

没有新增 `CANCELLED`、`failure_source`、process metadata 或新的 Context 类型。

### `dsh_runtime/runtime/executor.py`

- 仍是唯一 invocation governance owner；
- 将 Plugin coroutine 放入 invocation task；
- 使用 `asyncio.shield()` 区分 execution deadline 与显式 cleanup settlement；
- timeout 后显式 cancel invocation，并 await Plugin cleanup；
- cleanup exception 进入 `PluginResult.cleanup_error`，不覆盖 `StopReason.TIMED_OUT`；
- caller cancellation 仍向外传播，同时先等待 Plugin cleanup；
- 对普通 Plugin result 自动补齐 `COMPLETED`/`FAILED` stop reason；
- 非 `PluginResult` 返回值变为明确的 failed invalid-result，而不是 blank success。

### `dsh_runtime/controller.py`

- 成功判断使用 `StopReason.COMPLETED` 与 `success`；
- timeout 判断使用 `StopReason.TIMED_OUT`；
- 不再通过匹配 `"plugin execution timed out"` 决定 `TaskStatus.TIMED_OUT`；
- timeout logging 保留 cleanup failure 诊断；
- 普通 failure 使用结构化 stop reason，继续映射为 `TaskStatus.FAILED`。

## 3. Previous semantic ambiguity

2-C.2a 已证明旧路径：

```text
execution timeout
  -> Plugin cancellation
  -> finally cleanup
  -> cleanup raises
  -> wait_for propagates cleanup exception
  -> Executor generic exception branch
  -> original timeout fact is lost
```

旧实现还通过错误字符串判断 timeout：

```python
if error == PLUGIN_TIMEOUT_ERROR:
    task.status = TaskStatus.TIMED_OUT
```

这会把“错误文本恰好相同的普通失败”误判为 timeout，也无法表达：

```text
governing stop reason = timed_out
secondary cleanup fact = cleanup failed
```

## 4. Final ownership model

```text
DSHController
  - business loop
  - TaskState transition
  - whether another iteration is allowed

Executor
  - invocation task
  - execution timeout policy
  - Runtime-side cancellation intent
  - cleanup settlement observation
  - bounded result normalization

Plugin
  - concrete capability mechanics
  - internal protocol/process lifecycle
  - graceful interrupt and force cleanup
  - cleanup/quiescence bound
  - optional capability facts
```

没有创建第二个 Executor、ExecutionHandle、ProcessManager 或其他 lifecycle owner。

## 5. PluginResult change

最终最小形状为：

```python
PluginResult(
    success: bool,
    output: Any = None,
    error: str | None = None,
    stop_reason: StopReason | None = None,
    cleanup_error: str | None = None,
)
```

`error` 继续作为 bounded runtime-safe diagnostic boundary；它不应包含 raw protocol、stderr、thread ID 或 turn ID。

`cleanup_error` 只在 cleanup failure 被观察到时填充。它不是通用 cleanup taxonomy，也不是 process abstraction。

未加入：`safe_diagnostic` duplicate field、`failure_source` taxonomy、process outcome、usage、diff、streaming 或 resume fields。

## 6. Executor change

Executor 的 timeout 路径现在是：

```text
create invocation task
  -> await shield(invocation) until execution deadline
  -> record timeout intent
  -> cancel invocation
  -> await invocation cleanup
  -> capture cleanup exception if any
  -> return TIMED_OUT result with optional cleanup_error
```

因此 timeout 语义不再依赖 `wait_for()` 的异常传播形态，也不再依赖 error string。

需要强调：cleanup 是否有界仍由 concrete Plugin 的内部 cleanup/quiescence bound 保证；Executor 不会因此变成 ProcessManager。

## 7. TaskState / Controller change

没有向 `TaskState` 添加 `CANCELLED`、PID、return code、cleanup trace 或 process DTO。

Controller 只消费 bounded invocation result：

```text
StopReason.COMPLETED + success -> TaskStatus.COMPLETED
StopReason.TIMED_OUT          -> TaskStatus.TIMED_OUT
otherwise                     -> TaskStatus.FAILED
```

`TaskState.error` 保留 governing timeout/failure diagnostic；cleanup failure 通过 invocation result 与 structured logging 保持可观察，而不是把 TaskState 扩展成 execution internals DTO。

## 8. Cancellation behavior

### Timeout cancellation

- Executor 到达 execution deadline 后主动 cancel invocation；
- Plugin 的 `finally` cleanup 完成后才返回 timeout result；
- cleanup exception 不会覆盖 `StopReason.TIMED_OUT`。

### Outer cancellation

- caller cancel Executor task 后，Executor 先 cancel/settle invocation；
- Plugin cleanup 完成；
- `asyncio.CancelledError` 继续向 caller 传播；
- 不转换为普通 `FAILED`；
- 未添加 `TaskState.CANCELLED`，因为当前 DSHController 没有生产级 caller-cancellation owner 或 persisted transition。

## 9. Timeout + cleanup-failure behavior

现在的 normalized result 是：

```text
success       = false
stop_reason   = TIMED_OUT
error         = "plugin execution timed out"
cleanup_error = "RuntimeError: cleanup boom"
```

这保留了：

```text
governing stop reason != secondary cleanup fact
```

Controller 仍将 task 映射为 `TaskStatus.TIMED_OUT`，而不是因为 cleanup exception 被降级成普通 `FAILED`。

## 10. Process metadata decision

本 milestone 不引入 process outcome metadata。

理由：2-C.2b 只需要证明 timeout/cleanup distinction；首个真实 Codex capability 尚未进入实现，当前没有足够 concrete decision 证明 PID、exit code 或 signal 必须进入 Runtime result。

process lifecycle 仍是 optional execution fact。EchoPlugin 不需要 PID、return code、cleanup metadata，也没有被迫进入 subprocess model。

## 11. Explicit no-change decisions

本 milestone 没有实现或创建：

- `ExecutionHandle`；
- `ProcessManager`；
- `CANCELLED` TaskState；
- `ExecutionContext` cwd、cancellation、permission 字段；
- `WorkspaceContext`、`CancellationContext`、`PermissionContext`；
- CodexPlugin、app-server JSON-RPC、Codex permission mapping；
- workspace_id 到 cwd resolver；
- process outcome universal DTO；
- failure source/provider taxonomy；
- ExternalAgent、AgentExecutor、CLIExecutionCapability、Adapter、Provider Framework；
- streaming、resume、multi-turn、rollback、diff、usage/cost；
- Event Bus、Workflow DSL、Factory、dynamic loading。

## 12. Test matrix

| Scenario | Expected semantic | Result |
|---|---|---|
| Echo success | `COMPLETED`, output unchanged | PASS |
| ordinary Plugin exception | `FAILED`, no timeout metadata | PASS |
| plain timeout | `TIMED_OUT`, Controller maps `TaskStatus.TIMED_OUT` | PASS |
| misleading timeout error text | ordinary failure remains `FAILED` | PASS |
| timeout + cleanup exception | timeout retained, cleanup error observable | PASS |
| timeout + bounded cleanup | Executor returns only after cleanup | PASS |
| outer cancellation | cleanup completes, `CancelledError` propagates | PASS |
| invalid Plugin result | failed invalid-result, no blank success | PASS |
| non-process Echo | no process metadata required | PASS |
| previous disposable lifecycle cases | cancellation, process exit, quiescence evidence preserved | PASS |

## 13. Full regression command/result

执行环境：仓库 `.venv`。

完整命令：

```text
.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
23 passed in 0.37s
```

测试构成：

- 6 个 Runtime baseline tests；
- 8 个 2-C.2a disposable lifecycle tests；
- 9 个 2-C.2b semantic hardening tests。

production code 与新增测试均通过；没有失败或跳过测试。

## 14. Remaining unknowns

- Codex concrete capability 所需的 resolved cwd 与 risk intent；
- Codex native permission/sandbox mapping；
- app-server protocol lifecycle 与 final result parsing；
- process-tree outcome 是否需要进入最终 generic result；
- timeout 与 process exit race 的具体 metadata 形状；
- cleanup failure 在未来是否需要独立 failure source；
- DSH 是否最终需要 persisted cancellation state；
- Codex integration 对 workspace side effects 的实际验证。

## 15. Recommendation for next milestone

建议进入：

```text
Milestone 2-C.2c — First Codex-backed Bounded Capability
```

下一 milestone 才根据具体 Codex 实现引入：

- `workspace_id` 到 resolved cwd 的实际映射；
- bounded risk/authority intent；
- Codex native permission mapping；
- app-server initialize/thread/turn lifecycle；
- process-tree cleanup 与 optional process facts；
- Codex final result 到 generic `PluginResult` 的映射。

这些变化应继续留在具体 Plugin 与现有 Executor/Controller 边界内，不应先创建 provider framework。
