# 官方 Harness 插件抽离续接单

更新：2026-10-21。候选工作树：`D:\DeepSeekHarness\vis-runtime-candidate`，分支 `codex/vis-manifest-mvp-20261016`；本文件只记录独立候选与探针，不改变两个原工作树。以实时 `git status` 为准，候选提交尚未推送。D2 ExecuteGate 仍为 `NOT_CLAIMED`。

## 已完成与证据

1. 未修改的公开 `@deepseek-ai/dsh@0.2.1-rc.2`：外部 Host/Web 探针可安装，真实浏览器执行 client，鉴权 Host 路由 200，卸载后路由 404、首页可用。独立消费者在 `D:\DeepSeekHarness\vis-stable-release-artifacts\official-plugin-probe-20261020`；探针服务已停止、插件已卸载。
2. 专属 Host 工具探针 `tests/fixtures/official_harness_tool_probe` 和新验收探针 `tests/fixtures/official_runtime_status_probe`：官方 Host 可注册明确 `task_kind` 和两个固定用途 provider；无 Agent、非法类型、预取消均拒绝。新探针仅用于独立 Profile，固定临时工作区路径由配置给出。
3. `integrations/deepseek-harness`：治理协议、Host 自管持久策略 pin、FIFO worker、双 provider、Runtime one-shot transport/终态证据、工具和认证 Manifest 路由已从私有 Harness 核心抽离，公开包未修改。治理只在明确允许后调用启动函数；双 provider 在自身 `start()` 守门，直接启动也不能绕过。Runtime 工作区来自父 Session cwd。
4. 测试：`pnpm typecheck`；`pnpm build`；`pnpm test:entry` 2/2；`pnpm test:pin-store` 2/2；`pnpm test:worker` 3/3（真实 Python worker、独立临时审计）；`pnpm test:host-core` 1/1。更早的 admission 6/6、provider 3/3、launcher 2/2、tool 2/2 也已通过。受限沙箱启动 Python 曾返回 Windows `spawn EPERM`，窄范围外层运行后通过。
5. 官方 Host 无模型状态探针通过；第二个全新临时 Git 仓库的真实 `repository_inspection` 子任务已完成。会话 `session-2f1adbf9-1443-49be-8df7-0fc0fbde2371`，子任务 `99bd74e5-9913-45d5-800e-f19420a15ae1`，Manifest `completed`，审计为 `ALLOW`，无文件变动，Git 干净。认证证据接口：所属会话 200、未登录 401、错误参数 400、其他会话 404。官方 Host 重启后所属会话仍为 200，pin 文件仍在、Host stderr 为空。验收消费者路径：`D:\DeepSeekHarness\vis-stable-release-artifacts\official-plugin-probe-20261020`，独立 Profile 为 `home\profiles\runtime-official`。本次真实调用仅为只读、非 D2。
6. 首次真实只读样本揭示兼容失败：旧的私有 `subagent/governance-policy-pin` 必需事件使官方 Host 重启后拒绝读取该测试 Session，证据接口 500。该独立 Home 样本保留。现改用 `pinRoot` 下插件自管文件，在治理预启动评价前持久化，不向官方 Session 事件表写私有类型；第二次新会话及重启验收通过。已经带私有事件的会话仍需在副本上研究迁移，不能声称旧 Home 可直接切换。
7. 已把外部 Web 模块装入同一私有插件 tarball `@dsh-runtime/harness-plugin@0.1.0-rc.4`，官方包零修改。浏览器在重启的官方 Host 中重新打开第二次只读会话，展开原生过程组，点击插件工具行的“查看证据”；右侧“执行轨迹 / 实际变动 / 审计”均有内容，页面错误为空。实际变动页显示新增、修改、删除均无；审计页显示 settled 与调用 ID。截图：`D:\DeepSeekHarness\vis-stable-release-artifacts\official-plugin-probe-20261020\runtime-profile\official-rc4-evidence-drawer.png`。本次回放未调用模型。
8. `rc.7` Web 异常态验收：202→真实 Manifest 可转 completed；404 连续十次、500、损坏的 200 Manifest 均显示“终态证据不可用”且页面不崩溃；settled/aborted 显示“已取消”。损坏 Manifest 首次回放暴露组件渲染异常，随后暴露无限等待，已在客户端修复。回放脚本在独立消费者的 `runtime-profile\check-drawer-states.cjs`；测试响应仅由浏览器拦截，不是现场 Runtime 调用。
9. 新隔离写入 Profile `runtime-official-write` 在全新临时 Git 仓库进行一次非 D2 `repository_change`：会话 `session-d555895f-815c-43b8-8038-1e2aa1af3a59`，子任务 `e634df2a-b1dc-4288-839d-fc3c95b33638`；仅新增 25 字节无换行的 `runtime-write-acceptance.txt`，内容为 `OFFICIAL_RUNTIME_WRITE_OK`。审计 ALLOW、Manifest completed、Safe Trace `.closed`、验证 PASS、认证路由 200；官方 Web 实际变动页显示该文件和补丁，重启后仍能读回。脚本和截图在消费者 `runtime-profile\write-trial-20261021`。两个源码仓库均未作为任务目标。
10. 新隔离失败 Profile `runtime-official-failure` 用无效 `DSH_CODEBUDDY_MAX_TURNS` 触发真实 Runtime 子进程在模型调用前退出：会话 `session-10ab6ca7-cbf9-4032-a94b-6237f3a15da7`，子任务 `2bdd93a7-0b33-48ff-945d-2922954de787`。临时 Git 仓库保持干净，审计只有一次记录；`run-state.json` 为 settled/error、`manifest_available=false`，认证路由返回同等状态。`rc.7` 官方 Web 重启后显示“运行失败”，无页面脚本错误，截图为消费者 `runtime-profile\failure-trial-20261021\failure-ui-rc7.png`。这个样本没有终态 Manifest，不能宣称有完整证据抽屉。

