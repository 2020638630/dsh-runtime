# DSH Runtime 模型 API Agent 设计草案

> 状态：供负责人评审的方案草案，未实施、未做 API 现场调用；不改变现有 CLI 并行入口，也不改变 D2 ExecuteGate `NOT_CLAIMED`。

## 1. 建议结论

在 Runtime 现有 `Plugin` 接口下增加 `api_agent` 执行器，保留 `codebuddy`、`codex` 作为并行回退。外层 `DSHController` / `SimplePlanner` 继续拥有任务种类、工作/审查/检查三角色、最大阶段数、权限收窄、超时、取消、审计、工作区前后快照及 Evidence Manifest。新的执行器只负责一次角色阶段内的“模型请求 → 工具调用 → 结果回传 → 最终文本”有界循环。

首选做一个**受限 API Agent**，用 Pydantic AI Core 的模型提供商、函数工具和类型化输出做技术探针；具体版本须经锁定和契约测试。只复用模型与循环能力，不直接启用其完整 Coder/Shell/LocalWorkspace 组合：官方文档明确 `LocalWorkspace` 不是沙箱，完整 Coder 带持久 Shell 且无命令白名单。若框架不能满足取消、工具调用证据或模型观测要求，则在同一 `api_agent` 接口下用各厂商 SDK 实现小型循环。OpenHands SDK 或类似通用编码 Agent 可作对照原型，不直接接管 Runtime 的权限和结算。

此方案把“Agent 行为”和“模型 API 供应商”拆开：换模型不必换工具权限实现；不同供应商也不能因声称 OpenAI 兼容就自动获得工具能力。

## 2. 组件边界

```text
官方 Harness + 外部 Host/Web 插件
             |
        DSH Runtime
   治理门 / 任务状态 / Manifest
   worker -> reviewer 或 inspector
             |
   PluginRegistry: codebuddy | codex | api_agent
                                  |
            有界循环 + Runtime 自有工具执行器
                                  |
          Provider adapter / SDK / 可选网关
                                  |
       OpenAI、Gemini、DeepSeek 等模型 API
```

`api_agent` 的输入为冻结的角色配置、`ExecutionContext`、提示词与该阶段预算。输出仍为现有 `PluginResult`，包括 `StopReason`；不让模型自行宣告任务 `completed` 或审查 `PASS`。reviewer 的最终 verdict 继续按 Runtime 现有精确终行契约解析。模型文本不能证明文件变动；文件差异仍由 Runtime 前后观察给出。

reviewer 与 worker 使用独立模型会话，不继承 worker 的对话链；它只读取原始任务目标、当前工作区和 Runtime 提供的有限证据。两者可配置不同供应商，但“不同供应商”不能替代独立只读权限和实际文件核验。

## 3. 新执行器的最小工具面

首个版本仅提供 `list_files`、`read_file`、`search_text`、`apply_patch` 四个由 Runtime 实现的工具。所有路径先解析到本次绑定工作区，再校验规范路径、符号链接/Windows junction 与目标类型；每次调用记录工具名、结果类别和有界尺寸。`apply_patch` 只在 `worker` 且 `allow_workspace_write=true` 时注册，并在调用时再次检查；reviewer/inspector 根本看不到写工具。外部 shell、网络请求、Git 写操作、任意 Python 执行均不在首个工具面中。若实际编码能力不足，再以单独验收门槛加入受限命令工具。

每个阶段限制模型请求次数、工具调用次数、单次输出字节、总 token/费用预算和墙钟时长。取消先停止新 API 请求，再取消进行中的本地工具并结算；写工具需记录执行前/后状态。网络错误只能在**未执行任何写工具**或可证明幂等的单次请求边界重试，不能自动重放整个仓库任务。

## 4. 配置与凭据

