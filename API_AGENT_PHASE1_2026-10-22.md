# 模型 API Agent 第一阶段交接（2026-10-22）

## 当前状态

独立候选工作树：`D:\DeepSeekHarness\vis-api-agent-candidate-20261022`，从 Runtime `c179435` 新建。两个原工作树的未提交改动和未跟踪文件均保留。正式 D2 ExecuteGate 继续 `NOT_CLAIMED`。

本阶段实现**默认关闭的只读 API Agent 路由与无网络契约探针**。只有显式提供 schema v2 角色配置及仓库外连接文件时，`build_controller()` 才注册 `api_agent`；现有 schema v1 CLI Profile、官方 Harness 插件和日常入口不变。尚未用真实供应商执行模型调用。

- `api_agent_contract.py`：显式 schema v2，三角色可独立选 `api_agent` 或既有 CLI，API 角色要求供应商、模型、连接引用和每阶段请求/工具/token 上限；拒绝明文 key 和未知字段。
- `api_agent_connections.py`：只从仓库外本机 JSON 文件读取 key，供应商与端点须精确匹配；异常和对象表示不输出 key。连接文件样例放在 `D:\DeepSeekHarness\api-agent-local-config\connections.example.json`。
- `api_agent_loop.py`：模型传输和工具执行均注入；整批工具调用先校验再执行；只读角色不能获得写工具；记录请求模型与响应观测模型，禁止自动重试和整个任务重放。响应不提供 token 用量时失败关闭，后续要核验供应商是否稳定提供此数据。
- `api_agent_read_tools.py`：有界列目录、读 UTF-8 文件、文字搜索；排除已知敏感路径，拒绝相对逃逸和链接路径。Windows junction 已在本机隔离目录验收；文件并发替换防护仍待实现。
- `api_agent_chat_transport.py`：针对 OpenRouter / 硅基流动的非流式 Chat Completions 假 HTTP 探针；固定 HTTPS 端点、禁重定向和自动重试、校验 `finish_reason` 与用量、按类封装错误。OpenRouter 请求关闭路由回退并要求参数能力。测试版可选依赖固定在 `requirements-api-agent.txt` 的 `httpx==0.28.1`，尚未纳入可分发安装包。
- `plugins/api_agent.py` 与现有路由：schema v2 可逐角色混用 CLI 与 API；首期只允许 reviewer / inspector 进入 API Agent，worker 仍用 CLI。插件对写入上下文直接拒绝，连接文件缺失则在组装控制器时失败。工具终态和角色终态只记录名称、模型 ID、计数与结果类别，不记录 key、提示词、参数或文件内容；与 Evidence Manifest / Safe Trace 的正式接线仍待完成。

`apply_patch` 只出现在循环的预留工具名中，尚无写工具实现；现有只读 Broker 会拒绝它。

## 无模型验证

`python -m pytest -q`：564 passed、1 skipped（当前 Windows 权限下无法创建测试符号链接）。Windows junction 检查与全新隔离临时 Git 仓库只读检查通过；假 HTTP 覆盖双供应商请求、认证失败、429、503 和截断响应；假模型完成 Runtime 只读角色路由。所有测试不调用真实模型、不读取真实凭据。

## 首轮真实只读现场（2026-10-22）

用户把两套 key 填在仓库外的 `connections.example.json`；已将该文件**改名**为 `connections.local.json`，再创建纯占位示例。以下报告和 Runtime 事件均未保存 key、提示词或模型全文。

- OpenRouter：先从官方模型 API 核验 `cohere/north-mini-code:free` 的 `tools`、`tool_choice` 与零价字段，再在 `D:\DeepSeekHarness\api-agent-live-trials\readonly-5ux525pr` 的新 Git 仓库运行。任务 `completed`；实际 `read_file` 1 次、模型请求 2 次；请求与观测模型同为该固定 ID；输出包含测试标记；README 与伪 `.env` 哈希不变，Git 状态干净。安全事件在同名 `-evidence` 目录，扫描确认不含两套 key。
- 硅基流动：官方 `/v1/models` 返回账号可见的 `Qwen/Qwen3-8B`。首次在 `readonly-aiksm8f8` 的请求于 30 秒超时，0 次工具调用；第二次明确将单请求时限调到 60 秒，在 `readonly-6qbhugl5` 收到同一观测模型，但 512 输出 token 预算耗尽，仍为 0 次工具调用。两个仓库原文件哈希不变、Git 状态干净；没有自动重试，也不将该供应商记为通过。此模型的实际工具行为与免费计费状态尚待进一步确认。

这只是独立 Runtime 候选的只读现场；官方 Host 插件、Evidence Manifest/Safe Trace 接线、API worker 写入、桌面安装和第二台设备均未由此验收。

## 下一步优先级

1. **P0：只读边界**。补并发替换防护；明确工具事件如何进入 Safe Trace 和 Manifest。现有路径逃逸、Windows junction、敏感文件与隔离 Git 仓库的无模型验收已通过。
2. **P0：供应商传输**。OpenRouter 首个真实只读工具循环已通过；硅基流动须先查清免费模型的工具与思考 token 选项，再选一个固定模型做一次受控现场。取消和 API 费用数据仍待契约测试。可选 `httpx` 测试版本已固定，打包接线未完成。
3. **P0：写工具**。设计带预期哈希的文件补丁、冲突拒绝和受控原子写；工作区前后快照仍由 Runtime 外层结算。无模型验收过门槛才向 worker 暴露。
4. **P1：真实试用**。只读 v2 路由已接入候选 Runtime；在独立 Home、独立仓库中先做真实 inspector，之后再做 worker+独立 reviewer。观测模型不明时标记未知，不能冒称请求模型即实际模型。写入工具未就绪前，API worker 继续拒绝配置。
5. **跨环境验收**：第二台设备目前不可用，按用户安排推迟到今晚；不作为本机无模型开发阻塞项。

## 2026-10-23 接续：打开后路径校验

只读 Broker 的 `read_file` / `search_text` 文件内容读取改为打开后核对真实文件句柄路径，验证其仍在绑定工作区内、路径仍非敏感名称，并把读取限制为 `MAX_READ_BYTES + 1`。读取循环处理短 `os.read`，前后比较文件标识、大小和修改时间，检测到变动即拒绝。Windows 使用 `GetFinalPathNameByHandleW`，支持 `/proc/self/fd` 的系统使用打开文件描述符指向的路径；无法取得真实路径时拒绝读取。新增 Windows 受控测试：在原路径校验后把目录换成指向工作区外的 junction，文件读取必须失败且工作区外文件不变。另有短读取测试。没有调用模型或读取本机 API key。

