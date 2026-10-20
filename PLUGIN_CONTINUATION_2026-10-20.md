# 官方 Harness 插件抽离续接单

更新：2026-10-20。候选工作树：`D:\DeepSeekHarness\vis-runtime-candidate`，分支 `codex/vis-manifest-mvp-20261016`；截至 `69d72cc` 相对远端领先 11 个本地提交，尚未推送。本文件只记录独立候选与探针，不改变两个原工作树。D2 ExecuteGate 仍为 `NOT_CLAIMED`。

## 已完成与证据

1. 未修改的公开 `@deepseek-ai/dsh@0.2.1-rc.2`：外部 Host/Web 探针可安装，真实浏览器执行 client，鉴权 Host 路由 200，卸载后路由 404、首页可用。独立消费者在 `D:\DeepSeekHarness\vis-stable-release-artifacts\official-plugin-probe-20261020`；探针服务已停止、插件已卸载。
2. 专属 Host 工具探针 `tests/fixtures/official_harness_tool_probe`：官方 Host 可注册明确 `task_kind` 和两个固定用途 provider；无 Agent、非法类型、预取消均拒绝。0.0.3 探针已卸载，Profile 回到基线。
3. `integrations/deepseek-harness`：治理协议、会话 pin、FIFO worker、双 provider、Runtime one-shot transport/终态证据和工具已迁出私有 Harness 核心并针对公开包通过类型检查。治理只在明确允许后调用启动函数；双 provider 在自身 `start()` 守门，直接启动也不能绕过。Runtime 工作区来自父 Session cwd。
4. 验证：`pnpm typecheck`；`pnpm test:admission` 6/6；`pnpm test:worker` 3/3（真实 Python worker，独立临时审计，ALLOW/DENY、审计失败、超时）；`pnpm test:provider` 3/3；`pnpm test:launcher` 2/2；`pnpm test:host-core` 1/1；`pnpm test:tool` 2/2。Node 在受限沙箱中启动 Python 曾返回 `spawn EPERM`，对 `pnpm test:worker` 做窄范围外层运行后通过。没有模型调用或真实 Runtime 任务。

## 未完成与下次顺序

1. 将独立库构建为可安装 Host bundle，加入 Profile 配置校验、治理策略/证据路径校验与完整卸载；在官方公开发行包的独立 Home 中安装，不使用私有 Harness 构建产物作为宿主。
2. 在官方 Host 真实会话中验证 `exec.agent`、父 Session cwd、取消信号、策略 pin 与两种固定 provider。先做无模型拒绝与只读任务；真实模型调用/写入只在临时 Git 仓库和非 D2 配置中执行。
3. 接入认证 Evidence Manifest 路由并迁移 Web 抽屉；做读、写、失败、取消、证据缺失、卸载回退及旧 Home 副本验收。完成这些后才评估移除私有 Harness 分支的日常用途，归档/删除旧分支另审。

## 保护事项

原 Runtime `D:\PythonProject\dsh-runtime` 与原 Harness `D:\DeepSeekHarness\deepseek-harness` 均有用户未提交改动和未跟踪文件，禁止清理、重置、覆盖。独立候选提交不等于远端已推送。ZCode 的密钥文件不读、不复制、不提交。正式 D2 ExecuteGate 继续 `NOT_CLAIMED`。
