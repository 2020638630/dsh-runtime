# Milestone 2-C.2c：First Codex-backed Bounded Capability

日期：2026-09-05  
状态：完成，PASS  
范围：在现有 `Plugin.execute()` seam 内实现一个具体、一次性、bounded Codex app-server capability。

## 1. Scope

本 milestone 实现了：

```text
DSH task
  -> Executor governance
  -> CodexPlugin.execute()
  -> Codex app-server process
  -> initialize
  -> ephemeral thread/start
  -> single turn/start
  -> bounded final result
  -> cleanup/quiescence
  -> PluginResult
  -> Controller/TaskState
```

未实现：resume、streaming、persistent session、multi-turn、rollback、diff、usage/cost、Provider Framework、ExecutionHandle、ProcessManager。

## 2. Files changed

### Production

- `dsh_runtime/plugins/codex.py`
- `dsh_runtime/workspace/manager.py`
- `dsh_runtime/runtime/plugin.py`
- `dsh_runtime/runtime/executor.py`
- `dsh_runtime/controller.py`
- `dsh_runtime/state.py`

### Tests

- `tests/test_codex_plugin.py`
- `tests/codex_app_server_stub.mjs`
- Existing lifecycle and semantic-hardening tests were updated to preserve the new timeout/cleanup distinction.

## 3. StopReason ownership correction

先完成 Commit 0 修正：Executor 现在无条件把普通 Plugin return 归一化为：

```text
success=True  -> COMPLETED
success=False -> FAILED
```

Plugin 即使返回：

```python
PluginResult(success=True, stop_reason=StopReason.TIMED_OUT)
```

也会被 Executor 归一化为 `COMPLETED`。只有 Executor 的真实 execution deadline 路径可以产生 `TIMED_OUT`。

对应测试已覆盖：

- success Plugin 伪造 `TIMED_OUT`；
- failure Plugin 伪造 `TIMED_OUT`；
- 实际 Executor deadline 仍为 `TIMED_OUT`。

Commit 0 后先运行回归：`25 passed`。

## 4. Final ExecutionContext change

保留原有：

```text
task_id
workspace_id
goal
```

只增加两个具体 capability 已证明需要的字段：

```text
cwd: str | None
allow_workspace_write: bool
```

没有增加 iteration、cancellation token、Codex thread/turn ID 或新的 Context 类型。

`cwd` 是 resolved physical invocation location；`workspace_id` 仍是 logical identity。

## 5. Workspace resolution ownership

扩展现有 `workspace/manager.py`，新增 `WorkspaceManager`：

- `DSHController` 在调用 Plugin 前解析 logical `workspace_id`；
- resolver 验证 cwd 存在且为 directory；
- 解析失败时返回 bounded task failure，不启动 Codex；
- 解析出的 cwd 同时传给 `ExecutionContext` 与 Codex child process；
- CodexPlugin 不负责 logical workspace mapping；
- 没有创建 `WorkspaceContext`；
- 没有把绝对路径当作长期 workspace identity。

默认 `dsh.main` 映射到当前 Runtime cwd；测试使用显式 logical id 到 disposable directory 的 mapping。

## 6. Authority decision and native mapping

DSH-owned authority fact 是 `TaskState.allow_workspace_write`，默认值为 `False`。Controller 将它传入 `ExecutionContext`；Plugin params 中同名字段不会覆盖该值。

CodexPlugin 内部使用已由 2-A 证据确认的 native mapping：

```text
allow_workspace_write=False
  -> approvalPolicy = "never"

allow_workspace_write=True
  -> approvalPolicy = "on-request"
  -> approvalsReviewer = "auto_review"
  -> sandbox = "workspace-write"
```

没有暴露：

- `dangerously-bypass-approvals-and-sandbox`；
- `danger-full-access`；
- 通用 `PermissionPolicy` / `RiskFramework` / `AuthorityContext`。

因此 capability 参数不是 authority，CodexPlugin 不能通过 params 静默扩大权限。

## 7. Codex process/protocol lifecycle

实现位于 `dsh_runtime/plugins/codex.py`，没有创建 Adapter、Provider 或 ProcessManager。

一次 `execute()` 只执行：

```text
one app-server process
one initialize handshake
one ephemeral thread/start
one turn/start
one terminal turn result
one cleanup/quiescence
```

协议细节保持在 CodexPlugin 内部：

- JSON-RPC line framing；
- `initialize` / `initialized`；
- `thread/start`；
- `turn/start`；
- `turn/completed`；
- `item/completed` 中的 `agentMessage`；
- `phase=final_answer`，并支持 `phase=null` fallback；
- approval/input/MCP request fail-closed 或返回 evidence-backed unattended response。

Codex child 使用 direct process invocation，不经 shell。当前 Windows 环境的 asyncio overlapped PIPE 创建存在 `WinError 5`，因此 concrete Plugin 使用 `subprocess.Popen` 配合 `asyncio.to_thread` 进行 blocking pipe read/write；这不改变 Plugin contract，也不创建通用 process abstraction。

## 8. Result mapping

成功时 CodexPlugin 只返回：

```python
PluginResult(success=True, output=<bounded final answer>)
```

失败时只返回 bounded safe diagnostic，例如：

- `Codex workspace cwd is missing`；
- `Codex workspace cwd is invalid`；
- `Codex app-server startup failed`；
- `Codex bounded invocation failed: ...`。

Executor 负责补齐 `COMPLETED` / `FAILED` / `TIMED_OUT` stop reason。

没有暴露：

- threadId / turnId；
- raw JSON-RPC；
- raw stderr；
- reasoning / commentary / tool activity；
- internal retry details；
- process PID、exit code、signal。

## 9. Cancellation path

