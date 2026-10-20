# 官方 Harness 插件抽离续接单

更新：2026-10-20。候选工作树：`D:\DeepSeekHarness\vis-runtime-candidate`，分支 `codex/vis-manifest-mvp-20261016`；本文件只记录独立候选与探针，不改变两个原工作树。以实时 `git status` 为准，候选提交尚未推送。D2 ExecuteGate 仍为 `NOT_CLAIMED`。

## 已完成与证据

1. 未修改的公开 `@deepseek-ai/dsh@0.2.1-rc.2`：外部 Host/Web 探针可安装，真实浏览器执行 client，鉴权 Host 路由 200，卸载后路由 404、首页可用。独立消费者在 `D:\DeepSeekHarness\vis-stable-release-artifacts\official-plugin-probe-20261020`；探针服务已停止、插件已卸载。
2. 专属 Host 工具探针 `tests/fixtures/official_harness_tool_probe` 和新验收探针 `tests/fixtures/official_runtime_status_probe`：官方 Host 可注册明确 `task_kind` 和两个固定用途 provider；无 Agent、非法类型、预取消均拒绝。新探针仅用于独立 Profile，固定临时工作区路径由配置给出。
3. `integrations/deepseek-harness`：治理协议、Host 自管持久策略 pin、FIFO worker、双 provider、Runtime one-shot transport/终态证据、工具和认证 Manifest 路由已从私有 Harness 核心抽离，公开包未修改。治理只在明确允许后调用启动函数；双 provider 在自身 `start()` 守门，直接启动也不能绕过。Runtime 工作区来自父 Session cwd。
4. 测试：`pnpm typecheck`；`pnpm build`；`pnpm test:entry` 2/2；`pnpm test:pin-store` 2/2；`pnpm test:worker` 3/3（真实 Python worker、独立临时审计）；`pnpm test:host-core` 1/1。更早的 admission 6/6、provider 3/3、launcher 2/2、tool 2/2 也已通过。受限沙箱启动 Python 曾返回 Windows `spawn EPERM`，窄范围外层运行后通过。
5. 官方 Host 无模型状态探针通过；第二个全新临时 Git 仓库的真实 `repository_inspection` 子任务已完成。会话 `session-2f1adbf9-1443-49be-8df7-0fc0fbde2371`，子任务 `99bd74e5-9913-45d5-800e-f19420a15ae1`，Manifest `completed`，审计为 `ALLOW`，无文件变动，Git 干净。认证证据接口：所属会话 200、未登录 401、错误参数 400、其他会话 404。官方 Host 重启后所属会话仍为 200，pin 文件仍在、Host stderr 为空。验收消费者路径：`D:\DeepSeekHarness\vis-stable-release-artifacts\official-plugin-probe-20261020`，独立 Profile 为 `home\profiles\runtime-official`。本次真实调用仅为只读、非 D2。
6. 首次真实只读样本揭示兼容失败：旧的私有 `subagent/governance-policy-pin` 必需事件使官方 Host 重启后拒绝读取该测试 Session，证据接口 500。该独立 Home 样本保留。现改用 `pinRoot` 下插件自管文件，在治理预启动评价前持久化，不向官方 Session 事件表写私有类型；第二次新会话及重启验收通过。已经带私有事件的会话仍需在副本上研究迁移，不能声称旧 Home 可直接切换。

## 未完成与下次顺序

1. 当前私有可安装包为 `@dsh-runtime/harness-plugin@0.1.0-rc.2`；`runtime-official` 仅启用 `repository_inspection`，不作日常入口。真实官方 Host 曾以独立 Profile 启动，接受模型调用并在重启后读回 Manifest。`repository_change` 仍应被治理拒绝，尚需专门验收。
2. 迁移 Web 证据抽屉为外部 Web bundle，并在真实官方界面验收状态、实际变动、审计三个页签。随后做临时仓库写入、真实失败、取消、证据缺失、卸载回退与旧 Home 副本迁移。旧事件失败样本与新样本应分开核验。
3. 完成上述门槛后评估官方应用并行日常入口，最后再考虑简化私有 Harness 分支。不得因本次只读成功就删除或覆盖私有分支及旧 Home；归档、删除另审。

## 保护事项

原 Runtime `D:\PythonProject\dsh-runtime` 与原 Harness `D:\DeepSeekHarness\deepseek-harness` 均有用户未提交改动和未跟踪文件，禁止清理、重置、覆盖。独立候选提交不等于远端已推送。ZCode 的密钥文件不读、不复制、不提交。正式 D2 ExecuteGate 继续 `NOT_CLAIMED`。
