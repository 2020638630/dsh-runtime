# External Agent Integration Evidence Synthesis

日期：2026-09-05  
目的：合并 Milestone 2-A.1 的源码事实与 Milestone 2-A.2 的运行时验证，提取最小、证据驱动的 External Agent Integration Requirements。  
范围声明：本文不设计 Integration Contract，不创建接口、协议、类、dataclass 或新的 Runtime 抽象。

## 1. Executive Summary

当前证据证明，DSH 若治理类似 Codex 的外部 Agent 调用，至少必须能够处理以下运行时事实：外部调用拥有明确的 workspace/cwd；调用有可观察且可终止的进程生命周期；进程树需要被回收并确认 quiescence；取消与进程终止是不同层次的行为；execution timeout 与 disposal grace 不能混同；权限/沙箱选择会真实改变 side effects；失败需要区分来源、stop reason、process outcome 和安全诊断；结果边界至少要能表达最终结果、停止原因和安全失败信息。

这些是治理需求，不等于某个具体类名或层次结构。当前证据没有证明 DSH 需要 `AgentExecutor`、`CLIExecutionCapability`、通用 `ExternalAgent` interface、resume、streaming、rollback、Provider Framework、Factory、Event Bus 或 Workflow DSL。

核心边界保持不变：

```text
DSH owns the business loop.
External capability owns its bounded internal protocol mechanics.
Everything below DSH remains bounded and replaceable.
```

Codex 的 JSON-RPC、`initialize`、`thread/start`、`turn/start`、ephemeral thread 和 `turn/interrupt` 是当前产品机制，不应直接升级为 DSH 的通用领域模型。

## 2. Evidence Sources

### Source A — Milestone 2-A.1

文件：`collaboration/investigations/2026-09-05-m2-a1-deepseekharness-codex-cli.md`

证明了 DeepSeekHarness provider 的源码路径：父 Session cwd → `resolveChildCwd()` → `ctx.subprocess.spawn()` → package-local Codex wrapper → JSON-RPC app-server；以及 prompt、stdio、env、permission、取消、cleanup、failure 和 result filtering 的实现事实。

### Source B — Milestone 2-A.2

文件：`collaboration/investigations/2026-09-05-m2-a2-codex-runtime-behavior.md`

证明了当前机器上 package-local `@openai/codex@0.149.1` 的真实 app-server/provider 测试行为。兼容 Node 24 下 `real-product.spec.ts` 结果为 7/7 passed。实验使用真实 Codex app-server 进程，但 Responses API 是 loopback fixture；因此对进程、协议、权限映射、结果和 teardown 的证据强，对真实云模型服务行为的证据弱或未知。

### Evidence quality rule

- **Confirmed by Source / Config**：代码或配置直接证明。
- **Confirmed by Experiment**：本机受控实验直接观察。
- **Inference**：由两类证据推断，但不是直接行为证明。
- **Unknown**：当前材料不能确认。

## 3. Proven Runtime Requirements

本层只列同时具有源码事实与运行时验证，或已经由两层证据共同支持的最小 requirement。这里的 requirement 是 DSH 必须能治理/观察的语义，不是实现对象。

### R1 — Invocation 必须有明确 workspace identity / cwd

**Why it exists**：Codex child cwd 和 `thread/start.cwd` 都来自父 Session cwd；dangerous-write 实验确认文件副作用实际落在该 workspace。

**Evidence**：2-A.1 的 `parent.session.header.cwd`、`resolveChildCwd()`、spawn/thread cwd；2-A.2 的 disposable workspace 写入实验。

**Governance owner**：DSH 至少拥有任务 workspace identity 的选择或确认权；capability 负责在其边界内使用。

**Current behavior**：当前 provider 继承父 Session cwd，没有额外 workspace diff 回传。

**Open question**：未来 DSH 是否需要比父 Session cwd 更严格的边界或跨环境映射。

### R2 — 外部 invocation 必须有可观察的 process lifecycle

**Why it exists**：Codex 是独立 app-server child process；spawn、运行、exit code/signal、termination 和 whole-tree quiescence 都是现实行为。

