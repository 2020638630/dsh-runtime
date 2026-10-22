# 模型 API Agent 第一阶段交接（2026-10-22）

## 当前状态

独立候选工作树：`D:\DeepSeekHarness\vis-api-agent-candidate-20261022`，从 Runtime `c179435` 新建。两个原工作树的未提交改动和未跟踪文件均保留。正式 D2 ExecuteGate 继续 `NOT_CLAIMED`。

本阶段只实现**无网络契约探针**。这些模块尚未注册进 `build_controller()`，不改变官方 Harness 插件、现有 CLI Profile 或日常入口；不声称已支持真实模型调用。

- `api_agent_contract.py`：显式 schema v2，三角色可独立选 `api_agent` 或既有 CLI，API 角色要求供应商、模型、连接引用和每阶段请求/工具/token 上限；拒绝明文 key 和未知字段。
- `api_agent_connections.py`：只从仓库外本机 JSON 文件读取 key，供应商与端点须精确匹配；异常和对象表示不输出 key。连接文件样例放在 `D:\DeepSeekHarness\api-agent-local-config\connections.example.json`。
- `api_agent_loop.py`：模型传输和工具执行均注入；整批工具调用先校验再执行；只读角色不能获得写工具；记录请求模型与响应观测模型，禁止自动重试和整个任务重放。响应不提供 token 用量时失败关闭，后续要核验供应商是否稳定提供此数据。
- `api_agent_read_tools.py`：有界列目录、读 UTF-8 文件、文字搜索；排除已知敏感路径，拒绝相对逃逸和链接路径。仍属技术探针，尚未完成 Windows junction 和文件并发替换的真实现场验收。

`apply_patch` 只出现在循环的预留工具名中，尚无写工具实现；现有只读 Broker 会拒绝它。

## 无模型验证

`python -m pytest -q`：549 passed、1 skipped（当前 Windows 权限下无法创建测试符号链接）。混合 CLI/API 配置、受限只读工具与原 v1 配置的聚焦测试 `29 passed、1 skipped`。所有测试不调用模型、不读取真实凭据。

## 下一步优先级

1. **P0：只读边界**。在全新隔离 Git 仓库验收路径逃逸、Windows junction、敏感文件、并发替换；明确工具事件如何进入 Safe Trace 和 Manifest。
2. **P0：供应商传输**。为 OpenRouter 与硅基流动分别实现受限 Chat Completions 适配，单请求禁 SDK 隐式重试；核验工具调用、token 用量、响应模型 ID、取消与错误分类。先用假 HTTP 响应测试，只有全部通过后才加载用户本机 key。
3. **P0：写工具**。设计带预期哈希的文件补丁、冲突拒绝和受控原子写；工作区前后快照仍由 Runtime 外层结算。无模型验收过门槛才向 worker 暴露。
4. **P1：集成与真实试用**。schema v2 与现有 v1 并行；在独立 Home、独立仓库中先做只读 inspector，再做 worker+独立 reviewer。观测模型不明时标记未知，不能冒称请求模型即实际模型。
5. **跨环境验收**：第二台设备目前不可用，按用户安排推迟到今晚；不作为本机无模型开发阻塞项。

硅基流动 [Chat Completions 官方文档](https://docs.siliconflow.cn/docs/api/chat-completions-post) 与 OpenRouter [Chat Completion 官方文档](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request) 都展示工具调用字段，但具体模型能力必须现场验证。免费模型配额和可用性会变化，不在配置中硬编码。
