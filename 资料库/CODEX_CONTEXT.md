# DSH Runtime --- CODEX_CONTEXT

> Status: Initial architecture baseline\
> Updated: 2026-09-04\
> Purpose: Provide Codex with the agreed project context, architectural
> constraints, Phase 1 scope, naming conventions, and implementation
> boundaries.

------------------------------------------------------------------------

## 1. 项目目标

构建一套 **Local-first、可长期演进的个人 Agent Runtime**。

系统最终目标不是单纯实现一个聊天机器人，也不是单纯实现一个 RAG
知识库，而是逐步构建一个拥有以下能力的个人工作站级 AI 系统：

-   长期个人知识与工作记忆
-   本地 / 云端模型可插拔
-   MCP / Tool / Plugin 能力统一接入
-   Agent 任务调度与执行
-   全局任务状态与工作空间管理
-   可观测、可熔断、可审计
-   可迁移到不同物理设备
-   随着长期使用逐渐形成用户的"工作分身"

长期部署目标可能是家庭中的独立工作站，例如 Mac
mini，通过受控方式向外提供 MCP / Agent 能力。

------------------------------------------------------------------------

## 2. 核心设计哲学

### 2.1 DSH 是系统中控

系统采用 **DSH 作为全局白盒控制器**。

DSH 不只是一个 Agent，而是整个 Agent Runtime 的控制平面。

核心原则：

> 所有大的业务循环必须由 DSH 控制。

下层组件、Tool、Plugin、Model、Retriever
等都不能自行无限发起新的业务循环。

DSH 负责：

-   任务解析
-   任务调度
-   子任务拆分
-   Agent / Plugin 调用
-   上下文切片
-   迭代判断
-   工作空间管理
-   全局状态
-   SLA 控制
-   超时控制
-   Token / 成本控制
-   最大循环次数控制
-   熔断
-   日志与观测
-   最终结果汇总

基本关系：

``` text
User
  ↓
DSH
  ↓
Plugin / Agent / Retriever / Model / Tool
  ↓
Result
  ↓
DSH
```

而不是：

``` text
Agent A
  ↓
Agent B
  ↓
Agent C
  ↓
Agent A
  ↓
...
```

任何下层 Agent 都不允许拥有系统级无限自治权。

------------------------------------------------------------------------

## 3. 一切皆插件

系统整体遵循：

> Everything is a Plugin.

但 Phase 1 不要为了扩展性提前构建复杂抽象体系。

尤其避免：

-   AbstractFactory 泛滥
-   多层 Interface
-   PluginFactory
-   ProviderFactory
-   ModelFactory
-   RetrieverFactory
-   ExecutorFactory

第一阶段优先建立一套清晰、能运行、容易修改的骨架。

抽象应从真实需求中自然产生，而不是为了假想中的未来扩展提前设计。

初期插件可以只是：

``` python
class Plugin:
    name: str

    async def execute(self, ctx, params):
        ...
```

之后真实出现多种实现时再继续抽象。

------------------------------------------------------------------------

## 4. 建议总体架构

``` text
┌──────────────────────────────┐
│             User             │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│          DSH Controller      │
│                              │
│ Task Planning                │
│ Dispatch                     │
│ Iteration Control            │
│ Context Management           │
│ Workspace Management         │
│ Budget / Timeout             │
│ Circuit Breaker              │
│ Observability                │
└──────────────┬───────────────┘
               │
        Plugin Runtime
               │
   ┌───────────┼───────────────┐
   ▼           ▼               ▼
 Agent      Retrieval         Tools
 Plugin      Plugin           Plugin
   │           │               │
   ▼           ▼               ▼
 LLM       Memory / KB         MCP
             │
      ┌──────┴───────┐
      ▼              ▼
   pgvector         BM25
      │
      ▼
 PostgreSQL
```

未来还可以继续增加：

``` text
ModelPlugin
RerankerPlugin
MemoryPlugin
MCPPlugin
FilesystemPlugin
ShellPlugin
BrowserPlugin
CodePlugin
OllamaPlugin
OpenAIPlugin
CodexPlugin
```

