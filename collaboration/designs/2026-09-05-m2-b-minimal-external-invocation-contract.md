# Minimal External Invocation Contract Design

日期：2026-09-05  
状态：概念设计；未修改生产代码；未创建接口、协议、dataclass、Plugin implementation 或 framework。  
设计对象：DSH Runtime 与一个 bounded external invocation 之间的最小语义边界。

## 1. Executive Summary

第一版不需要新增一套顶层 External Agent 执行框架。当前 Runtime 已经有明确的 owner：`DSHController` 拥有业务 loop，`Executor` 拥有 plugin 调用与 timeout wrapper，`Plugin` 是执行边界，`PluginResult` 是结果返回边界，`TaskState` 是任务状态 owner。

但是，现有边界尚未完整表达 2-A.3 允许进入 Contract Design 的语义：cancellation、cleanup/quiescence、failure source、process outcome、safe diagnostic、permission/risk intent 和 terminal outcome。因而推荐的方向不是增加 `AgentExecutor` 或 `CLIExecutionCapability`，而是：

1. 保留现有 `Plugin.execute()` 作为顶层 integration seam；
2. 让 DSH-owned timeout、cancellation、workspace identity 和 risk gate 成为调用语义；
3. 让 process lifecycle 成为可选的 execution fact，而非所有 capability 的必需模型；
4. 让 capability 负责产品协议、内部 bounded retry、产品结果解析和 graceful interrupt attempt；
5. 在真正实现前，最小评估现有 `ExecutionContext`、`PluginResult` 和 `TaskState` 是否需要增量字段，而不是建立新的抽象层。

当前最小 Contract 可以进入设计桌面的，是“语义集合”和“ownership boundary”，不是具体类型命名。

## 2. Design Inputs

输入材料：

- `collaboration/investigations/2026-09-05-m2-a1-deepseekharness-codex-cli.md`
- `collaboration/investigations/2026-09-05-m2-a2-codex-runtime-behavior.md`
- `collaboration/investigations/2026-09-05-m2-a3-external-agent-evidence-synthesis.md`

### 2-A.3 allowed evidence boundary

2-A.3 的 Minimum Evidence Set 允许进入本轮设计讨论的事实为：

- 明确 workspace identity/cwd；
- bounded、可观察的 invocation lifecycle；
- process-backed invocation 的 completion 与 process outcome 分离；
- 适用时进行 whole-tree cleanup/quiescence；
- DSH 拥有 business iteration continuation/stop decision；
- DSH 拥有 execution-timeout policy，disposal grace 与之分离；
- cancellation intent 与 protocol interrupt/process cleanup 分离；
- permission/sandbox 是治理 concern，native mapping 属于 capability；
- side effects 可能存在且不能假设自动 rollback；
- bounded result：final result、stop reason、safe diagnostic、相关 process outcome；
- failure source 不应被压成单一 success/error；
- 当前证据不要求 resume、streaming、diff/rollback、usage accounting 或 multi-turn session。

## 3. Existing Runtime Responsibilities

### `DSHController`

当前代码中 `DSHController.run()`：

- 设置 task running；
- 按 `task.iteration < task.max_iterations` 驱动业务 loop；
- 从 `SimplePlanner` 得到下一步；
- 调用 `Executor.execute()`；
- 增加 iteration；
- 将成功/失败写入 `TaskState`；
- 决定 task completed、failed、timed out 或 max iterations。

因此它已经是 DSH business loop owner。外部 capability 不应获得继续下一轮的权限。

### `Executor`

当前 `Executor.execute()`：

- 从 `PluginRegistry` 取得 plugin；
- 使用 `asyncio.wait_for(plugin.execute(...), timeout_seconds)`；
- 记录 plugin started/completed/timed out/failed；
- 将 timeout 转成 `PluginResult(success=False, error=...)`；
- 将异常转成 plugin failure result。

它已经是当前 plugin invocation wrapper 和 execution timeout 的现有 owner，但结果/取消/cleanup 的语义仍然较薄。

### `Plugin` / `PluginResult`

当前 `Plugin` 只有：

```text
name
async execute(ctx, params) -> PluginResult
```

当前 `PluginResult` 只有：

```text
success
output
error
```