**Evidence**：2-A.1 的 subprocess path；2-A.2 的正常、直接终止、取消测试及 `waitForExit()` 通过。

**Governance owner**：共享 process owner 负责 OS 进程机制；DSH 必须能观察生命周期边界并决定何时允许任务继续/结束。

**Current behavior**：subprocess service 使用 detached process/tree management，`child.done` 提供 exit facts，`waitForExit()` 观察 whole-tree。

**Open question**：特定 Codex tool path 是否会生成 descendants，当前实验没有观察到但也没有证明绝不会发生。

### R3 — Cleanup 必须达到 whole-tree quiescence

**Why it exists**：直接 child exit 不必然等于 descendants 消失；当前 subprocess owner 的约定显式等待 whole-tree。

**Evidence**：2-A.1 的 `terminate()` / `waitForExit()` 源码；2-A.2 的 handles quiescence 验证。

**Governance owner**：DSH governance 需要把“调用结束”和“进程树已回收”区分开；具体 SIGTERM/SIGKILL/taskkill 机制属于 process capability。

**Current behavior**：POSIX 使用 detached process group；Windows 使用 tree termination；dispose 后等待 whole-tree。

**Open question**：远程或非本地执行环境是否能提供同等 whole-tree 事实。

### R4 — Permission / sandbox 语义必须被显式治理

**Why it exists**：实验确认 `never` 阻止升级副作用，dangerous mode 可写 disposable workspace；模式选择改变实际 side effects。

**Evidence**：2-A.1 的 permission mapping；2-A.2 的 permission denial 与 dangerous write 实验。

**Governance owner**：DSH 拥有是否允许该风险级别的业务治理权；capability 负责把选择映射到 Codex 或其他产品的 native mechanism。

**Current behavior**：Codex provider 使用固定 provider-instance permission mode；没有 per-run 通用交互审批通道。

**Open question**：不同 capability 的权限语义是否可直接比较，当前没有足够证据制定统一枚举。

### R5 — Result boundary 必须是有界且可判断的

**Why it exists**：当前 provider 只向父级返回最终文本或安全 diagnostic，不把 raw stdout、协议 payload、reasoning、commentary、tool activity、workspace diff 或完整 usage 传回。

**Evidence**：2-A.1 的 `collectOutput()`、failure diagnostic 和 result settlement；2-A.2 的 final text、safe failure、stderr 与 workspace 实验。

**Governance owner**：DSH 负责把外部结果纳入自身 task/iteration 结果边界；capability 负责其产品输出的解析。

**Current behavior**：成功需要 terminal completed 且有非空答案；失败带 stop reason 和安全诊断；原始过程信息留在 host stderr/内部。

**Open question**：未来是否需要过程事件或 usage，当前没有证据支持默认 streaming/result expansion。

### R6 — Failure 必须保留来源差异

**Why it exists**：已存在 input/preflight、startup/spawn、protocol、service/product、permission/sandbox、cancellation、process、invalid-result、teardown 等不同失败来源。

**Evidence**：2-A.1 failure model；2-A.2 的 permission、service retry、direct process termination、cancellation 和 safe diagnostics 实验。

**Governance owner**：DSH 需要知道任务是失败、取消、终止还是清理异常；capability 负责产品/协议细节分类。

**Current behavior**：`CodexRunFailure`、stop reason、failure category、HTTP status 和 process outcome 分层存在。

**Open question**：跨不同外部 capability 是否需要相同粒度，当前不能假设 Codex category 是通用集合。

## 4. DSH Governance Requirements

这层不是说当前 provider 缺少实现，而是由 DSH 原则与真实外部行为共同证明：这些决策不能隐含地交给外部 Agent 的内部 loop。

### G1 — DSH 必须拥有业务 iteration 的继续/停止决策

外部 app-server 可以拥有自己的协议交互、tool activity 和 bounded internal retry。2-A.2 观察到 stream disconnect 时 Codex 有 5 次内部 retry，但这不等于 DSH 的业务 iteration，也不应改变 DSH 对任务是否继续的最终治理权。

**Current behavior**：当前 Codex provider 一次 run 只有一个 Codex turn；外部产品内部的 retry 对 provider 是内部机制。

