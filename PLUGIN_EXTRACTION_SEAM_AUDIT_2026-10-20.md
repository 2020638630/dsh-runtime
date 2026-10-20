# 官方 Harness 插件抽离：首轮接口与差异审计

日期：2026-10-20。性质：PLUG-01 官方发行包外部插件探针及 PLUG-02 源码差异审计；**尚非真实 Runtime 任务验收**。比较基准是本机官方 `origin/master` `687f282e86` 与私有候选 `08d207d31e`。用户的两个原源码工作树及 ZCode 凭据目录未被改动。

## 可直接使用的官方扩展机制

1. 官方 `docs/subsystems/client-modules.md` 的客户端包契约：包声明 `dsh.client`、`platform: web`、`exports["./client"]`，Web Host 加载其 client bundle。
2. 官方 `packages/client/ui-tool/README.md` 及 `ui-skill/src/client/index.ts`：业务 UI 可按工具名注册 `tool.call.toolview` 槽位，并在包内登记语言资源。抽屉的卡片/三页签可迁移到该机制。
3. 官方 `docs/cookbook/extension-cookbook.md`：Subagent provider 注册与工具暴露是两层；现有 Runtime Host provider 已是可安装包形态。

以上仅证明接口存在。尚需真实验证外部包的构建产物、React/样式装载、槽位类型、翻译、Host 路由和插件生命周期。

## 私有候选相对官方的关键差异分类

| 差异位置 | 分类 | 抽离动作 / 验证点 |
| --- | --- | --- |
| `packages/subagent/subagent-dsh-runtime/**` | 可迁入外部 Host 包 | 迁移 provider、Manifest、认证路由及测试；修正 `workspace:*`、发布元数据，固定兼容范围。 |
| `packages/client/ui-tool/src/client/tool/toolviews/dsh-runtime-row.*` | 可迁入外部 Web 包 | 改用公开导出类型与包内 locale；确认 CSS、Portal、认证请求在官方发行包有效。 |
| `packages/client/ui-tool/src/client/apply.ts` 的 `dshRuntimeToolview` 注册 | 可从官方核心移除 | 外部 `dsh.client` 自行注册 `key: dsh_runtime`；不与原内置注册同时启用。 |
| `packages/client/ui-conversation/src/client/locales.ts` | 可迁入外部 Web 包 | 将专属文字移入插件自己的中英文字典。 |
| `packages/subagent/tool-subagent/src/index.ts` 的 `workloadProposal`、`task_kind`、一次性提示 | **当前宿主核心依赖** | 优先验证专属外部工具能否通过公开 API 保留授权与一次性通知；否则提炼通用上游接口。不得靠 prompt 推断 `task_kind`。 |
| `packages/subagent/subagent/src/types.ts` 的 `taskKind` 转发及 `src/index.ts` 的治理变更 | **当前宿主核心依赖，且混有 D2** | 拆分产品所需的显式工作类型传输与内部 D2 治理；不得把 D2 资格门槛隐含进用户插件。 |
| `apps/web`、`apps/cli`、`packages/boot/app-boot` 的其他差异 | 发布/诊断/兼容性待归类 | 逐项与插件运行最小需求比对；部分可能是独立发布修复，不属于 Runtime 扩展。 |

## 首个真实探针的通过条件

从一个未编辑、固定版本的**官方安装产物**开始，安装仅包含最小 Host 和 Web client 的外部包；启动隔离 Profile 后，Web 页面能加载外部工具卡，Host 的独立认证路由可访问，禁用/卸载后槽位与路由消失且官方页面仍可用。探针只用假证据和临时仓库，不调用模型，不使用 D2。失败时保存版本、错误与最小复现，不把私有候选的已构建页面当作官方兼容证据。

若工具入口无法在公开 Subagent API 上准确传递 `repository_inspection` / `repository_change`，本轮先记录需要的最小上游接口提案，再决定是否创建专属工具包；不得提前宣布“官方零补丁”。

## 官方发行包最小外部插件探针（同日完成）

