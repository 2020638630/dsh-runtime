# DSH Runtime — 2026-09-07 CodeBuddy Native Contract 会话交接

## 1. 仓库状态

```text
Repository: D:\PythonProject\dsh-runtime
Remote: https://github.com/2020638630/dsh-runtime.git
Branch: master
HEAD: ebb191a docs: add CodeBuddy Codex session handover
Formal regression baseline: 46 passed
```

本轮没有修改 production code、existing tests 或 `PROJECT_STATE.md`，也没有
重新运行测试。`46 passed` 是当前正式回归基线，不是本轮新增测试结果。

本交接创建前，工作区有四份未跟踪 investigation artifact：

```text
collaboration/investigations/2026-09-07-codebuddy-local-native-contract-verification.md
collaboration/investigations/2026-09-07-codebuddy-native-debt-closure.md
collaboration/investigations/2026-09-07-codebuddy-noninteractive-bash-approval-verification.md
collaboration/investigations/2026-09-07-codebuddy-windows-spawn-eperm-investigation.md
```

它们是连续调查产生的项目文档，不是 production/test 变更。临时验证仓库均已
删除。

## 2. 正式里程碑状态

```text
Milestone 1: CLOSED
Milestone 2: IMPLEMENTATION COMPLETE;
             REAL-SERVICE VERIFICATION DEFERRED / ENVIRONMENT_BLOCKED
Milestone 3: CLOSED / VERIFICATION PASS
Milestone 4: CLOSED / VERIFICATION PASS
Current version: v0.1.0-m4
```

不要自动声明或启动 Milestone 5。CodeBuddy native investigation 不改变 M1–M4
状态，也不关闭 M2 real Codex service debt。

## 3. Runtime ownership 保持冻结

```text
Caller
  -> TaskState
  -> DSHController
  -> Planner
  -> one bounded Executor invocation
  -> Plugin
  -> bounded PluginResult
  -> last_invocation_result
  -> post-result Planner
  -> terminal Decision or next bounded action
```

- DSHController owns the business loop, invocation budget, and terminal
  transition.
- TaskState owns caller/task input, lifecycle, iteration, final result, and the
  latest successful invocation result.
- Planner owns business-intent routing, post-result evaluation, and terminal
  Decisions.
- Executor owns one invocation's timeout, cancellation cleanup, settlement,
  and StopReason normalization.
- A concrete Plugin owns its bounded native mechanics.
- WorkspaceManager owns logical-workspace-to-cwd resolution.
- CodexPlugin owns the bounded Codex app-server lifecycle.

现有 action -> settled result -> Planner -> next action/terminal Decision seam
已经能够表达未来的 CodeBuddy -> Codex 流程。当前没有证据要求新增 Controller、
Executor、WorkflowEngine、Provider Framework、ProcessManager 或其他 owner。

## 4. 目标产品 workflow 与当前总判断

项目 owner 已提出真实 workflow：

```text
Caller / DSH
  -> CodeBuddy primary coding/repository executor
  -> settled CodeBuddy result and/or workspace mutation
  -> Planner post-execution evaluation
  -> Codex independent read-only final verifier
  -> settled verification result
  -> Planner terminal Decision
  -> DSH-owned TaskState completion
```

角色保持：CodeBuddy 是 builder/primary executor；Codex 是 independent
read-only verifier；DSH 是 submission、governance、orchestration、business loop
和 final completion owner。

总体产品判断仍是：

```text
PROMISING BUT PRODUCT CONTRACT INCOMPLETE
```

最新的 `SPAWN BLOCKER RESOLVED` 只关闭 native spawn 问题，不等于完整产品
contract 已完成，也不授权 implementation design 或 implementation。

## 5. Native contract 已验证事实

本机安装：

```text
package: @tencent-ai/codebuddy-code
version: 2.143.0
launcher: D:\Program Files\node-js\codebuddy.cmd
```

### 已通过

- `--print` 可完成非交互 authenticated model turn，无登录提示。
- text、stdin 和 JSON event-array 输出均已观察。
- `--max-turns` 可产生可观察的 bounded settlement。
- `--permission-mode acceptEdits --tools Read,Edit` 可直接修改 exact process
  cwd 中的文件。
- 不使用 `--add-dir`、CLI sandbox 或 dangerous bypass 时，同 cwd mutation
  可由外部进程立即观察。
