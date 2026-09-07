# DeepSeekHarness → Codex CLI Invocation Investigation

调查日期：2026-09-05  
调查对象：`D:\DeepSeekHarness\deepseek-harness`  
调查范围：`packages/subagent/subagent-codex` 及其实际使用的 `packages/subprocess` 本地实现。  
本报告只记录现有源码和真实配置能够支持的事实，不创建 Integration Contract，也不改变 Runtime 行为。

## 1. Executive Summary

当前调用并不是通过 shell 执行 `codex <prompt>`，也不是向交互式 Codex CLI 写入一段普通文本。`CodexProvider.start()` 从父 Session 读取 cwd，经 `resolveChildCwd()` 得到子进程 cwd；`startCodexRun()` 通过 `ctx.subprocess.spawn()` 启动包内解析出的官方 Codex wrapper，参数固定为 Node executable、wrapper、`app-server --stdio`。随后 `CodexAppServerWire` 在 stdin/stdout 上运行 JSON-RPC：`initialize` → `initialized` → `thread/start`（ephemeral）→ `turn/start`（文本 blocks）→ 等待 `turn/completed`。

stdout 是协议输入，不作为普通文本直接读取；stderr 只转发到宿主 stderr，是辅助观察流。一次 run 只有一个新进程、一个临时 thread、一个 turn，没有 resume、continuation、pooling 或 wall-clock timeout。取消会先发 `turn/interrupt`（best effort），同时由 subprocess 层对整个进程树执行终止升级并等待 quiescence。成功结果只保留最终文本；失败结果使用受限的 stage/category/可选 HTTP status 和 process outcome。

## 2. Invocation Path

```text
SubagentProvider.start()
  ↓ packages/subagent/subagent-codex/src/index.ts:70-110
CodexProvider
  ↓ request.parent.session.header.cwd
resolveChildCwd('subagent-codex', undefined, parentCwd)
  ↓
startCodexRun(request, spec)
  ↓ packages/subagent/subagent-codex/src/run.ts:230-255
ctx.subprocess.spawn({
  argv: [process.execPath, CODEX_PACKAGE_BIN, 'app-server', '--stdio'],
  cwd,
  stdin/stdout/stderr: pipe,
  env,
  graceMs,
})
  ↓
CodexAppServerWire.start()
  ↓
initialize → initialized
  ↓
thread/start { cwd, ephemeral: true, [model], permission/sandbox fields }
  ↓
turn/start { threadId, input: text blocks }
  ↓ JSON-RPC notifications / server requests
turn/completed
  ↓
collectOutput() → final_answer text, or nullable-phase fallback
  ↓
subprocessRunHandle({ result, cancellation, teardown })
```

## 3. Evidence Table

