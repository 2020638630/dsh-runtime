# Milestone 2-C.1：First Real Capability Implementation Plan

日期：2026-09-05  
状态：计划完成，尚未授权实现  
范围：只收敛第一个真实 bounded external capability 的最小 change set；本轮不修改 production code。

## 1. 输入与边界

本计划基于以下材料：

- `collaboration/investigations/2026-09-05-m2-a1-deepseekharness-codex-cli.md`
- `collaboration/investigations/2026-09-05-m2-a2-codex-runtime-behavior.md`
- `collaboration/investigations/2026-09-05-m2-a3-external-agent-evidence-synthesis.md`
- `collaboration/designs/2026-09-05-m2-b-minimal-external-invocation-contract.md`
- 当前 `dsh_runtime` 源码与 `tests/test_runtime.py`

首个目标默认选择：Codex-backed bounded capability。此选择只决定具体 Plugin 的产品实现，不把 Runtime contract 变成 Codex-specific contract。

明确不在本轮：

- 不修改 `dsh_runtime` production code；
- 不实现 `CodexPlugin`、app-server JSON-RPC 或真实 Codex integration tests；
- 不创建 `AgentExecutor`、`ExternalAgent`、Adapter、Provider Framework、Factory、ProcessManager 或新的 Context hierarchy；
- 不进入 Milestone 2-C.2；
- 不加入 resume、streaming、rollback、diff、usage/cost、multi-turn 或 Event Bus。

## 2. 当前 Runtime 真实边界

```text
TaskState
  ↓
DSHController（拥有 business loop 与 task terminal decision）
  ↓
SimplePlanner（生成 plugin + params）
  ↓
Executor（查找 Plugin、timeout 包装、异常转换、logging）
  ↓
Plugin.execute(ExecutionContext, params) -> PluginResult
  ↓
PluginRegistry / concrete Plugin
```

### 2.1 已经够用的部分

| 组件 | 已有能力 | 对第一 capability 的结论 |
|---|---|---|
| `DSHController` | 拥有 iteration、一次 action 后的 terminal decision、task logging | 保留，不把 loop 放进 Plugin |
| `SimplePlanner` | 返回 plugin 名称与参数 | 保留；Codex 参数先由具体 Plugin 定义 |
| `Executor` | registry lookup、`asyncio.wait_for`、异常边界、timeout logging | 作为最小治理入口保留 |
| `Plugin` | `async execute(ctx, params)` | 首先验证继续沿用，不预先改成 handle API |
| `PluginRegistry` | 静态注册、重复注册检查、unknown plugin 失败 | 不改 |
| `TaskState.workspace_id` | logical workspace identity | 保留；不把绝对路径当作长期身份 |
| `TaskState.iteration` | DSH iteration correlation | 保留，但当前未传入 `ExecutionContext`，后续若有实际决策需要再最小补齐 |
| observability | JSON-line structured lifecycle logging | 保留 logger；只增加实际需要的 bounded facts |
| `EchoPlugin` | 非 process、无副作用的回归 capability | 必须继续不受影响 |

### 2.2 当前不足

- `ExecutionContext` 只有 `task_id`、`workspace_id`、`goal`，没有 resolved cwd、cancellation intent 或 risk intent；
- `ExecutionContext` 没有 `iteration`，所以 invocation 与 business iteration 尚未在 Plugin 输入中显式关联；
- `PluginResult` 只有 `success/output/error`，不能分别表达 stop reason、failure source、safe diagnostic 和 optional process outcome；
- `TaskState` 没有 `CANCELLED`，也只有一个字符串 `error`；
- `Executor` 的 timeout 返回通用字符串，尚未表达 timeout 与 process outcome/cleanup 的关系；
- `workspace/manager.py` 目前只定义 logical `Workspace`，没有 logical id 到 resolved cwd 的映射能力；
- 当前 controller 在首个 action 后返回，这是 Milestone 1 的边界，不应在本计划中扩展成 agent loop。

## 3. ExecutionContext 评估