最终 `python -m pytest -q` 为 **566 passed、1 skipped**。第一次全套运行时，既有 Safe Trace 时序测试只收到 3 条而非 6 条记录，单项重跑和后续两次全套运行通过。此偶发问题需在 Safe Trace 独立工作中诊断；不把它算作 API Agent 文件边界失败。

**剩余边界**：`list_files` 和 `search_text` 的目录枚举仍按路径进行，目录在遍历期间被替换的竞争尚未完全关闭；不得据此宣称只读 Broker 生产级安全。下一步先约束目录枚举，随后把 API Agent 安全事件正式接入 Evidence Manifest / Safe Trace，再开放 API worker 写工具。硅基流动真实工具调用仍未通过；不增加无计划的模型重试。两个原工作树保持原状，D2 ExecuteGate 保持 `NOT_CLAIMED`。

## 2026-10-23 接续：硅基流动固定模型与目录枚举

用户明确允许使用代金券涵盖的非免费模型。本机从硅基流动账户 `/v1/models` 只读查询确认 `Qwen/Qwen3-Coder-30B-A3B-Instruct` 当前可见，再在全新 `D:\DeepSeekHarness\api-agent-live-trials\readonly-rhh_zpc_` Git 仓库执行一次有界 `repository_inspection`。报告和安全事件位于同名 `-evidence` 目录：任务 `completed`，模型请求 2 次，`read_file` 工具 1 次，请求与观测模型 ID 一致，测试标记出现；README 与伪 `.env` 未变，Git 仍干净。扫描证据确认不含两套本机 API key。直接运行脚本路径时 Python 未把仓库根目录加入模块路径，首次执行在导入阶段退出且尚未创建试验仓库；后续从仓库根目录设置 `PYTHONPATH` 后成功。今后可用 `python -m scripts.api_agent_readonly_trial ...` 从仓库根目录运行。此次只证明该模型在此账户和此固定配置下完成一次工具循环；代金券实际抵扣与后续可用性仍由平台账户结算决定。此前 `Qwen/Qwen3-8B` 的失败记录继续保留。

目录枚举增加了进入和退出时的路径与目录标识复核；`search_text` 每个遍历目录均复核，遇到链接目录立即拒绝进入。枚举还在产生结果时执行条目上限，避免先排序整个巨大目录后才拒绝。Windows 受控测试在首次路径检查之后，把目录换成工作区外 junction：`list_files` 和 `search_text` 均不得返回外部数据。**此仍为原型防线**：枚举期间的快速换出换回尚可能绕过两次检查；正式发布前须使用句柄绑定的枚举能力或限制这些工具，并补对抗性验证。下一步优先把 API Agent 事件接入正式 Evidence Manifest / Safe Trace，再评估只读角色试用 Profile。D2 ExecuteGate 仍为 `NOT_CLAIMED`。

### 正式证据接线的已知约束

当前独立 Host Bundle 的 `run.ts` 只向 Runtime 子进程传 `DSH_CODEBUDDY_SAFE_EVENT_TRACE_DIR`；`evidence-manifest.ts` 只识别 `codebuddy-safe-worker-*.jsonl`，并对 `repository_inspection` 固定写 `execution_trajectory.status=not_applicable`。因此本次 `runtime-events.jsonl` 只能算隔离试验日志，**尚不是官方 Host 的终态 Evidence Manifest**。下一任务需新增 API Agent 专属的有界、白名单 Safe Trace 与 `.closed` 标记，Host 用独立来源标记读取，严格按 run ID、文件名、目录和终态绑定；旧 CodeBuddy 轨迹的判断保持原样。只读 inspection 的 API 轨迹要有明确来源，不能因任务种类沿用 `not_applicable`。先用伪模型和临时 Home 测试完成、失败、取消及缺失轨迹，再考虑真实 Host 现场。

Runtime 侧已先实现**默认关闭**的 `DSH_API_AGENT_SAFE_EVENT_TRACE_DIR`：启用时要求合法 `DSH_RUNTIME_RUN_ID` 和工作区外绝对目录，只写角色、工具名、结果类别、序号、终态及 `.closed` 的大小绑定，不写 key、提示词、工具参数或模型文本；完成、失败和取消均有终态路径。直接伪模型测试已覆盖完成与取消。Host 尚未设置这个变量，也未读取 `api-agent-safe-role-*.jsonl`；因此不能将独立 Runtime 轨迹称为正式 Manifest 或抽屉验收。

**同日后续实现（覆盖上句的 Host 尚未接线状态）**：候选 Host 现在把同一 run 专用 Safe Trace 目录通过新的 `DSH_API_AGENT_SAFE_EVENT_TRACE_DIR` 传给 Runtime，并只在子进程退出后读取 `api-agent-safe-role-*.jsonl` 与 `.closed`。读取器验证 run ID、目录、文件名、大小、序号、白名单字段、角色、工具名和终态；inspection Manifest 可用独立来源 `api_agent_safe_event_trace`，配置预期为 API inspector 却没有轨迹时标记 `unavailable`，旧 CLI inspection 仍为 `not_applicable`。Profile 校验显式接受 schema v2 的 **inspector API 角色**，连接文件仅通过 `apiAgentConnectionsPath` 传给 Runtime；API worker 和 reviewer 暂时在 Host 拒绝，待各自证据路径完成。TypeScript 类型检查、打包构建、5 项伪轨迹/Manifest 测试、入口配置测试和旧启动测试通过；Python 全套为 **575 passed、1 skipped**。这些是候选源码和无模型测试，**尚未打包安装或在真实官方 Host 中做 API inspector 现场**。下一步在隔离 Home 与仓库中安装候选包并验收；实际账户抵扣仍需平台结算确认。

