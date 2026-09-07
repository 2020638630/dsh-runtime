# DSH Runtime — 2026-09-07 CodeBuddy / Codex 会话交接

## 仓库与提交状态

- Repository: D:\PythonProject\dsh-runtime
- Remote: https://github.com/2020638630/dsh-runtime.git
- Branch: master
- Tracking: origin/master
- 已推送提交: 19ecfbb — feat: complete bounded runtime milestones
- 提交内容: M1–M4 Runtime 实现、测试、协作记录、M4-C closure，以及
  CodeBuddy primary execution + Codex verification feasibility investigation
- 提交前全量回归: .venv\Scripts\python.exe -m pytest -q -> 46 passed

当前交接文档创建后会产生一个新的文档提交；production code 和 tests 不会
因交接而改变。

## 当前正式里程碑状态

    Milestone 1 — DSH Runtime Skeleton
    CLOSED

    Milestone 2 — External Capability Integration
    IMPLEMENTATION COMPLETE
    REAL-SERVICE VERIFICATION DEFERRED / ENVIRONMENT_BLOCKED

    Milestone 3 — Bounded Planner-Driven Task Continuation
    CLOSED
    VERIFICATION PASS

    Milestone 4 — Read-only Repository Analysis Workflow
    CLOSED
    VERIFICATION PASS

    Regression baseline
    46 passed

Milestone 2 的真实 Codex reopen gate 仍是最小 real Codex turn 达到
turn/completed。不要因环境可用性变化自动把它变成新的产品 milestone，也不要
在新会话中重复真实 Codex service retry。

Milestone 4 保持 CLOSED。除非 executable evidence 直接推翻已冻结的只读
invariant、Planner routing、M3 post-result completion path、Echo compatibility
或其他 M4-specific invariant，否则不 reopen M4。

## 已验证的 Runtime 能力边界

    Caller
      -> TaskState
      -> DSHController
      -> Planner
      -> one bounded Executor invocation
      -> Plugin
      -> bounded PluginResult
      -> last_invocation_result
      -> post-result Planner
      -> terminal task result or next bounded action

已冻结的 ownership:

- DSHController owns business loop, invocation budget, and terminal transition.
- TaskState owns caller/task input, lifecycle, iteration, final result, and latest
  successful invocation result.
- Planner owns business-intent-to-action selection and terminal Decisions.
- Executor owns one invocation's timeout, cancellation cleanup, settlement, and
  StopReason normalization.
- Concrete Plugin owns bounded native mechanics.
- WorkspaceManager owns logical workspace to cwd resolution.
- CodexPlugin owns the bounded Codex app-server lifecycle.

M3 已经证明:

- A -> settled result -> Planner -> B continuation；
- Planner post-result evaluation；
- invocation budget；
- terminal result ownership；
- failure/timeout terminality；
- successful invocation != successful task。

M4 已经证明:

- TaskKind.REPOSITORY_ANALYSIS；
- caller expresses business intent rather than Codex/provider；
- production SimplePlanner -> CodexPlugin；
- logical workspace and read-only authority；
- last_invocation_result -> terminal Decision -> TaskState.result -> COMPLETED；
- DEFAULT -> Echo compatibility。

不要重新设计 continuation、Controller completion shortcut、provider framework、
workflow engine、generic history 或 generic permission policy。

## 新的产品需求

项目 owner 已明确提出一个真实产品 workflow:

    Caller / DSH
      -> CodeBuddy primary task executor
      -> settled CodeBuddy result and/or workspace mutation
      -> DSH Planner post-execution evaluation
      -> Codex independent final verifier, preferably read-only
      -> settled verification result
      -> Planner terminal Decision
      -> DSH-owned TaskState completion

业务角色:

- CodeBuddy = builder / primary executor，负责 coding、repository mutation、
  可能的 command/test execution。
- Codex = independent reviewer / verifier，检查结果 workspace，不应默认修改。
- DSH = task submission、governance、orchestration、business loop 和 final
  completion owner。

CodeBuddy 在用户工作环境中可用/有经济优势，是 product/economic constraint。
它说明为什么选择 CodeBuddy 作为 primary executor，但不授权创建 generic
provider-routing abstraction。

## CodeBuddy 可用环境证据