保留当前 `schema_version: 1` 的 CLI 配置语义；新增配置使用 `schema_version: 2`，以免旧 Profile 被静默重解释。建议每个角色分别指明 `adapter: api_agent`、`provider`、`model`、`connection_ref`、可选能力策略与预算。`connection_ref` 指向本机受控凭据配置，Profile、Manifest、Safe Trace 中都不存明文 API key。端点只能来自用户明确配置的可信连接；禁止模型输出覆盖 endpoint、凭据或权限。

请求模型与响应中可观测模型分别记录；响应不提供模型 ID 时标为“未观测”，不能把请求值当观测值。启动前探测工具调用、流式拼装、结构化输出、取消与费用数据的实际能力，不满足角色最低要求即拒绝启动，不静默降级或换模型。OpenAI 兼容 API 可作为一种 provider 类型，但 Gemini/Anthropic 的原生工具协议与流式帧应分别做契约测试。ZCode 只借鉴协议转换测试样例，不读取或迁移其密钥。

远端模型 API 会接收为完成任务而发送的仓库片段与工具结果；安装界面须明确目标供应商、端点和数据发送范围。配置可限定允许发送的工作区、单次读取大小和禁止路径；任何凭据文件应在读取工具层拒绝，不能只靠提示词告知模型不要读取。

直接模型 API 使用供应商自己的 API 凭据与计费；现有 Codex/CodeBuddy CLI 登录态不自动等同于 API 授权。对 OpenAI，ChatGPT 订阅与 API 平台分别计费。API 凭据启用、预算上限和目标供应商须由用户在试用前明确配置。

## 5. 选型评估

| 方案 | 可用部分 | 对本项目的判断 |
| --- | --- | --- |
| Pydantic AI Core + 自有受限工具 | 多供应商模型封装、工具调用、类型化输出 | 首选技术探针；需验证跨供应商工具语义、取消、观测和依赖体积。 |
| OpenAI Agents SDK | 应用内 Agent 循环、工具与观测 | 适合 OpenAI 优先路线；非 OpenAI provider 的协议能力、默认 trace 出站须单独处理，不作为“任意模型即用”的保证。 |
| OpenHands / Pydantic AI 完整 Coder Harness | 丰富的代码 Agent 能力 | 作为质量与成本对照；其工具、Shell、工作区行为必须逐项收窄才可进入 Runtime。 |
| LiteLLM 等统一网关 | 路由、统一 API、密钥与预算管理 | 可作为可选 provider 层；不会替代受控工具执行和 Runtime 审计，也不能假定所有后端工具语义一致。 |
| 完全自写模型协议与 Agent 循环 | 精确控制边界与证据 | 框架探针失败时的后备；应只实现已验收的少数供应商，避免自建广泛兼容层。 |

## 6. 开发顺序与验收

1. **API-01 契约冻结（无模型）**：定义 `api_agent` 配置 v2、工具事件、取消/错误分类、预算和凭据引用。以假模型覆盖零/单/并行工具调用、部分 JSON、无效参数、模型拒绝、429、断流、超时、取消、API 返回模型缺失。现有 CLI Profile 回归不变。
2. **API-02 受限工具执行（无模型）**：独立临时仓库测路径逃逸、junction、只读写入企图、补丁冲突与并发取消；实际工作区变动和 Safe Trace 对齐，失败关闭。
3. **API-03 一个真实供应商**：先选用户已有合法 API 访问的一种模型，在全新临时 Git 仓库做只读 inspector，再做 worker 写入 + 独立 reviewer；核对请求/观测模型、精确文件字节、审查 verdict、Manifest 和审计。CLI 日常入口并行保留。
4. **API-04 第二供应商与安装**：至少一种非同协议供应商重复契约与真实现场；安装包可选装 API 依赖，全新 Home、旧会话、回退和无凭据分发复验。未覆盖的模型仍显示“未经验证”。

是否把 API Agent 升为默认角色，应在 API-03/04 的独立现场、长期错误样本和费用上限均过门槛后单独决定；当前官方 Harness 插件交付不以此为阻塞项。