但 Phase 1 不需要全部实现。

------------------------------------------------------------------------

## 5. 当前已有本地基础设施

现有开发环境：

``` text
Windows 10
│
├── Ollama
│   └── :11434
│
└── WSL2
    └── Ubuntu 22.04
        │
        └── FastAPI
            └── :8800
```

已有项目结构大致：

``` text
api/
core/
    embeddings
    llm
    reranker
    config

services/
    chat
    knowledge
    retrieval

retrievers/
    bm25
    hybrid

schemas/
    pydantic models
```

已有 / 计划中的数据组件：

``` text
Obsidian
   ↓
Knowledge ingestion
   ↓
PostgreSQL
   ↓
pgvector
```

Retrieval：

``` text
BM25
+
Vector Search
+
Hybrid Retrieval
```

当前本地模型：

``` text
Generation:
qwen2.5:7b

Embedding:
nomic-embed-text
```

模型由 Ollama 提供。

------------------------------------------------------------------------

## 6. Ollama 的定位

经过讨论后形成的重要结论：

> Ollama 不是 Phase 1 的必要组件。

早期曾考虑让 Ollama 作为第一层 Defense / Compression Layer，例如：

``` text
Raw Context
     ↓
Local Ollama
     ↓
定向摘要
     ↓
摘要 + 原始数据 Pointer
     ↓
Cloud / Strong Agent
```

目标包括：

-   大文本搬运
-   信息压缩
-   隐私过滤
-   Context Reduction
-   低价值文本预处理

但存在明显风险：

``` text
qwen2.5 7B
+
消费级硬件
+
大量上下文
=
潜在高延迟
```

如果所有请求都必须经过 Ollama，会导致整个 Agent Runtime
的吞吐量被最慢模型锁死。

所以 Phase 1：

``` text
DSH
   ↓
Cloud / Codex / Strong Model
```

可以直接运行。

Ollama 后续作为可选 Plugin 接入：

``` text
LocalLLMPlugin
```

只有特定任务才路由过去，例如：

``` text
private data
cheap summarization
offline task
embedding
background preprocessing
```

因此必须避免：

``` text
DSH → Ollama → Everything
```

推荐：

``` text
              ┌→ Ollama
DSH → Router ─┼→ Cloud LLM
              ├→ Codex
              └→ Other Models
```

------------------------------------------------------------------------

## 7. 记忆系统

系统长期目标不是保存无限 Chat History，而是构建真正的 Memory Layer。

Memory 与 Knowledge Base 必须区分。

### Knowledge

相对稳定：

``` text
文档
笔记
代码
Obsidian
技术资料
项目资料
```

### Memory

来自 Agent 的长期经历：

``` text
用户偏好
架构决策
项目历史
踩坑经验
工作习惯
任务结果
重要上下文
```

未来建议逻辑：

``` text
Conversation
     ↓
Memory Candidate
     ↓
Memory Extraction
     ↓
Memory Store
     ↓
Retrieval
```

不要简单：

``` text
Conversation
     ↓
Vector DB
```

------------------------------------------------------------------------

## 8. Memory 数据设计的重要原则

必须区分：

``` text
Semantic Content
```

和：

``` text
Runtime Metadata
```

错误做法：

``` json
{
  "memory": "项目位于 C:/Users/xxx/project"
}
```

这种内容在换设备后会污染长期记忆。

应该保存逻辑关系：

``` json
{
  "entity": "dsh-runtime",
  "type": "project",
  "workspace": "dsh.main"
}
```

物理环境映射：

``` text
workspace dsh.main
    ↓
Environment Registry
    ↓
/home/<user>/...
```

换设备后只更新 Environment Registry，而不是重新修改所有 Memory。

------------------------------------------------------------------------

## 9. Memory 可迁移原则

长期记忆绝不能绑定：

``` text
Windows path
WSL path
Mac path
IP address
port
hostname
device name
```

Memory 保存：

``` text
logical identity
semantic relationship
project identity
decision
experience
```

Environment 保存：