**Open question**：未来某 capability 是否会暴露多个内部步骤，仍需逐个验证；不能因此预设 multi-agent 或 workflow model。

### G2 — DSH 必须区分 execution timeout、cancellation、disposal grace

三者语义必须保持分离：

| Semantic | Meaning supported by evidence |
|---|---|
| execution timeout | DSH 对一次外部执行允许持续多久的治理决定；当前 Codex provider 没有 wall-clock invocation timeout |
| cancellation | 上层请求撤销；当前会尝试 `turn/interrupt`，并触发本地 run abort |
| disposal grace | 终止后等待/升级的清理宽限；当前 `disposeGraceMs` 不是 execution timeout |

**Evidence**：2-A.1 明确指出 caller owns timeout classification；2-A.2 未观察到 provider timeout，但观察到内部 retry；取消和 quiescence 测试通过。

**Requirement**：DSH 不能把“调用还在运行”“调用被请求取消”“进程正在清理”“进程树已消失”压成一个状态。

### G3 — DSH 必须拥有 cancellation authority，capability 提供 bounded interrupt mechanism

当前 `turn/interrupt` 是 best effort；process termination 才是 authoritative cleanup。由此可确认：取消不是仅发送一个产品协议消息，也不是仅杀掉 child，而是上层意图与底层回收的组合语义。

**Requirement**：DSH 必须能发起/判断取消；capability 可以尝试优雅中断；最终 process cleanup 不能依赖外部 Agent 自愿退出。

### G4 — DSH 必须知道 side effects 可能已发生且没有自动 rollback

dangerous write 已在 disposable workspace 中发生；当前 provider 不回传 diff，也没有 rollback。取消或失败后的部分 side effects 仍未完全实验确认，但不能把“任务失败”解释为“工作区未改变”。

**Requirement**：DSH 至少要把 workspace identity、权限选择和 side-effect 可能性作为治理事实保留。

### G5 — DSH 必须拥有外部调用的边界，不把外部内部机制当成 DSH loop

外部 Agent 可以有 JSON-RPC 请求、tool calls、approval requests、internal retries 和多个状态事件。这些属于 capability 内部机制。DSH 的边界是：是否发起、是否允许继续、何时取消/超时、如何纳入任务结果、何时完成清理。

### G6 — DSH 必须能区分安全结果与原始诊断

当前 provider 有意把 raw stderr、命令、路径、协议 payload 和 workspace diff 排除在父级结果外，同时保留有限的安全 failure diagnostic。DSH 需要认识到“完整可观测性”和“可返回给上层的结果”不是同一个边界。

## 5. Codex-specific vs Generic Runtime Concerns

| Concern | Codex-specific mechanism | Generic runtime requirement? | Reason |
|---|---|---|---|
| JSON-RPC | app-server line-framed JSON-RPC、request correlation | **No, not as a domain contract** | 外部调用需要可读写的受控交互通道，但具体 framing/protocol 属于 capability |
| `initialize` / `initialized` | Codex app-server handshake | **No** | 是 Codex startup detail；通用需求只是 startup readiness/success boundary |
| ephemeral thread | Codex `thread/start` 的 product concept | **No** | 通用 runtime 需要明确执行实例边界，但不需要 Codex thread 语义 |
| `turn/start` / `turn/completed` | Codex 单轮协议方法与状态 | **No, not by name** | 通用 runtime 需要 bounded execution/result completion，不应复制产品方法名 |
| cwd | Codex child 与 thread 的运行目录 | **Yes, workspace identity/cwd semantics** | 外部工具副作用依赖位置；具体映射方式仍可替换 |
| prompt text blocks | Codex 输入形式 | **Partly** | 通用调用需要 bounded input；text block schema 是当前 capability detail |
| `turn/interrupt` | Codex remote interrupt request | **Partly** | 通用 runtime 需要 cancellation intent；具体 interrupt method 是 Codex-specific |
| process termination | OS/process-tree implementation | **Yes, bounded lifecycle cleanup** | 外部进程若存在，DSH 必须能观察/触发有界清理；具体 signal/taskkill 非通用领域字段 |
| exit code / signal | subprocess outcome | **Yes** | 是跨进程 failure observation 的现实事实，但编码形式可能随执行世界变化 |
| permission mode mapping | Codex `approvalPolicy`、reviewer、sandbox fields | **Yes, as risk/permission governance** | 具体字段是 Codex-specific；副作用许可是 DSH governance concern |
| `final_answer` / `phase:null` | Codex agentMessage selection rule | **No, not by name** | 通用需求是 bounded result interpretation；phase names 不应成为 DSH 领域模型 |
| internal retry | Codex Responses retry behavior | **No as DSH loop** | 可存在于 bounded capability 内部，但不拥有 DSH business iteration |
| workspace diff | 当前 Codex provider 不收集 | **Not proven** | side effects are proven; diff/rollback/transaction semantics are not |
| resume | 当前 provider 不使用 | **No** | 当前 absence of requirement is a result；Codex product-level continuation 尚未证明为 DSH 需求 |