Host 安装候选已打成私有 `@dsh-runtime/harness-plugin@0.1.0-rc.15` tarball，保存在 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\dsh-runtime-harness-plugin-0.1.0-rc.15.tgz`；包含独立 API Trace 读取器，不含凭据。此包还没有安装进新 Home；版本号只标识候选，不能当作稳定发布。

硅基流动 [Chat Completions 官方文档](https://docs.siliconflow.cn/docs/api/chat-completions-post) 与 OpenRouter [Chat Completion 官方文档](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request) 都展示工具调用字段，但具体模型能力必须现场验证。免费模型配额和可用性会变化，不在配置中硬编码。

## 2026-10-23：rc15 官方 Host 隔离安装与无模型激活

候选提交 `aed2494` 干净；原 Runtime 与 Harness 工作树分别仍有 16 和 106 项 Git 可见状态，均未清理、重置或覆盖。五小时额度检查时已用 56%，周额度已用 9%。

在 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023` 建立全新的 `runtime-source`、`home-api-inspector` 和 `inspection-repo`，没有复制旧 Home 或凭据。Runtime 源码从已核对 SHA256 的 `runtime-source-aed2494.zip` 解包；独立 Profile `home-api-inspector/profiles/runtime-api-inspector` 离线安装私有 rc15 tarball，配置仅启用 `repository_inspection`、schema v2 的硅基流动 API inspector，模型固定为 `Qwen/Qwen3-Coder-30B-A3B-Instruct`，请求/工具/输出上限为 3/3/512。Profile 仅保存仓库外连接文件的绝对路径和连接引用，不含 key。隔离仓库 README 为 `RC15_HOST_INSPECTION_MARKER`，当前 Git 干净。

首次启动的 `spawn EPERM` 是沙箱不允许创建治理子进程；窄范围授权后，第二次启动因政策哈希不符被治理 worker 拒绝。原因是 Profile 误用了 JSON 文件字节 SHA256 `013cfa...`，而协议要求 Runtime `load_policy_artifact()` 的规范化政策哈希 `c1cb7d...`。只修正该隔离 Profile 后，未修改的官方 `@deepseek-ai/dsh@0.2.1-rc.2` 在端口 31715 启动且 rc15 不再出现未激活警告。认证首页 200，匿名证据路径 401，认证但缺坐标的证据路径 400。没有调用模型，也没有产生 Runtime 任务或证据 Manifest。

目前官方 Host 进程与内置浏览器的独立页面保持打开；浏览器原生文件夹选择器需用户本机选取 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\inspection-repo` 并切到“仅可查看”。用户完成后，在该独立工作区发起一次固定范围的 `dsh_runtime` / `repository_inspection` 现场，再核对 Safe Trace、`.closed`、Manifest 来源、审计、README 哈希与 Git 状态。不要在默认工作区调用，也不要启用 D2。若进程已退出，须在同一 Home 上确认无其他 Host 实例后重启；避免同时启动两个实例。

**发布限制仍在**：目录枚举的快速换出换回竞争尚未用句柄绑定的枚举防线消除；API worker 与 API reviewer 未经 Host 验收；此 rc15 是私有候选，不能宣称稳定版或代金券必然抵扣。

## 2026-10-23：官方 Host 真实 API inspector 现场

用户在隔离官方 Host 页面添加 `inspection-repo` 工作区；两个新会话均明确设置“仅可查看”，每个会话只启动一次 `dsh_runtime` 的 `repository_inspection`。Home、仓库、证据路径均保持隔离；此现场不是 D2。

1. 首次 run `dsh-runtime-b1f20e81-8a67-4fb3-aff1-c13098afc615`：治理审计 `ALLOW`，Runtime 终态 `failed / api_agent tool_error`。API Safe Trace 有 `.closed`、来源 `api_agent_safe_event_trace`、状态 `available`，记录 `list_files` 和 `read_file` 完成、`search_text` 失败。安全轨迹按设计不保存模型工具参数，因此**无法确认失败的精确参数或错误原因**。在同一隔离仓库直接无模型执行这三个工具的合法参数均通过；不据此推断模型当时的参数。证据抽屉三个页签显示失败状态、零文件变动与已结算审计。
2. 第二次新会话收窄为仅 `read_file(path=README.md)`；run `dsh-runtime-c7973891-807d-46ad-ab64-011090eb43d4` 的 Manifest 为 `completed`，轨迹 `available / observed_stream_complete`，工具计数 `read_file=1`、其他两项为零，`.closed` 存在，审计 `settled`，变动列表全空。网页证据抽屉三页签均显示对应终态。README 的 SHA256 仍为 `A5D4141E18CB0099E47E01EF8A25B4DFFAA1FC6198B3D99ACB50FBA957332B63`，Git 干净。该现场证明未修改的官方 Host、独立 rc15 插件、真实硅基流动 API inspector、终态 Manifest 与 Web 抽屉可联动；不证明代金券抵扣或 API worker/reviewer 能用。

宿主 DeepSeek-V4.1-Flash 在第二次 Runtime 启动后把返回的 subagent ID 当作后台 job ID，额外尝试 `job_list`/`job_output`，随后试图运行普通命令。普通命令被人工停止并显示 aborted；仓库仍干净。**这属于父 Agent 对异步子任务回执的理解问题，不是 Runtime API inspector 的第二次调用。**候选源码 `src/tool.ts` 的工具说明已补充“结果通过子任务状态更新送达，ID 不是后台 job ID”；`pnpm typecheck`、`pnpm build`、`pnpm test:tool`（2/2）通过。此说明更改尚未打进 rc15 安装包，需下一候选包与现场验证，不能声称已修复父 Agent 行为。

下一步优先级：先把工具说明更改及现场记录做本地提交；再处理目录枚举的句柄绑定或收缩 `list_files/search_text` 工具面。此安全边界未闭合前，不提升 API inspector 为日常默认，更不启用 API reviewer/worker。然后对父 Agent 异步回执做无模型契约验收，视需要发 rc16 隔离包；API reviewer 和受控写工具分别走独立门槛。五小时额度最新检查为已用 83%、周额度已用 13%，达到五小时剩余 10% 或周剩余 2% 时按用户要求记录后停手。

异步工具说明已打入未安装的私有 `@dsh-runtime/harness-plugin@0.1.0-rc.16` 候选包：`D:\DeepSeekHarness\api-agent-host-artifacts-20261023\dsh-runtime-harness-plugin-0.1.0-rc.16.tgz`，SHA256 `2FFA2A3C802070424A7D4EF39D844FFA43D7A852C0C5E80EE759B7A56DE18D04`，22 个文件。离线构建与打包通过；扫描本机两套连接密钥字节，rc16 包及本次隔离 Home 的 13 个小型配置/证据文件均未命中。rc16 尚未安装或做模型现场，因此不能把工具说明改动计为已验证修复。rc15 的成功与失败 run 均保留在原隔离 Home 中。

### 额度交接（2026-10-23）

五小时额度已用 **90%**、周额度已用 **14%**，达到用户设定的五小时剩余 10% 停止线。候选分支 HEAD `09d627b` 且工作树干净；两个原工作树的 Git 可见状态仍分别为 16 和 106 项。未推送、未切换日常入口、未执行 D2。隔离官方 Host 仍在端口 31715，内置浏览器保留成功任务证据抽屉；下一次操作先确认该 Host 是否仍在线，不要并发启动同一 Home。

下一步先用**无模型**方法收紧目录枚举竞争边界，并检验父 Agent 对 Runtime 异步子任务回执的契约；随后在新的隔离 Home 安装 rc16 对照包，不覆盖 rc15 的 Home 或证据。API reviewer 的双轨迹 Manifest 和 worker 受控写工具按设计文档分别推进。五小时窗口显示北京时间 **2026-10-23 14:12:20** 重置；已通过本线程 heartbeat 创建一次性续跑 `dsh-runtime`，目标约 14:17，执行后须停用自身。定时依赖本机与 Codex 桌面应用保持运行；若用户手动先续跑，定时执行时应核对状态避免重复。

### 2026-10-23 定时续跑：无模型安全收缩与父 Agent 契约

额度恢复后检查：五小时已用 2%、周已用 15%；候选 `8890473` 起始干净，两个原工作树分别有 16 与 106 项 Git 可见状态，均未清理、重置或覆盖。rc15 隔离 Home 与证据保留，端口 31715 当前不在监听；没有重做模型现场。

**目录枚举**：当前 `list_files` / `search_text` 无法排除目录快速换出换回造成的名称泄漏，因此直接从模型 `READ_TOOLS`、供应商工具 schema 以及 `WorkspaceReadBroker` 实现中撤下。API inspector 当前只能调用显式路径的 `read_file`，仍须经过打开后文件句柄边界核对。旧轨迹读取器继续认识历史工具名以正确显示 rc15 证据，不代表新候选仍可执行这些工具。无模型测试覆盖 Broker 直接拒绝、模型回包在执行前拒绝、供应商传输不公布目录工具、Windows junction 在文件打开前替换。定向测试 24 passed、1 skipped；Python 全套 574 passed、1 skipped。

**异步回执**：`dsh_runtime` 启动只返回子代理 ID，启动参数固定 `delivery: parent`。新增无模型工具契约测试核对可信父 Agent、固定 inspection provider、`delivery: parent`、工具说明中“等待子任务状态更新 / ID 非后台 job”及仅有启动回执的渲染；`pnpm test:tool` 为 3/3。此测试证明接线与文字契约，不证明父模型已经学会等待；当时 rc16 尚未安装，不能声称现场行为修复。API reviewer/worker 均未开放，D2 ExecuteGate 继续 `NOT_CLAIMED`。

候选安全收缩与测试已本地提交为 `88fcb78`，工作树干净。新建 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc16-isolated-check`，从该提交的 Git archive 解出 Runtime 源码，复制已核对 SHA256 为 `2FFA2A3C802070424A7D4EF39D844FFA43D7A852C0C5E80EE759B7A56DE18D04` 的 rc16 包，独立 Home/Profile 仅引用仓库外连接文件路径，不复制 key。`pnpm install --offline --ignore-scripts` 成功，官方 0.2.1-rc.2 CLI 合成配置退出 0、stderr 0，配置含独立插件。首次默认沙箱启动如历史现场一样因治理子进程 `spawn EPERM` 未激活；停止该隔离进程后，窄范围授权重启，插件无激活警告、stderr 0、认证本地首页 HTTP 200，随后停止，端口不再使用。此项没有调用模型、没有 Runtime 任务或新 Manifest，也不证明父 Agent 现场遵循异步回执。rc15 Home 和两条历史 run 未动。

