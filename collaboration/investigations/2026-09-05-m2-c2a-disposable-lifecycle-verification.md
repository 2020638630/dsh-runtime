# Milestone 2-C.2a：Disposable Lifecycle Verification

日期：2026-09-05  
状态：完成  
范围：只验证现有 `Executor` + `asyncio.wait_for()` + `Plugin.execute()` seam；没有修改 production code、Runtime semantic models 或引入新 abstraction。

## 1. Scope

本轮回答的问题是：

> 当前 coroutine seam 能否让一个具体 process-backed capability 在 `Plugin.execute()` 内拥有 bounded cancellation、cleanup 与 quiescence lifecycle，并在 cleanup 完成后才把控制权交还给 DSH？

验证对象：

- `dsh_runtime.runtime.executor.Executor`；
- 现有 `asyncio.wait_for(plugin.execute(...), timeout)`；
- test-only disposable Plugin doubles；
- 一个由当前 Python 解释器启动的短命 helper subprocess；
- 现有 `EchoPlugin` regression。

未验证/未实现：Codex、app-server JSON-RPC、真实 permission mapping、workspace resolver、`PluginResult`/`TaskState` 扩展、`ExecutionHandle`。

## 2. Existing Runtime Seam

当前 production path 是：

```text
Executor.execute()
  -> asyncio.wait_for(plugin.execute(...), timeout)
  -> PluginResult
```

当前 Executor：

- 将 Plugin exception 转换为 `PluginResult(success=False, error=...)`；
- 将 `asyncio.TimeoutError` 转换为 `plugin execution timed out`；
- 没有第二个 cleanup owner；
- 没有 process manager、handle 或 cleanup taxonomy；
- 外层 `asyncio.CancelledError` 不被普通 `Exception` 分支吞掉。

测试文件：

- `tests/test_disposable_lifecycle.py`

## 3. Test Harness

测试 harness 使用三类 disposable double：

1. `CleanupProbe`：在 `finally` 中执行真实 async delay，记录取消与 cleanup 顺序；
2. `SimulatedProcessPlugin`：模拟 graceful interrupt 失败、force termination 与 quiescence；
3. `SubprocessPlugin`：通过 `asyncio.create_subprocess_exec()` 启动 helper process，在 `finally` 中 terminate 并 await process exit。

此外使用 `SuppressingProbe` 验证违反 cooperative cancellation 的 Plugin 行为，并使用 `EchoPlugin` 验证 non-process regression。

## 4. asyncio Cancellation Findings

### 4.1 Timeout cancellation propagation

**Given**：Plugin 阻塞等待，并在收到 cancellation 时记录 `CancelledError`。  
**When**：Executor 使用 `timeout_seconds=0.005` 调用它。  
**Observed**：Plugin 依次记录 `running`、`cancelled`，最终 Executor 返回 timeout result。  
**Conclusion**：`wait_for()` 确实向 Plugin coroutine 传播取消；timeout 没有被当作 ordinary plugin failure。  
**Contract implication**：第一版 concrete Plugin 可以继续使用 `execute()` seam，但必须 cooperative 地传播 cancellation。

### 4.2 Outer task cancellation

**Given**：Executor invocation 正在运行，Plugin 在 `finally` 中有 async cleanup。  
**When**：调用方直接 cancel 外层 Executor task。  
**Observed**：Plugin 收到 cancellation，完成 cleanup；外层 `CancelledError` 继续传播给调用方。  
**Conclusion**：timeout cancellation 与 caller cancellation 都能穿过当前 seam，但当前 Executor 没有把 caller cancellation 转换为 `PluginResult`。  
**Contract implication**：这是当前 cancellation authority 的自然边界；是否需要 `TaskState.CANCELLED` 应留到 semantic hardening 决定，本轮不新增。

## 5. finally / Cleanup Findings

### 5.1 Cleanup ordering

**Given**：Plugin 在 `finally` 中执行 `await asyncio.sleep(0.02)`。  
**When**：执行 timeout。  
**Observed**：顺序为：

```text
running
cancelled
cleanup_started
cleanup_finished
Executor returns timeout
```

并且 `cleanup_done` 已设置后测试才收到 Executor result。  
**Conclusion**：对于 cooperative coroutine，当前 `wait_for()` 会等待 cancellation handling 与 `finally` cleanup 完成。  
**Contract implication**：terminal timeout result 不会早于该 Plugin 自己声明的 cleanup completion。