``` text
physical location
path
endpoint
machine
runtime
```

因此设备迁移：

``` text
Memory 不变
Environment Mapping 改变
```

------------------------------------------------------------------------

## 10. RAG 的定位

RAG 并没有"过时"。

RAG 是：

> External Knowledge Retrieval Mechanism.

Agent Memory / LLM Wiki / Knowledge Graph / Context Engineering 并不是
RAG 的完全替代品。

未来系统可能是：

``` text
                Context Builder
                     │
       ┌─────────────┼──────────────┐
       ▼             ▼              ▼
     RAG          Memory        Workspace
       │             │              │
 Vector/BM25     Experience       Current
       │          History          Task
       └─────────────┬──────────────┘
                     ▼
                    LLM
```

RAG 是整个 Context System 的一个组件，不是整个 Agent 系统。

------------------------------------------------------------------------

## 11. Workspace

DSH 应维护公共任务工作空间。

例如：

``` text
workspace/
    task.json
    state.json
    context/
    outputs/
    artifacts/
    logs/
```

所有下层 Plugin：

``` text
读取 DSH 提供的数据
执行
写入 Result
返回 DSH
```

不要允许下层组件任意控制其他组件。

推荐任务状态：

``` python
class TaskState:
    task_id
    goal
    status
    iteration
    max_iterations
    created_at
    deadline
    budget
    context
    artifacts
    errors
```

------------------------------------------------------------------------

## 12. Plugin Runtime

Phase 1 可以非常简单：

``` python
class Plugin(Protocol):

    name: str

    async def execute(
        self,
        ctx: ExecutionContext,
        params: dict
    ) -> PluginResult:
        ...
```

Registry：

``` python
class PluginRegistry:

    plugins: dict[str, Plugin]

    def register(self, plugin):
        self.plugins[plugin.name] = plugin

    def get(self, name):
        return self.plugins[name]
```

DSH：

``` python
result = await registry.get(plugin_name).execute(
    context,
    params
)
```

暂时不要复杂化。

------------------------------------------------------------------------

## 13. DSH 主循环

建议 Phase 1 实现显式 Runtime Loop。

伪代码：

``` python
while not task.finished:

    if task.iteration >= task.max_iterations:
        break

    if task.timeout():
        break

    if task.over_budget():
        break

    decision = await planner.next_action(task)

    result = await plugin_runtime.execute(
        decision.plugin,
        decision.params
    )

    task.apply(result)

    observer.record(
        decision,
        result
    )

    task.iteration += 1
```

核心原则：

> Loop 在代码中，而不是藏在 LLM Prompt 中。

LLM 可以决定：

``` text
下一步做什么
```

但是 Runtime 决定：

``` text
是否允许继续
```

------------------------------------------------------------------------

## 14. Defense Layer

长期可以设计两级防御：

``` text
Layer 1
Local Processing

Layer 2
DSH Governance
```

例如：

``` text
Input
 ↓
Local Sanitizer / Compressor
 ↓
DSH
 ↓
Agent
```

但 Phase 1 不强制 Local LLM。

Defense 可以首先只是 deterministic code：

``` text
size limit
file whitelist
permission
secret masking
token limit
timeout
```

比强制依赖本地 LLM 更稳定。

------------------------------------------------------------------------

## 15. Observability

从第一阶段开始至少保存：

``` text
task_id
plugin
start_time
end_time
duration
status
input_size
output_size
iteration
error
```

未来增加：

``` text
token
cost
model
retrieval score
tool calls
retry
cache hit
```

不要第一阶段搭 Prometheus / Grafana。

先结构化日志即可。

例如：

``` json
{
  "task_id": "...",
  "iteration": 2,
  "plugin": "retrieval",
  "duration_ms": 328,
  "status": "success"
}
```

------------------------------------------------------------------------

## 16. Phase 1 范围

当前 Phase 1 的目标：

> 搭出 Agent Runtime 骨架。

不是：

> 搭完整 AI OS。

建议只实现：

