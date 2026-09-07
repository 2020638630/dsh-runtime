# DSH Runtime — 2026-09-05 会话收尾交接

## 当前工程状态

- Repository：`D:\PythonProject\dsh-runtime`
- Python package：`dsh_runtime`
- 当前分支：`master`
- HEAD：`23763b6` (`feat: establish DSH Runtime milestone 1 baseline`)
- Tag：`v0.1.0-m1`
- Remote：未配置
- Runtime 生产代码：未修改

当前 Git 工作区仍有未跟踪内容：

- `PROJECT_STATE.md`
- `collaboration/`
- `资料库/`

本次新增的报告和设计文档都尚未 commit。

## 已完成 Milestone

- Milestone 0 — Repository Analysis
- Milestone 1 — Runtime Skeleton
- Milestone 1.1 — Baseline Hardening
- Milestone 2-A.1 — DeepSeekHarness → Codex CLI Invocation Path Investigation
- Milestone 2-A.2 — Codex CLI / app-server Runtime Behavior Verification
- Milestone 2-A.3 — External Agent Integration Evidence Synthesis
- Milestone 2-B — Minimal External Invocation Integration Contract Design

## 当前 Runtime Skeleton

现有核心边界：

```text
DSHController
  → SimplePlanner
  → Executor
  → PluginRegistry / Plugin
  → PluginResult
  → TaskState
```

当前已存在：

- `TaskState`
- `SimplePlanner`
- `Plugin` Protocol
- `PluginRegistry`
- `PluginResult`
- `Executor`
- `DSHController`
- `EchoPlugin`
- timeout boundary
- error boundary
- max iteration boundary
- structured lifecycle logging

验证结果：

```text
pytest: 6 passed
compileall: passed
```

## Milestone 2-A / 2-B 结论

真实 DeepSeekHarness 证据确认：

- Codex 使用 package-local app-server 进程。
- 外部调用具有 workspace/cwd、进程生命周期、terminal result 和 cleanup 边界。
- process-backed capability 需要 whole-tree quiescence 观察。
- cancellation、protocol interrupt、process termination、disposal grace 必须区分。
- permission/sandbox 会改变真实副作用能力。
- DSH 必须拥有 business loop、execution timeout policy、cancellation intent、workspace identity 和风险治理。
- capability 负责产品协议、参数映射、bounded internal retry、产品结果解析和 graceful interrupt attempt。
- process facts 是可选 execution facts，不应强制所有 capability 采用 subprocess 模型。
- 当前证据不要求 resume、streaming、workspace diff、rollback、usage accounting、multi-turn session 或 generic permission enum。

Milestone 2-B 的推荐方向：

- 保留现有 `DSHController → Executor → Plugin → PluginResult` 顶层边界。
- 优先对现有边界做最小、证据驱动的演进。
- 不新增 `AgentExecutor`、`CLIExecutionCapability`、`CodexAdapter`、`ExternalAgent` hierarchy 或 Provider Framework。
- 只有在具体 process-backed plugin 证明现有 coroutine/cleanup 语义不足时，才重新评估是否需要显式 invocation handle。

## 本会话产生的文档

- [2-A.1 调查报告](../investigations/2026-09-05-m2-a1-deepseekharness-codex-cli.md)
- [2-A.2 运行时验证报告](../investigations/2026-09-05-m2-a2-codex-runtime-behavior.md)
- [2-A.3 证据综合报告](../investigations/2026-09-05-m2-a3-external-agent-evidence-synthesis.md)
- [2-B 最小 Contract 设计](../designs/2026-09-05-m2-b-minimal-external-invocation-contract.md)

## 当前停止点

本轮已完成 Contract Design，尚未进入实现阶段。

不要自动开始：

- CodexPlugin
- LLMPlugin
- RetrievalPlugin
- AgentExecutor
- CLIExecutionCapability
- CodexAdapter / CodeBuddyAdapter
- ExternalAgent interface
- Provider Framework
- Factory
- Event Bus
- Workflow DSL
- resume / streaming / rollback / usage framework
- Milestone 2-C

## 新对话建议开场动作

1. 阅读本交接文件及 2-B 设计报告。
2. 检查 `git status --short --branch`。
3. 先由用户明确是否进入实现，以及选择哪个具体 capability 作为第一个真实实现对象。
4. 如果进入实现，只做一个小目标，并优先复用现有 Plugin/Executor/TaskState 边界。
5. 实现前不得把概念设计直接转成通用 framework 或 speculative abstraction。

## 新对话开场白（可直接复制）

```text
继续 DSH Runtime 项目。

正式 Repository：
D:\PythonProject\dsh-runtime

请先阅读：

D:\PythonProject\dsh-runtime\collaboration\sessions\2026-09-05-m2b-handover.md
D:\PythonProject\dsh-runtime\collaboration\designs\2026-09-05-m2-b-minimal-external-invocation-contract.md
D:\PythonProject\dsh-runtime\PROJECT_STATE.md

当前状态：

- Milestone 0、1、1.1 已完成
- Milestone 2-A.1、2-A.2、2-A.3 已完成
- Milestone 2-B 已完成：Minimal External Invocation Integration Contract Design
- Git baseline：v0.1.0-m1
- HEAD：23763b6
- 当前分支：master
- Remote：未配置
- Runtime 生产代码尚未修改

当前设计结论：

- DSH owns the business loop.
- External capability owns bounded internal mechanics.
- 优先复用 DSHController、Executor、Plugin、PluginRegistry、PluginResult、TaskState。
- process lifecycle 是可选 execution fact，不是所有 capability 的强制模型。
- timeout、cancellation、disposal grace 必须保持不同语义。
- workspace identity、risk/permission、side effects、failure source、terminal result 必须有清晰边界。

除非我明确确认，否则不要：

- 实现 CodexPlugin、LLMPlugin、RetrievalPlugin 或其他具体 Plugin
- 创建 AgentExecutor、CLIExecutionCapability、ExternalAgent、Adapter、Provider Framework、Factory
- 创建 resume、streaming、rollback、usage、Event Bus、Workflow DSL
- 开始 Milestone 2-C

本轮先不要编码。请先确认你已读取交接资料，并汇报当前设计边界和下一步需要我明确的实现目标。
```

