# DSH Runtime 独立插件产品形态与交付计划

> 状态：2026-10-20 设计增补，待实现与验收；不替代已批准的 R9 可视化基线。
> 产品目标：把独立 Python Runtime 作为官方 DeepSeekHarness 的可安装扩展使用，并让 Runtime 分别配置工作、审查与只读检查的执行器和模型。
> 现有私有 Windows 0.2.1 是并行试用基线，不等于本计划的独立插件验收通过。

## 1. 最终用户体验与边界

用户安装官方 DeepSeekHarness，再安装一个私有 DSH Runtime 扩展包，配置 Python Runtime 路径、治理策略、工作区外的证据目录，以及各工作流角色所用的执行器与模型。用户从 Harness Web 发起 `repository_inspection` 或 `repository_change`；Runtime 保持任务状态、阶段调度、权限收窄与终态判决的所有权。Harness 扩展负责发起一次 Runtime 子进程调用、认证读取终态证据，并在工具卡中显示“执行轨迹 / 实际变动 / 审计”抽屉。

产品边界：

- `repository_change` 默认仍是一次有权限的工作阶段、一次独立只读审查阶段，最后由 Runtime 解析审查判决；`repository_inspection` 只有只读阶段。模型或供应商可变不改变阶段数、权限上限、超时、取消、无自动业务重试和证据来源规则。
- 模型文本不能充当文件变动事实。实际变动来自前后工作区观察；Safe Trace 只记录受限的操作元数据；缺失证据按现有 Manifest 契约降级。
- D2 ExecuteGate 属内部工程治理，保持 `NOT_CLAIMED`，不随用户插件安装而开放或宣传。
- Memory/RAG、实时事件流、桌面专属抽屉均不属于此轮最小交付；Web 终态抽屉先稳定。

## 2. 组件责任与安装形态

| 组件 | 最终责任 | 当前事实 / 差距 |
| --- | --- | --- |
| `dsh-runtime` Python 包 | 工作流、角色选择、执行器注册、权限/治理、审查判决、终态 JSON、Safe Trace | 控制循环已存在；`SimplePlanner` 仍把 CodeBuddy/Codex 写死，托管 Codex Home 有固定默认模型。 |
| Harness Host 扩展 | Profile 安装、受治理的 `dsh_runtime` 工具、子进程生命周期、Evidence Manifest、认证读取接口 | `@deepseek-ai/dsh-subagent-dsh-runtime` 已具备包和 Bundle 形态，但仍依赖私有 Harness 的通用 `tool-subagent` 扩展和工作区依赖；尚未在未修改的官方发行版验证。 |
| Harness Web 扩展 | 仅注册 `dsh_runtime` 工具视图、三栏抽屉及自有翻译 | 现有实现仍嵌在 `ui-tool` 与 `ui-conversation`。官方 `dsh.client` 和 `tool.call.toolview` 可作为迁出接口，须以真实外部包安装验证。 |
| ZCode 参考适配 | OpenAI 兼容协议到 Vertex Gemini / Vertex Claude 的转换、工具调用与流式处理 | 只作设计/测试参考，不复制密钥或直接把本地代理当作 Runtime 执行器；先核实各 CLI 的自定义模型入口。 |

首个目标为**可在未修改的官方 Harness 发行包上安装与卸载**的私有扩展。允许把确实缺失的通用宿主接口作为独立上游提案，但发布验收不能暗中依赖私有核心补丁。安装产物必须脱离 monorepo 的 `workspace:*` 引用，声明真实兼容版本，固定包哈希和 Runtime 版本；安装、禁用、卸载及回退均不得破坏旧 Home、旧会话或原仓库工作树。

## 3. Runtime 角色与模型配置契约（拟新增）

配置按**角色**而不是按全局“当前模型”表达。建议字段示例（名称与格式要在实现时冻结）：

```yaml
schema_version: 1
roles:
  worker:
    adapter: codebuddy
    model: null             # null = 该执行器经过验证的自身默认值
  reviewer:
    adapter: codex
    model: null
  inspector:
    adapter: codex
    model: null
```

- `worker` 仅用于 `repository_change` 的可写阶段；`reviewer` 仅用于独立只读审查；`inspector` 仅用于 `repository_inspection`。配置不得提升任务或治理策略授予的权限。
- `adapter` 是 Runtime 注册的执行器 ID；`model` 是该执行器可接受的模型 ID，不意味着任意执行器支持任意供应商。每个适配器声明支持的模型选择、凭据来源、工具能力、只读能力、流式/证据能力。启动时对不兼容组合明确报错。
- 默认配置必须复现现有 CodeBuddy 写入、Codex 审查/检查行为。Codex 的单次 `model` 参数可作为首个接线点；托管 Home 的固定默认模型应转为版本化配置。CodeBuddy 的模型覆盖先核实 CLI 正式接口及回传证据，不能猜测参数。
- 配置只保存凭据**引用**（环境变量名、受控凭据文件引用或执行器既有登录态），不保存明文。Manifest 可记录角色、适配器、请求模型、观测模型及缺失原因，不得写入 token、请求正文或密钥路径内容。
- 运行中的配置与版本必须冻结到该次调用；修改 Profile 只影响后续任务。网络/API 级重试须受限且幂等；整个仓库任务不自动重跑。