``` text
DSH
Plugin Registry
Plugin Runtime
Task State
Workspace
Simple Planner
Simple Observability
Circuit Breaker
```

初始 Plugin：

``` text
EchoPlugin
FilePlugin
LLMPlugin
RetrievalPlugin
```

甚至 Retrieval 都可以第二步再接。

------------------------------------------------------------------------

## 17. Phase 1 暂时不要做

不要立即实现：

``` text
Multi-Agent swarm
Agent-to-Agent autonomous loops
Complex workflow DSL
Plugin Marketplace
Dynamic hot loading
Abstract factories
Distributed runtime
Kafka
Kubernetes
Graph database
Complex Memory Reflection
Automatic Skill evolution
Advanced model router
Full permission engine
```

它们都可以未来演进。

------------------------------------------------------------------------

## 18. 第一阶段建议目录

``` text
app/
├── api/
│   └── routes/
│
├── dsh/
│   ├── controller.py
│   ├── planner.py
│   ├── state.py
│   ├── breaker.py
│   └── context.py
│
├── runtime/
│   ├── plugin.py
│   ├── registry.py
│   ├── executor.py
│   └── result.py
│
├── plugins/
│   ├── echo.py
│   ├── llm.py
│   ├── retrieval.py
│   └── filesystem.py
│
├── workspace/
│   ├── manager.py
│   └── models.py
│
├── observability/
│   └── logger.py
│
├── memory/
│   └── ...
│
├── knowledge/
│   └── ...
│
└── schemas/
```

不要将现有项目全部推翻。

Codex 应优先检查现有结构：

``` text
api/
core/
services/
retrievers/
schemas/
```

然后以最小侵入方式重构或增加：

``` text
dsh/
runtime/
plugins/
workspace/
```

------------------------------------------------------------------------

## 19. 实施原则

Codex 在修改项目时必须遵守：

### 规则 1

先阅读现有代码，不允许根据本文直接重写整个项目。

### 规则 2

优先复用现有：

``` text
core
services
retrievers
schemas
```

### 规则 3

每次提交只解决一个小目标。

### 规则 4

不要进行 speculative abstraction。

没有第二种真实实现时，不创建 Factory。

### 规则 5

Runtime 控制循环。

LLM 不拥有无限循环权。

### 规则 6

所有 Plugin 有明确：

``` text
input
output
timeout
error boundary
```

### 规则 7

Memory 不直接保存机器相关信息。

### 规则 8

任何物理路径必须通过 Environment / Workspace Mapping 解析。

------------------------------------------------------------------------

## 20. Codex 第一阶段任务

首先不要写大量业务代码。

第一轮任务：

1.  阅读当前 Repository。
2.  输出当前项目真实架构。
3.  找出：
    -   可以保留的模块
    -   可以复用的模块
    -   与新 DSH Runtime 重叠的模块
    -   强耦合点
4.  提议最小改造方案。
5.  生成目标目录。
6.  实现最小 Plugin Protocol。
7.  实现 PluginRegistry。
8.  实现 TaskState。
9.  实现最小 DSH Controller。
10. 使用 EchoPlugin 跑通完整生命周期。

目标链路：

``` text
HTTP Request
    ↓
DSH
    ↓
PluginRegistry
    ↓
EchoPlugin
    ↓
PluginResult
    ↓
DSH
    ↓
HTTP Response
```

只有这条链路稳定后再继续增加：

``` text
LLMPlugin
RetrievalPlugin
MemoryPlugin
```

------------------------------------------------------------------------

## 21. 第一个验收标准

运行：

``` text
POST /agent/tasks
```

输入：

``` json
{
  "goal": "hello agent"
}
```

Runtime：

``` text
create task
↓
DSH starts
↓
planner selects echo
↓
plugin execute
↓
result recorded
↓
task completed
```

输出：

``` json
{
  "task_id": "...",
  "status": "completed",
  "iterations": 1,
  "result": "hello agent"
}
```

同时产生结构化日志。

这是 Phase 1 第一个真正完成的 milestone。

------------------------------------------------------------------------

## 22. Codex 工作方式