已在本机发现并只执行了 version/help 检查:

    package: @tencent-ai/codebuddy-code
    version: 2.143.0
    command: codebuddy / cbc
    launcher: D:\Program Files\node-js\codebuddy.cmd

    codebuddy.cmd --version
    2.143.0

已确认的 headless/native surface:

- -p / --print: non-interactive output and exit；
- --output-format: text、json、stream-json；
- --input-format: text、stream-json；
- --max-turns；
- --permission-mode；
- --tools、--allowedTools、--disallowedTools；
- --add-dir；
- --sandbox；
- --acp；
- --serve；
- --no-session-persistence。

安装包还暴露 in-process server surface:

    start(options)
    query(sessionId, input, options) -> QueryTicket
    interrupt(sessionId)
    subscribe(sessionId, listener)
    close(sessionId)

其中声明的 QueryOptions 包括 cwd、permissionMode、maxTurns、
abortController、sandbox、settings、authentication 等；QueryResult 包括
runId、stopReason、assistantText、errorMessage。

这些证据证明 CodeBuddy 存在 automation-friendly surface，但没有证明:

- 当前机器已经完成可供 DSH unattended 使用的认证；
- real task turn 可以完成；
- 文件一定写入 DSH resolved cwd；
- sandbox/worktree/hidden state 不会改变 handoff；
- output JSON schema、exit code、process tree、cleanup/cancellation 已满足
  DSH Plugin contract。

本次未启动 real CodeBuddy task，也未启动 real Codex task。

## Feasibility investigation 结论

调查记录:

    collaboration/investigations/2026-09-07-codebuddy-execution-codex-verification-investigation.md

现有 Runtime 对目标流程的判断:

- Controller 已支持 action -> settled invocation -> Planner -> next action ->
  terminal Decision，无需专用 two-action controller。
- Executor 对 plugin name agnostic，CodeBuddy 和 Codex 都可作为一次 bounded
  invocation。
- Planner 已能在第一个 invocation settle 后选择第二个 action。
- TaskState 的 goal、workspace、allow_workspace_write、iteration、
  max_iterations、last_invocation_result 足以承载已知最小 handoff。
- 同一 logical workspace/cwd 可让 CodeBuddy workspace effect 被 Codex 检查。
- CodexPlugin 的只读 verifier 角色可由 Planner prompt 表达，暂不需要新的
  Codex mode 或新的 Plugin owner。

最小 handoff 倾向于:

    original task goal
      + same logical workspace / resolved cwd
      + settled CodeBuddy result or diagnostic
      -> Planner-generated verifier prompt
      -> Codex read-only invocation

不应先增加 generic context、result history、artifact envelope 或 diff DTO。

## 当前 verdict

    PROMISING BUT PRODUCT CONTRACT INCOMPLETE

这不是 NOT JUSTIFIED。产品需求现在是真实且具体的，且架构上可表达；但也不是
JUSTIFIED FOR MINIMAL IMPLEMENTATION DESIGN，因为以下契约尚未确定:

1. 选择 CLI print、in-process server query、ACP 还是其他确切入口；
2. CodeBuddy 是否直接修改同一 resolved cwd，还是创建 sandbox/worktree；
3. DSH write authority 如何映射到 CodeBuddy permission mode、tools、add-dir
   和 sandbox；
4. CodeBuddy settled output 是 text、JSON、exit code + stdout，还是 workspace
   effect only；
5. 一个 CodeBuddy invocation 的 max-turn/budget 边界；
6. Codex 发现问题后是 FAILED、COMPLETED-with-report、human review，还是其他
   明确状态；
7. 首版是否明确排除 CodeBuddy repair/retry；
8. unattended authentication/configuration 的来源。

没有这些答案，不应声称完整产品 acceptance contract 已成立。

## 预计的最小未来边界

仅作为 feasibility estimate，不是 implementation plan:

    distinct business TaskKind / caller intent
      + Planner CodeBuddy -> Codex sequencing
      + one bounded CodeBuddyPlugin
      + existing CodexPlugin

预计:

- TaskState / TaskKind: CHANGE LIKELY；
- Planner: CHANGE LIKELY；
- new CodeBuddyPlugin: CHANGE LIKELY；
- PluginRegistry: CHANGE POSSIBLE BUT NOT YET JUSTIFIED；
- CodexPlugin: NO CHANGE EXPECTED；
- Controller: NO CHANGE EXPECTED；
- Executor: NO CHANGE EXPECTED；
- WorkspaceManager: NO CHANGE EXPECTED，前提是两者共享 resolved cwd。