## 6. Lifecycle Semantics

当前事实可抽象为语义序列，而不是 Codex 协议对象序列：

```text
preflight
  → external process starts
  → capability becomes ready
  → bounded execution begins
  → capability emits/returns terminal outcome
  → DSH observes result or cancellation/failure
  → disposal starts
  → whole process tree reaches quiescence
```

对应 Codex 的具体实现是：

```text
spawn
  → initialize / initialized
  → ephemeral thread
  → one turn
  → turn/completed or failure
  → run.dispose()
  → terminate / waitForExit
```

第一段可能进入未来治理语义；第二段仍是 Codex protocol detail。特别是“capability ready”不应直接命名为 `initialize`，“bounded execution”不应直接命名为 `turn`。

## 7. Loop Ownership Analysis

### DSH business loop

DSH owns：

- 是否发起该外部调用；
- 是否允许该 DSH task/iteration 继续；
- DSH 自己的 max iteration、timeout 和 budget 决策；
- 是否取消；
- 如何将外部结果纳入 task state；
- 何时认为外部 process cleanup 足够完成。

### Capability internal mechanism

Capability may own bounded：

- Codex app-server handshake；
- JSON-RPC framing/request correlation；
- Codex thread/turn association；
- 产品内部 tool activity；
- 产品内部有限 retry；
- 产品输出到最终结果的解析；
- 产品协议级 interrupt attempt。

### Boundary

“Codex 有 internal retry”只证明 capability 内部有一项 bounded behavior，不证明 DSH 应把 retry 计为 DSH iteration，也不证明 DSH 应自动重试业务任务。任何业务级继续、重试、改派或结束仍属于 DSH governance。

## 8. Timeout / Cancellation / Disposal Semantics

### Execution timeout

这是 DSH 对外部执行允许的最长业务时间。当前 2-A.1/2-A.2 证据只证明 provider 没有自己的 wall-clock invocation timeout；没有证明 Codex 产品不存在任何内部服务/request timeout。因此 DSH 未来不能假设“没有 provider timeout”就等于“系统已有 timeout”。

### Cancellation

这是上层撤销执行的意图。当前路径：request abort → local run abort → best-effort `turn/interrupt` → subprocess termination path。Codex 是否接受 interrupt、interrupt 后的产品 turn status 和部分 side effects 仍有 Unknown。

### Disposal grace

这是终止和回收阶段的 bounded grace。当前实现执行 process-tree termination escalation，并等待 whole-tree quiescence；它不决定一次正常 invocation 是否超时。

### Required distinction

未来设计桌面可以讨论这三个语义是否需要独立输入/状态，但当前不把它们命名成任何新类或接口。

## 9. Workspace and Side-effect Semantics

已知事实：

- workspace/cwd 继承父 Session；
- child cwd 与 Codex thread cwd 一致；
- dangerous permission mode 已实际写入 disposable workspace；
- `never` 模式已实际拒绝升级命令并保持目标文件不存在；
- 当前 provider 不回传 workspace diff；
- 当前 provider/文档没有自动 rollback；
- 取消或失败后的部分 side effects 未直接实验确认。