| 字段/语义 | Need now | Why | Evidence | Existing alternative |
|---|---|---|---|---|
| `task_id` | 已有，直接复用 | 需要 invocation correlation | 当前 `TaskState`、Controller logging | 无需新增 correlation object |
| `workspace_id` | 已有，直接复用 | DSH 的 logical workspace identity | 2-A.1/2-A.2/2-B workspace findings | 不创建 `WorkspaceContext` |
| `iteration` | 可能需要，建议作为最小候选 | 2-B 要求 task + business iteration correlation；当前只在 Controller 内可见 | `TaskState.iteration` 已存在，当前未传入 ctx | 可先由 logging 关联；若 Plugin 不消费则不新增 |
| `goal` | 已有，直接复用 | Echo 与当前 planner 输入依赖 | 当前 `SimplePlanner`、`EchoPlugin` | 无需重新定义 input DTO |
| resolved cwd | Codex capability 需要 | child process 与 product thread 都需要 cwd | 2-A.1/2-A.2/2-B R1 | 优先由现有 workspace module/resolver 提供，再传给具体 Plugin；不创建 Context hierarchy |
| cancellation signal/token | 需要由具体 lifecycle 证明后决定 | DSH 必须拥有 cancellation authority；当前只有隐式 asyncio cancellation | 2-A.3 G2/G3，2-B §6 | 第一阶段可使用 coroutine cancellation；只有 Plugin 无法感知/协调时才加最小字段 |
| risk/authority intent | 需要有显式治理语义，但不一定进 core Context | capability 不得静默扩大权限 | 2-A.2 permission experiments，2-B §7.3 | 先由具体 Codex params 做 bounded mapping；不创建通用 permission enum |

结论：不创建 `BoundedInvocationRequest`、`WorkspaceContext` 或 `CancellationContext`。只有当 Codex Plugin 的实际输入证明某字段必须由 Runtime 传递时，才对现有 `ExecutionContext` 做单字段演进。

## 4. Plugin Protocol 与 timeout/cancellation 结论

### 4.1 Protocol

保留：

```python
async execute(ctx, params) -> PluginResult
```

具体 Plugin 应在该 coroutine 内完成其 bounded internal mechanics：启动、协议 startup、产品结果解析、graceful interrupt attempt、process cleanup，以及必要的 `finally` 和 quiescence 等待。

暂不引入：`start()`、`ExecutionHandle`、`cancel()`、`dispose()`。只有 disposable process-backed test 证明现有 coroutine 无法表达 cleanup ownership 或 timeout/cancellation race，才重新评估显式 handle。

### 4.2 `asyncio.wait_for()` 能保证什么

Python asyncio 语义下，`wait_for()` 超时时会取消被等待的 Task，并等待取消处理完成；因此如果 Plugin 正确响应 cancellation，且 `finally` 中的 cleanup 本身能完成，Executor 可以观察到 cleanup 后再返回 timeout。

但它不是 process-backed cleanup 的完整保证：

- Plugin 吞掉 `CancelledError` 或继续运行时，超时边界可能被拖延；
- `finally` 中若 cleanup 永不完成，`wait_for()` 不能凭自身提供独立的第二层有界 quiescence；
- 外部 process 的 interrupt、tree termination、exit observation、disposal grace 与 execution timeout 是不同语义；
- 当前 Executor 没有记录 cleanup failure，也没有 process outcome 字段。

因此结论是：

> `wait_for()` 足以作为协作式 coroutine capability 的第一版 timeout 基础，但不足以单独证明任意 process-backed Plugin 已完成 bounded cleanup。必须先做 disposable lifecycle tests；Codex Plugin 的 cleanup 是否需要内部 handle 由测试结果决定。

## 5. PluginResult、TaskState 与 process facts

### 5.1 PluginResult

不把它一次性改成“大而全 DTO”。实现授权后，优先评估以下最小演进：

- `stop_reason`：至少能区分 completed、failed、timed_out、cancelled/aborted；
- `failure_source`：粗粒度区分 input、startup、product、permission、timeout、cancellation、process、invalid-result、cleanup；
- `safe_diagnostic`：与最终 output 分离，禁止把 raw protocol/stderr 泄露到业务结果；
- `process_outcome`：可选，仅由 process-backed capability 提供，例如 exit code/signal。

这些字段可以是现有结果边界的最小可选字段；不引入通用异常层级、原始事件、token usage、diff 或 session IDs。

### 5.2 TaskState

建议在后续实现中只增加 DSH 必须做 terminal decision 的事实：

