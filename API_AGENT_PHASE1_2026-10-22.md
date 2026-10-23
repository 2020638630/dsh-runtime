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

硅基流动 [Chat Completions 官方文档](https://docs.siliconflow.cn/docs/api/chat-completions-post) 与 OpenRouter [Chat Completion 官方文档](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request) 都展示工具调用字段，但具体模型能力必须现场验证。免费模型配额和可用性会变化，不在配置中硬编码。