这足以支持 EchoPlugin 和 Milestone 1 的 bounded action，但不能直接表达外部调用已证明存在的 stop reason、failure source、safe diagnostic、process outcome 或 cleanup state。

### `TaskState`

当前已有 `task_id`、`workspace_id`、`goal`、`max_iterations`、`timeout_seconds`、`status`、`iteration`、`result`、`error` 和 timestamps。它已经拥有 task-level terminal state，但没有 cancellation state、failure source、process outcome 或 side-effect observation。

### `PluginRegistry`

当前只负责按名称注册和获取 plugin。没有证据要求它承担 process lifecycle、permission policy、provider discovery 或 dynamic loading。

## 4. Contract Semantics

本节先定义语义，不定义 Python 类型。

### 4.1 Invocation Input Semantics

一个 bounded external invocation 至少需要能表达：

| Semantic | DSH-owned? | Capability-specific? | v1 disposition |
|---|---:|---:|---|
| workspace identity / cwd boundary | Yes, at least selection/confirmation | Capability applies it to native runtime | Enter v1 |
| bounded input | Yes, size/lifetime boundary | Input encoding belongs to capability | Enter v1 |
| execution timeout policy | Yes | Capability may observe/translate it | Enter v1 |
| cancellation intent | Yes | Protocol interrupt is capability detail | Enter v1 |
| permission/risk intent | Yes, as a gate/decision | Native approval/sandbox mapping | Enter v1 semantically, no common enum yet |
| environment/configuration | Boundary-controlled | Native names and mapping belong to capability | Only explicit bounded config |
| model/provider selection | Not generically proven | Capability-specific | Keep capability-specific |
| retry count | DSH owns business retry policy | Capability may have bounded internal retry | Do not expose Codex retry as DSH iteration |

### 4.2 DSH-owned versus mapping detail

DSH decides whether an invocation is allowed, where it belongs, how long it may run, when it is cancelled, what risk boundary is allowed, and whether a terminal outcome permits the next business iteration.

The capability decides how to start its own protocol, how to map a risk boundary to native fields, how to perform bounded internal retry, how to parse product output, and how to attempt graceful interrupt.

The contract must not grant the capability task-state mutation authority, cross-capability orchestration authority, unlimited retry authority, or business-loop ownership.

## 5. Lifecycle Model

### 5.1 Public semantic lifecycle

The minimum public lifecycle is:

```text
preflight
  → capability start
  → ready / accepted
  → bounded execution
  → terminal outcome
  → disposal
  → quiescence when applicable
```

These boundaries have different visibility:

| Boundary | Must be contract-relevant? | Reason |
|---|---:|---|
| preflight | Yes | Invalid input, cwd or risk must fail before uncontrolled execution |
| capability start | Yes | DSH needs to distinguish startup failure from execution result |
| ready / accepted | Yes semantically | Prevent claiming an invocation exists before capability accepts it |
| bounded execution | Yes | DSH timeout/cancellation and business iteration apply here |
| terminal outcome | Yes | DSH needs a decision point for task state and next iteration |
| disposal | Yes | Terminal result does not imply resources are gone |
| quiescence | Yes when process/resource-backed | Cleanup completion is a separate observable boundary |
| product protocol steps | No public DSH state | Codex `initialize`, `thread/start`, `turn/start`, `turn/completed` are implementation details |
| intermediate commentary/tool events | Not v1 contract | Current provider filters them; no streaming requirement is proven |

### 5.2 Lifecycle invariant

An invocation is not fully cleaned up merely because it has a terminal result. For process-backed capability, cleanup remains pending until the applicable process tree reaches quiescence or a bounded cleanup failure is reported.

## 6. Timeout / Cancellation / Disposal

### 6.1 Execution timeout

**Semantic definition**：DSH-owned policy defining the maximum allowed execution duration for one invocation or business action.

**Recommended placement**：It should remain a Runtime/`Executor` responsibility at the top-level boundary, because the current `Executor` already owns `asyncio.wait_for`. The value may be passed to a capability as bounded input, but the capability must not silently replace DSH's timeout decision with its own unbounded policy.

**On timeout**：the invocation should produce a distinct timeout stop reason, not a generic product failure. The task may become `TIMED_OUT` under current `TaskState` semantics. The exact result shape is a future implementation decision.