复核时原 Runtime 工作树为 16 项、原 Harness 工作树为 108 项 Git 可见状态；后者较交接时的 106 项增加，原因未在本轮追查。本轮只写独立候选和新隔离 Home，未修改、清理或重置原工作树。rc16 隔离服务已停止且随机端口不再监听；五小时已用 15%、周已用 17%。

下一步：在仍隔离的官方 Host 中仅在必要时做 rc16 父 Agent 行为现场，重点观察是否还误用通用 job 工具；若出现误用，应改工具回执/宿主提示并补无模型契约，再次隔离验收。API reviewer 双轨迹和 API worker 原子写工具仍是独立门槛。当前候选仅可作为私有只读试用，不能提升日常默认。两原工作树与 D2 状态须复核后再推进。

### 2026-10-23 后续：API reviewer 双轨迹与 worker 补丁计算

在独立候选分支继续开发，起点 `1e6d622` 干净。Host schema v2 现在允许显式选择**只读** API reviewer，worker API 仍拒绝。Host 将本次 `repository_change` 的 CLI worker Safe Trace 保持在 `execution_trajectory`，把 API reviewer 的独立 `.closed` 轨迹写入 `review_trajectory`，校验同一 run、trace ID、角色和终态。Reviewer 轨迹缺失、角色不符、失败或取消时，不以终行文本冒认可信 `PASS`；worker 阶段先失败、reviewer 未启动时标 `not_applicable`。Codex / CodeBuddy worker 与 API reviewer 的权限字段分别归属，页面审计页显示 API reviewer 轨迹状态与终态。Runtime 对 API reviewer 的 `FAIL` 文案不再误称 Codex。伪模型测试覆盖 reviewer 完成与 provider 失败，既有取消路径和 Host 伪轨迹测试覆盖其余终态；真实 reviewer 模型现场尚未进行，不能视作日常资格。

API worker 仍不开放：`apply_patch` 已从模型角色允许集合与供应商工具 schema 撤下，即使直接给循环写权限也只暴露 `read_file`。新增纯函数 `plan_text_patch` 仅在内存中检查原文件完整 SHA-256、旧文本唯一匹配、UTF-8、BOM/NUL 和 32 KiB 上限，返回候选新字节与摘要；它没有打开路径或写文件能力。后续须设计真实文件句柄到工作区的绑定、抗目录替换的原子落盘、取消与前后证据，才可注册写工具。