开始编码前，请先输出：

``` text
CURRENT_ARCHITECTURE.md
```

说明真实 Repository 当前结构。

然后输出：

``` text
MIGRATION_PLAN.md
```

说明如何从当前结构演进到 DSH Runtime。

不要一次性实施所有功能。

首先只完成：

``` text
Milestone 0:
Repository Analysis

Milestone 1:
DSH Runtime Skeleton

Milestone 2:
LLM Plugin

Milestone 3:
Retrieval Plugin

Milestone 4:
Persistent Task State

Milestone 5:
Memory Layer
```

每个 Milestone 完成后都应保证系统仍可运行。

------------------------------------------------------------------------

## 23. 最重要的架构约束

如果后续实现与以下原则冲突，应优先遵守这些原则：

``` text
DSH owns the loop.

Everything below DSH is bounded.

Everything is replaceable.

Memory stores semantics, not environment.

Local LLM is optional.

Plugins grow from real requirements.

Do not abstract before evidence.

Build the skeleton first.
```

当前最高优先级：

> 先让最小 DSH Runtime 真正跑起来，再逐步往骨架上添肉。

------------------------------------------------------------------------

## 24. Project Naming & Workspace Convention

当前项目正式工程名称：

``` text
DSH Runtime
```

统一命名：

``` text
Project Name:
DSH Runtime

Repository:
dsh-runtime

Python Package:
dsh_runtime

Logical Workspace ID:
dsh.main
```

### 24.1 Source Code 与 Runtime Data 分离

源码仓库和 Agent 运行数据必须分离。

推荐结构：

``` text
~/workspace/
└── dsh-runtime/
    ├── app/
    ├── tests/
    ├── docs/
    ├── pyproject.toml
    └── ...

~/agent-data/
├── workspaces/
│   └── dsh.main/
│       ├── state/
│       ├── context/
│       ├── artifacts/
│       └── logs/
├── memory/
├── knowledge/
├── cache/
└── config/
```

其中：

``` text
~/workspace/dsh-runtime
```

属于 Git Repository。

``` text
~/agent-data
```

属于 Runtime Data Root，不应直接作为源码仓库的一部分。

### 24.2 禁止使用物理路径作为 Workspace Identity

Workspace 的逻辑身份：

``` text
dsh.main
```

物理路径仅作为 Runtime Mapping。

禁止将：

``` text
C:\Users\...
/home/...
/Users/...
```

作为 Workspace ID 或长期 Memory 中的实体身份。

正确方式：

``` text
workspace://dsh.main
```

通过 WorkspaceResolver / Environment Mapping 在运行时解析实际路径。

例如：

``` yaml
workspaces:
  dsh.main:
    root: "${DSH_WORKSPACE_ROOT}/dsh.main"
```

不同设备只需要修改环境配置。

例如当前开发环境：

``` text
DSH_DATA_ROOT=~/agent-data
DSH_WORKSPACE_ROOT=~/agent-data/workspaces
```

未来迁移设备时：

``` text
Memory / Knowledge / Task semantics
            ↓
          不改变

Environment / Physical Path Mapping
            ↓
          改变
```

### 24.3 Logical Resource URI

系统内部应逐步优先使用 Logical Resource URI，而不是传播裸物理路径。

建议 URI Scheme：

``` text
workspace://
memory://
knowledge://
artifact://
```

示例：

``` text
workspace://dsh.main/docs/ARCHITECTURE.md

memory://projects/dsh-runtime

knowledge://java/spring

artifact://task-20260904-001/result.json
```

注意：

Phase 1 不要求一次性实现完整 URI Framework。

第一阶段只需要确保核心数据模型不会把物理路径当成逻辑身份。

当实际出现 WorkspaceResolver 的需求时，再实现最小 Resolver。

不要因此提前设计复杂的 Virtual Filesystem、Storage Provider Factory 或
Resource Abstraction Framework。

------------------------------------------------------------------------

## 25. Current Engineering Identity

从现在开始，讨论中以下名称具有明确含义：

``` text
DSH Runtime
```