**Cleanup**：timeout must initiate cancellation/cleanup and must not return control while a process-backed invocation is known to remain live, subject to the cleanup boundary and any cleanup failure.

**Ordering**：if timeout and process exit race, DSH should retain both the governing stop reason and observed process outcome; whichever arrives first must not erase the other fact.

### 6.2 Cancellation

Cancellation is an upper-layer intent, with the following distinguishable stages:

```text
cancel requested
  → capability interrupt attempted (optional / best effort)
  → execution settles as cancelled or another terminal outcome
  → process cleanup (if applicable)
  → quiescence (if applicable)
```

The current Codex evidence proves that protocol interrupt and process termination are separate. A successful interrupt attempt is not proof of cleanup; process termination is not the same semantic event as the cancellation request.

### 6.3 Disposal grace

Disposal grace is a lower-level cleanup bound used to escalate termination and wait for resource quiescence. It is not the maximum execution time and should not automatically change an ordinary running task into a timeout.

**Open design question**：Whether disposal grace belongs as an explicit public invocation input or remains capability/process implementation configuration. Current evidence proves the semantic distinction, but not the need for a universal public field.

## 7. Workspace / Permission / Side Effects

### 7.1 Workspace semantics

The first version must associate the invocation with a logical workspace identity and ensure that the capability receives the resolved execution location required by its environment. For current Codex, parent Session cwd is used for both child process and product thread.

The contract should not make physical paths the long-term identity of a workspace; the existing DSH `workspace_id` is the relevant logical identity, while path resolution remains environment-specific.

### 7.2 Side-effect semantics

The contract must not imply that failure, cancellation or timeout rolls back external effects. The current evidence proves that explicit dangerous mode can write the disposable workspace, while the provider does not return a diff or perform rollback.

Minimum semantic statement:

```text
This invocation may have side effects within its permitted boundary.
Terminal failure or cancellation does not imply no side effect.
```

No transaction, snapshot, diff system or rollback manager is justified by current evidence.

### 7.3 Permission / risk semantics

This is both:

- a Codex-specific mechanism: `approvalPolicy`, reviewer and sandbox fields;
- a generic DSH governance concern: the invocation's allowed authority/risk boundary changes possible side effects.

The first contract should express the semantic fact that DSH authorizes a risk/authority boundary, while allowing each capability to map it natively. It should not yet define a universal `PermissionPolicy` enum because the reports contain evidence for one Codex mapping, not a cross-capability equivalence.

**Benefit of a semantic gate**：DSH retains authority and prevents a capability from choosing a broader risk mode silently.

**Cost**：different capabilities may not share the same vocabulary; a premature common enum could misrepresent capability semantics or hide important distinctions.

## 8. Result Semantics

### 8.1 Minimum terminal facts

The minimum conceptual terminal result needs to make these facts available at the boundary:

- terminal versus non-terminal status;
- bounded final output, when available;
- stop reason;
- coarse failure source, when not successful;
- safe diagnostic, when useful and safe;
- process outcome when the invocation is process-backed;
- correlation to DSH task and business iteration.

This does not require one large DTO. The facts can remain separated by ownership: capability produces a bounded outcome; `Executor`/Controller applies it to DSH task state; process facts remain optional.

### 8.2 Not required in v1 result

- raw stdout/stderr;
- raw product protocol frames;
- Codex `threadId`/`turnId` as DSH domain fields;
- reasoning, commentary, tool activity;
- complete usage/token/cost;
- workspace diff;
- streaming events;
- resume/session identifiers.

### 8.3 Result interpretation

Capability owns product-specific parsing and maps its result into bounded terminal facts. DSH owns the task-level meaning: completed, failed, timed out, cancelled, or whether another business iteration is permitted. DSH should not need to understand Codex's `final_answer` or `phase:null` names.

## 9. Failure Semantics

### 9.1 Minimum failure sources

The first semantic failure model should distinguish these sources:

```text
preflight/input
startup
execution/product
permission/sandbox
cancellation
timeout
process
invalid result
cleanup
```

This is a conceptual source classification, not a complete exception hierarchy and not necessarily a universal enum.

### 9.2 Ownership of failure facts