当前无模型验证：Python 全套 **591 passed、1 skipped**；Host `pnpm typecheck`、`pnpm build`、`pnpm test:entry` 4/4、`pnpm test:host-core` 1/1、`pnpm test:worker` 3/3、`pnpm test:api-agent-trace` 13/13 已通过。默认沙箱对 Git/Python 子进程报 `EPERM`，这些既有测试经窄范围授权在独立临时目录成功。五小时额度最近已用 41%、周已用 21%，未触发停止线。没有调用模型、没有触碰 D2，也没有改动两个原工作树。

### 2026-10-23：rc17 reviewer Profile 无模型官方宿主验收

前述 reviewer 双轨迹与补丁纯计算已本地提交为 `058c22a`，提交后候选工作树干净。将 Host 包版本升至私有 `0.1.0-rc.17`，产物位于 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc17-reviewer-check\dsh-runtime-harness-plugin-0.1.0-rc.17.tgz`，SHA256 为 `F2F6BA98D204FDAA4A9EFFB600CAEFAE4F62C780C7F30748C81DEA785871A919`，共 22 个文件。逐个检查包内文件，未命中本机连接配置中的两项密钥字节；配置文件本身不在包中。

在新的 `rc17-reviewer-check` 下从 `058c22a` Git archive 展开 Runtime，建立独立 Home/Profile，离线安装 rc17。Profile 使用 schema v2 的 CodeBuddy worker、硅基流动 API reviewer 与 inspector，仅引用工作树外连接配置路径，未复制 key。官方 0.2.1-rc.2 CLI 配置合成确认插件与 reviewer 条目存在。首次启动因新 Home 缺审计目录未激活，补齐后沙箱报 `spawn EPERM`；停止各隔离进程后，经窄范围授权重启，插件没有激活告警，认证页面 HTTP 200，随后停止临时宿主。**没有调用模型、执行 Runtime 任务或产生 reviewer Manifest**；此项只证明包安装与官方宿主激活，不把 reviewer 提升为日常可用。

下一步在全新临时 Git 仓库做一次受控 `repository_change`：CLI worker 完成最小写入，API reviewer 只读核验，并检查同一 run 的两条 `.closed` 轨迹、独立权限字段、终态 Manifest、审计和精确文件字节。若父 Agent 误把子代理 ID 当 job ID，单独记录并修工具回执，不把它归为 reviewer 成功。API worker 写工具仍关闭，D2 ExecuteGate 仍为 `NOT_CLAIMED`。最近核对两个原工作树分别为 16 与 106 项 Git 可见状态；本次仅写隔离候选与新 Home。五小时额度已用 51%、周额度已用 23%。

### 2026-10-23：直接 Runtime reviewer 现场发现工具协议问题

在 `rc17-reviewer-check` 下新建隔离 Git 仓库和证据目录做非 D2 写入验收。第一轮在配置解析阶段因试验脚本将 inspector 错配为 CodeBuddy 而拒绝，仓库保持干净。第二轮 CodeBuddy 正确创建 `result.txt`，但试验脚本的 run ID 缺 `dsh-runtime-` 前缀，API reviewer Safe Trace 预检失败；该失败仓库和证据均保留。第三轮使用合法 run ID 后，worker 创建精确 `RC17_REVIEWER_OK\n` 字节，README 不变；CodeBuddy 与 API reviewer 各有同一 run 的 `.jsonl`、`.closed`。Reviewer API 阶段返回 `completed` 轨迹，但模型把 `<function=read_file>` 写成普通文本，没有发出原生工具调用，也没有给出精确末行，Runtime 以 `invalid verifier result` 判任务 `failed`。因此不能宣称 reviewer 现场通过，且 rc17 包不作为 reviewer 日常版。

据此候选源码增加 reviewer 专用 system 约束，并在没有真实 `read_file` 工具调用时以 `reviewer_no_file_read` 失败关闭，不接受文本伪工具调用或无文件证据的 `PASS`。无模型测试已覆盖此拒绝和真实工具调用后通过，`tests/test_api_agent_contract.py` 与 Runtime reviewer 路由测试合计 **32 passed**。这项修正还没有打进 rc17 包，也没有做新模型现场；若继续现场须用新源码与新临时仓库，保留上述三轮失败证据。五小时额度最近已用 60%、周已用 24%。

本次 Python 全套为 **592 passed、1 skipped、1 failed**；失败项仍是 `test_safe_event_trace_streams_only_allowlisted_metadata`，期望 6 条、实际 3 条，单项复跑亦失败。它属于先前交接已见的 CodeBuddy JSON 数组 Safe Trace 观察问题，和本次 API reviewer 修改不在同一文件；当前不能把全套称为通过。简单分块解析器复现未触发同样问题，后续应以真实假 CLI 输出时序单独定位，不通过放宽断言掩盖轨迹不完整。

第四轮独立临时仓库使用 reviewer system 约束后，worker 仍创建正确文件；这次 reviewer 发出了原生工具调用，但供应商同一响应还附带短文本，旧循环以 `mixed_text_and_tools` 失败关闭，API 轨迹 `failed` 且工具未执行。候选循环现在只在文本不超过 4096 字符时**丢弃**随原生工具调用附带的普通文本，仍先验证整批工具参数并仅执行原生调用；超长文本在 Broker 前拒绝。相关定向测试 **44 passed**。随后在第四轮已隔离仓库上单独重跑 reviewer：两次原生 `read_file`，精确末行 `DSH_VERIFICATION: PASS`，API 轨迹 `completed` 且 `.closed` 存在，README/result 文件哈希前后相同。Safe Trace 只记录工具名，不记录目标路径；因此这证明 reviewer 阶段可在该模型与配置下完成，不代替官方 Host 双轨迹 Manifest 现场，也不抹去四轮完整任务失败记录。

排除上述唯一已知 CodeBuddy Safe Trace 失败项后，全套其余 **594 passed、1 skipped、1 deselected**。当前不能称全套无条件通过；需要单独修复该 Safe Trace 时序问题。API reviewer 新兼容处理仍未打入 rc17 安装包。

### 2026-10-23：rc18 隔离包与后续门槛

短文本伴随原生工具调用的修正已本地提交 `fe74842`。从该提交归档 Runtime 源，并制作私有 `@dsh-runtime/harness-plugin@0.1.0-rc.18` 包，存放在 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc18-reviewer-check\dsh-runtime-harness-plugin-0.1.0-rc.18.tgz`，SHA256 `D8051E12A728748299B878E8CC9F9ABD16608221EF820ADE5760E0BF151E1A3E`。22 个包内文件均未命中本机连接配置的两项 key 字节；包不含连接配置。新的隔离 Home/Profile 离线安装成功；未修改的官方 0.2.1-rc.2 CLI 配置合成包含插件与 API reviewer，窄范围授权启动无插件告警，认证首页 HTTP 200，随后停止。此次**无模型**官方 Host 验收不证明 reviewer 的双轨迹 Manifest 现场通过，也不改变日常入口。