### 5.2 Async cleanup duration

**Given**：execution timeout 为 5ms，cleanup 需要至少 20ms。  
**When**：Executor 执行 timeout。  
**Observed**：总 wall-clock duration 至少包含 cleanup delay，明显超过 5ms。  
**Conclusion**：当前 `timeout_seconds` 是 cancellation 开始前的 execution budget，不是 Executor 返回的 absolute wall-clock bound。  
**Contract implication**：execution timeout 与 cleanup/quiescence bound 必须保持两个语义；process-backed Plugin 需要自己为 cleanup 提供内部 bounded wait。

## 6. Cleanup Exception Behavior

**Given**：Plugin 在 `finally` cleanup 中抛出 `RuntimeError("cleanup boom")`。  
**When**：同样触发 execution timeout。  
**Observed**：当前 `wait_for()` 最终抛出 cleanup exception；Executor 的 generic `Exception` 分支将其转换为失败 result。原始 `plugin execution timed out` 不再保留。

**Conclusion**：cleanup exception 可以被当前 coroutine seam 表达，但当前 production mapping 会让 cleanup exception 覆盖原始 timeout。

**Contract implication**：这是 semantic hardening 的真实输入：后续最小规则必须保留“timeout 是 governing stop reason”与“cleanup failed 是附加 failure fact”的区别，不能靠现有单一 error string 完成完整表达。本轮不修改 `PluginResult`。

## 7. CancelledError Suppression Behavior

**Given**：Plugin 捕获 `CancelledError`，等待额外 30ms 后返回 success。  
**When**：Executor timeout 为 5ms。  
**Observed**：`wait_for()` 等待该 coroutine 完成，最终返回 success；总时长至少达到额外 delay。  
**Conclusion**：`wait_for()` 不是不可绕过的 absolute timeout；Plugin 可以通过吞掉 cancellation 改变 terminal result。

这属于：

```text
contract violation by Plugin
```

而不是：

```text
contract incapable of expressing required lifecycle
```

第一版 concrete Plugin 的 contract 必须规定：收到 cancellation 后不得把取消静默转换为成功；如果需要延迟，应在内部 bounded cleanup 中显式完成并重新传播取消。

## 8. Process-backed Lifecycle Findings

### 8.1 Simulated graceful → force cleanup

**Given**：graceful interrupt 明确失败，force termination 与 quiescence wait 可用。  
**When**：Plugin 在 cancellation 后进入 `finally`。  
**Observed**：

```text
cancelled
graceful_attempt
graceful_failed
force_terminate
quiescent
Executor returns timeout
```

**Conclusion**：具体 Plugin 可以在一次 `execute()` coroutine 内表达 graceful attempt、force fallback 与 quiescence confirmation。graceful failure 不必自动等同于 overall invocation failure，只要 force cleanup 成功且 quiescence confirmed。

### 8.2 Actual helper subprocess

**Given**：Plugin 启动 Python helper process，等待 invocation cancellation。  
**When**：Executor timeout 触发 Plugin cleanup。  
**Observed**：顺序为：

```text
started
cancelled
terminate_requested
process_exited
Executor returns timeout
```

测试在 Executor 返回后确认 child `returncode` 非空，因此 process 已退出。  
**Conclusion**：在这个 concrete test double 中，process termination 与 exit observation 可以被 Plugin 自己拥有；不需要 Runtime-wide `ProcessManager` 或 `ExecutionHandle` 才能完成该 lifecycle。

## 9. Timeout vs Cleanup-bound Findings

当前模型可以表达两个连续阶段，但只有通过具体 Plugin 内部实现：

```text
execution timeout
  -> coroutine cancellation
  -> bounded internal cleanup/quiescence
  -> terminal result returned
```

`Executor` 自己目前只拥有第一层 `wait_for()`。它不能自动知道外部 process 是否已 quiescent，也不能在 cleanup exception 时保留双重事实。因此：

- execution timeout 是 DSH/Executor governance fact；
- cleanup/quiescence bound 是 process-backed Plugin 的 bounded internal mechanic；
- 两者不能合并成一个 timeout 数值或一个普通 error string；
- 未来 semantic hardening 需要保存 governing stop reason 与 cleanup/process facts，但不需要在本轮创建新 lifecycle abstraction。

## 10. Quiescence Findings