表示整个个人 Agent Runtime 系统。

``` text
DSH
```

表示 Runtime 中负责全局任务调度、循环控制、治理和观测的核心 Controller。

``` text
dsh-runtime
```

表示当前 Git Repository。

``` text
dsh.main
```

表示当前系统自身的 Logical Workspace。

``` text
~/workspace/dsh-runtime
```

表示推荐的源码物理位置，但它不是系统身份的一部分。

``` text
~/agent-data
```

表示推荐的 Runtime Data Root，同样属于可迁移的 Environment
Configuration。

未来如果个人 Assistant 获得独立产品名称，该名称属于 DSH Runtime 之上的
Assistant / Persona Layer，不改变底层 Runtime 的工程名称。

------------------------------------------------------------------------

## 26. 当前决策摘要

截至本基线版本，已经确定：

1.  DSH 是全局白盒中控，拥有系统级业务循环控制权。
2.  下层 Agent / Plugin / Tool 不拥有无限业务循环权。
3.  "一切皆插件"是演进方向，但 Phase 1 不做过度抽象。
4.  Ollama / Local LLM 不是 Phase 1 的硬依赖。
5.  现有 RAG、BM25、pgvector、Obsidian 等能力应尽量复用，不因引入 DSH
    而推翻。
6.  Memory 与 Knowledge 必须区分。
7.  Memory 保存语义，不保存机器环境身份。
8.  物理路径通过 Environment / Workspace Mapping 解析。
9.  源码与 Runtime Data 分离。
10. 第一目标不是完整 AI OS，而是跑通最小 DSH Runtime 生命周期。
11. Codex 必须先完成 Milestone 0 Repository Analysis，再进入代码修改。
12. 所有后续架构设计优先服从"最小可运行骨架 + 从真实需求演进"的原则。

------------------------------------------------------------------------

## 27. Milestone Gate

Codex 不应默认连续执行所有 Milestone。

推荐流程：

``` text
CODEX_CONTEXT.md
       ↓
Codex 阅读真实 Repository
       ↓
Milestone 0 — Repository Analysis
       ↓
CURRENT_ARCHITECTURE.md
MIGRATION_PLAN.md
       ↓
Human Review
       ↓
Milestone 0 approved
       ↓
Milestone 1 — DSH Runtime Skeleton
```

Milestone 0 未经确认，不进入 Milestone 1。

------------------------------------------------------------------------

## 28. Codex Provider 使用边界与认证策略

Codex 在 DSH Runtime 中的定位是：

> **Codex is an optional bounded execution provider, not the default
> compute backend.**

Codex 应作为高价值 Coding Agent Plugin
使用，而不是所有任务的默认执行引擎。

适合路由给 Codex 的任务包括：

``` text
Repository Analysis
Architecture Refactor
复杂 Debug
Code Review
跨文件修改
测试失败定位
Milestone Implementation
```

不应默认消耗 Codex 的任务包括：

``` text
简单文件读取
格式转换
普通摘要
Memory Extraction
Embedding
简单分类
常规 Retrieval
低价值后台任务
```

推荐关系：

``` text
                    DSH
                     │
               Agent / Model Router
                     │
       ┌─────────────┼──────────────┐
       │             │              │
       ▼             ▼              ▼
   DeepSeek        Codex         Local LLM
   Provider        Plugin         Ollama
```

### 28.1 Official Integration Only

DSH 调用 Codex 时必须优先使用 Codex 官方支持的集成面，例如官方 Codex
CLI、SDK、`exec`、`app-server` 或后续官方提供的等价接口。

DSH 不得：

``` text
绕过 Codex authentication
绕过 sandbox / permission controls
绕过 rate limits
绕过 usage limits
绕过 safety controls
模拟或逆向私有接口
抓取或复制 ChatGPT / Codex 登录态
自行管理 ChatGPT OAuth token
```

Codex 的认证、sandbox、model configuration 和权限控制应尽量继续由官方
Codex Runtime 管理。

推荐边界：