当前候选唯一重复失败的全套项是 CodeBuddy Safe Trace 假 CLI 流式观察。假 CLI 的完整输出已核对为合法 JSON、四个顶层事件；把同一字节按单字节和整块交给观察器均能离线解析四项。实际测试运行时轨迹只记录首个模型事件与 `trace_incomplete`，故问题更可能在运行时文件观察/收尾时序，尚未定位到具体语句。不得通过放宽事件数断言宣称完整。

下一步按优先级：先把 CodeBuddy Safe Trace 观察器的真实文件时序故障定位并修复，再在**全新临时仓库与新 run**中用 rc18 官方 Host 做真实 CLI worker + API reviewer，核对同一 run 的两条 `.closed`、终态 Manifest、审计、文件字节和抽屉显示。API worker 原子落盘与跨第二设备验收继续独立推进。D2 ExecuteGate 保持 `NOT_CLAIMED`；两个原工作树最近分别为 16 与 106 项 Git 可见状态，未清理、重置或覆盖。五小时额度最近已用 78%、周已用 27%，尚未触发 10% / 2% 停止线。

**随后修复进展**：重复运行假 CLI 时，失败样本的观察器在进程已退出但重定向 stdout 末字节尚未可读时提前终结（失败时读到 672 字节、正常为 673 字节）。候选 Runtime 的文件观察器现于进程退出后做最多四次、每次 20 ms 的有界 EOF 复核；若字节仍缺失，仍标记轨迹不完整。新增延迟写入最后一个 `]` 的确定性测试，不放宽原有六事件断言。原失败项与新测试通过，Python 全套 **596 passed、1 skipped**。此修正尚未进入 rc18 Home 内的 Runtime 源副本；未来真实 Host 现场应从修正提交重新归档到**新**隔离位置。此前 rc18 无模型激活结果仍只证明包可加载。

### 2026-10-23：下一次真实 Host 验收已就绪

Safe Trace 修正及 rc18 版本记录已本地提交 `54877d2`，候选工作树干净。为避免覆盖 rc18 的无模型样本，新建 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc18-live-reviewer-ready`：Runtime 源从 `54877d2` Git archive 展开，rc18 包按 SHA256 复制核对，独立 Home/Profile 离线安装，仓库外连接文件仅以路径引用。全新 `trial-repo` 只有固定 README 标记并已提交为干净 Git 基线，README SHA256 `C404ED049DE3BDE4F45252CEB6BF253F0969EFC4F037A1B50BF904E18FD86B36`。官方 0.2.1-rc.2 CLI 配置合成含 API reviewer；隔离 Host 无模型启动无激活告警，认证首页 HTTP 200，随后停止，未调用模型、未写试验仓库。

**下一操作**：先确认额度与隔离 Host 当前未运行，再只在上述 `trial-repo` 做一次非 D2 真实官方 Host `repository_change`，目标为单一新文件；核对 CodeBuddy worker、API reviewer 两条同一 run 的 `.closed`、终态 Manifest 的 `execution_trajectory`/`review_trajectory`、审计、精确字节与抽屉。失败则保留该 run 与仓库，另建隔离仓库修复。API worker 仍关闭，不能把 reviewer 的单独成功误称完整 Host 通过；第二设备继续等待用户可用。原 Runtime 与 Harness 工作树最近分别为 16 与 106 项 Git 可见状态，均未清理、重置或覆盖；D2 ExecuteGate 仍 `NOT_CLAIMED`。五小时额度最近已用 89%，周已用 29%；一旦达到 90% / 98% 停止线，更新本交接并安排本线程一次性续跑，旧 `dsh-runtime` heartbeat 目前为 `PAUSED`，不能直接沿用其过时 prompt。

### 2026-10-23 晚间：一次性续跑等待页面任务

候选 `codex/model-api-agent-20261022` 为 `f268146`，续跑开始时干净；隔离 `trial-repo` 为干净 `master`，README 标记未变。两原工作树仍分别有 16 与 106 项 Git 可见状态，未清理、重置或覆盖。五小时额度已用 6%、周额度已用 30%，未触发停止线。隔离官方 Host 使用 `rc18-live-reviewer-ready/home` 的 `runtime-api-reviewer` Profile 启动，进程 PID 31400，新的日志为同目录 `host-live-stdout.log`/`host-live-stderr.log`；认证页面 HTTP 200，stderr 为空。浏览器已尝试打开该隔离页面，并向用户发出在 `trial-repo` 中执行一次非 D2 `repository_change` 的页面操作说明。记录时 `home/evidence` 尚无新 run，试验仓库仍干净；因此**没有模型现场结果，不得宣称双轨迹验收通过**。后续先核对该 Host 是否仍运行及试验仓库、证据目录是否已变化，避免重复调用；用户回执后再核对同 run 两条 `.closed`、Manifest、审计、精确字节与证据抽屉。API worker 保持关闭，D2 ExecuteGate 保持 `NOT_CLAIMED`。

**用户页面回执及磁盘核对**：随后用户在此隔离工作区完成一次 `repository_change`，页面 DSH Runtime 工具卡显示 `completed / PASS` 且三个抽屉页签可见。run 为 `dsh-runtime-04e239cc-62d5-4de1-bc00-bfdf4f4861b3`，终态 Manifest 为 `completed`、`exit_code=0`、审查 `PASS`、审计 `settled`（call ID `233ae2e7-b3e1-4750-b694-55de6a88e84c`）。`execution_trajectory` 为 `safe_event_trace / available / complete`，`review_trajectory` 为 `api_agent_safe_event_trace / available / complete / completed`；两条 `.closed` 的 run ID 相同且记录的 6464/996 字节分别等于对应 JSONL 实长。API reviewer 轨迹有两次 `read_file`。Manifest 的唯一新增文件为 `rc18-host-review.txt`，实测内容十六进制为 `524331385F484F53545F5245564945575F4F4B0A`、20 字节、SHA-256 `E0B4EC2CF115F21B108F8B4E67B0592A4466A95BCE572DC605A9252886CBC0E0`；README 哈希仍为原基线值。两个本机连接密钥在此 run 证据文件中均未命中。

**独立质量问题**：API reviewer 的模型叙述错误声称文件为 22 字节、LF 后另有 NUL，虽然同一叙述给出 `PASS`；磁盘字节与 Manifest 的确定性快照均证明该声称错误。不能将该模型叙述视作字节证据，也不能把现场 `PASS` 扩展为“审查文本完全准确”。下一步优先让 `read_file` 的真实句柄读取结果携带确定性的字节数与 SHA-256，并收紧 reviewer 提示与无模型契约，再在新隔离 run 验收；旧 run 和文件保留，不覆盖。API worker 写工具仍关闭，第二设备仍待用户可用，D2 ExecuteGate 保持 `NOT_CLAIMED`。

**候选修正**：`read_file` 现在从同一已验证句柄的字节生成 JSON 结果，包含 `byte_length`、SHA-256 和 UTF-8 内容；结果大小继续有界。API reviewer 系统提示和供应商工具描述明确要求用这些字段支撑精确字节声明。新增无模型测试核对真实 Broker 到模型下一轮消息的元数据、Unicode/LF 字节数与 JSON 扩张拒绝；Python 全套 **599 passed、1 skipped**，`git diff --check` 无格式错误。此修正仍只在候选源码中，未打新包或复测真实模型；rc18 的原现场证据不改写。

**复测准备**：上述修正与记录已在隔离候选分支本地提交为 `19bcc72`，提交后工作树干净。新建 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc18-metadata-retest-ready`，Runtime 源从该提交归档（ZIP SHA-256 `5D0A64FA7B1ED2CA3932C6A87249FF734FED31D6C44D1E675C630BD266C96702`），Host 复用同字节 rc18 插件包（SHA-256 `D8051E12A728748299B878E8CC9F9ABD16608221EF820ADE5760E0BF151E1A3E`）；另设独立 Home/Profile，连接文件仍仅以仓库外路径引用。新的 `trial-repo` Git 基线干净，README SHA-256 `617651FDD2B57A52DB06AE063C5EF8F23CBEB270A2DD31A37EA0BA4A79CC4EC5`。官方 CLI 配置合成退出 0、stderr 0，只含新隔离路径；新 Host PID 30388，认证页面 HTTP 200、stderr 0，尚无新 Manifest。已打开隔离浏览器页面，等待用户在该新仓库执行一次非 D2 任务并回执；后续须核对磁盘字节、模型叙述、两条 `.closed`、Manifest 与审计，不能把旧 rc18 的结果当作本次结果。