- `dontAsk + explicit Bash(...) allow` 可以通过非交互 permission matcher，
  并真实发出 Bash function call。
- 普通主机上下文中的 CodeBuddy Bash 已真实执行：

```text
Command: echo CB_NATIVE_OUTSIDE_SANDBOX_OK
Stdout: CB_NATIVE_OUTSIDE_SANDBOX_OK
Stderr: (empty)
Exit Code: 0
Signal: (none)
```

### Result normalization 已冻结的最小规则

- CLI exit code 0 不是 native/task success 的充分条件。
- final `result.subtype=success` 且 `is_error=false` 也不是充分条件。
- 必须检查 Bash/其他 tool 的 `function_call_result`，包括 native error、
  stdout、stderr、exit code 和 signal。
- tool result 中出现 permission denial、spawn failure、native error 或 required
  operation 未执行时，应归一化为 unsuccessful `PluginResult` /
  `StopReason.FAILED`。
- outer DSH timeout 保持现有 `StopReason.TIMED_OUT` ownership。

不需要为了当前证据创建 generic event DTO 或 result envelope。

## 6. `spawn EPERM` 根因与最终 verdict

在 Codex 托管执行沙箱内：

- Node `child_process.spawn()` 启动 `cmd.exe`、absolute Python、child Node 和
  Git Bash 均返回 `spawn EPERM`；
- Git Bash 初始化还报告 `couldn't create signal pipe, Win32 error 5`；
- CodeBuddy 因同一边界无法启动 Bash。

在同一机器、同一 disposable cwd、托管沙箱外：

- Node 成功启动 cmd、Python、Node 和 Git Bash；
- Git Bash 输出 `NODE_GIT_BASH_OK` 并 exit 0；
- CodeBuddy 的受限 `Bash(echo:*)` 调用输出预期文本并 exit 0。

因此根因是 earlier verifier 的 outer managed execution sandbox 禁止 Node
创建子进程；不是 machine-wide Windows policy，也不是 CodeBuddy permission
matcher、Python、Git Bash 安装或 Runtime product defect。

该专项调查的唯一最终 verdict：

```text
SPAWN BLOCKER RESOLVED
```

CodeBuddy 内部的 `dangerouslyDisableSandbox: true` retry 无法绕过启动
CodeBuddy 的外层托管沙箱；它不构成 permission matcher 缺陷证据。

## 7. 尚未关闭的 native debt

spawn blocker 关闭后，下列项目变为“可继续验证”，但本轮没有越界继续：

1. command-enabled 配置是否阻止 outside-cwd/absolute-path read 与 write；
2. repository-local edit -> test command -> settled result 的完整可重复证据；
3. command child/background descendant 在 timeout/parent termination 后是否存活；
4. cleanup 应归类为 top-level termination sufficient、process-tree termination
   required，还是 native interrupt required；
5. 最小 JSON/tool-error normalization 对更多 native failure 的稳定性；
6. `--no-session-persistence` 对 intended invocation 的 durable disk 语义。

这些是 CodeBuddy-specific native contract 问题。即使后续发现需要 process-tree
处理，第一 ownership hypothesis 仍应是 bounded CodeBuddyPlugin mechanics，不能
直接泛化为 Runtime ProcessManager 或 Executor redesign。

## 8. 仍待 owner 决定的 product questions

1. 首版是否正式选择 CLI `--print` 作为 exact CodeBuddy surface；
2. write authority 如何映射到 Read/Edit/Bash 及其 allow rules；
3. 首版是否要求 command/test，还是只允许 file mutation；
4. CodeBuddy invocation 的 max-turn、outer timeout 和其他 budget；
5. Codex negative verification 映射到 FAILED、COMPLETED-with-report、human
   review，还是其他 TaskState 语义；
6. 首版是否明确排除 CodeBuddy repair/retry；
7. unattended authentication/configuration 的部署来源与稳定性要求；
8. 必须关闭哪些剩余 native debt，才能授权 minimal implementation design。

不要用 investigation agent 自行替 owner 回答这些产品问题。

## 9. 下一会话边界

在 owner 给出明确任务前，不要：