**Given**：Plugin 在 cleanup 内使用自己的 bounded `asyncio.wait_for()` 等待 quiescence，并在 deadline 到期时抛出 safe error。  
**When**：Executor 处理 timeout cancellation。  
**Observed**：Executor 返回 failure result，diagnostic 包含 `quiescence deadline exceeded`。  
**Conclusion**：当前 `execute()` seam 能表达 quiescence failure；但 Executor 目前只得到 generic failure string，无法区分原始 timeout 与 cleanup/quiescence failure。

因此，当前 seam 对 lifecycle mechanics 足够，对完整 runtime result semantics 尚不够。这正是 2-C.2b 的 hardening 输入，而不是引入 handle 的证据。

## 11. Non-process Regression

`EchoPlugin` 仍然通过当前 Executor 成功返回：

```text
success = true
output = "unchanged"
```

它不需要 PID、process outcome 或 cleanup lifecycle。该结果支持：

> Process lifecycle is an optional execution fact, not the universal Plugin model.

## 12. Contract Violations vs Contract Limitations

### Plugin contract violations

- 吞掉 `CancelledError` 后继续运行并返回 success；
- 在要求 bounded cleanup 的场景中无限等待；
- 把 graceful interrupt 失败静默当成 quiescence 成功；
- 在允许的 risk boundary 外自行扩大权限。

### 当前 contract/semantic limitations

- `PluginResult` 只有一个 `error` 字符串，不能保留 timeout + cleanup failure 两个事实；
- `TaskState` 没有独立 cancelled state；
- Executor 没有 cleanup/process outcome metadata；
- caller cancellation 没有被转换为 runtime terminal result；
- workspace/cwd、risk intent 尚未进入 runtime contract。

前一组不能用新增 Runtime abstraction 来掩盖；后一组应在具体 capability 需求驱动下进入 2-C.2b 的最小 semantic hardening。

## 13. ExecutionHandle Decision

最终决定：

```text
PASS
```

理由：测试证明一个 concrete process-backed Plugin 可以在同一个 `Plugin.execute()` coroutine 内完成：

- coroutine cancellation；
- `finally` cleanup；
- bounded async cleanup；
- graceful interrupt failure 后的 force cleanup；
- helper process exit observation；
- quiescence confirmation / failure reporting。

因此：

```text
ExecutionHandle remains NOT JUSTIFIED.
```

该 PASS 有明确前提：Plugin 必须 cooperative、内部 cleanup 必须有界、process-backed cleanup 必须由 Plugin 自己等待 quiescence。测试没有证明当前通用 Executor 自动替所有 Plugin 提供这些保证。

## 14. Minimal Production Implications

本轮不实施，但后续 2-C.2b 应优先处理：

1. timeout stop reason 与 cleanup failure 不再互相覆盖；
2. 保留 safe diagnostic 与 optional process outcome 的区别；
3. 明确 outer cancellation 与 timeout 的 task-level mapping；
4. 为具体 process-backed capability 定义 cleanup/quiescence 的 bounded rule；
5. 保持 EchoPlugin 等 non-process capability 无需伪造 process fields；
6. 仍不创建 `ExecutionHandle`、`ProcessManager` 或通用 permission framework。

## 15. Remaining Unknowns

- 真实 Codex app-server 的 interrupt receipt 与 process-tree behavior；
- Codex 具体 stdout/stderr、approval、sandbox 与 workspace mapping；
- 子进程树而非单个 child 的 Windows cleanup 细节；
- timeout 与 process exit 同时发生时的最终 metadata 形状；
- cleanup failure 是否应令一个原本可接受的 `TIMED_OUT` 结果变成 task failure；
- cancellation 是否需要独立 `TaskState.CANCELLED`；
- concrete capability 是否需要 resolved cwd 与 risk intent 进入 `ExecutionContext`。

## 16. Recommendation for 2-C.2b

建议进入：

```text
Milestone 2-C.2b — Runtime Semantic Hardening
```

但只做由本报告证明的最小变化：先定义 timeout/cancellation/cleanup/process facts 的 ownership 与 mapping，再决定 `PluginResult`、`TaskState` 或 `ExecutionContext` 的最小字段。完成 hardening 前不实现 CodexPlugin。

## 17. Verification Record

执行命令：

```text
.venv\Scripts\python.exe -m pytest -q tests/test_disposable_lifecycle.py
```

结果：

```text
8 passed in 0.38s
```

本轮未修改任何 `dsh_runtime` production file。
