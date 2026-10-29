# DSH Runtime 模型 API Agent 设计草案

> 状态：持续更新的设计草案。API inspector 已在独立 Runtime 与未修改的官方 Harness + rc15 插件中完成一次真实只读现场；API reviewer 仅在未打包的候选源码中允许配置，尚无真实宿主现场；API worker 仍关闭。现有 CLI 并行入口不变，D2 ExecuteGate 仍为 `NOT_CLAIMED`。现场证据见 `API_AGENT_PHASE1_2026-10-22.md`。

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

当前候选只向模型提供 `read_file`，且 Broker 仅接受显式相对文件路径。目录枚举的路径检查曾存在快速换出换回竞争；`list_files` 与 `search_text` 已从模型 schema、角色允许集合及 Broker 实现中同时撤下。`read_file` 在打开后核对真实文件句柄路径与边界，并拒绝敏感路径。未来若需要目录枚举，须先设计句柄绑定方案并通过对抗性验证，再单独开放。`apply_patch` 仍是待实现的 worker 写工具门槛，当前 Host 只在候选源码中允许只读 API reviewer，尚未安装验收。外部 shell、网络请求、Git 写操作、任意 Python 执行均不在工具面中。

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

## 7. 下一阶段的证据与权限门槛

API reviewer 不能仅靠 Runtime 能调用该角色就对外开放。候选 Host 现已接受独立配置的只读 API reviewer，终态 Manifest 分别保留 CLI worker 的 `execution_trajectory` 和 API reviewer 的 `review_trajectory`，通过角色与 `.closed` 校验拒绝互相冒充。`phase_2_codex_effective_write` 在 API reviewer 配置下为 `null`，避免暗示 Codex 参与。Reviewer 的精确终行判决仍由 Runtime 解析；缺失 reviewer 轨迹为 `unavailable`，但 worker 未完成、审查阶段未启动时为 `not_applicable`。无模型测试已覆盖假模型成功、供应商失败，以及 Host 对缺失、错误角色、失败和取消轨迹的拒绝；仍须在独立临时仓库做真实写入与异模型审查，方可考虑日常启用。

API worker 要另设门槛：候选已经加入**不接触文件系统**的 `plan_text_patch`，对原文件完整 SHA-256、唯一旧文本、UTF-8、BOM/NUL 与 32 KiB 上限做确定性检查，并给出新字节与摘要；它只负责补丁计算，不授予写权限。模型端 `apply_patch` schema 和角色允许集合仍关闭。下一步须将已打开文件与工作区绑定，设计抗 Windows junction/目录替换的原子落盘，再用独立临时仓库验证哈希冲突、取消及变化证据，方可开放 API worker。当前显式 `read_file` 的收缩也不替代长期并发文件系统攻击评估。工作区前后快照与 Safe Trace 各自提供观察证据，不以模型最终文本代替。

官方宿主的父 Agent 还需要正确理解异步回执：`dsh_runtime` 启动时返回的是子任务 ID，终态通过 `delivery: parent` 的子任务状态更新到达，不能把 ID 交给通用 job 工具。rc15 现场中父 Agent 曾误用 job 工具；候选源码的无模型契约测试现已验证固定 provider、可信父 Agent、`delivery: parent`、仅含 ID 的启动回执与工具说明。此测试不证明父模型会遵循说明；rc16 的真实宿主行为仍未现场验收。