- `CANCELLED` 只有在第一版要保留 cancellation 与 failed 的区别时才增加；当前证据支持这是独立语义，但实现前仍需以测试确认映射；
- 不把 process outcome、raw diagnostic、cleanup trace 全部塞进 `TaskState`；
- cleanup failure 必须可观察，是否改变 task terminal status 由 Executor/Controller 的明确规则决定；
- timeout 与 cancellation 不应通过普通 `FAILED` 静默折叠。

### 5.3 Process outcome 放置

process outcome 是 optional execution fact，不是所有 Plugin 的通用属性。第一版优先由具体 process-backed Plugin 产生并作为 optional result metadata 或 executor-side metadata 传递；只有 Controller 的 task decision 需要它时，才提升到 `TaskState`。

不创建 `ProcessManager`，也不要求 EchoPlugin、远程 API 或 RAG capability 制造虚假的 process 字段。

## 6. Workspace 与 risk/permission 最小方案

### Workspace

`TaskState.workspace_id` 继续表示 logical identity。Codex 首次实现需要一个 resolved cwd，并将同一 cwd 用于 child process 与 Codex `thread/start`。解析位置优先放在现有 workspace module 或 ExecutionContext construction seam；不要让绝对路径成为 workspace identity，也不解决远程/distributed workspace 映射。

### Risk / permission

首版采用“DSH 允许的 bounded intent + Codex Plugin 内部 native mapping”：

- DSH/调用参数明确允许的风险边界；
- Codex Plugin 将其映射为 `approvalPolicy` / sandbox native fields；
- Plugin 不得自行升级到更宽权限；
- 使用 disposable workspace 做 permission denial 与 explicit side-effect tests。

不创建通用 `PermissionPolicy` enum 或 permission framework。一个 Codex 映射不足以证明 Codex、RAG、MCP、remote API 共享同一权限词汇。

## 7. Failure mapping 最小规则

不创建复杂 exception hierarchy。具体 Plugin 到 runtime 的 bounded mapping 至少覆盖：

| 来源 | 最小结果 | DSH 处理 |
|---|---|---|
| input/preflight | safe diagnostic | FAILED，通常不启动 invocation |
| startup | failure source=startup | FAILED |
| execution/product | bounded output 或 safe diagnostic | FAILED，除非未来有明确 policy |
| permission/sandbox | safe permission diagnostic | FAILED 或 policy-visible failure |
| timeout | stop reason=timed_out | TIMED_OUT；保留 cleanup/process facts |
| cancellation | stop reason=cancelled/aborted | 只有不丢信息时才映射为 CANCELLED |
| process | process outcome + safe diagnostic | FAILED 或沿用先前 timeout/cancel stop reason |
| invalid result | no blank success | FAILED |
| cleanup | 不得静默丢失 | 记录诊断；必要时使 completion 失效 |

必须保持以下区分：

```text
failure source != stop reason
process outcome != safe diagnostic
cancel request != interrupt success
terminal result != cleanup complete
```

## 8. Change Surface Matrix

| Component | Current State | Required Change | Why | Risk | Test |
|---|---|---|---|---|---|
| `ExecutionContext` | task/workspace/goal 三字段 | 先不改；若 Codex 实际需要，再加最小 cwd/iteration/cancellation 字段 | 避免 speculative context hierarchy | 中 | context propagation |
| `Plugin` | `async execute(ctx, params)` | 保持 protocol；要求具体 Plugin 在 coroutine 内拥有 bounded lifecycle | 现有 seam 已足够作为起点 | 低 | Echo regression + disposable cancellation |
| `PluginResult` | success/output/error | 最小增加 terminal/failure/diagnostic/process metadata，字段以测试证明为准 | 当前字符串会丢失 proven distinctions | 中 | result mapping / invalid result |
| `Executor` | `wait_for` + generic exception/timeout mapping | 保持 timeout owner；明确 cancellation、cleanup wait/failure 与 result mapping | DSH governance 应在此处 | 高 | timeout ordering / cleanup failure |
| `TaskState` | 无 CANCELLED，单一 error | 评估最小 `CANCELLED` 与必要 terminal facts | 不折叠 cancellation/timeout | 中 | task state mapping |
| `DSHController` | 拥有 loop，首 action 后返回 | 不改 loop ownership；只消费清晰的 terminal result | 防止 capability 变成 agent loop | 低 | existing controller tests |
| `PluginRegistry` | 静态注册 | 不改 | 已满足替换 capability seam | 低 | existing registration tests |
| `workspace` module | 只有 logical `Workspace` | 若 Codex 需要，增加最小 resolver/映射能力 | 提供 cwd 而不污染 identity | 中 | workspace propagation |
| observability | structured lifecycle events | 增加 bounded safe fields；不记录 raw protocol/stderr/secret | 需要观察 race 与 failure source | 中 | log field assertions |
| `EchoPlugin` | 非 process success | 不改行为 | 证明 process facts 是 optional | 低 | existing Echo test |