- 声明 Milestone 5；
- 创建 implementation design 或 implementation plan；
- 修改 production code、existing tests 或 `PROJECT_STATE.md`；
- 创建或注册 CodeBuddyPlugin；
- 修改 TaskKind、SimplePlanner、CodexPlugin、Controller 或 Executor；
- 实现 CodeBuddy -> Codex workflow；
- 实现 repair/retry、streaming、resume、rollback 或 generic provider routing；
- 重试 real Codex service；
- 把 approval-based restrictions 描述为 hard filesystem confinement；
- 在真实 DSH Runtime 仓库中把 CodeBuddy 作为 cwd 运行 mutation/command probe；
- 使用 `-y`、`--dangerously-skip-permissions`、`bypassPermissions`、
  `--add-dir` 或 CLI sandbox。

如果 owner 授权继续 native verification，所有 CodeBuddy write/command probe
仍必须在 disposable temporary Git repository 中进行。涉及托管沙箱内
`spawn EPERM` 时，应使用已完成的 A/B 证据，不要反复重跑已知失败路径。

## 10. Authoritative files for the next session

按顺序读取：

```text
D:\PythonProject\dsh-runtime\PROJECT_STATE.md
D:\PythonProject\dsh-runtime\collaboration\closures\2026-09-07-m4c-readonly-repository-analysis-closure.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-next-concrete-goal-selection.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-execution-codex-verification-investigation.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-local-native-contract-verification.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-native-debt-closure.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-noninteractive-bash-approval-verification.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-windows-spawn-eperm-investigation.md
D:\PythonProject\dsh-runtime\collaboration\sessions\2026-09-07-codebuddy-native-contract-handover.md
```

## 11. 可直接复制的新会话开场白

```text
继续 DSH Runtime 项目。请先读取并遵守以下文件：

D:\PythonProject\dsh-runtime\PROJECT_STATE.md
D:\PythonProject\dsh-runtime\collaboration\closures\2026-09-07-m4c-readonly-repository-analysis-closure.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-next-concrete-goal-selection.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-execution-codex-verification-investigation.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-local-native-contract-verification.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-native-debt-closure.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-noninteractive-bash-approval-verification.md
D:\PythonProject\dsh-runtime\collaboration\investigations\2026-09-07-codebuddy-windows-spawn-eperm-investigation.md
D:\PythonProject\dsh-runtime\collaboration\sessions\2026-09-07-codebuddy-native-contract-handover.md

当前仓库状态：
- Remote: https://github.com/2020638630/dsh-runtime.git
- Branch: master
- HEAD: ebb191a
- 正式测试基线：46 passed（本轮文档调查未重跑测试）
- 工作区包含五份未跟踪的 investigation/session 文档；没有 tracked production/test diff

正式里程碑状态不变：M1、M3、M4 已关闭；M2 implementation complete，
real-service verification 仍为 DEFERRED / ENVIRONMENT_BLOCKED。不要自动声明或
启动 Milestone 5。

CodeBuddy native 当前证据：
- 非交互认证、same-cwd Read/Edit mutation、max-turn bound 已验证；
- dontAsk + explicit Bash allow 已通过 permission layer；
- earlier spawn EPERM 已确认来自 Codex outer managed execution sandbox；
- 同机器沙箱外 Node、Git Bash 和 CodeBuddy Bash 均真实执行成功；
- 专项最终 verdict：SPAWN BLOCKER RESOLVED；
- exit code 0 或 session-level success 不能替代 function_call_result 检查。

总体产品判断仍是 PROMISING BUT PRODUCT CONTRACT INCOMPLETE。尚未关闭的重点包括
command-enabled workspace boundary、descendant cleanup/timeout、完整 edit->test
settlement，以及 owner 对 CLI surface、authority mapping、budget、negative verifier
semantics、repair/retry scope 和 design gate 的决定。

本次先不要修改 production code/tests/PROJECT_STATE.md，不要创建 CodeBuddyPlugin，
不要创建 implementation design，不要重试 real Codex service，不要在真实仓库中
运行 CodeBuddy mutation/command probe，也不要使用任何 dangerous permission bypass。

请先报告你读取到的仓库、里程碑、Runtime ownership、CodeBuddy native verdict、
remaining native debt 和 open product questions，然后等待我的明确安排。
```

## 12. Handoff completion

本交接只保存上下文与边界。它不改变里程碑状态，不关闭 M2 real-service debt，
不宣布 implementation readiness，也不授权任何新的 Runtime 行为。