新 owner、WorkflowEngine、Provider Framework、PipelineExecutor、
CodeBuddyCodexCoordinator、ExecutionHandle、ProcessManager、generic
PermissionPolicy 均 NOT JUSTIFIED。

## 后续会话禁止事项

在 owner 没有进一步授权和补齐契约前:

- 不声明 Milestone 5；
- 不创建实现计划；
- 不修改 production code；
- 不修改 tests；
- 不创建 CodeBuddyPlugin；
- 不注册 CodeBuddy；
- 不增加 TaskKind；
- 不修改 SimplePlanner；
- 不修改 CodexPlugin；
- 不实现 CodeBuddy -> Codex；
- 不实现 repair/retry、多轮、streaming、resume、rollback；
- 不实现 write-capable workflow；
- 不实现 task cancellation；
- 不重试真实 Codex service；
- 不把 CodeBuddy 可用性泛化为 provider/router framework。

下一步只能是:

1. 等待 owner 回答 open product questions；
2. 在明确授权后，更新 feasibility/contract evidence；
3. 只有 owner 明确授权 implementation design，才另起设计任务；
4. 只有 owner 明确授权 implementation，才进入实现任务。

## 可直接复制的新会话开场白

继续 DSH Runtime 项目。

请先阅读并以以下文件为 authoritative baseline:

    D:\PythonProject\dsh-runtime\PROJECT_STATE.md
    D:\PythonProject\dsh-runtime\collaboration\closures\2026-09-06-m2-external-capability-integration-closure.md
    D:\PythonProject\dsh-runtime\collaboration\closures\2026-09-06-m3-bounded-task-continuation-closure.md
    D:\PythonProject\dsh-runtime\collaboration\closures\2026-09-07-m4c-readonly-repository-analysis-closure.md
    D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-next-concrete-goal-selection.md
    D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-execution-codex-verification-investigation.md
    D:\PythonProject\dsh-runtime\collaboration\sessions\2026-09-07-codebuddy-codex-verification-handover.md

Repository:
    D:\PythonProject\dsh-runtime

Remote:
    https://github.com/2020638630/dsh-runtime.git

Current branch/commit:
    master
    19ecfbb feat: complete bounded runtime milestones

正式状态:

    Milestone 1: CLOSED
    Milestone 2: IMPLEMENTATION COMPLETE;
                  REAL-SERVICE VERIFICATION DEFERRED / ENVIRONMENT_BLOCKED
    Milestone 3: CLOSED / VERIFICATION PASS
    Milestone 4: CLOSED / VERIFICATION PASS
    Regression baseline: 46 passed

新的真实产品需求是:

    DSH submission/governance
      -> CodeBuddy primary coding/repository executor
      -> settled result and/or workspace effect
      -> Planner
      -> Codex independent read-only final verifier
      -> Planner terminal Decision
      -> DSH TaskState completion

当前 feasibility verdict:

    PROMISING BUT PRODUCT CONTRACT INCOMPLETE

本机已确认:

    @tencent-ai/codebuddy-code 2.143.0
    codebuddy.cmd --print / --output-format / --max-turns / permission controls
    in-process server query/interrupt/subscribe/close declarations

但以下契约仍待 owner 明确:

    exact CodeBuddy surface
    same cwd versus sandbox/worktree
    write authority mapping
    settled output shape
    bounded turn/budget
    Codex negative-verification task semantics
    repair/retry scope
    unattended authentication/configuration

当前任务不是实现。请不要:

    声明 Milestone 5
    创建实现计划
    修改 production code/tests
    创建或注册 CodeBuddyPlugin
    修改 TaskKind/SimplePlanner/CodexPlugin
    实现 CodeBuddy -> Codex
    重试 real Codex service

请先报告你读取到的仓库、提交、里程碑、Runtime seam、CodeBuddy verdict 和
open product questions，然后等待我明确安排。

## Handoff completion

本交接文档用于下一会话恢复上下文。它不改变 M1–M4 状态，不授权新的 Runtime
行为，不关闭 Milestone 2 real-service debt，也不宣布 Milestone 5。