| Concern | Observed Behavior | Evidence | Status |
|---|---|---|---|
| process spawn | 通过 `ctx.subprocess.spawn()` 启动；不是 `child_process` 直接由 Codex provider 调用 | `packages/subagent/subagent-codex/src/index.ts:101`; `src/run.ts:241-249` | Confirmed Fact |
| executable | 从 `@openai/codex/package.json` 的 `bin.codex` 解析绝对 wrapper；argv 为 `[process.execPath, CODEX_PACKAGE_BIN, 'app-server', '--stdio']` | `src/run.ts:44-53,135-136` | Confirmed Fact |
| shell | spawn spec 没有 `shell` 字段；本地实现直接调用 Node `spawn(program,args,options)` | `packages/subprocess/subprocess-local/src/spawn.ts:349-360` | Confirmed Fact |
| cwd | 取 `request.parent.session.header.cwd`；缺失时立即失败；经 `resolveChildCwd()` 解析后同时作为 subprocess cwd 和 `thread/start.cwd` | `src/index.ts:74-90`; `src/run.ts:242-244`; `src/wire.ts:288-294` | Confirmed Fact |
| workspace boundary | 代码把父 Session cwd 作为 child cwd；本次范围内没有看到额外的路径白名单或 workspace 子目录隔离 | `src/index.ts:74-90`; `src/wire.ts:288-294` | Confirmed Fact（后半句为范围内观察） |
| prompt input | 只接受非空 text `ContentBlock[]`，保留文本顺序；turn/start 映射为 `{type:'text', text, text_elements:[]}` | `src/run.ts:161-180`; `src/wire.ts:319-324` | Confirmed Fact |
| stdin | pipe；JSON-RPC transport 使用 child stdin；本地 subprocess 的 batch stdin 支持不适用于此处，因为 provider 没有传 `stdin: {data:...}`；teardown 时会 `child.stdin?.end()` | `src/run.ts:243`; `src/wire.ts:192-205`; `src/run.ts:190-221` | Confirmed Fact |
| stdout | pipe；由 `JsonRpcLineTransport` 读取和解析 JSON-RPC line frames；最终答案从协议 notification 中选择，不直接返回原始 stdout | `src/run.ts:255-258`; `src/wire.ts:226-244,637-706` | Confirmed Fact |
| stderr | pipe；每个 chunk 同步写入 `process.stderr.fd`；stderr error 不决定 run terminal state | `src/run.ts:261-275` | Confirmed Fact |
| exit code | `child.done` resolve 为 `{exitCode, signal}` 时转成 process failure facts；spawn-level rejection 也转成 process/unknown；process outcome 可进入安全 diagnostic | `src/run.ts:289-305,371-375` | Confirmed Fact |
| timeout | 没有独立的 Codex wall-clock execution timeout；源码明确由 caller 负责 timeout classification；`AbortSignal.timeout(ceil(disposeGraceMs))` 只用于异常路径观察 child exit | `packages/subprocess/subprocess-local/src/spawn.ts:459`; `src/run.ts:404-412` | Confirmed Fact |
| cancellation | request abort 会触发本地 `runAbort`、调用 `wire.interrupt()`；返回的 `subprocessRunHandle` 也保留 `requestCancel` 和 teardown | `src/run.ts:312-318,436-443` | Confirmed Fact |
| process termination | subprocess 本地实现树级终止：POSIX detached process group，Windows `taskkill /PID /T /F`；`terminate()` 为 SIGTERM → graceMs → SIGKILL；`waitForExit()` 观察 whole-tree | `packages/subprocess/subprocess-local/src/spawn.ts:350-360,425-464`; `packages/subprocess/subprocess/src/index.ts:82-94` | Confirmed Fact |
| environment | 本地 subprocess 对 ambient env 做 credential-shaped (`KEY|PASSWORD|SECRET|TOKEN`) 和 `DSH_*` scrub，再叠加 spec.env；PATH、HOME、locale、proxy 等普通环境保留；Codex provider 的 `env` 默认 `{}` | `packages/subprocess/subprocess/src/index.ts:37-64`; `packages/subprocess/subprocess-local/src/spawn.ts:26-40`; `src/index.ts:38-59` | Confirmed Fact |
| permission mode | `never` → `approvalPolicy:'never'`；`approve-for-me` → `on-request` + `auto_review` + `workspace-write`；dangerous mode → `never` + `danger-full-access` | `src/wire.ts:32-43`; `src/wire.ts:288-294` | Confirmed Fact |
| approval interaction | 已知 command/file approval 根据 available decisions 返回 cancel 或 decline；permission grant 返回空 permissions；user input 返回空 answers；MCP elicitation 返回 decline；未知 server request fail closed | `src/wire.ts:511-634` | Confirmed Fact |
| session continuation | 每次 start 都是新 app-server、新 ephemeral thread、单个 turn；没有 resume/continuation/pooling | `src/run.ts:225-230`; `src/wire.ts:282-301,308-371`; `README.md` implementation/limitations sections | Confirmed Fact |
| structured output | 解析 JSON-RPC/app-server structured messages；不解析 Codex CLI 普通文本格式；只选 `agentMessage` 的 `phase:'final_answer'`，无 final phase 时回退到最新 `phase:null` | `src/wire.ts:637-671`; `src/wire.ts:392-399`; `README.md` Run flow | Confirmed Fact |
| output format dependency | 依赖 app-server JSON-RPC 方法、thread/turn IDs、terminal status 和 agent message phase；成功但无非空答案视为 invalid-result | `src/wire.ts:321-371,637-706` | Confirmed Fact |
| workspace mutation | Codex 在父 Session cwd 中执行，且 permission mode 可允许 workspace-write 或 danger-full-access；源码没有 rollback 或 diff capture | `src/wire.ts:288-294`; `README.md` Known Limitations | Confirmed Fact（实际是否发生 mutation 需实验） |
| success criterion | initialize、thread/start、turn/start 成功；最终 turn status 为 completed；且 `collectOutput()` 得到非空答案 | `src/run.ts:322-326,386-393`; `src/wire.ts:337-371` | Confirmed Fact |
| failure criterion | 启动/协议/turn/process/teardown 等失败会分类或包装；非 completed turn 按 failure info 分类，max token 返回 `max-tokens`，无答案为 invalid-result | `src/run.ts:289-305,328-355,386-426`; `src/wire.ts:337-371` | Confirmed Fact |
| cleanup | `disposeProcess()` 先关闭 wire，再 end stdin、terminate、waitForExit、await done；最后解除 stderr listeners；成功、失败和 published run teardown 都覆盖 | `src/run.ts:190-221,277-286,328-350,436-443` | Confirmed Fact |

