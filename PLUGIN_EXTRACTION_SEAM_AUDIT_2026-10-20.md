# 官方 Harness 插件抽离：首轮接口与差异审计

日期：2026-10-20。性质：PLUG-01/02 的只读源码探针；**尚非外部安装验收**。比较基准是本机官方 `origin/master` `687f282e86` 与私有候选 `08d207d31e`。用户的两个原源码工作树及 ZCode 凭据目录未被改动。

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

## 官方发行包最小外部插件探针（同日追加）

- 在 `D:\DeepSeekHarness\vis-stable-release-artifacts\official-plugin-probe-20261020` 用公开 npm registry 安装官方 `@deepseek-ai/dsh@0.2.1-rc.2`；CLI 用独立 Node 24 运行，`--version` 返回 `0.2.1-rc.2`。此消费者不引用私有 Harness 候选包。
- 建立全新 `DSH_HOME`，首次 `--profile web --dump-config` 成功。最小包 `@local/dsh-runtime-probe@0.0.1` 只含空 Host `apply` 和一个注册 `dsh_runtime_probe` 键的 Web client bundle，打包为本地 tarball；没有模型、Runtime 任务或证据内容。
- `dsh plugin --profile web add <tarball>` 成功，Profile 配置中出现插件。官方 `dsh web --no-open --port 0` 启动后，本地认证入口 HTTP 200、HTML 包含该插件的客户端 bundle 引用；插件所在 `/plugins/??...client.js` 资源 HTTP 200，响应含 `@local/dsh-runtime-probe` 的客户端工厂。
- 停止本次探针服务后，`dsh plugin --profile web remove @local/dsh-runtime-probe` 成功；再次转储配置不含探针，内容与安装前转储完全一致。
- 这证明**外部包安装、官方 Web 加载图与配置卸载**可行；尚未用浏览器执行该客户端模块，也未注册或调用 Host 认证 API，更未证明真实 Runtime provider / `task_kind` 能零补丁工作。PLUG-01 仍为进行中。全部产物及不含用户凭据的输出留在上述独立探针目录。