- 在 `D:\DeepSeekHarness\vis-stable-release-artifacts\official-plugin-probe-20261020` 用公开 npm registry 安装官方 `@deepseek-ai/dsh@0.2.1-rc.2`；CLI 用独立 Node 24 运行，`--version` 返回 `0.2.1-rc.2`。此消费者不引用私有 Harness 候选包。
- 建立全新 `DSH_HOME`，首次 `--profile web --dump-config` 成功。最小包 `@local/dsh-runtime-probe@0.0.1` 只含空 Host `apply` 和一个注册 `dsh_runtime_probe` 键的 Web client bundle，打包为本地 tarball；没有模型、Runtime 任务或证据内容。
- `dsh plugin --profile web add <tarball>` 成功，Profile 配置中出现插件。官方 `dsh web --no-open --port 0` 启动后，本地认证入口 HTTP 200、HTML 包含该插件的客户端 bundle 引用；插件所在 `/plugins/??...client.js` 资源 HTTP 200，响应含 `@local/dsh-runtime-probe` 的客户端工厂。
- 停止本次探针服务后，`dsh plugin --profile web remove @local/dsh-runtime-probe` 成功；再次转储配置不含探针，内容与安装前转储完全一致。
- 将探针升级为 `@local/dsh-runtime-probe@0.0.3`：Host 用官方 `ctx.connection.fetch.register` 注册 `/api/dsh-runtime-plugin-probe`，Web client 注册 `dsh_runtime_probe` 工具视图并在激活时加入测试用 DOM 标记。官方 Web 的匿名路由返回 **401**；浏览器通过一次性本地认证入口后，路由返回 **200** 和 `{"plugin":"loaded"}`；Playwright 真浏览器加载官方页面并确认客户端标记已挂载，记录 `{"http":200,"clientActivated":true}`。测试驱动只借用本机 Playwright，运行目标仍是公开 npm 官方包；没有使用私有 Harness 业务源码。
- 再次停止官方 Web 并卸载 0.0.3 探针。卸载后的配置不含包，`git diff --no-index` 对基线配置无语义/行差异（PowerShell 原始字符串比较因换行编码不同返回 false）；重启后的认证首页为 **200**，HTML 不再引用探针 bundle，同一认证会话访问原 Host 路由返回 **404**。探针服务已停止。
- 因此 PLUG-01 的**安装、Host 认证路由、Web 客户端执行、卸载**最小接口验收通过。它只注册了测试视图，没有显示真实 Manifest，更没有运行 Python Runtime；不代表 PLUG-03/04/REL-01 通过。所有探针产物保留在独立目录，未进入两个原源码工作树。

## 阻碍现有 Runtime provider 直接安装到官方版的两条私有核心依赖

1. 私有 `subagent-dsh-runtime` 在 `apply` 时依赖 `PythonGovernanceBridgeService`，该服务向通用 `ctx.subagents` 注册 `registerGovernedStartRoute`、`registerGovernedStartBinding`、`registerGovernedStartEvaluator`。官方 `@deepseek-ai/dsh-subagent@0.2.1-rc.2` 不具备这些注册方法。原包直接打包到官方版会在装载阶段失败。只删除服务并让官方 `SubagentService.startActivation` 直接调用 `provider.start` 会绕过已批准的预启动策略、审计与会话策略 pin，**禁止作为兼容修复**。
2. 私有 `tool-subagent` 在工具参数中声明 `task_kind`，限制到 `workloadProposal: dsh-runtime`，并将其转发为子代理请求的 `taskKind`；官方工具及请求类型没有这套契约。现有 provider 的 `resolveTaskKind(request.taskKind)` 需要精确值。不能凭提示词、默认写入类型或模型解释来补足。

### PLUG-02 安全抽离路径

先做独立 Host 工具入口，参数必须是枚举 `repository_inspection | repository_change`，由工具实现固定 reason code，校验当前父会话和工作区，且一次调用只能启动一次 Runtime。将 `GovernanceBridge.evaluatePreStart` 的会话 pin、Python 持久 worker、失败关闭、审计输出移入该外部包的可信启动路径；**拿到允许决策后**才创建子进程。外部工具不得依赖官方通用 `tool-subagent` 自动注入的 `task_kind`，也不得将模型传来的 reason code 当作可信输入。

首个实现门槛：用官方包的公开 Host tool API 证明工具注册、会话身份及取消信号可达；针对 `repository_inspection`、`repository_change`、拒绝/超时/worker 异常做启动前阻断测试，再与原治理审计逐项对照。若公开 API 不提供可信会话或取消信号，应提交最小通用上游接口提案并等待公开发行，不能以私有宿主补丁假装插件独立。之后才迁移现有 provider、Manifest 和 Web 抽屉，并做官方安装包真实读写/失败/取消及卸载回退验收。D2 ExecuteGate 保持 `NOT_CLAIMED`。

已核对官方 `@deepseek-ai/dsh-tools@0.2.1-rc.2` 的发行类型：`ToolRunContext` 有由宿主设置的 `agent?: Agent` 与 `signal: AbortSignal`；因此外部专属工具可从 `exec.agent` 获取调用者并按 `exec.signal` 取消，而不让模型提供身份。仍须在真实官方 Host 运行时验证 agent 与会话的可信绑定。官方 `@deepseek-ai/dsh-subagent@0.2.1-rc.2` 暴露 `startActivation`，但缺少上述治理注册接口；不能仅靠类型强转传递 `taskKind` 后声称预启动治理已成立。

