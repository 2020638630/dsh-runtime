# RC4 私有试用后的下一阶段任务

状态：2026-10-19 的执行顺序。依据 [R9 设计基线](PROJECT_TARGET_AND_RUNTIME_VISUALIZATION.md)、[实施清单](RUNTIME_VISUALIZATION_BACKLOG.md)和[完整 Home 并行试用记录](PRIVATE_HOME_STAGE_AND_ROLLBACK_RUNBOOK_2026-10-19.md)。当前不移动默认分支、不删除旧分支、不发布稳定版；D2 ExecuteGate 保持 `NOT_CLAIMED`。

## 已关闭的前置项

- RC4 已安装 Web、Windows 未签名目录包和桌面历史 Manifest 三页签有验收记录；负责人截图与导入的只读历史证据相符。
- 完整日常 Home 已做受限备份，RC4 在独立副本迁移并重读 33/33 条 Session；RC3 已安装包配合另一份升级前完整副本读回 33/33。日常 Home 未切换。
- 2026-10-19 再查官方 Harness `master` 为 `687f282e8625c6b8d11ff58211a90524be2e4317`，已是私有 Harness 候选 `819dc46ea7953598b239a82e25abe7d87c64add3` 的祖先，当前没有新的官方提交需要合并。
- 旧日常 `web` Profile 在 RC4 上虽可解析，但提示 `agent-presets` 补丁目标不存在；其解析结果仍是默认 `workspace-write`，Runtime provider 仅有 `runtimeRoot`。因此旧 Profile 不作为 RC4 试用入口。新增 `packed-rc4-full-home-stage` 已解析为只读、仅 `repository_inspection`，审计和证据路径均在独立副本内。
- 候选 Web 的聊天及轨迹图片展示聚焦测试 **5/5** 通过；完整 Home 内 2 个附件是文件名与 SHA-256 一致的 PNG。历史会话没有引用这两个附件，故没有实际旧会话附件页面验收。
- 负责人在专用 RC4 Web 完成一次真实、非 D2 的只读 `repository_inspection`；Manifest 为 `completed`、退出码 0，审计 `settled`，临时仓库保持干净。三页抽屉截图与落盘证据一致，首次缺审计目录的拒绝已由此次复验关闭。

## 优先队列

| 顺序 | 任务 | 完成条件 | 当前边界 |
| --- | --- | --- | --- |
| P0 | 固定安全试用入口 | 在独立 Home 中使用专用只读 Profile，验证启动、会话列表、可读历史及关闭服务；给使用者一份不指向旧 `web` Profile 的启动说明 | 已关闭：真实只读调用及三页抽屉通过，临时仓库干净；审计目录入口预检已生效 |
| P1 | 完成附件和凭据的实际使用验收 | 用独立数据和有引用的附件样本走认证读取与页面展示；核对已完成模型会话的终态、证据和仓库无变化 | 已关闭：有限只读模型调用、真实新会话图片引用、刷新重开后的展示和图片查看层均有现场回执；旧日常 Home 中两张无引用图片仍不算历史附件验收 |
| P2 | 固定私有发布审查结果 | 对两个候选远端 SHA、默认分支、版本/锁文件、已完成的构建与安装证据、Actions 关闭后的必需门槛逐项签收；仅针对新增差异重验 | 远端分支与成对 RC4 标签已复核；本地构建和标准安装证据在案。Actions 已关闭，远端检查未运行；分支保护与 required checks 尚未从设置页核对 |
| P3 | 决定部署和分支切换 | 前三项关闭后，提交可回退的日常启动与默认分支方案，明确负责人批准点；发布稳定标签和清理旧分支分别决策 | RC4 仍是私有候选；GitHub Actions 关闭，分支保护状态尚需核对 |

## 执行约束

**P2 当前核对（2026-10-19）**：官方 Harness `master` 仍为 `687f282e8625c6b8d11ff58211a90524be2e4317`，是私有候选的祖先，没有新上游提交待合并。Harness 私有默认线仍为 `60c8f0c813a55754338d1e53a655f480a5f62f02`，候选为 `819dc46ea7953598b239a82e25abe7d87c64add3`；Runtime `master` 仍为 `ebb191ae998af6251731f02e28ba16d4ce733fac`，候选文档头部为 `f234880421a1cc180a1fdad0c811726d507f0f46`。私有远端的 RC4 注释标签分别剥离为 Harness `819dc46`、Runtime `15d871d`，与[固定源码表](PRIVATE_VISUALIZATION_TRIAL_2026-10-19_RC4.md#固定源码)一致。Harness 本地归档清单 SHA-256 仍为 `96d85dd6f297fe61c84f4e1f891b728ecb70f2c5d9df57962578523368f88c12`，归档仍为 DSH 345 包和 vendor 9 包；先前的静态检查、正式构建、标准安装及桌面未签名目录包证据继续适用于固定源码。此项是来源和产物存在性复核，没有重跑全套门槛或取得远端 CI 结果。Runtime `master` 的无保护提示仅有负责人先前页面截图，尚需在仓库设置页核对实际保护规则；Harness 私有默认线也需同样核对。分支保护和离线发布判定完成前，不移动默认分支或发布稳定版。

- 本机试用入口为 `D:\DeepSeekHarness\vis-trial-rc4-home\artifacts\START_RC4_READONLY_TRIAL.cmd`。双击后通过已安装 RC4、独立完整 Home 和专用只读 Profile 启动本机 Web，浏览器应自动打开；关闭前用 `Ctrl+C` 停止。试用工作区已在 `D:\DeepSeekHarness\vis-rc4-readonly-usage-20261019` 新建并提交初始 README，`main` 分支干净；仅在试用会话中选择该仓库，不把两个源码仓库设为任务工作区。启动本身不调用模型；发送消息前需明确该次任务内容。
- 优先在独立 Home、独立临时 Git 仓库完成 P0/P1；日常 Home 保持原状。凭据内容、备份 Manifest 和用户截图只留本机，不进入 Git。
- 若官方 `master` 后续前移，先在隔离候选中合并新提交并审查差异，再做受影响范围的适配验收；已通过的历史证据不无故重跑。
- 两个原工作树的已跟踪改动和未跟踪文件保留；不清理、不重置、不覆盖。旧 D2 分支继续留作内部治理审查，不能因“只留最新”而直接删除。
- 额度交接阈值为周剩余不高于 2% 或五小时剩余不高于 10%；达到阈值时记录完成项与下一步，再安排续跑。
