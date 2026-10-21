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
11. 旧日常 Home 的 `sessions`（33 个文件，约 4.8 MB）被单向复制到隔离的 `home-migration-20261021`，未复制凭据；官方 Host 从副本启动，六个工作区在 Web 中可列出，已打开其中一个旧会话，页面无脚本错误且输入区可见。打开会话使副本的 `session-1b348fe1-71c1-4ee3-85a7-d57906f41345/session.v4.jsonl.zstd` 从 379 字节变为 459 字节；其余 32 个复制文件与原件 SHA256 相同。原 Home 不是启动目录。这里只证明一个旧会话的原地副本迁移，尚未逐一验证其余工作区和私有事件旧样本；记录和无模型浏览器脚本在独立消费者 `home-migration-20261021`。
12. 插件卸载回退：在同一独立消费者新建只含官方 base/Web 两个 bundle 的 `runtime-official-removed` Profile，未装 Runtime 插件。重启后首页 200、原认证证据路由 404；浏览器重新打开此前的失败测试会话，输入区可见、插件工具行数为 0、页面脚本错误为空。日志与无模型脚本在消费者 `runtime-profile\removed-trial-20261021`。这是隔离 Profile 的卸载模拟，尚未更改日常入口。
13. 现场取消仍未过门槛：四次独立临时仓库尝试留在消费者的 `cancel-trial-20261021`、`cancel2-trial-20261021`、`cancel3-trial-20261021`、`cancel4-trial-20261021`。第一次 `repository_inspection` 实际选择 Codex，直接诊断显示 Codex app-server 启动失败；后三次 `repository_change` 的治理审计为 ALLOW，但官方 Host 的 Runtime run-state 很快变为 settled/error、无 Manifest，本地等待型 CodeBuddy 替身未留下启动标记，因此并未执行取消。第四次已将父会话改为“工作区内修改”并让宿主继承完整 PATH，结果相同。四个临时仓库均保持干净。直接 Python 诊断曾验证替身可启动，但不能替代官方 Host 现场调用。验收专用状态探针 `0.0.5` 增加了仅在 `allowInterrupt: true` 的隔离 Profile 中注册的中断路由；无模型的不存在目标调用返回 200/accepted。下次应先在隔离包中取得 Runtime 子进程退出原因，再考虑新的模型现场尝试，避免重复消耗。以上均非 D2。

## 未完成与下次顺序

1. 当前私有可安装包为 `@dsh-runtime/harness-plugin@0.1.0-rc.7`；`runtime-official` 仅启用 `repository_inspection`，不作日常入口。真实写入只在专用临时仓库和 Profile 验收过，尚未推广至日常 Home。
2. 下一步先用无模型诊断定位上述 Runtime 子进程早退，再验收真实取消路径、证据缺失与旧 Home 副本的其余工作区。取消的浏览器回放已通过，但尚缺现场取消一个正在运行的官方 Host 子进程；应将两者明确区分。旧事件失败样本与新样本分开核验。检查窄窗口和键盘操作；旧 Home 不应直接切换。
3. 完成上述门槛后评估官方应用并行日常入口，最后再考虑简化私有 Harness 分支。不得因本次只读成功就删除或覆盖私有分支及旧 Home；归档、删除另审。

## 保护事项

原 Runtime `D:\PythonProject\dsh-runtime` 与原 Harness `D:\DeepSeekHarness\deepseek-harness` 均有用户未提交改动和未跟踪文件，禁止清理、重置、覆盖。独立候选提交不等于远端已推送。ZCode 的密钥文件不读、不复制、不提交。正式 D2 ExecuteGate 继续 `NOT_CLAIMED`。

## 额度交接

2026-10-21 额度已恢复。旧一次性定时因关机未执行，已删除，避免迟到重复启动。最近查询五小时额度剩 11%、周额度剩 56%；接近用户设定的 10%/2% 停止阈值。候选 `rc.7` Web 修复已提交为 `4a4a330`，副本迁移与卸载记录已提交为 `e356dd2`，取消探针及前三次诊断为 `ee2ad2c`；第四次对照记录待提交。独立消费者中的 tarball、Profile、临时仓库、浏览器脚本与截图是验收材料，不在源码提交范围。所有隔离 Host 已停止。两个原工作树未修改，候选未推送，D2 仍为 `NOT_CLAIMED`。续跑不重复提交已完成或失败的模型任务。