**复测结果**：用户完成页面任务后，run `dsh-runtime-4ae6f08f-da9d-4d6e-9d48-4558eb7ac805` 的 CodeBuddy worker 写出了唯一新文件 `metadata-review-check.txt`，实测 `METADATA_REVIEW_OK\n` 为 19 字节、SHA-256 `F503C94E09B6E85FE75A38B3A2DB68DDDD6A6D3AE08CBF2478863DFF186397D6`，README 哈希不变。双轨迹 `.closed` 的 run ID 相同、长度匹配（worker 5744、reviewer 735），审计 `settled`。**整次任务失败**：Manifest 为 `failed`，判决 `UNAVAILABLE`，API reviewer 轨迹以 `failed` 终结；只发生一次 `read_file` 调用且状态为 `failed`，所以没有模型审查叙述可供核对。Archive 中的 Broker 对此文件做直接只读测试可返回正确 19 字节与 SHA-256，且文件写入时间早于 reviewer 工具调用；现场失败的具体工具参数因 Safe Trace 最小化未保存，不能断言是哪条路径触发拒绝。保留此失败 run，不把文件成功误报为完整验收通过。

**后续候选修正**：只对只读 Broker 明确抛出的 `ValueError`，API Agent 在既有请求/工具预算内给模型一个不含路径或异常文本的通用“不可读取”回执，允许纠正一次路径；任意其他异常仍直接失败。Reviewer 必须至少有一次成功的原生 `read_file` 才能给出判决，失败的读也消耗工具预算。新增无模型契约覆盖一次拒绝后成功、仅拒绝后伪 PASS 不得通过；Python 全套 **601 passed、1 skipped**。这尚未打入新的隔离 Runtime 源，也未经过再次真实模型现场，不能宣称修复了上述失败的未知具体原因。API worker 仍关闭，D2 ExecuteGate 保持 `NOT_CLAIMED`。

**有界纠错现场**：候选修正已提交 `58bf5e1`，随后从该提交在 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc18-read-retry-ready` 归档源码（ZIP SHA-256 `023D0F749C7386A627BEBF71685A0B41AA1E9329B6AF69A2C0E838820F70F5EF`），复用字节相同的 rc18 Host 包、另建 Home/Profile 和干净 `trial-repo`（README SHA-256 `0E9D27A211C1869BB9B36493E5E442AD29C8CF134300A6B717652ECAA04AE7B4`）。官方 CLI 合成配置退出 0、stderr 0；隔离 Host PID 21640，认证页面 HTTP 200、stderr 0。用户在新工作区完成一次非 D2 `repository_change`，run `dsh-runtime-85790bda-1e22-472a-aeff-0fa89c52f3fe` 写出唯一文件 `retry-review-check.txt`，实际 `RETRY_REVIEW_OK\n` 为 16 字节、SHA-256 `3202733A154DF4FEA35D1C2E50060E50C1BFFD008722A74159E2CC241A312231`，README 哈希未变。双轨迹 `.closed` 同 run 且长度匹配（worker 5746、reviewer 1245），审计 `settled`。Reviewer 轨迹显示第一次 `read_file` 失败、之后两次成功，说明通用纠错路径在真实模型调用中发生；但终态仍为 `failed / UNAVAILABLE`，未得到最终审查文本。配置仅 3 个请求/3 个工具调用，预算耗尽是合理假设，但原 Safe Trace 只写笼统 `failed`，无法确定具体类别；不得把此推断当作已证实根因。旧失败 run 保留。

**失败类别诊断候选**：Runtime 的 `.closed` 标记现在只允许固定白名单中的 `failure_code`，不写工具参数、路径、提示词、模型文本或异常；旧成功标记格式保持原样。Host 读取器验证该白名单后将类别写入 Manifest 的 `review_trajectory.failure_code`，审计页在存在时显示。模型提示要求成功读取目标文件后尽快给最终判决，避免无理由重复读。Python 全套 **602 passed、1 skipped**；Host 类型检查、14/14 API Trace 测试与构建通过，默认沙箱的 Git 子进程 `spawn EPERM` 用窄范围授权重跑通过。独立 rc19 Host 包位于 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc19-failure-diagnostic\dsh-runtime-harness-plugin-0.1.0-rc.19.tgz`，SHA-256 `2CFA3450FC7980044B8209FF9B48143DD5B4A9F193B4F07C7AE5AE7BCE7EB974`；逐个扫描 22 个包内文件，未命中本机两套 API key。此代码与包尚未装入新隔离 Home，仍需下一次现场确定失败类别和最终审查结果。API worker 关闭，D2 ExecuteGate 保持 `NOT_CLAIMED`。