### 专属 Host 工具负向探针（同日）

隔离消费者将 `tests/fixtures/official_harness_tool_probe` 打包为 `@local/dsh-runtime-tool-probe@0.0.3`，通过官方 `dsh plugin` 安装到全新 Home。未调用模型和 Runtime。官方 Web 认证页为 200，鉴权诊断路由返回 200，并报告 `registered=true`、`hasTaskKind=true`、`inspectionProviderRegistered=true`、`changeProviderRegistered=true`、`noAgentRejected=true`、`invalidTaskKindRejected=true`、`preAbortedRejected=true`。这是真实官方 Host 的工具与两个固定用途 provider 注册、负向执行结果；它**尚未**证明真实父 Agent/Session 绑定、治理 worker 决策或 Runtime 启动。停止服务、卸载包后，Profile 配置与基线无行差异。探针代码作为可复验夹具入库，详细说明见夹具 README。

官方发行的 `SubagentStartRequest` 类型确实没有 `taskKind`。因此正式实现按检查/写入两个 provider 名称固定工作类型及 reason code，专属工具只从已验证枚举选择 provider；不在官方请求对象上增加私有字段。治理调用须放在**每个 provider 自身的 `start()`**，在 Python Runtime 子进程启动之前完成，并且拒绝、超时、worker 异常均失败关闭。这样即使其他合法 Host 入口直接启动某个 provider，也不能绕开治理。探针 provider 故意无条件抛出“governance is not installed”，只验证可注册性。

### 独立治理桥移植首轮（同日）

`integrations/deepseek-harness` 建立为 `private: true` 的不可发布骨架，固定公开 `@deepseek-ai/*@0.2.1-rc.2` 依赖；从私有候选迁出 `protocol.ts`、`session-pin.ts`、`bridge.ts`，只把原私有 `GovernedSubagentStartRoute` 类型改成插件自身的封闭二元组类型。`pnpm typecheck` 通过。`startGoverned` 作为未来 provider `start()` 的最后启动门，六个无模型单元测试通过：明确允许一次启动、策略拒绝、worker FAILURE、桥接异常、预取消、评估期间取消。单元测试的 launch 仅为计数器，**尚非真实 Python worker/审计或 Runtime 子进程验收**。下一步是隔离 worker 的真实拒绝、超时和持久 pin 测试，再把该门接入双 provider。

随后 `pnpm test:worker` 在独立临时目录以 Python 3.12 启动真实 `dsh_runtime.governance_worker`，通过 Node 桥完成 READY、会话绑定、inspection 允许和部署未启用的 change 拒绝；相同会话的策略 pin 保持一致，审计 JSONL 有对应 ALLOW/DENY 两条。另两例证明审计路径不可写时真实 worker 不触发 Runtime 启动回调、worker 不响应而超时时同样不触发。此测试的启动回调仍为计数器，**不代表官方 Host 中的 provider 已接线或真实 Runtime 子进程已验收**。下一步是把 `startGoverned` 接入双 provider 的 `start()`，针对官方 Host 的实际会话和取消信号做现场验证。

双 provider 的 `start()` 已通过 `createGovernedProvider` 接上 `startGoverned`，公开 `@deepseek-ai/dsh-subagent@0.2.1-rc.2` 类型检查通过，`pnpm test:provider` 三例通过：直接调用只读 provider 遇策略拒绝不启动、明确允许启动一次、直接调用写入 provider 遇桥接失败不启动。两个 provider 的 task kind 与 reason code 在构造时固定，不经过官方请求的私有字段。此处 launcher 仍为测试回调；下一门槛是把真实 Runtime 子进程适配器接入并在官方 Host 现场确认会话身份、取消和终态证据。

现已将原有 `run.ts` 和其终态 Evidence Manifest、工作区快照、Safe Trace、调用轨迹、终态读取模块复制到独立骨架；公开 `@deepseek-ai/*@0.2.1-rc.2` 下类型检查通过。`createRuntimeLauncher` 将双 provider 的固定工作类型接给原有 one-shot transport，只使用父 Session 的 `header.cwd` 作为目标工作区，缺失时在 product entrypoint 前失败。两项无模型测试通过。这证明迁移代码的类型与工作区选择，**尚未**验证官方 Host 中真实 Runtime 子进程、终态 Manifest 或证据抽屉。

`mountHostCore` 将策略 pin、Python worker、Runtime launcher、双 provider 组合在一起；只有 worker READY 后才注册 provider。启动失败时逐项撤销注册并释放 worker/pin，卸载函数可重复调用。类型检查与一项 worker 启动失败回滚测试通过。它目前是库入口，尚无可安装 Host bundle 或模型工具；正式安装之前必须补真实 Host 会话、工具、证据路由和生命周期验收。