## 9. Proposed implementation sequence（后续获授权时）

每个 commit 都应小、可测试、可回滚，并避免无关重构。

### Commit 1 — Runtime semantic hardening

目标：在现有 `Plugin`/`Executor`/`PluginResult`/`TaskState` 边界内，定义并实现最小 terminal/failure mapping；只加入被 Codex capability 的实际 DSH decision 证明需要的字段。

验收：现有 6 个回归场景全部通过；Echo 行为不变；timeout、invalid result、failure source 不再靠不可区分的字符串推断。

### Commit 2 — Cancellation / cleanup disposable tests

目标：先用 test doubles 验证 cancellation、`finally`、cleanup ordering、cleanup failure、timeout race。若现有 `execute()` coroutine 能满足 bounded lifecycle，则不引入 handle。

验收：

- timeout 会触发 Plugin cancellation；
- cleanup 在 Executor 返回前完成，或 cleanup failure 被明确记录；
- cancellation 与 timeout 不互相误报；
- process-backed facts 可缺省，Echo 不受影响。

若测试证明 coroutine seam 不足，暂停并单独提出 handle 设计；不在同一 commit 偷渡新 hierarchy。

### Commit 3 — Codex-backed bounded Plugin minimum

目标：只实现一个具体 Codex Plugin，内部封装 app-server JSON-RPC、initialize、ephemeral thread/start、single turn/start、final answer parsing、best-effort interrupt 与 process-tree cleanup。

约束：Codex-specific names/fields 只存在于 Plugin 内部；DSH 只接收 generic bounded result semantics；无 resume、streaming、rollback、diff、usage 或 multi-turn。

### Commit 4 — Codex integration tests

目标：在 disposable workspace 验证 success、permission denial、process failure、timeout、cancellation、quiescence、safe diagnostic 与 workspace propagation。

约束：真实模型/账号行为与 loopback fixture 要区分；测试不能把 fixture 证据描述成 cloud model quality 证据。

## 10. 明确 No-Change 清单

本计划及其后的首个 capability 实现，除非新证据与明确授权，否则不修改或创建：

- `PluginRegistry` 的架构；
- `SimplePlanner` 的业务 loop ownership；
- `DSHController` 的 loop ownership；
- Event Bus、Workflow DSL、Factory、dynamic loading；
- Provider Framework、`ExternalAgent`、`AgentExecutor`、`CLIExecutionCapability`；
- `CodexAdapter`、`CodeBuddyAdapter` 或 provider hierarchy；
- `WorkspaceContext`、`CancellationContext`、`PermissionContext`；
- `ProcessManager`；
- resume/session continuation、streaming/progress、rollback/transaction/snapshot/diff；
- usage/token/cost accounting；
- generic permission enum、generic cross-provider error taxonomy；
- 将所有 capability 强制建模为 subprocess；
- 将 Codex `threadId`、`turnId`、raw JSON-RPC、stderr、reasoning/tool activity 暴露为 DSH domain result。

## 11. 完成条件与下一步

Milestone 2-C.1 完成条件：

1. 明确首个 capability 为 Codex-backed bounded capability；
2. 证明现有 `Plugin.execute()` 是首选起点，handle 仅为实验失败后的备选；
3. 明确 `wait_for` 对 cooperative cleanup 的能力边界；
4. 明确 ExecutionContext、PluginResult、TaskState、Executor 的最小候选变更；
5. 产出 Change Surface Matrix、No-Change 清单、测试计划与 commit sequence；
6. 未修改 production code，未进入 2-C.2。

下一步需要用户明确授权一个具体实现 commit，优先从 Commit 1 或 Commit 2 开始，而不是直接实现通用框架或 CodexPlugin。