| Fact | TaskState impact | Diagnostic-only possibility | Stop reason possibility |
|---|---|---|---|
| preflight/input failure | Task fails before execution | Include safe validation detail | error / failed |
| startup failure | Task fails; no normal execution result | Yes, startup stage | error |
| execution/product failure | Task fails unless policy says otherwise | Product detail should be bounded | error |
| permission/sandbox failure | Usually failed; may be policy-visible | Native reason should be safe | error |
| cancellation | Task becomes cancelled/aborted semantic state | Interrupt detail may be diagnostic | cancelled / aborted |
| timeout | Task becomes timed out | Timing detail may be diagnostic | timed_out |
| process failure | Task fails or becomes cancelled depending on preceding cause | Exit code/signal useful | error or cancelled |
| invalid result | Task fails | Parser detail may be diagnostic | error |
| cleanup failure | Must remain observable even after primary result | Often diagnostic, but not silently dropped | error if cleanup invalidates completion |

The exact mapping to current `TaskStatus` needs implementation review. Current `TaskStatus` has no cancelled state and therefore cannot fully represent all proven external invocation outcomes without either a minimal state evolution or a deliberate mapping decision.

### 9.3 Do not conflate

```text
failure cause  !=  stop reason
process outcome !=  safe diagnostic
cancel request !=  interrupt success
terminal result !=  cleanup complete
```

## 10. Process-backed vs Non-process Invocation

Process lifecycle is an optional execution fact, not the universal shape of the entire Contract.

### Process-backed capability

May expose/require observation of:

- process started/accepted;
- exit code/signal;
- termination request;
- process-tree cleanup;
- whole-tree quiescence;
- cleanup failure.

Current Codex is in this category.

### Non-process capability

Examples include remote API, RAG service, MCP transport or local library call. They still need bounded execution, cancellation/timeout semantics as applicable, terminal result and failure source, but may have no process id, exit code, signal or tree quiescence.

Therefore process facts should be optional and absent rather than fabricated. Making every capability subprocess-centric would incorrectly force RAG or remote APIs to model fake process lifecycle.

## 11. Candidate Contract Shapes

At most three shapes are considered. They are conceptual only.

### Option A — Thin Invocation

```text
DSH / Executor
  → invoke bounded capability(input)
  → await terminal outcome
```

**Strengths**：lowest complexity; fits current `Plugin.execute()` and `Executor`; process optional; easy to test with EchoPlugin.

**Weaknesses**：cancellation and post-result disposal are implicit in coroutine behavior; harder to represent a live process handle or quiescence independently; current `TaskState`/`PluginResult` need semantic expansion.

**Fit**：good for one-shot non-process capabilities; possible baseline for process-backed plugin if cleanup is reliably owned inside `execute()`.

**Abstraction risk**：low.

### Option B — Invocation plus lifecycle handle

```text
DSH / Executor
  → start bounded capability
  → handle.result
  → handle.cancel()
  → handle.dispose()
  → await quiescence when applicable
```

**Strengths**：makes cancellation, disposal and process-backed lifecycle explicit; testable race boundaries; does not require process facts for non-process implementations if handle semantics are optional internally.

**Weaknesses**：introduces a new lifecycle concept; risks duplicating `Executor`; needs careful ownership rules; may be premature for current one-shot Runtime Skeleton.

**Fit**：best semantic fit for Codex-like process-backed invocation, but not yet proven necessary as a new public top-level abstraction because current plugin coroutine plus `finally` can potentially own cleanup.

**Abstraction risk**：medium.

### Option C — Runtime-owned wrapper around capability call

```text
DSH / Executor owns timeout, cancellation and disposal wrapper
  → capability supplies one bounded call
  → Runtime applies terminal result and optional process facts
```

**Strengths**：preserves existing owners; centralizes DSH governance; process remains optional; minimizes product protocol leakage.

**Weaknesses**：requires a capability to expose enough cancellation/cleanup hooks without inventing a generic framework; current `ExecutionContext` does not carry cancellation signal; `PluginResult` is too small for all facts.

**Fit**：recommended direction, implemented only through the smallest evidence-backed evolution of existing boundaries if/when implementation is authorized.

**Abstraction risk**：low to medium, depending on whether changes stay inside existing Plugin/Executor/TaskState owners.

### Shape decision