因此最小 requirement 是“DSH 必须知道此次外部调用在哪个 workspace 运行、以何种风险/权限语义运行、结果可能包含已发生副作用”。更强的 snapshot、transaction、rollback、diff capture 或 sandbox manager 目前都没有足够证据进入第一版 contract。

## 10. Failure Semantics

### Failure source categories

以下分类有 2-A.1 源码和/或 2-A.2 实验依据：

| Source category | Meaning in current evidence | Generic status |
|---|---|---|
| preflight/input | cwd 缺失/解析失败、prompt 非法或为空、请求已取消 | Proven runtime concern |
| spawn/startup | child spawn、payload、initialize/thread startup 失败 | Proven runtime concern |
| protocol | stream close、invalid response、ID mismatch、unknown request | Proven concern; protocol details are capability-specific |
| product/service | turn failure、HTTP/service error、内部 retry exhausted | Proven concern; category names not necessarily generic |
| permission/sandbox | approval denied、sandbox failure、side effect policy rejection | Proven governance concern |
| cancellation | 上层 abort、interrupt attempt、aborted settlement | Proven governance concern |
| process | exit code/signal、early process exit、direct termination | Proven runtime concern |
| invalid result | completed 但没有非空 final answer | Proven result-boundary concern |
| teardown | termination/wait cleanup failure | Proven runtime concern |

### Keep separate

- **Failure cause**：来自哪一层、为什么失败。
- **Stop reason**：一次 run 对上层如何结束，例如 completed、aborted、max-tokens、error。
- **Process outcome**：exit code 和 signal 等 OS 观察。
- **Safe diagnostic**：允许跨 result boundary 暴露的有限诊断。

当前证据支持这四者不能合并成单一 boolean success/error，但不支持为它们创建通用对象模型。

## 11. Result Boundary

DSH 真正需要接收到的最小 result-level facts 是：

- 是否形成 terminal outcome；
- bounded final result（当前 Codex 是最终 text）；
- stop reason；
- failure 是否发生及其粗粒度来源；
- 必要时的 safe diagnostic；
- process outcome（若外部 process 存在）；
- 与当前 DSH task/iteration 的关联事实。

其中最后一项是 DSH governance 需要的关联语义，不是当前 Codex provider 已有的独立字段。

当前不应默认要求：

- raw stdout/stderr；
- raw JSON-RPC；
- commentary/reasoning/tool activity；
- 完整 usage/token；
- workspace diff；
- streaming events；
- product-specific `phase` 或 thread/turn ID。

这些内容可能对诊断有用，但当前证据不足以证明它们属于第一版通用结果边界。

## 12. Ownership Matrix

| Concern | DSH owns | Capability owns | Shared / boundary | Status |
|---|---:|---:|---:|---|
| business iteration loop | X |  |  | Proven by architecture principle + evidence |
| internal protocol mechanics |  | X |  | Codex-specific capability detail |
| execution timeout decision | X |  |  | Provider currently has none; caller governs |
| internal retry policy |  | X |  | Allowed only as bounded capability behavior |
| cancellation intent | X |  |  | DSH decides to cancel |
| protocol interrupt attempt |  | X | X | Capability attempts; DSH observes outcome |
| process termination mechanics |  | X | X | OS mechanism in subprocess owner; DSH requires bounded cleanup |
| process lifetime decision | X |  | X | DSH decides lifecycle boundary; capability reports process facts |
| whole-tree quiescence evidence |  | X | X | Process owner observes; DSH depends on it |
| workspace identity/cwd selection | X |  | X | Current provider inherits parent cwd; capability applies it |
| workspace mutation |  | X | X | Capability causes effects; DSH governs allowed boundary/risk |
| permission/sandbox risk decision | X |  | X | DSH policy concern; capability maps native fields |
| product permission mapping |  | X |  | Codex-specific mechanism |
| result interpretation |  | X | X | Capability parses product output; DSH decides task meaning |
| stop reason propagation | X | X | X | Capability reports; DSH governs task state |
| safe diagnostic shaping |  | X | X | Provider currently shapes; DSH must preserve safe boundary |
| raw stderr/protocol payload |  | X |  | Not parent result by current behavior |
| rollback/diff capture |  |  |  | Unknown / not justified |
| resume/session continuation |  |  |  | Not required by current evidence |