### rc19 独立 Host 现场准备（2026-10-23）

候选分支 `codex/model-api-agent-20261022` 的 HEAD 为 `5f43570`，开始时工作树干净。新隔离位置为 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc19-budget-live-ready`；Runtime 源归档 SHA-256 `35CF180B7DD280709948AA043EDB9655E8F79DD1A8BDB78F8256240E15EB9D04`，rc19 Host 包 SHA-256 `2CFA3450FC7980044B8209FF9B48143DD5B4A9F193B4F07C7AE5AE7BCE7EB974`。独立 Home/Profile 离线安装成功，官方 0.2.1-rc.2 CLI 配置合成退出 0、stderr 为空，配置指向新隔离目录且不含旧 rc18 路径；API reviewer 预算为最多 5 请求、4 工具调用、1024 输出 token。新 `trial-repo` 为干净 Git 基线，README SHA-256 `155E7BE658C8E007EA57791B162C5466ACC90E88C60D5B838A40951E7E33287D`。

已停止上一轮隔离 Host PID 21640；新隔离官方 Host PID 3500，认证首页 HTTP 200、stderr 为空。已打开本地页面，并请用户在 `trial-repo` 中只执行一次非 D2 `repository_change`，创建 `rc19-budget-check.txt`，内容 `RC19_BUDGET_OK\n`。写下此记录时新仓库尚无目标文件、新 Home 尚无 Manifest；**不能视为现场已通过**。待回执后核对终态、失败类别、两条同 run `.closed`、精确字节、审计和抽屉。两个原工作树仍分别为 16 和 106 项 Git 可见状态，均未清理、重置或覆盖；D2 ExecuteGate 保持 `NOT_CLAIMED`。五小时额度当时已用 52%、周已用 38%。

**rc19 现场结果**：用户只发起一次 `dsh_runtime` 的 `repository_change`，run `dsh-runtime-291b8715-24f7-414f-aa1e-bc639fbb61a9`。页面显示 `completed / PASS`、抽屉三个页签可见。Manifest 为 `completed`、退出码 0、审查 `PASS`、审计 `settled`（call ID `ae8fcb13-b4f5-4869-b1a3-28a620351eca`）；CodeBuddy 执行轨迹和 API reviewer 审查轨迹均 `available / complete`，同一 run 的两个 `.closed` 记录长度分别为 6464 和 996 字节，与 JSONL 实长相等。API reviewer 两次 `read_file` 均完成，终态 `completed`，`failure_code` 为 null，模型证据文本中的 15 字节、SHA-256 和十六进制均与磁盘一致。

唯一新增文件 `rc19-budget-check.txt` 实测十六进制 `524331395F4255444745545F4F4B0A`、15 字节、SHA-256 `37834105B665EDAB988C34A7F0AF0558AFC08741FAED0A73072285DCC9EE8F62`；README SHA-256 保持基线 `155E7BE658C8E007EA57791B162C5466ACC90E88C60D5B838A40951E7E33287D`，Git 状态仅显示该未跟踪新文件。运行前核对目标文件不存在、仓库干净且 HEAD 只含 README；Manifest 的前后快照记录 `beforeBytes: null`、`added_files: [rc19-budget-check.txt]`，可确认此 run 窗口新增。审查模型所说“文件已经存在”是在审查阶段观察 worker 写入后的状态，不推翻前后快照。试验 Host PID 3500 已停止，证据和文件保留。此结果证明 rc19 的官方 Host + CodeBuddy worker + API reviewer 双轨迹通过一次隔离非 D2 写入现场；不证明 API worker 可写、跨设备可用、稳定版发布或正式 D2 ExecuteGate。

### 2026-10-23：产品里程碑与 rc19 私有预览包

正式任务顺序见 `PRODUCT_MILESTONES_AND_NEXT_TASKS_2026-10-23.md`。M0 官方插件/终态抽屉本机隔离验收通过；M1 私有并行包尚需跨设备与回退门槛；M2 API inspector/reviewer 只读角色已各有本机现场；M3 API worker 写入未开放；M4 第二设备待用户可用；M5 稳定版和旧分支收敛须在回退证据后逐条处理；M6 实时流及 Memory/RAG 后置。

从固定功能源码 `5f43570` 与 rc.19 插件制作私有 ZIP `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc19-private-preview-kit-20261023-r2.zip`，SHA-256 `72F0F7CEE601D7E6A74171E382BA8D47D5181C30893C4A32D48687A083D7E9BC`，5 个条目逐项哈希与原件相符。r2 仅补充官方 Host 版本需人工核对的说明，功能产物未变，首版 ZIP 保留为历史候选。安装器与说明在候选源码的 `scripts/Install-ApiReviewerPreview.ps1`、`API_REVIEWER_PRIVATE_PREVIEW_README.md`；ZIP 仅含插件包、Runtime 源包、Manifest、安装器、说明。扫描包内及内层归档 232 个文件/条目，对本机两项 API key 字节命中 0。用户的连接文件仍只在包外，Profile 仅引用其路径。

全新隔离 Home 两次离线安装成功；最新版安装器在 `rc19-kit-install-check2-20261023` 安装 46 个依赖成功。首次全新 Home 的官方 `0.2.1-rc.2` CLI 配置解析退出 0、stderr 0；官方 Host 无模型首页 HTTP 200、stderr 0，测试进程已停止。重复安装在写入前拒绝，Profile 哈希未变；Home 内嵌 Runtime 目标在写入前拒绝且目标不存在。此处没有调用模型或触及旧日常 Home；包尚未在第二设备安装、未升日常默认、未推送或发布。D2 ExecuteGate 仍为 `NOT_CLAIMED`。