Choose **Option C as the semantic direction**, with Option A as the initial implementation shape where a plugin's `execute()` can safely own its complete bounded lifecycle. Do not create Option B's public handle until a concrete process-backed plugin proves that coroutine cancellation and `finally` cleanup cannot satisfy the required lifecycle boundary.

## 12. Decision Matrix

| Concern | Existing Owner | New Contract Need | New Type Needed? | Reason |
|---|---|---|---|---|
| business iteration | `DSHController` | Preserve ownership | No | Already implemented and explicitly bounded |
| plugin execution | `Executor` + `Plugin` | Add external bounded-call semantics minimally | Not proven | Existing boundary is the natural seam |
| execution timeout | `Executor` / `TaskState.timeout_seconds` | Distinguish from cleanup grace | No new top-level type | Existing timeout wrapper already exists |
| cancellation | Not fully owned; asyncio cancellation is implicit | Explicit cancellation intent and bounded settlement | Possibly minimal existing-boundary field | Current context has no signal; no new subsystem justified |
| workspace | `ExecutionContext.workspace_id`, `TaskState.workspace_id` | Confirm logical identity and resolved location semantics | No `WorkspaceContext` justified | Existing logical workspace owner exists |
| permission/risk | None currently | DSH-side gate + capability-specific mapping | Common enum not justified | One Codex mapping is evidence, cross-capability vocabulary is not |
| process lifecycle | Underlying plugin/capability; no DSH object | Optional process facts and cleanup boundary | No `ProcessManager` justified | Current evidence proves concern, not new owner |
| cleanup | Plugin coroutine / underlying process owner | Must not disappear after terminal result | Handle only if concrete need appears | Existing Executor does not yet model post-result quiescence |
| result | `PluginResult` + `TaskState.result` | Bounded final output, stop reason, source, diagnostic | Minimal evolution likely; large DTO not justified | Current result shape is too thin but ownership exists |
| failure | `Executor` converts exceptions; `TaskState.error` stores string | Preserve source/stop/process distinctions | Exception hierarchy not justified | Current string error loses proven distinctions |
| diagnostics | observability logger + `PluginResult.error` | Safe diagnostic separate from raw process/protocol output | No new logging framework | Existing logging boundary can remain |
| loop ownership | `DSHController` | Capability cannot continue business loop | No | Directly proven and already implemented |
| iteration correlation | `TaskState.iteration` / controller logging | Include invocation-to-iteration association | No new owner | Existing task/iteration facts are sufficient conceptually |
| resume | None | Explicitly absent in v1 | No | Absence of requirement is a result |
| streaming | None | Explicitly absent in v1 | No | Intermediate events are capability internals for now |

## 13. Recommended Minimal Contract

This is a conceptual sketch, not production code.

### 13.1 Semantic request sketch

```text
BoundedInvocationRequest
  task correlation: task_id + business iteration
  workspace identity: logical workspace_id
  resolved execution location: only where capability requires it
  bounded input: capability-defined input within DSH limits
  execution timeout policy: DSH-owned
  cancellation signal/intent: DSH-owned
  risk/authority intent: DSH-owned semantic gate
  capability-specific configuration: explicit and bounded
```

The name `BoundedInvocationRequest` is illustrative only and should not be created as a type in this milestone.

### 13.2 Semantic terminal outcome sketch

```text
TerminalOutcome
  terminal: true
  final_output: bounded capability result, if any
  stop_reason: completed | failed | timed_out | cancelled | aborted | ...
  failure_source: optional coarse source
  safe_diagnostic: optional
  process_outcome: optional { exit_code, signal }
  correlation: task_id + business iteration
```

The `stop_reason`, `failure_source`, `safe_diagnostic` and `process_outcome` concepts must remain semantically separate. This sketch does not mandate one DTO; they may be represented by existing `PluginResult`/`TaskState` evolution and runtime-owned metadata.

### 13.3 Lifecycle rule sketch

```text
DSH starts one bounded plugin invocation.
Capability performs only its bounded internal mechanics.
DSH owns timeout and cancellation intent.
Capability may attempt graceful interrupt.
Terminal result is not cleanup completion.
Process-backed capability must not be considered quiescent until its
applicable process cleanup boundary is satisfied.
DSH alone decides whether another business iteration is allowed.
```