## 4. Process Lifecycle

```text
1. preflight
   - 校验 text-only、非空 prompt
   - 检查 request.signal 尚未 aborted
   - 解析父 Session cwd

2. spawn
   - 直接 spawn Node + package-local Codex wrapper
   - `app-server --stdio`
   - stdin/stdout/stderr 全部为 pipe
   - 本地实现创建 detached/tree-managed process

3. running / protocol startup
   - `CodexAppServerWire.start()` 开始读取
   - initialize request/response
   - initialized notification
   - thread/start 创建 ephemeral thread
   - 完成后才 publish run

4. output handling
   - stdout 由 JSON-RPC line transport 消费
   - 接收 turn/item notifications 和 server approval/input requests
   - stderr 同步转发到宿主 stderr

5. one turn
   - turn/start 提交 text blocks
   - 等待匹配 thread/turn 的 turn/completed
   - 选择 final_answer 或 phase:null 文本

6. completion / failure
   - completed + 非空答案：completed
   - max token：max-tokens
   - interrupted / failed / invalid protocol / process exit：aborted 或错误/诊断，取决于共享 run settlement

7. cleanup
   - close JSON-RPC wire
   - end stdin
   - terminate whole process tree
   - 等待 whole-tree exit 和 child.done
   - detach stderr listeners
```

## 5. Failure Model Observed

代码直接支持的失败路径包括：

- 父 Session 没有 cwd。
- cwd 解析失败。
- request 在 app-server 启动前已 aborted。
- subprocess spawn 抛出错误（例如 executable/runtime 不可用的启动级错误；具体 OS 错误文本被安全包装）。
- initialize 或 thread/start 的协议响应无效、请求失败或 child 在发布前退出。
- app-server protocol stream 提前结束。
- stdout/input/output stream error。
- turn/start 失败。
- turn 终态不是 completed：包括 interrupted、failed 及产品返回的 limit/access-policy/service/transport/product-error/unknown 类别。
- Codex 返回 context/token limit：返回 `max-tokens` 结果路径。
- Codex 返回 sandbox failure 或权限请求被 decline/denied：记录安全 diagnostic；具体是否继续/最终失败由 turn 状态决定。
- 未知 app-server server request：fail closed。
- completed turn 没有非空 final answer：`invalid-result`。
- request abort：调用 interrupt，并触发本地进程树终止。
- teardown 的 wait/termination 失败：`teardown` failure，必要时与原 failure 组成 `AggregateError`。

没有代码证据表明这里存在独立 wall-clock timeout、重试、fallback executable、resume recovery 或 side-effect rollback。

## 6. DSH-Relevant Findings

### Finding 1 — 生命周期

DeepSeekHarness 把一个 Codex invocation 绑定为“一个新 app-server + 一个 ephemeral thread + 一个 turn”，并且只在 initialize 与 thread/start 成功后发布 run。

Potential DSH implication：未来 DSH 若接入，需要明确这套 publication 前后生命周期边界，以及一次 DSH iteration 是否对应一个完整外部 process/thread/turn。

### Finding 2 — timeout 与 cancellation