## 4. ZCode 可借鉴与不可直接复用的部分

`C:\Users\Administrator\Documents\ZCode` 是只读参考来源。`vertex_openai_proxy.py` / `claude_adapter.py` 展示了 OpenAI 兼容请求到 Gemini、Vertex Claude 的消息、工具调用、流式帧和错误映射；相关无网络测试覆盖了并行工具调用、签名回传、429 与流式拆包。可把协议转换及契约测试思路用于**独立模型网关适配层**。

它本身不是仓库执行器：它不承担 Runtime 的工作区授权、文件变动证据、任务结算或只读审查约束。CodeBuddy/Codex 能否把该代理作为后端，必须分别查证其正式配置接口和模型能力。ZCode 的 `.env`、服务账号和日志内容不复制到产品文档、测试夹具、提交或诊断输出。任何网关出站脱敏均是附加防护，不替代 Runtime 的工作区与证据边界。

## 5. 优先级开发任务与验收门槛

| ID / 优先级 | 任务 | 可验证完成条件 |
| --- | --- | --- |
| PLUG-01 / P0 | 官方 Host 插件接口探针 | 在**未修改的官方发行包**中，以包或 tarball 安装一个最小 Host+Web 客户端插件；能注册独立工具视图和认证 API；禁用/卸载后官方功能正常。记录真实兼容版本、安装命令及任何缺口。 |
| PLUG-02 / P0 | 宿主核心差异归类 | 对私有 Harness 相对官方的 Runtime 功能差异逐项标记“迁入扩展 / 通用接口需上游 / 非产品 D2 / 发布兼容修复”；特别处理 `tool-subagent` 的 `task_kind`、一次性提示和 `subagent` 请求类型，证明不依赖私有核心后才能宣布零补丁。 |
| PLUG-03 / P0 | Host 扩展独立打包 | Provider、Manifest、读取路由、Schema 合入外部包；去除 `workspace:*` 发布依赖与错误的官方仓库元数据；在干净安装上通过只读、写入、失败、取消及证据缺失测试。 |
| PLUG-04 / P0 | Web 抽屉独立打包 | 将 `dsh-runtime-row`、CSS、翻译迁到外部 `dsh.client` 模块，以公开槽位注册；不再编辑官方 `ui-tool`、`ui-conversation`。真实页面三页签与鉴权读取通过。 |
| MODEL-01 / P0 | 角色配置与默认兼容 | 冻结 schema、解析/预检、每次调用冻结与安全记录；无配置时现有 CodeBuddy→Codex 与只读检查行为不变；错误配置在模型/文件调用前失败。 |
| MODEL-02 / P1 | Codex 模型参数接线 | reviewer / inspector 分别选择模型，托管 Home 不再强制单一硬编码模型；在独立 Home 的真实只读试用中验证请求模型、观测模型与审查结论。 |
| MODEL-03 / P1 | CodeBuddy 模型能力核验与接线 | 先确认当前 CLI 的正式模型配置与可用证据；支持时实现 worker 选择，不支持时给出明确诊断；不通过环境变量或未验证命令开关假装成功。 |
| MODEL-04 / P2 | ZCode 风格网关适配试验 | 用独立测试凭据/假服务验证 Gemini 或其他后端的工具、流式、错误、取消及脱敏边界；只有执行器确实支持该协议时才纳入角色配置。 |
| REL-01 / P0 | 官方安装端到端与回退 | 固定官方 Harness、插件、Runtime 三个版本；全新 Home 的只读/写入/抽屉现场验收、旧 Home 迁移副本检查、禁用/卸载/回退通过；保留独立 Windows 0.2.1 日常入口直到新路径通过。 |
| REL-02 / P1 | 双仓主干收敛 | Runtime 已提交功能以私有 `master` 为主干；Harness 在插件脱离私有核心后选定主干。先审查独有 D2 提交并保留可寻址历史，再按授权归档旧分支；不触及原有未提交/未跟踪内容。 |

**执行顺序**：PLUG-01 → PLUG-02 → PLUG-03/04；MODEL-01 可与 PLUG-02 后的独立 Runtime 工作并行，随后 MODEL-02/03；完成 REL-01 后才判定“官方应用可安装插件”达成，再执行 REL-02。MODEL-04 是后续扩展，不阻塞首个稳定插件版本。每项验证应保留来源版本、命令、测试结果与现场/回放区别。

## 6. 当前事实、风险与下一步

截至本设计增补：R9 首期终态证据已在私有 Harness 与 Runtime 组合中验证；0.2.1 私有 Windows 版已并行试用。插件可独立安装于官方发行版、模型角色可配置、全功能无私有核心补丁**均尚未验证，不作为当前已交付声明**。

下一项直接工作为 PLUG-01：固定一个官方发行版本，在隔离目录中完成最小双面插件的打包、安装、加载、卸载探针；同时输出 PLUG-02 差异矩阵。探针使用独立 Home 与临时仓库，不碰两个原工作树和用户 ZCode 的凭据文件。