## 未完成与下次顺序

1. 当前私有可安装包为 `@dsh-runtime/harness-plugin@0.1.0-rc.7`；`runtime-official` 仅启用 `repository_inspection`，不作日常入口。真实写入只在专用临时仓库和 Profile 验收过，尚未推广至日常 Home。
2. 下一步继续验收真实取消路径、证据缺失、卸载回退与旧 Home 副本迁移。取消的浏览器回放已通过，但尚缺现场取消一个正在运行的官方 Host 子进程；应将两者明确区分。旧事件失败样本与新样本分开核验。检查窄窗口和键盘操作；旧 Home 不应直接切换。
3. 完成上述门槛后评估官方应用并行日常入口，最后再考虑简化私有 Harness 分支。不得因本次只读成功就删除或覆盖私有分支及旧 Home；归档、删除另审。

## 保护事项

原 Runtime `D:\PythonProject\dsh-runtime` 与原 Harness `D:\DeepSeekHarness\deepseek-harness` 均有用户未提交改动和未跟踪文件，禁止清理、重置、覆盖。独立候选提交不等于远端已推送。ZCode 的密钥文件不读、不复制、不提交。正式 D2 ExecuteGate 继续 `NOT_CLAIMED`。

## 额度交接

2026-10-21 额度已恢复。旧一次性定时因关机未执行，已删除，避免迟到重复启动。最后查询五小时额度剩 67%、周额度剩 65%。候选中的 `rc.7` Web 修复和本交接更新待提交；独立消费者中的 tarball、Profile、临时仓库、浏览器脚本与截图是验收材料，不在源码提交范围。失败 Profile 的 Host PID 以消费者 `runtime-profile\failure-trial-20261021\host.pid` 为准，任务完成后应停止。两个原工作树未修改，候选未推送，D2 仍为 `NOT_CLAIMED`。续跑不重复提交已完成的模型任务。