当前实现有 request abort、`turn/interrupt` 和进程树终止，但没有调用级 wall-clock timeout；`disposeGraceMs` 负责终止升级和清理等待。

Potential DSH implication：DSH 的 timeout policy 不能从当前 Codex provider 中推定为已有；取消时还必须考虑协议 interrupt 与 OS process termination 的双层行为。

### Finding 3 — process boundary

Codex 作为独立进程运行；POSIX 进程组或 Windows process tree 由 shared subprocess owner 管理，并等待 whole-tree quiescence。

Potential DSH implication：DSH 的 process boundary / cleanup 观察不能只以直接 child exit 为完成依据。

### Finding 4 — workspace boundary 与 side effects

child cwd 和 `thread/start.cwd` 都来自父 Session cwd；源码没有 rollback。`workspace-write` 和 `danger-full-access` 明确允许不同程度的文件副作用。

Potential DSH implication：workspace identity、可写边界和取消后的已发生副作用需要作为外部调用的治理事实保留。

### Finding 5 — result boundary

父级只收到最终文本或安全失败诊断；commentary、reasoning、tool activity、raw stderr、workspace diff、usage 和协议 payload 不进入父 Session。

Potential DSH implication：若 DSH iteration 需要可观测性，不能假设当前 provider 的 result 已包含完整过程事件。

### Finding 6 — failure propagation

进程 outcome、协议 failure category、turn status、取消和 teardown 由不同层产生，最终通过 `settleRunResult()` 与 `CodexRunFailure` 汇合。

Potential DSH implication：未来治理需要区分 process failure、protocol/product failure、cancellation 和 cleanup failure，而不能只依据一个 exit code。

## 7. Unknowns Requiring Experiment

以下问题不能仅由当前源码确认：

- 当前安装环境中实际解析到的 `@openai/codex` wrapper 绝对路径和实际版本之外，真实启动时的最终 OS command line 细节。
- Codex app-server 在当前机器、当前账号和当前配置下实际采用的 model、HOME/CODEX_HOME 配置、认证状态和 native sandbox 默认行为。
- `never` 模式下 Codex 的 native sandbox 具体允许/拒绝哪些操作。
- 一次真实调用是否会修改 workspace、修改哪些文件，以及取消/失败后留下哪些副作用。
- Codex 是否会产生 descendant processes，以及这些 descendant 是否继承 stdio；代码定义了 whole-tree 管理，但未证明具体调用一定产生 descendant。
- stdout/stderr 的真实字节序、chunk 边界和高输出量时的实际 backpressure 行为。
- Codex 对未知/非预期 JSON-RPC notification 的实际返回行为。
- 实际账户/服务错误会映射到哪些 `codexErrorInfo` 值；源码只覆盖已知映射和 unknown fallback。
- 真实环境下 `turn/interrupt` 是否总能被 app-server 接收，以及 interrupt 后 process teardown 的时序。
- native Codex 是否可能自行维护可恢复 session 状态；本 provider 本身没有 resume 调用，但外部产品行为仍需文档/实验确认。

## 8. Candidate Contract Inputs

这里只列出现实证据支持的候选输入名称，不创建 interface、protocol 或 dataclass。

### Evidence-backed

- parent Session cwd / resolved child cwd
- text-only prompt blocks
- optional fixed model
- permission mode
- explicit child environment overlay
- process disposal grace
- request abort signal
- subprocess spawn operation
- final text result
- stop reason
- safe failure diagnostic
- process outcome：exit code / signal

### Possibly needed

- invocation timeout（当前 provider 没有，但 DSH governance 可能需要）
- explicit cancellation/termination deadline（当前只有 dispose grace）
- workspace mutation/result-side-effect observation（当前不回传 diff）
- lifecycle stage：initialize / thread-start / turn-start / turn / process / teardown
- failure category 与可选 HTTP status
- iteration correlation（当前 Codex provider 自身只执行一个 turn）

### Not justified yet

- `AgentExecutor`
- `CLIExecutionCapability`
- `CodexAdapter`
- `CodeBuddyAdapter`
- Provider Framework / Dynamic Loader / Factory
- generic Workflow DSL / Event Bus
- session resume contract
- streaming result contract
- generic multi-agent contract

