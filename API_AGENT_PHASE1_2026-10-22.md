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

**异步回执**：`dsh_runtime` 启动只返回子代理 ID，启动参数固定 `delivery: parent`。新增无模型工具契约测试核对可信父 Agent、固定 inspection provider、`delivery: parent`、工具说明中“等待子任务状态更新 / ID 非后台 job”及仅有启动回执的渲染；`pnpm test:tool` 为 3/3。此测试证明接线与文字契约，不证明父模型已经学会等待；rc16 尚未安装，不能声称现场行为修复。下一步在全新隔离 Home 做 rc16 无模型安装与激活，对照不覆盖 rc15；模型现场仅在有明确诊断需要时再安排。API reviewer/worker 均未开放，D2 ExecuteGate 继续 `NOT_CLAIMED`。