Runtime timeout 或 caller cancellation 进入现有 Executor：

```text
Executor cancellation
  -> Plugin coroutine cancellation
  -> CodexPlugin best-effort turn/interrupt
  -> stdin close
  -> Windows taskkill /PID /T /F
  -> process wait
  -> re-propagate outer CancelledError or return TIMED_OUT
```

`turn/interrupt` 是 best effort；process/tree cleanup 与 quiescence 是 authoritative boundary。

CodexPlugin 不吞掉 `CancelledError`，也不把 caller cancellation 转成普通 success/failed result。

## 10. Cleanup/quiescence behavior

CodexPlugin 自己拥有 cleanup grace：

- 关闭 JSON-RPC stdin；
- Windows 使用 `taskkill /PID /T /F` 处理 process tree；
- 等待 child exit；
- grace 到期时使用 force kill fallback；
- cleanup 与 Executor execution timeout 分开。

这保持：

```text
Executor timeout != CodexPlugin cleanup/quiescence bound
```

未创建 `ExecutionHandle` 或 `ProcessManager`。

## 11. Process outcome decision

本 milestone 不向 generic `PluginResult` 添加 PID、exit code、signal 或 universal process metadata。

CodexPlugin 内部只使用 process state 判断：

- child 是否启动；
- cleanup 是否完成；
- quiescence 是否满足。

当前没有 Controller decision 需要这些事实，因此它们保持 capability-internal optional execution facts。

## 12. Safe diagnostic boundary

`PluginResult.error` 继续作为 bounded safe diagnostic boundary。

- stderr 使用 DEVNULL，不泄露到 result；
- raw protocol frame 不进入 result；
- 启动/协议错误使用固定阶段诊断；
- 不包含 credential、token、environment secret、reasoning 或原始 JSON。

## 13. Test evidence

### Deterministic loopback evidence

`tests/codex_app_server_stub.mjs` 是 test-only Node app-server-shaped process，不代表真实 Codex 或云端模型行为。

`tests/test_codex_plugin.py` 覆盖：

- one process / one ephemeral thread / one turn success；
- logical workspace 到 cwd 传递；
- read-only native mapping；
- workspace-write native mapping；
- params 不能扩大 authority；
- invalid workspace 在 spawn 前失败；
- protocol/product failure；
- missing executable；
- Executor timeout 与 process cleanup；
- caller cancellation 与 cleanup；
- Echo/non-process regression。

### Real local Codex evidence

当前机器实际环境：

```text
codex-cli 0.153.0
C:\Users\Administrator\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe
```

既有调查中的 DeepSeekHarness package-local `@openai/codex@0.149.1` 与 Node 24 路径仍可通过 `node_executable` + `codex_wrapper` 显式注入；默认路径使用当前机器已验证的 PATH Codex 0.153.0。

真实本机 probe 使用 disposable `CODEX_HOME`，确认实际 Codex app-server 完成：

```text
initialize
thread/start
ephemeral = true
thread cwd = D:\PythonProject\dsh-runtime
```

真实 turn smoke 使用只读 authority 与 45 秒 Executor deadline；当前环境没有在 deadline 内返回 terminal model result，Plugin 正确返回 `TIMED_OUT` 且 cleanup_error 为空。该结果证明 bounded timeout/cleanup，不证明云端模型成功或账户服务质量。

另一次使用默认 `C:\Users\Administrator\.codex` 的尝试被 Codex 自身拒绝，原因是该目录 SQLite state 初始化 `WinError 5`；这属于宿主 Codex home 权限问题，已通过 disposable `CODEX_HOME` 隔离。真实模型 turn 结果仍保持 Unknown。

## 14. Full regression result

完整命令：

```text
.venv\Scripts\python.exe -m pytest -q
```

最终结果：

```text
33 passed in 1.12s
```

其中包含：

- 6 个 Runtime baseline tests；
- 8 个 2-C.2a lifecycle tests；
- 11 个 2-C.2b semantic hardening tests；
- 8 个 CodexPlugin/loopback tests。

## 15. Remaining unknowns

- 当前真实 Codex 0.153.0 环境下的云端 model turn 成功路径；
- 真实账户/服务认证与模型响应行为；
- real turn 中 approval request 的具体完整序列；
- Codex tool path 产生 descendant process 时的实际 Windows tree behavior；
- workspace-write 模式下真实文件 side effect 的完整验证；
- timeout 与真实 `turn/completed` 同时到达时的产品级 race 细节；
- 是否需要未来将某些 process facts 提升到 generic result；
- 是否需要未来 persisted caller cancellation state。

## 16. Architecture implications

本 milestone 证明：

- `Plugin.execute()` 仍足以承载第一个 process-backed capability；
- Executor 仍是唯一 Runtime timeout governance owner；
- DSH workspace identity 与 physical cwd 可以由现有 workspace owner 分离管理；
- authority 可以用单一 DSH-owned bounded fact 驱动具体 Codex native mapping；
- process lifecycle 可保持 CodexPlugin 内部，不需要 universal process model；
- non-process Plugin 不需要伪造 PID/process metadata；
- 不需要 ExternalAgent、Provider Framework、Adapter、AgentExecutor 或 ExecutionHandle。

## 17. Next recommendation

建议下一步进入真实 Codex integration evidence hardening：

1. 在具备可用 Codex model service 的 disposable `CODEX_HOME` 下验证 successful turn；
2. 验证 read-only denial 与 workspace-write side effect；
3. 验证真实 turn cancellation、interrupt 与 tree quiescence；
4. 只在这些 concrete facts 需要时，再增补最小 result metadata。

不要由此创建通用 provider/process framework，也不要把当前真实模型环境 Unknown 误写成成功证据。