## 13. Unresolved Requirements

These are risks or possible future needs, not first-version contract requirements:

- invocation wall-clock timeout implementation details beyond the governance requirement that DSH owns the decision;
- exact interrupt acceptance and post-interrupt product status;
- cancellation-time partial side effects;
- read/modify/delete/cwd-outside/child-process permission behavior across modes;
- descendant-process behavior in more tool paths;
- workspace diff or rollback semantics;
- streaming/progress/event exposure;
- usage/token/cost accounting;
- multi-turn or persistent session behavior;
- resume/continuation;
- generic permission vocabulary across providers;
- generic external-agent error taxonomy beyond preserving source distinctions;
- remote execution-world semantics;
- product-specific model selection and fallback behavior.

## 14. Anti-Abstraction Check

The result below concerns the named architecture concepts, not whether the underlying runtime fact exists.

| Candidate | Result | Evidence for | Evidence against / missing |
|---|---|---|---|
| `AgentExecutor` | **Not justified** | An external run is executed and bounded | No evidence that a new orchestration object is needed; DSH already owns loop and current provider has concrete lifecycle code |
| `CLIExecutionCapability` | **Not justified** | A child process is launched | Current path is app-server over JSON-RPC, not a generic text CLI; no second implementation or shared seam requirement |
| `CodexAdapter` | **Not justified** | Codex-specific protocol mapping exists | Mapping exists inside current provider; no proven need to expose a separate adapter layer |
| `CodeBuddyAdapter` | **Not justified** | None in the two reports | No CodeBuddy runtime evidence in this milestone |
| `ExternalAgent` | **Partially justified** | There is a real bounded external-agent-like invocation and result boundary | The semantic need is proven, but a generic object/interface across products is not |
| `ExternalAgentRequest` | **Partially justified** | cwd, bounded input, permission, env, cancellation and timeout governance are real concerns | Exact cross-provider field set and ownership are not yet validated |
| `ExternalAgentResult` | **Partially justified** | final result, stop reason, safe diagnostic and process outcome are real facts | Codex-specific output/status details must not be prematurely generalized |
| `WorkspaceContext` | **Not justified** | Workspace/cwd is a proven requirement | Need for a new context object is not proven; current parent Session cwd is sufficient evidence |
| `ProcessManager` | **Not justified** | Process-tree ownership and quiescence are proven | Shared subprocess service already provides these mechanics; a new DSH manager is speculative |
| `PermissionPolicy` | **Partially justified** | Permission/sandbox choice changes real side effects and needs governance | A unified enum/policy object across capabilities is not justified |
| Session abstraction | **Not justified** | Codex uses ephemeral thread/session concepts | Current provider has no resume; product session semantics are not a DSH requirement |
| Streaming abstraction | **Not justified** | Product emits intermediate protocol/tool events | Parent result intentionally filters them; no DSH streaming requirement has been proven |

“Partially justified” means the underlying semantic concern may enter Milestone 2-B discussion; it does not authorize creating the named type or hierarchy.

## 15. Minimum Evidence Set for Milestone 2-B

The following requirements have enough evidence to enter a future Contract Design discussion, if that milestone is explicitly approved:

1. External invocation has an explicit workspace identity/cwd boundary.
2. External invocation has a bounded, observable lifecycle.
3. Process-backed invocation exposes completion and process outcome separately.
4. Cleanup must include process-tree termination and whole-tree quiescence where applicable.
5. DSH owns business iteration continuation/stop decisions.
6. DSH owns execution-timeout policy; disposal grace remains separate.
7. Cancellation intent is distinct from protocol interrupt and process cleanup.
8. Permission/sandbox risk is an explicit governance concern; product mapping remains capability-specific.
9. Side effects may survive failure/cancellation; absence of rollback must not be assumed away.
10. Result boundary is bounded and must support final result, stop reason, safe diagnostic, and relevant process outcome.
11. Failure source distinctions must not be flattened into one success/error bit.
12. Current evidence does not require resume, streaming, diff/rollback, usage accounting, or multi-turn session semantics.

The list above contains requirements only. It does not define an interface, protocol, class, enum, or data model.