### 13.4 Minimal evolution recommendation

If implementation is later authorized, first evaluate a small evolution of existing owners:

- `ExecutionContext`: carry only the cancellation/workspace facts genuinely needed by a concrete capability;
- `PluginResult`: carry only the proven terminal/result distinctions that the Controller must act on;
- `TaskState`: add only task-level states/facts that cannot be represented without losing timeout/cancellation/process distinctions;
- `Executor`: preserve timeout ownership and coordinate cancellation/cleanup without moving business-loop authority into plugins.

Do not introduce a second executor, a generic agent hierarchy, or a common permission enum as part of that evolution.

## 14. Impact on Existing Runtime Skeleton

### What already fits

- `DSHController` fits DSH-owned loop semantics.
- `Executor` fits DSH-owned timeout wrapping.
- `Plugin` fits a replaceable bounded capability seam.
- `PluginRegistry` fits static bounded registration.
- `TaskState.workspace_id` fits logical workspace identity.
- `TaskState.iteration` fits DSH iteration correlation.
- structured lifecycle logging fits basic observation.

### What is currently insufficient

- `ExecutionContext` has no explicit cancellation signal or risk intent.
- `PluginResult.success/output/error` cannot preserve failure source, stop reason, safe diagnostic and optional process outcome separately.
- `TaskState` has no explicit cancelled status and only one string error field.
- `Executor` timeout conversion returns a generic error string and does not conceptually expose post-timeout process quiescence.
- current controller returns after the first action, which is consistent with Milestone 1 but does not yet prove a richer multi-iteration external-agent policy.

### Design consequence

The existing skeleton should not be discarded or wrapped in a new external execution subsystem. The likely implementation work, if separately approved, is an incremental boundary adjustment driven by the first real plugin requirement. This milestone does not authorize that code change.

## 15. Not in v1

The following are explicitly outside the first Contract:

- resume / session continuation;
- streaming or progress event contract;
- workspace diff;
- rollback, transaction, snapshot;
- usage/token/cost accounting;
- multi-turn or persistent session;
- generic cross-provider error taxonomy;
- generic permission enum or permission framework;
- Event Bus;
- Workflow DSL;
- dynamic loading;
- Provider Framework;
- CodeBuddy compatibility layer;
- `AgentExecutor`;
- `CLIExecutionCapability`;
- `CodexAdapter`;
- `ExternalAgent` class/interface hierarchy;
- `ProcessManager`;
- `WorkspaceContext` object solely for naming purposes.

## 16. Open Questions

- Can a concrete process-backed plugin safely own interrupt and whole-tree cleanup inside a cancellable `execute()` coroutine, or is an explicit handle required?
- Should disposal grace be a public invocation semantic or remain capability/process configuration?
- What is the smallest safe addition to `TaskState` for cancelled and cleanup-failed outcomes?
- Should `PluginResult` be expanded, or should runtime metadata remain separate from capability output?
- How should DSH distinguish timeout-versus-process-exit races in task state while preserving both facts?
- How should risk intent be represented without pretending Codex, RAG, MCP and remote API permissions are equivalent?
- What exact workspace resolver semantics are needed when logical `workspace_id` maps to different physical environments?
- What evidence would justify streaming, usage, diff, rollback or resume in a later milestone?

## 17. Implementation Preconditions

Before any production implementation, all of the following should be explicit:

1. A concrete real capability is selected; no generic framework is implemented speculatively.
2. Its invocation lifecycle and cancellation behavior are documented by source or experiment.
3. The smallest existing owner (`Plugin`, `Executor`, `TaskState` or `PluginResult`) that can carry each new semantic is identified.
4. Any new field is tied to a demonstrated DSH decision, not merely to a product protocol detail.
5. Process facts remain optional so non-process capabilities are not forced into subprocess semantics.
6. Timeout, cancellation and disposal tests cover race ordering and cleanup/quiescence.
7. Permission/risk tests use disposable workspaces and verify side effects directly.
8. No resume, streaming, rollback, usage, multi-agent or provider abstraction is added without new evidence.

The next implementation milestone, if approved, should therefore begin with one concrete bounded capability and a narrow change to the existing Plugin/Executor boundary. It should not begin with a new abstraction hierarchy.