``` text
DSH
 │
 │ bounded execution request
 ▼
CodexPlugin
 │
 ▼
Official Codex Runtime
 │
 ├── authentication
 ├── sandbox
 ├── model
 ├── permissions
 └── usage controls
```

### 28.2 Personal 与 Automation Profile 分离

设计上区分两种 Codex Execution Profile。

#### codex.personal

用于开发者人在环的日常开发与交互式工作。

``` yaml
profile: codex.personal
provider: codex
auth: native-chatgpt
purpose: interactive-development
automation: limited
```

该 Profile 主要用于：

``` text
人工发起
交互式开发
Repository 探索
代码讨论
短期受控任务
```

不得默认作为 DSH 长期无人值守执行入口。

#### codex.automation

用于未来 DSH 的正式自动化执行。

``` yaml
profile: codex.automation
provider: codex
auth: developer-api
purpose: automated-agent
budget: controlled
timeout: controlled
concurrency: controlled
```

该 Profile 应具备明确：

``` text
budget
timeout
concurrency
max iterations
usage accounting
error boundary
circuit breaker
```

长期或无人值守的 DSH Automation 应优先使用 developer / API
authentication，而不是依赖个人 ChatGPT 登录态。

### 28.3 Credential Ownership

DSH 不拥有 Codex Credential。

原则：

> Authentication belongs to the provider runtime, not to DSH memory.

禁止把以下内容写入：

``` text
Memory Store
Knowledge Base
Task State
Workspace Artifact
普通日志
```

例如：

``` text
ChatGPT OAuth Token
OpenAI API Key
Codex Session Credential
Refresh Token
```

DSH 只允许引用逻辑认证 Profile：

``` text
codex.personal
codex.automation
```

真正 Credential 应由环境变量、系统 Secret Store、官方 Codex
配置或未来专门的 Secret Provider 管理。

### 28.4 Usage Governance

Codex 调用必须服从 DSH 的全局治理。

任何 Codex Task 至少应受以下边界控制：

``` text
timeout
max iterations
concurrency
budget / usage quota
workspace permission
result size
error boundary
```

未来可以形成：

``` text
DSH Task
   ↓
Router
   ↓
Policy Check
   ↓
Execution Profile
   ↓
CodexPlugin
   ↓
Official Codex Runtime
```

DSH 不应为了提高吞吐量而主动规避 Codex
的服务端限制，也不应通过多账户、并发放大或 Credential Rotation 绕过
Usage Limit。

### 28.5 Phase 1 实施范围

本节首先作为 **治理约束** 存在。

Phase 1 不需要立即实现：

``` text
复杂 Provider Router
完整 Credential Manager
多账户调度
动态 Cost Optimizer
复杂 Quota Engine
```

Phase 1 只需确保：

1.  `CodexPlugin` 被视为可选、可替换、受限的执行 Provider。
2.  DSH 不直接持有或持久化 Codex 登录凭据。
3.  Codex 调用有 timeout 和 error boundary。
4.  不将 Codex 作为所有任务的默认 Backend。
5.  为未来 `codex.personal` / `codex.automation` Profile
    分离保留简单配置入口。
6.  不为了未来 Profile 系统提前建立复杂 Factory / Provider Framework。

### 28.6 当前策略

当前开发阶段允许：

``` text
Human
  ↓
DSH
  ↓
codex.personal
  ↓
Official Codex Runtime
```

用于本地、人在环、受控的开发实验。

未来进入长期后台运行、定时任务、大规模并发或无人值守执行前，应切换到：

``` text
DSH
  ↓
codex.automation
  ↓
Developer / API Authentication
```

并重新核对当时最新的 OpenAI Codex 文档、套餐限制与适用服务条款。

------------------------------------------------------------------------

# End of Architecture Baseline

This document is the initial architectural baseline for DSH Runtime.

When actual repository code conflicts with assumptions in this document:

1.  Do not silently rewrite the repository to match the document.
2.  Report the discrepancy.
3.  Distinguish current reality from target architecture.
4.  Propose the smallest migration path.
5.  Wait for confirmation before performing structural changes.
