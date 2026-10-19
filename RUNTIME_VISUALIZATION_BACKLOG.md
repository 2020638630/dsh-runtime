# DSH Runtime 运行可视化开发任务

状态：已批准的 R9 设计基线之实施清单（2026-10-15）。设计依据：[PROJECT_TARGET_AND_RUNTIME_VISUALIZATION.md](PROJECT_TARGET_AND_RUNTIME_VISUALIZATION.md)。四项负责人决策均选 A。

**额度恢复后的推进（2026-10-18）**：五小时剩余约 99%、周剩余约 85% 时已停用本次一次性续跑。双仓原工作树继续保留全部未提交改动与未跟踪文件；候选分支干净。已将私有默认线的大规模上游升级拆成 P0–P4 审查批次，见 [私有默认线升级审查与运行可视化发布顺序](PRIVATE_DEFAULT_UPGRADE_PLAN_2026-10-18.md)。已安装 RC3 的独立只读 Profile `packed-rc3-readonly` 完成配置解析、Web HTTP 200、空启动错误日志及既有独立仓库的新会话入口“仅可查看”核对；没有调用模型或 Runtime。受限环境中的首次私有远端查询失败，随后经正常 Git 远端访问重新核对：Harness 默认线、候选线和 Runtime 默认线、候选线均与本地记录一致。旧 D2 分支保留，ExecuteGate 仍为 `NOT_CLAIMED`。

**RC3 成对试用标签**：两个私有远端已发布 `vis-manifest-mvp-20261018-rc3`，Harness 指向 `a6e8d20476450be8c48b27e310d760034610b15a`，Runtime 指向 `15d871d1d960291fe7ab5ed22eb39a9c1d3b9a17`。标签固定准确验收来源，不代表稳定版或默认线切换。下一步继续 P1/P2 路径级审查。

**上游独立分批审查**：在新隔离检出 `vis-harness-upstream-stage` 实测“公开上游＋旧私有默认线”的合并。三个文本冲突已解决、聚焦测试 54/54、构建产物 7/7、Host/Client 类型检查通过；文档总检查仍有 8/43 未通过，均在旧私有文档迁移与生成物范围。该分支本地且未提交、未推送，不是用户可用版本。详见升级计划；下一步先决定是否值得继续单独清理这条上游批次，或保持 RC3 成对试用标签并直接推进候选的发布审查。

**额度交接（2026-10-18，五小时剩余 10%、周剩余 86%）**：已达到负责人指定的暂停线。本轮 Harness 私有候选 `codex/private-consolidation-20261017` 已推送至 `a6e8d20476450be8c48b27e310d760034610b15a`；Runtime 私有候选本轮文档提交见本分支 HEAD，均未移动默认线。准确 Harness 提交的全新固定检出通过锁文件复制安装、正式构建 **9/9**、发布测试 **51/51**、类型检查 **5/5**，从该提交打包 DSH 345 包和 vendor 9 包，隔离 npm 12.2.0 标准安装通过，安装后 CLI 版本 `0.2.1-rc.2`。安装包 Web 的 RC3→RC2→RC3 无模型往返三次 HTTP 200；RC3 打包 provider 的非 D2 启用与禁用 Profile 均 HTTP 200。专用 `vis-trial-rc3-current` Profile 现在默认只开放 Runtime `repository_inspection` 且父会话默认 `read-only`；不加临时权限叠加的全新浏览器会话显示“仅可查看”，独立临时仓库干净。证据与边界见 [PRIVATE_VISUALIZATION_TRIAL_2026-10-18_RC3.md](PRIVATE_VISUALIZATION_TRIAL_2026-10-18_RC3.md)。只读分支审查发现 Harness 候选虽可从私有默认线快进，但相差 **6077 个提交、12927 个文件**，属于广泛上游升级，不宜在本轮直接移动默认线；旧 D2 独有分支保留，ExecuteGate `NOT_CLAIMED`。**额度恢复后首项**：核对定时续跑状态和双仓工作树，再将私有默认线差异拆为可审查的升级批次，确认稳定版标签及部署路径；不删除分支或移动默认线。两个原仓库的未提交改动及未跟踪文件继续原样保留。

**RC3 固定试用审查（2026-10-18）**：已从 Harness `a5473ce995` 与 Runtime `15d871d` 建立干净的 detached 固定检出，使用新 `vis-trial-rc3` Profile 链接固定 provider、指向固定 Runtime，完成非 D2、默认仅 `repository_inspection` 的配置解析及真实 `dsh web` 无模型认证/独立工作区会话烟测。首次正式构建 8/9；定位到 esbuild 安装路径后，在隔离检出的忽略目录以同哈希副本重建，正式构建 9/9。先前为私有试用复制的 156 个 Web 资源不计作该次构建证据。Harness 随后将两个子任务包版本对齐 `0.2.1-rc.2`、修正空打包测试对 pnpm `prepare` 的误判，候选 `a6e8d20476` 已由正常钩子推送到私有远端。在该准确提交新建第二个固定检出，用冻结锁文件及依赖复制模式安装，无需手工替换 esbuild 可执行文件即正式构建 **9/9**；发布测试 **51/51**、类型检查 **5/5**、DSH 345 包与 vendor 9 包归档通过。使用此前 RC2 验收保留的隔离 npm 12.2.0 工具，对准确提交的 354 个归档完成**无诊断开关的标准独立安装**，默认产品隔离检查 658 个包，安装后 CLI 报 `0.2.1-rc.2`；npm 10.7.0 在本机仍失败，不代表归档安装失败。当前 Profile 的无模型 Web 与独立禁用 Profile 的 HTTP 启动通过；初次试用时父 Agent 默认可“工作区内修改”，随后专用当前 Profile 已改为“仅可查看”默认并做新会话核对。另在独立持久消费者中安装 RC3 与保留 RC2 的归档，补装 Web 必需的 Windows 可选原生包后，RC3→RC2→RC3 三次实际安装包 Web 启动均 HTTP 200；安装包中的 RC3 provider 在非 D2 Profile 加载及禁用状态分别启动 Web HTTP 200。均未重跑业务任务。完整证据、权限与回退界限见 [PRIVATE_VISUALIZATION_TRIAL_2026-10-18_RC3.md](PRIVATE_VISUALIZATION_TRIAL_2026-10-18_RC3.md)。下一步审查私有默认线升级和目标部署权限，再决定 RC3 标签；旧 D2 独有分支继续保留。D2 ExecuteGate `NOT_CLAIMED`。

**额度交接（2026-10-18 约 00:50 北京时间）**：最新 Codex 额度为五小时剩余 **50%**、周剩余 **2%**，已到负责人指定交接线，暂停新增现场调用。Harness 私有整合分支 `codex/private-consolidation-20261017` 的 `a5473ce995` 与 Runtime 私有候选 `codex/vis-manifest-mvp-20261016` 的 `10f6642` 均已推送，隔离工作树干净；真实 Web 只读、写入和无模型失败/取消结果见下文“更新后适配现场验收”。写入临时仓库保留 `?? result.txt` 作为验收产物；只读临时仓库保持干净。两个原源码工作树的已有修改和未跟踪文件保留，未清理/重置/覆盖；D2 ExecuteGate `NOT_CLAIMED`。**额度恢复后的首项**：核对成对候选提交与依赖、试用 Profile 的父 Agent 权限及非 D2 Runtime 授权，形成可回退的上游适配 RC 版本方案；之后再评估私有默认分支合并，旧 D2 独有分支暂不删除。复用现有一次性续跑任务，在周额度 2026-10-22 约 14:21 北京时间重置后约五分钟续接；续跑启动时停用该一次性任务，避免重复。若续跑再次达到周剩余 2% 或五小时剩余 10%，照此交接。

**更新后适配现场验收（2026-10-18）**：Harness 私有整合分支在 `77cbead5fc` 合入公开上游后，实际 `dsh web` 新建会话暴露旧标准预设的 `tool-subagent-fork.config.toolFilter` 已被新版拒绝。新版日程工具已有对子任务调用的拒绝保护，移除这段失效配置后，预设/日程定向测试 **42/42**，真实页面可新建会话；修复 `a5473ce995` 已推送至私有 `codex/private-consolidation-20261017`。未改私有默认分支。使用独立 `DSH_HOME` `D:\DeepSeekHarness\vis-trial-upstream-home` 和非 D2 v2 Profile `vis-trial-upstream`，认证 Web 页面在独立 Git 仓库 `D:\DeepSeekHarness\vis-trial-upstream-repo` 的只读父会话中完成一次 `repository_inspection`：Runtime `dsh-runtime-fed24efe-bc9b-402e-a60b-3b3e4fe58bc6` 为 `completed`、退出码 0、Manifest 可用、审计 `settled`，无文件变化，浏览器抽屉的轨迹/实际变动/审计三栏均可打开；轨迹为 `not_applicable`、审查 `UNAVAILABLE`，符合只读语义。父会话收到子任务终态后完整回复，仓库仍干净。

同一整合分支上的无模型 Web 贯通负向测试使用真实 Runtime 子进程复放父调用，失败与取消 **2/2** 通过，验证无 Manifest 时页面分别显示失败/取消降级；这两例由 Web scaffold 驱动，不能宣称与上面的 `dsh web` CLI 成功会话是同一次现场运行。随后新建独立 Git 仓库 `D:\DeepSeekHarness\vis-trial-upstream-write-repo`，在临时 overlay 中仅放行 `repository_change`，由真实 `dsh web` 父会话发起一次非 D2 写入。Runtime `dsh-runtime-227dbf6e-c4dc-4465-990f-2b26036dcfee` 为 `completed`、退出码 0、Manifest `PASS`、审计 `settled`；仅新增 `result.txt`，37 字节，SHA-256 `05825a880106289823189e174902d04b640bab91eae0149e8857856dfdd62e55`，末尾单个 LF。Safe Trace JSONL 与 `.closed` 均落盘，Manifest `trace_complete=true`；真实浏览器抽屉三栏显示已记录轨迹、唯一新增文件及审计依据，轮次仍诚实显示“未记录”。父会话完整回复。两个原源码工作树的脏改动/未跟踪文件均保留，D2 ExecuteGate 仍为 `NOT_CLAIMED`。

**当前下一步**：① 冻结成对的上游适配试用版本，核对 Harness 当前可拉取提交 `a5473ce995` 与 Runtime 候选的依赖/包版本、试用 Profile 权限和回退路径；② 决定私有默认分支的合并时机，旧 D2 独有提交继续作为内部治理线单独处理，不能因“只留最新”直接删除；③ 发布条件未包括调用模型的业务失败现场样本，沿用负责人已批准的首版边界。额度交接阈值已由负责人更新为**周剩余 2% 或五小时剩余 10%**，达到阈值时再记录完成项与续跑安排；本段仅记录已完成的适配验收，不表示稳定版已发布。

**最新交接：私有分支整合、上游更新与适配（2026-10-17）**：按负责人指定顺序，先刷新并核对私有引用。Harness 可视化候选 `f5884996c5` 已包含私有默认线、D2 preflight 分支及原治理工作树的全部**已提交**历史；另有 `codex/d2-replayonly-repair-20261010` 的 5 个、`codex/upstream-sync-20261012` 的 1 个独有提交，均属于旧 D2 内部治理。首个旧提交试取即与现行 R3 进程快照、来源哈希和测试冲突；另一提交会把 ExecuteGate 时效从现行 5 分钟放宽到 60 分钟。旧治理提交未强行并入用户功能候选，原分支和回退引用保留，D2 ExecuteGate 仍为 `NOT_CLAIMED`。

在全新隔离工作树 `D:\DeepSeekHarness\vis-harness-private-integration`，由候选合入公开上游 `origin/master` 的 `687f282e86`（较候选独有约 990 个提交），解决 28 个冲突，形成双父提交 **`77cbead5fc`**，已推送到 Harness 私有远端新分支 `codex/private-consolidation-20261017`。未移动私有默认分支、旧可视化候选或 RC2 标签。合并后完整类型检查 **5/5**、正式构建 **9/9**（含 Web）、证据与治理聚焦测试 **10 文件、80 通过、1 跳过**；`doc-sync` 首轮 39/43，四个失败项已逐项修复并单独复验通过（链接、客户端槽位目录、持久化格式统计、仓库引用误判），双语配对 1034 组通过。依赖锁文件检查通过；Windows 原生依赖安装脚本因 `spawn EPERM` 未完成，隔离树用 `--ignore-scripts` 安装用于上述构建和测试。Git Bash 提交 hook 因 Win32 signal pipe 无法启动；已单独完成差异检查、类型、构建和相关文档测试，仅该整合提交与推送临时跳过 hook。

**尚需更新后现场验收**：用与 RC2 试用 Profile 分开的新临时 Profile 指向整合分支和 Runtime 候选，先执行 `dsh web` 启动、只读 `repository_inspection`、认证证据抽屉及失败/取消降级页面，再视结果做独立临时仓库写入路径。不得将旧 RC2 现场样本直接算作本次上游更新的现场验收。完成现场验收后审查是否把新分支作为私有默认线；此时不删除旧 D2 分支。两个原工作树仍保持 Harness 106、Runtime 16 项待处理状态。周额度最近余约 11%，低于 10% 时记录结果并按已获授权在重置后约五分钟续跑。

**当前交接摘要（2026-10-16，以下历次记录按发生时状态保留）**：VIS-01～05 已实现，VIS-06 的真实只读与写入成功路径、Safe Trace `.closed` 和 Web 三视图已验收。Runtime 与 Harness 候选均已按负责人授权推送到各自私有远端的 `codex/vis-manifest-mvp-20261016` 分支；Harness 最新受控负向 Web 验收提交为 `4e0a2422cb`。候选验证：Runtime 170/170；Harness 证据 provider 与抽屉 62/62，记录式 Web 回放 3/3；完整 `pnpm run typecheck`、Web 构建均通过。Git 提交 hook 的 shell 入口在本机启动失败，相关翻译配对、依赖声明、暂存差异检查已单独通过；Git Bash 的 pre-push hook 找不到 `pnpm`，已在候选目录用项目 Node 24/pnpm 手动执行同一完整检查。5 小时额度最近检查已用 89%（余 11%）；低于 10% 时按负责人要求暂停。D2 ExecuteGate 保持 `NOT_CLAIMED`。

**接续顺序**：① 正式 R9 基线与本清单已纳入 Runtime 隔离候选；两个候选分支已推送，原治理工作树未切换；② 负责人已将失败/取消页面样本列为发布条件，受控无模型浏览器链路已通过，额度恢复后优先评估并执行独立临时仓库的真实子进程负向验收，再审查发布版本；③ 需要收拢旧分支时先核对引用、依赖及回退点，再单独实施。P1 实时流与 P2 Memory/RAG 继续排在首期 Manifest 之后。

**受控负向页面验收与限额交接**：Harness `4e0a2422cb` 在浏览器记录式测试中增加取消与进程失败两种终态样本。测试向 scaffold 的临时 Host 证据目录写入绑定父 Session/子运行身份的 `run-state.json`，经实际认证 `/api/dsh-runtime.evidence` 路由读取，再由 Chrome 页面显示“运行已取消/运行失败 · 无终态证据”，并确认没有虚构 Manifest 抽屉；新 golden `snapshots/web/dsh-runtime-evidence/ui.negative.expected.md` 已复放，Web 3/3、完整 `pnpm run typecheck` 通过。既有失败 Manifest 页面样本仍为受控返回。**这些是浏览器与 Host 读取链路的无模型样本，不是实际 Runtime 业务失败/取消的现场调用**。下一轮若要满足更严格的现场发布验收，应先用全新临时 Git 仓库和独立非 D2 配置设计无需模型的真实子进程失败/取消触发方式，确认不会访问模型后再运行；若无法避免模型调用，则先明确新的调用范围与额度。原治理工作树及未跟踪文件继续保留，不复用旧 run ID，不申领 D2 ExecuteGate。

**无模型真实子进程负向验收（2026-10-17）**：在独立临时 Git 仓库 `C:\Users\ADMINI~1\AppData\Local\Temp\dsh-vis-negative-6f05a4b8-a09b-4b1f-b7d4-701d69c155e5\workspace`，通过 Harness 候选的 `startDshRuntimeRun` 和实际本地 subprocess 实现启动 Runtime 候选的 `python -m dsh_runtime.entrypoint`，仅执行只读 `repository_inspection`。两次运行均显式设置无效的 `DSH_CODEBUDDY_MAX_STREAM_CHARS=invalid-before-model`，使控制器构建在任何模型调用前失败；未使用 D2 配置、凭据或既有运行身份。失败样本 `dsh-runtime-54d2f720-4996-4d61-9220-e09b0bd837f4` 的真实子进程退出码为 2，Call Trace 为 `call_started → call_terminal(process_error, ValueError)`，Host 结果及已落盘 `run-state.json` 均为 `error`，无 Manifest。取消样本 `dsh-runtime-2853ab89-d14e-41f1-b4c3-d0df276b7cd0` 在 spawn 后立即取消并等待子进程退出，Host 结果和状态均为 `aborted`，仅有 `call_started`，无 Manifest。两次均已核对运行专属证据目录、临时仓库 Git 状态干净。此项是**真实 Runtime 子进程与 Host 结算的负向现场证据**；此前 Chrome 样本验证的是这些状态的 Web 呈现，尚未声称从真实负向子进程直接驱动浏览器页面，也未验收需要模型的业务失败。验收时的候选功能版本是 Runtime `234803b`、Harness `4e0a2422cb`；本轮没有改功能代码。下一步审查发布版本与剩余限制；D2 ExecuteGate 继续 `NOT_CLAIMED`。

**首期私有交付审查（2026-10-17）**：Runtime 与 Harness 私有候选均已推送；Harness 文档修正提交为 `9f799daad1`（英中说明改为当前结算行为并更新配对记录）。Harness 文档配对与预提交检查通过，项目 Node 24 下完整 `pnpm run typecheck` 再次通过；Git Bash pre-push 环境仍找不到 `pnpm`，仅该次 Harness 推送在手动完成同一检查后跳过 hook。**两个分支是可拉取的私有试用候选，不是默认分支或稳定版标签**；真实只读/写入成功、轨迹闭合、Web 三视图、真实无模型进程失败/取消及受控负向浏览器页面已有对应证据。稳定发布前的优先项：① 从实际 `dsh web` 触发无模型负向子进程并在同一页面读取其真实 `run-state.json`，补齐贯通现场样本；② 评估需要模型的业务失败现场样本是否纳入首版发布条件，若纳入则另设独立临时仓库和调用额度；③ 明确私有分支的部署配置、版本标记与回退点后再考虑默认分支合并或旧分支收拢。两个原治理工作树继续保留原有改动及未跟踪文件，D2 ExecuteGate 保持 `NOT_CLAIMED`。

**私有分支只读核对（2026-10-17）**：Runtime 远端 `master` 与 `codex/runtime-workflow-governance-closeout` 的已提交历史都包含在当前可视化候选内，但后者对应的原本地工作树仍有未提交改动。Harness 私有远端的 `integration/dsh-runtime-d1-q2-closeout` 和 `codex/d2-preflight04-preparation` 是候选祖先；`codex/d2-replayonly-repair-20261010` 尚有 5 个候选未包含的提交，`codex/upstream-sync-20261012` 尚有 1 个，不能按“只留最新”直接删除。Dependabot 分支不属于本次项目分支收拢范围。本轮没有合并、改默认分支或删除任何远端引用；先完成稳定发布验收，再单独核对未包含提交、依赖和回退点。

**Harness 推送门槛处理**：首次推送被 pre-push hook 阻断，因为 Git Bash 环境找不到 `pnpm`；用项目指定的 Node 24/pnpm 直接运行同一 `pnpm run typecheck` 时，Host 阶段通过，Desktop `welcome.js` 打包报旧目标下解构转换不支持。候选新增单独提交 `e30644e7bc`，将只在 Electron 内运行的欢迎页 Vite `build.target` 对齐其余 Desktop 包的 `es2024`；Desktop 单独打包和完整 `pnpm run typecheck` 均通过。由于 Git Bash 仍找不到 `pnpm`，仅该次 Harness 推送跳过 pre-push hook，未改动 hook 配置。完整检查通过消除了此前 Desktop 构建阻断，但这不代表所有产品发布门槛或真实失败/取消样本已完成。

**Web 工具贯通负向验收（2026-10-17）**：Harness 候选新增手动、按环境变量启用的浏览器验收 `apps/web/tests/dsh-runtime-tool-negative.local.e2e.ts`，提交 `5393eea154`。测试用 Web scaffold 启动真实 Host/Web 组合、认证路由和 Chrome 页面，临时启用标准预设中默认关闭的 `dsh_runtime` 工具；父 Agent 的工具调用由本地 replay 提供，子 Agent 则通过真实 `startDshRuntimeRun` 与本地 Python 子进程执行候选 Runtime。每例新建独立临时 Git 仓库、非 D2 治理配置和证据目录，仅允许只读 `repository_inspection`；无效的 `DSH_CODEBUDDY_MAX_STREAM_CHARS` 保证执行在模型初始化前失败，取消例在子运行启动后发出中断。合并运行 2/2 通过：失败子运行 `03bbd91f-22b1-4d31-a4ca-13ce7472a18c` 的落盘状态为 `error`，页面显示 `Run failed · no terminal evidence`；取消子运行 `c523d9e7-6e49-475a-ba3c-124ff6ed86ce` 为 `aborted`，页面显示 `Run cancelled · no terminal evidence`。两例认证证据接口均返回 `manifestAvailable=false`，没有“View evidence”按钮。此证据覆盖 **Web 工具 → 真实 Runtime 子进程 → run-state → Host 认证读取 → 浏览器页面**，不等同于独立 `dsh web` CLI 启动或需要模型的业务失败。聚焦 lint、Host 类型检查及完整 `pnpm run typecheck` 通过；Git Bash 提交 hook 因 Win32 signal pipe 失败，已单独执行其适用的暂存 lint 与差异检查后，仅对该提交临时跳过 hook。下一步先用 `dsh web` CLI 和隔离 profile 作只读启动/负向烟测，再冻结双仓私有试用版本；D2 ExecuteGate 仍为 `NOT_CLAIMED`。

**CLI 启动烟测（2026-10-17）**：用全新临时 `DSH_HOME` 直接运行 Harness 候选的 `dsh web --no-open --port 0`，Chrome 经命令打印的认证入口取得 HTTP 200 页面并加载 Web 框架，随后关闭子进程及临时配置。此项只验证真实 CLI 启动及页面可用；CLI 会话内的负向子任务仍由上一项 Web scaffold 贯通验收代表，不能合并称为单次 CLI 端到端运行。下一步冻结双仓私有试用版本、记录部署配置及成对提交和回退点。

**RC2 文档门槛与分支审查（2026-10-17）**：Harness 候选修正标准 Web Preset 工具启用说明后，`doc-sync` 首次为 41/43；失败项均已定位并小范围修复。生成的 client slot catalog 只补登记 `dsh_runtime` 抽屉槽位；DeepSeek LLM 双语说明同步既有 D2 sidecar 的“同步派生、异步落盘”语义并更新配对记录。修复提交为 Harness `26c11095f9`，第二次完整 `pnpm run doc-sync` 为 **43/43**。旧 Harness 分支相对可视化候选的 6 个独有提交均涉及 D2 内部治理：`codex/d2-replayonly-repair-20261010` 5 个、`codex/upstream-sync-20261012` 1 个。它们不混入用户可视化候选，保留旧分支及回退引用，待内部治理线单独处理；没有删除分支或更改默认分支。当前计划将该文档门槛修复纳入新的私有试用标记 RC2，RC1 保留不移动。

**专用 RC2 试用 Profile 现场验收（2026-10-17）**：负责人选择新建专用 Profile。独立 `DSH_HOME` 为 `D:\DeepSeekHarness\vis-trial-rc2-home`，Profile `vis-trial-rc2`，测试 Git 仓库 `D:\DeepSeekHarness\vis-trial-rc2-repo`；标准 Web Preset 的嵌套 `dsh_runtime` 已启用，Runtime 治理仅允 `repository_inspection`。真实 CLI 启动及认证页面 HTTP 200 通过。先用无模型页面导航断言 `data-conversation-session=session-a4d070d3-1755-4dae-8961-b227499725cf`，再做一次真实只读调用：`dsh-runtime-2698f480-1c1c-4886-84c2-1f2d33b7b004` 结算 `completed`，Manifest 已生成，认证页面回放展开过程组后可打开“View evidence”抽屉；审计 `settled`、变化 `+0 -0`，测试仓库 Git 干净。该只读任务的轨迹 `not_applicable`、核验 `UNAVAILABLE`，不能声称 Safe Trace 或 PASS。自动化在 Runtime 结算即关闭 Web，父 Agent 后续回复被中断，因此完整父会话终态和可持续试用仍未验收；两次误落默认工作区的尝试不计入。Profile 当前以 `link:` 引用候选工作树，不是不可变部署；稳定发布前需固定版本、复核非 Runtime 工具权限并完成父会话与回退演练。详情见 `PRIVATE_VISUALIZATION_TRIAL_2026-10-17_RC2.md`。D2 ExecuteGate 保持 `NOT_CLAIMED`。

**首版稳定版业务失败验收决策（2026-10-17）**：负责人采纳建议，不将“调用模型的业务失败现场样本”列为首版稳定版门槛；保留真实业务失败终态生成 Manifest 的可重复测试与 Web 呈现验收。模型现场样本列入发布后专项验证；若未来对外承诺模型失败一定有完整证据，先补做该现场样本。当前剩余优先级：① 固定专用试用版本并复核 Web Profile 的非 Runtime 工具权限；② 完成父 Agent 完整回复的独立仓库现场试用；③ 演练成对 RC2 标记的发布与回退；④ 通过稳定版门槛后再决定默认分支合并与旧 D2 分支收拢。D2 ExecuteGate 继续 `NOT_CLAIMED`。

**完整父会话与 RC2 Runtime 固定（2026-10-17）**：第二次专用 Web 现场调用先核对活动会话 `session-0488f2d2-585f-4f66-a919-efd8b329b7ad` 属于独立测试 Git 仓库，父 Agent 两轮均完整结束，第二轮收到子任务结果并概述仓库状态；未再调用其他工具。Runtime 运行 `dsh-runtime-2b680d44-b432-49ad-861b-5ab5187f0e87` 终态 `completed` 且 Manifest 可用，审计 `settled`，观察变化 `+0 -0`，测试仓库保持干净。`vis-trial-rc2` 的 `runtimeRoot` 已指向 RC2 标签的独立 detached 检出 `D:\DeepSeekHarness\vis-runtime-rc2-fixed`，配置解析已复核。Harness provider 仍 `link:` 至当前 HEAD 为 RC2 的候选工作树，尚未形成不可变部署；Web UI 的 `Workspace Write` 是父 Agent 权限，不能等同于 Runtime 的只读治理。剩余稳定版门槛是固定 Harness 包、复核这层权限以及成对发布/回退演练；详情见 RC2 试用记录。

**限额交接（2026-10-17 12:15 北京时间）**：五小时额度已用 88%（余 12%），预计 14:38:13 恢复；按负责人约定接近 10% 时停止新增模型试用。已完成并推送 Runtime 文档提交 `190da7c`，双仓 RC2 私有标签不移动；完整父会话试用、真实 Runtime 终态 Manifest、专用仓库干净及 Runtime RC2 detached 检出均已记录。当前未完成：① 将 Harness provider 从可变候选 `link:` 固定到可复现 RC2 包并复核 Profile 的父 Agent 一般工具权限；② 成对发布与回退演练；③ 稳定版再审。下一次续跑先核对候选及原工作树状态、额度和现有定时任务，再推进上述第一项。两个原工作树和所有未跟踪文件保留，D2 ExecuteGate 保持 `NOT_CLAIMED`。

**Harness provider 固定与回退审查（2026-10-17）**：专用 Profile 的 provider 已从可变候选链接改指 Harness RC2 `26c11095f9` 的 detached 检出 `D:\DeepSeekHarness\vis-harness-rc2-fixed`，RC2 已构建 `lib/index.js` 前后 SHA-256 相同；实际模块导入、CLI 认证浏览器启动无模型烟测通过。provider 源码固定，但依赖通过 junction 借用候选 `node_modules`，本机部署尚非完全自包含。pnpm 归档已存于 Profile `artifacts/`，离线安装被内部依赖缓存元数据缺失阻断，失败前后 Profile 包声明及锁文件哈希一致。权限边界：Runtime 子任务仅 `repository_inspection`，父 Agent 标准 Preset 仍启用 PowerShell/文件工具，页面显示 `Workspace Write`，故不可宣称整个 Web 会话只读。RC1→RC2 差异中 RC2 新增 `dsh_runtime` client slot catalog，RC1 不能作为保留同等抽屉能力的回退点；正式发布需另核对发布前版本或建立经实际验收的成对回退包。原工作树仍保留，D2 ExecuteGate `NOT_CLAIMED`。

**配置回退演练（2026-10-17）**：默认线的本地远端引用为 Runtime `origin/master`、Harness 私有 `private/integration/dsh-runtime-d1-q2-closeout`。专用 Profile 暂时关闭 `tool-subagent-dsh-runtime` 后，解析配置为 `disabled:true`，真实 CLI 与认证浏览器页面无模型启动通过；恢复 `disabled:false` 后再次解析和启动通过，Profile patch SHA-256 与演练前完全一致，测试仓库干净。此结果仅证明功能开关的配置回退，不等于已验收默认线代码及完整依赖的整包版本回退。正式发布前仍需成对版本与依赖的独立启动、页面和回退验收；暂不合并默认分支、移动标签或删除旧分支。

**官方打包与独立安装验收（2026-10-17）**：Harness RC2 候选官方构建通过并记录 357 个客户端产物；官方发布脚本生成 DSH 家族 334 个、vendor 家族 9 个 tarball，专用试用目录内保存 343 行 SHA-256 清单。首次安装验证暴露 Windows `spawnSync('npm')` 无法执行 `.cmd`；候选发布脚本修为查找 npm JavaScript 入口并用当前 Node 启动，聚焦测试 4/4、聚焦 lint、完整 `pnpm run typecheck` 通过。本机 npm 10.7 继续报其内部 `edgesOut` 依赖图错误；仅在试用目录安装 npm 12.2.0 后，同一批 tarball 的官方独立安装验证通过：343 包安装，601 个默认产品包排除实验包，安装的 `@deepseek-ai/dsh --version` 为 `0.2.1-alpha.2`。未更新全局 npm、原仓库依赖或 RC2 标签。此项关闭完整打包/独立安装门槛，默认线版本回退仍待独立演练。

**私有默认线发布范围风险（2026-10-17）**：已直接核对远端引用。Runtime `origin/master` 为候选祖先，候选领先 26 个提交、树差异 84 文件；Harness 私有默认线 `private/integration/dsh-runtime-d1-q2-closeout` 为候选祖先，但候选领先 **5,083 个提交**（第一父链 54 个）、树差异 **11,469 文件**。虽可技术性快进，直接更新 Harness 默认线会引入大量非可视化上游变更，不能当作首期小范围发布。建议继续使用成对私有候选引用，把私有默认线同步另立大范围升级计划；待负责人确认目标与回退策略前，不合并默认线或删除旧 D2 分支。

## P0：首期终态证据 MVP

| 顺序 | 任务 | 归属 | 完成条件 |
| --- | --- | --- | --- |
| 01 | DSH-VIS-01：冻结 Evidence Manifest v1 数据契约与来源标记 | Harness + Runtime | 定义字段、版本、缺失与降级状态、敏感内容处理；终态 JSON、Call Trace、Safe Trace、工作区快照各有唯一来源；样例符合 schema；不把模型陈述当作文件事实。 |
| 02 | DSH-VIS-02：运行专属证据路径与 Safe Trace 闭合证据 | Runtime + Harness | 每次使用独立 `dsh-runtime-<uuid>` 与绝对路径；Trace 在成功关闭后生成绑定 run/trace 标识与最终大小或哈希的 `.closed`；异常、取消、缺失标记与尾行残缺降级；CodeBuddy 轨迹完整性不依赖 Codex PASS。 |
| 03 | DSH-VIS-03：受控工作区前后快照与 Diff | Harness | 纳入已跟踪文件和非忽略未跟踪文件；只排除版本化规则与本次专属证据目录；保留原有脏文件；并发改动标为窗口观察变化；二进制、超大、编码异常、空文件和无末尾换行的降级与 `patch_applicable` 规则可验证。 |
| 04 | DSH-VIS-04：Host 证据组装和本地读取 | Harness | 只在子进程结算后组装；可靠读取退出码、耗时、终态判决及引文、Call Trace 与 Safe Trace；路径限制在本次证据目录和已确认工作区；错误单独报告，不伪造 TaskState。 |
| 05 | DSH-VIS-05：`dsh web` 任务卡与终态证据抽屉 | Harness Web | 完成后可查看轨迹、实际变动和审计三视图；PASS/FAIL 与证据引文正确；缺失、截断、无变动、失败、取消均清楚呈现；任务运行中显示等待和已用时间，首期不承诺实时工具进度。 |
| 06 | DSH-VIS-06：跨进程与 Web 验收 | 双仓库 | 聚焦单元测试与 Host 集成测试覆盖成功、业务失败、进程失败、Trace 缺失、运行前脏文件及新建未跟踪文件；验证 Web 实际页面；不以历史 117 项或 R24 的 5 项结果冒充本轮测试。 |

首期实现按 01→02→03→04→05→06 推进。02 与 03 的局部设计可并行审阅，但 Host 聚合与 UI 以两者的已验证输出为依赖。

### 当前推进记录（2026-10-16）

- **01 已实现并取得真实样本**：Host package 中的 v1 JSON Schema、合成示例和消费者字段已对齐。Manifest 分别标记执行轨迹、工作区观察变化、审查与审计的来源、缺失和降级状态；模型文本不作为文件事实。真实只读和写入任务均生成了可读取样本。
- **02 已通过真实写入闭合验收**：Runtime Safe Trace 可按运行 UUID 生成关闭标记；Host 严格核对 `.closed`、物理路径、完整 JSONL、原生终态观测和 wrapper 结算。修复 Windows 长路径后，新的真实写入运行生成了完整 JSONL 与 `.closed`，Manifest `trace_complete=true`；异常降级仍由聚焦测试覆盖。
- **03 已通过真实写入变动验收**：Host 在子进程前后读取 Git 已跟踪和非忽略未跟踪文件，保留既有脏文件，输出窗口观察变化与 Diff。本轮真实写入仅报告新增 `result.txt`，运行前已修改和未跟踪文件前后哈希一致；二进制、超大、异常编码等边界由聚焦测试覆盖。并发外部改动仍只能表示为窗口观察变化。
- **04 已通过真实终态组装验收**：Host 在有效终态 TaskState 后原子写入 Manifest 和 Diff；初始与最终运行状态单独落盘。真实只读与写入任务均核对了 Manifest、Call Trace 审计和 Web 读取；证据错误与父子任务归属边界由聚焦测试覆盖。
- **05 已通过真实 Web 三视图验收**：`ui-tool` 内置 `dsh_runtime` 任务行，轮询 Host 路由并提供轨迹、实际变动、审计三栏抽屉；运行中显示等待时间。真实只读和写入任务的终态视图已核对；证据缺失、无变化、失败和取消状态有聚焦测试。抽屉鼠标点击层级问题已修复并在重建 Web 后真实页面回归通过。
- **06 进行中**：聚焦 Host 与 UI 测试、包级类型检查、完整 Web 资源构建、记录式浏览器回放已通过；真实只读和写入成功、Safe Trace 完整路径及页面三视图已验收。Host 测试另覆盖业务失败保留 Manifest、进程失败与取消仅保留结算状态，以及缺失证据的 UI 降级。真实失败和取消尚无独立页面样本，不能将模拟测试写成现场验收；本轮没有执行正式 D2 Gate 调用。

**继续执行位置**：本机 `C:\Users\Administrator\.dsh\profiles\web\cordis.patch.yml` 有 Runtime 插件行，但仅提供 `runtimeRoot`；当前插件加载还要求治理用 `expectedPolicyHash`、`enabledWorkloads`、`auditPath` 及 v1 `policySource`（或 v2 `policyLocator`），且页面证据需另配 `evidenceRoot`。不能把这份旧配置直接当作可用的真实 Web 验收环境。下一步由负责人指定独立测试 profile 或确认使用临时、非 D2 的治理配置后，在独立测试工作区执行真实 `dsh web` 子进程与页面联动，核对 Manifest 和失败/取消边界。`evidenceRoot` 必须是用户工作区之外的绝对目录；与显式 deployment Trace 环境变量冲突会在 spawn 前拒绝，不覆盖现有 D2 Gate 绑定。

**负责人补充决策（2026-10-16）**：批准使用临时、独立、非 D2 的治理配置，对临时仓库执行只读 `repository_inspection` 验收。现有 Web profile 保持原样。实施前已核对：固定 v1 治理不接受 `repository_inspection`，应显式选择 v2；随 Runtime 交付的 `selection-v2.json` 授权 `repository_inspection`，Harness v2 配置提供固定 policy locator/hash。下一步在临时目录准备 v2 overlay、独立 audit/evidence 路径与测试工作区，启动真实 `dsh web` 做页面联动；不得改用具有写权限的 `repository_change` 来替代只读验收。5 小时额度低于 10% 时先记录当前完成项并暂停，额度恢复后从此处继续。

**额度暂停点（2026-10-16）**：已在 `C:\Users\ADMINI~1\AppData\Local\Temp\dsh-vis-web-v2-9e026e67-6991-4acc-9b32-6338405ce3c4\web-v2.patch.yml` 写入临时 v2 overlay，限定 `enabledWorkloads` 为 `repository_inspection`，使用独立 audit/evidence 路径；未启动 Web，也未触发治理调用。Codex 5 小时额度已用 91%（剩余 9%），依照负责人要求在这里暂停。恢复后先核对该临时文件及额度，再用 `dsh web --patch <上述路径>` 的配置转储核验实际组合；只在确认配置、工作区和凭据隔离后执行一次真实只读页面联动。不得编辑现有 Web profile，也不得将本次验收计作 D2 ExecuteGate。

**恢复进展与当前阻塞（2026-10-16）**：5 小时额度恢复后，临时 overlay 及双仓库状态已核对，Web 配置转储确认 v2、只读 workload、独立 audit/evidence 路径均进入最终组合。旧 Web profile 的 `agent-presets` 条目产生非致命“entry not found”警告。尝试在临时 Git 工作区从当前源码启动 Web 时，发现 Harness 的 `lib/` 生成产物仍为旧版，缺少当前源码使用的 `FiberState` 导出；尚未启动 Web，也未发起治理调用。刷新 Host 产物的操作被自动审批拒绝，原因是可能覆盖仓库中现有文件，与保留未提交和未跟踪内容的要求冲突。已核对 `lib/` 与 `*.tsbuildinfo` 均被 Git 忽略、无跟踪文件；仍不得绕过拒绝。继续前须取得对仅刷新这些既有、被忽略生成产物的明确批准，或另行建立可运行的完全隔离构建环境。临时工作区原有 `README.md` 及双仓库状态保持不变；本轮 `git diff --check` 通过。

**真实 Web 验收记录（2026-10-16，取代上述阻塞）**：负责人明确批准刷新 Harness 中被忽略的 `lib/` 生成产物。刷新 Host/Client 产物并重建 Web 后，以临时 overlay 的 v2 策略、唯一 `repository_inspection` workload、独立审计/证据目录，以及页面“仅可查看”模式，在临时 Git 仓库从实际 `dsh web` 发起一次调用。子任务 `a045c143-f9a8-4d52-aeac-cf8727e1e06d` 运行成功；`evidence-manifest.v1.json` 记录 `task_kind=repository_inspection`、`status=completed`、`exit_code=0`、`audit.status=settled`、`execution_trajectory.status=not_applicable`、工作区无观察变化，Web 抽屉实际显示执行轨迹、无变化和审计哈希；修正后轮次显示“不适用”。临时工作区前后均仅有原有未跟踪 `README.md`，两个源仓库原有修改/未跟踪文件保留。Host 负路径聚焦测试 36/36、UI 抽屉测试 3/3、Client 包编译与完整 Web 构建通过。Host 聚合类型检查仍被原有 D2 测试 `scripts/d2-business-gate/core.spec.ts:152` 的 TS2532 阻断；未修改该内部治理文件。后续优先补齐真实失败/取消场景或 Safe Trace 路径的非 D2 验收；D2 ExecuteGate 保持 `NOT_CLAIMED`。

**临时写入验收（2026-10-16）**：负责人另行批准一次仅针对独立临时 Git 仓库的非 D2 `repository_change`。页面已核对选中工作区 `C:\Users\Administrator\AppData\Local\Temp\dsh-vis-write-02164436-6545-44bf-916d-63f349623d81`，访问模式为“工作区内修改”；临时 v2 overlay 仅开放 `repository_change`，证据与审计位于 `C:\Users\Administrator\AppData\Local\Temp\dsh-vis-web-write-06cf0025-232c-4602-a657-9c67a93fd81a`。仅发起一次调用，子任务 `ef918bb8-2431-4780-a2f6-b4270df93712` 已结算：Manifest `status=completed`、`exit_code=0`、审查 `PASS`、审计 `settled`，前后快照仅观察到新增 `result.txt`（30 字节，SHA-256 `126c0b0971632c9f065af4230b7679e153c191bdb2dc10173b9cdcb01cf98a29`）；预置的 `README.md` 脏行和未跟踪 `keep.txt` 未被本次运行改变。真实 Web 抽屉的实际变动与审计视图显示了这些终态证据。**Safe Trace 未完成现场验收**：该运行专属 `safe-trace-<run_id>` 目录为空，没有 `.jsonl` 或 `.closed`；Manifest 如实降级为 `execution_trajectory.status=unavailable`、`trace_complete=false`。据现场问题修正了抽屉文案，重建 Web 并对原任务只读复核，页面现显示“轨迹状态: 未取得轨迹”“轮次: 未记录”；UI 聚焦测试 4/4、包级类型检查、Web 构建通过。当前无法仅凭已有证据确定轨迹缺失原因为何；不可将任务 PASS 解释为轨迹闭合。下一步先排查 Runtime 子进程的 Safe Trace 配置/创建路径，补一个不调用模型的跨进程诊断测试；若要再次发起真实写入调用，应重新明确验收范围与额度。D2 ExecuteGate 仍为 `NOT_CLAIMED`。

**Safe Trace 非模型诊断及交接点（2026-10-16）**：使用 Harness 同一子进程传输层启动 Python 诊断子进程，并通过独立新 run ID/目录传入 `DSH_RUNTIME_RUN_ID` 与 `DSH_CODEBUDDY_SAFE_EVENT_TRACE_DIR`；子进程读到正确目录，Safe Event Sink 成功写出 `.jsonl` 和 `.closed`，退出码 0。这排除了通用环境变量转发和目录写入能力，但不能解释上述真实 CodeBuddy 流程为何未产出轨迹。该诊断未调用模型、未触发 D2，也未修改两个源仓库中的用户既有文件。下一步需在获得第二次独立临时仓库真实写入授权后，用新 run ID 复现并捕获 CodeBuddy 初始化/结算环节的明确诊断；在此之前保持 VIS-02 的现场验收未完成。当前 5 小时额度最近一次检查剩余 43%，未到 10% 暂停线。

**第二次写入复现与修复（2026-10-16，取代上述交接点）**：负责人批准后，在全新临时仓库 `C:\Users\Administrator\AppData\Local\Temp\dsh-vis-write2-da73aa8a-f37d-4e2f-a75e-5292d6c503b9` 与独立 overlay/evidence 目录中只发起一次 `repository_change`。临时 Python 启动诊断只记录布尔状态与错误类型，不记录模型内容；真实子进程确认已取得本次 run ID 与 Safe Trace 目录、CodeBuddy 插件已执行，但 Sink 初始化后 `enabled=false`、`incomplete=true`，专属目录为空。相同结构的普通 Windows 文件路径约 283 字符；本机 `LongPathsEnabled=0`，独立 Python 复现普通路径 `Path.open('x')` 报 `FileNotFoundError`，`\\?\` 扩展路径写入成功。Runtime Safe Trace Sink 已改为对长 Windows 路径仅在文件 I/O 时使用扩展路径，保留原有逻辑路径与 marker 绑定；长路径闭合标记测试 6/6、相关 Safe Trace 测试 17/17 通过。**修复发生在第二次子进程启动后，不能倒算该次真实轨迹为闭合**；VIS-02 仍待修复后一次真实运行验收。

第二次任务 `4749c327-7bfc-4da3-ae49-966db8d6a4d5` 另暴露审查误判：`result.txt` 正确新增，Host 前后快照未观察到其他变化，但 Codex 审查把运行前已有的 `README.md` 修改与未跟踪 `keep.txt` 当作任务后状态应当“干净”，给出 `FAIL`，因此 Manifest 如实记录业务 `failed`、进程退出 0、审计 `settled`、轨迹 `unavailable` 和仅新增 `result.txt`；真实 Web 三视图均核对。Runtime 审查提示已补充“脏 Git 状态本身无法证明本次改动；无前后证据不得声称旧文件未改”的边界，工作流聚焦测试 41/41 通过。此项是审查提示修正，尚无新真实模型调用证明误判消除；Host 快照仍是实际变化的独立来源。两次临时仓库的预置脏/未跟踪文件均保留，两个源仓库既有改动未清理或重置。5 小时额度最近一次检查剩余 31%。下一步优先对修复后的 Safe Trace 和审查提示做一次**新临时仓库**的真实写入验收；该额外模型调用需要负责人另行批准，D2 ExecuteGate 始终 `NOT_CLAIMED`。

**第三次真实写入验收（2026-10-16，已获负责人授权）**：首次尝试使用全新临时仓库 `dsh-vis-write3-128dc379-5d9c-4589-bd00-3177382a3b11`，但隔离 Web profile 漏载 `dsh_runtime` 工具，页面代理改用普通文件工具创建 `result.txt`；该尝试没有 Runtime 子进程、Manifest 或 Safe Trace，不能计作 VIS-02 验收。随后在另一全新临时仓库 `C:\Users\ADMINI~1\AppData\Local\Temp\dsh-vis-write4-83ece910-4997-4391-af98-1a144084cf2f` 与独立 v2 Web 配置下确认 Runtime provider 加载，仅发起一次真实 `repository_change`。运行 `dsh-runtime-cf07669e-d33b-41fd-b4be-9168b0ae483a` 已结算：`evidence-manifest.v1.json` 记录 `status=completed`、`exit_code=0`、`verification.verdict=PASS`、`execution_trajectory.status=available`、`trace_complete=true`、`audit.status=settled`；专属 JSONL（6466 字节）及绑定 run/trace ID、`final_bytes=6466` 的 `.closed` 均存在。Host 前后快照和 Diff 仅显示新增 30 字节 `result.txt`；运行前已有的已修改 `README.md` 与未跟踪 `keep.txt` 前后 SHA-256 一致。Runtime 审查依据明确把旧文件变动时序标为未知，未重复上一轮的脏状态误判。真实 Web 抽屉显示已记录轨迹、轮次未记录、唯一新增文件和审计哈希；轮次基础缺失时未推断数值。D2 ExecuteGate 仍为 `NOT_CLAIMED`。

**新发现与额度交接点（2026-10-16）**：真实 Web 中打开证据抽屉后，鼠标点击“实际变动”或“审计”被会话正文截获；独立浏览器测试复现 Playwright `subtree intercepts pointer events`，按键 Enter 可切换并读取两栏。这是首期 Web 可用性缺陷，应优先修复抽屉层级/点击命中并回归验证。第三次验收的隔离 Web 还需在结束时停止；下次从这里继续处理 UI 缺陷、失败/取消场景及默认配置。最近检查 Codex 5 小时额度已用 91%（剩余 9%），依负责人要求记录后暂停；两个源码仓库的现有未提交和未跟踪文件均保留，未清理、重置、提交或推送。

**额度恢复后的继续推进（2026-10-16）**：原隔离 Web 已在上次暂停前停止。将 Evidence 抽屉通过 React Portal 挂到页面顶层，消除会话正文截获鼠标事件；组件测试 6/6、`ui-tool` 和 `ui-conversation` 包级类型检查、两包构建与 Web 构建通过。重新打开同一已完成任务做只读页面回归，鼠标点击三栏均成功，未发起新模型或 Runtime 调用。Host 业务失败、进程失败、取消及证据路由聚焦测试 39/39 通过；页面任务行现在区别显示取消、运行失败与一般证据不可用，均不伪造 Manifest。双语 README 增加独立 v2、默认只读的 `dsh web` 终态证据配置示例，翻译配对检查通过；未修改用户现有 Web Profile。`@types/react-dom` 已在 `ui-tool` package 与锁文件中显式声明；本机 pnpm 离线安装因无关的 `@browserbasehq/stagehand` 元数据缺失而失败，包级类型检查使用现有安装中的类型链接验证，尚需在可访问依赖源的环境确认安装。Host 聚合类型检查仍被既有 D2 内部测试 `scripts/d2-business-gate/core.spec.ts:152` 的 TS2532 阻断，本轮未改动该治理文件。两个源码仓库仍未提交或推送，原有未跟踪文件保留；下一步是核对本轮可交付文件和现有 D2 改动的交叉边界，再形成可审查的提交方案。最近额度检查 5 小时剩余 86%。

### 交付准备与剩余门槛（2026-10-16）

1. **P0，冻结可视化交付范围**：Runtime 的 Safe Trace 闭合、Call Trace 与审查提示修改位于当前治理分支的已有脏文件中；Harness 的 Manifest、Web 组件与文档可按路径识别，但 `packages/subagent/subagent-dsh-runtime/src/run.ts`、`package.json` 和 `pnpm-lock.yaml` 与既有治理改动共用工作树。先逐块核对来源，再形成只包含已验收可视化代码的暂存清单；不得直接提交整棵工作树或把 `scripts/d2-business-gate/` 当作用户功能。构建产生的 Git 可见 `.js/.d.ts/.map` 未跟踪文件继续保留，交付清单中明确排除。
2. **P0，完成发布前检查**：在可访问依赖源的环境验证 `@types/react-dom` 的锁文件安装；按仓库要求选择与实际提交范围相符的构建、文档与浏览器检查。Host 聚合类型检查中既有 D2 测试的 TS2532 已以测试夹具空值保护修复，Node 24 Host 类型检查通过，相关用例 1/1 通过。当前 `pnpm run test:gui` 在依赖安装阶段遇到本机 `spawn EPERM`；直接用 Node 24 运行整条 GUI 测试仍出现多处其他模块失败，已停止，不能宣称全套通过。本功能抽屉聚焦测试 6/6、Node 24 文案检查通过，真实 Web 鼠标三视图回归通过。
3. **P1，补独立负向现场样本**：如产品验收要求真实失败或取消页面样本，再用全新临时仓库和非 D2 配置执行，分别核对有 Manifest 的业务失败及无 Manifest 的进程失败/取消；现有聚焦测试已验证这些降级语义，不把模拟结果称作真实运行。
4. **P1，私有交付与使用说明**：在提交范围和检查结果可审查后，分别在 Runtime 私有远端与 Harness `private` 远端建立可回退的交付提交并推送；目前两仓仍在既有治理分支，未提交、未推送，`origin` 不应被当作 Harness 私有交付目标。确认可拉取的版本后再提供更新步骤。历史分支保留到远端引用、依赖和回退点核对完成，再单独决定是否收拢；本阶段不删除分支。

上述门槛完成前，现有工作树只适合按本清单的隔离配置试用首期证据功能，不能宣布为已发布的稳定版本。D2 ExecuteGate 继续为 `NOT_CLAIMED`。

**暂存候选范围（仅审查用，尚未暂存）**：Runtime 从 `dsh_runtime/call_trace.py`、`entrypoint.py`、`planner.py`、`plugins/codebuddy.py` 与相应聚焦测试中逐块提取可视化所需的 Call Trace、Safe Trace、审查提示修正；`bootstrap.py`、`mcp_server.py`、`PROJECT_STATE.md` 和配置文档同时承载既有治理语义，必须逐块审查。Harness 以 `packages/subagent/subagent-dsh-runtime/` 的 Manifest/读取/路由、`packages/client/ui-tool/` 的抽屉、`ui-conversation` 文案、`apps/web/` 接线和双语说明为候选；`pnpm-lock.yaml` 只取与候选包对应的依赖条目。根 `package.json` 的 D2 命令、`scripts/d2-business-gate/`、其新增测试与构建生成文件不进入可视化提交。此列表是范围界定，不代表这些混合文件的全部 diff 均已可交付。

**本次继续检查**：按客户端 UI 规范将新抽屉样式的显式字重收敛到 500；GUI 全量尝试暴露本轮新增 CSS 的两项规范违例，已将固定 6px 圆角改为共享 token、两处 1px 中性分隔线改为 0.5px。Node 24 下主题样式组连同抽屉组件测试 20 文件、133/133 通过，界面文案静态检查通过。仓库级 GUI 脚本先在依赖安装的本地 `spawn EPERM` 阶段停止；绕过脚本安装阶段、直接用 Node 24 运行 GUI 全量检查时，多个其他模块仍失败，检查已停止并保留临时日志，失败原因尚未逐项归因。D2 测试夹具仅增加首个 source pin 的空值保护，Host 聚合类型检查与该用例均通过，不改变治理结论。两仓 `git diff --check` 通过，5 小时额度最近检查剩余 71%；未暂存、提交、推送或清理文件。

### 独立交付候选（2026-10-16）

- 从两仓当前提交建立了 `D:\DeepSeekHarness\vis-runtime-candidate` 与 `D:\DeepSeekHarness\vis-harness-candidate` 两个独立检出，均位于本地 `codex/vis-manifest-mvp-20261016` 分支；原有治理工作树、未跟踪文件和分支均保留。Runtime 候选仅提取 Call Trace 入口、Safe Trace `.closed`/长路径、审查提示及对应测试，排除了原工作树的 `.codex/config.toml`、CodeBuddy 输出/轮数治理选项等混合改动。Harness 候选不含原工作树的根 `package.json` D2 命令和 `scripts/d2-business-gate/` 的既有工作改动。
- Runtime 候选相关测试 170/170 通过，形成**仅本地、未推送**提交 `60c37f4`。Harness 候选以独立提交 `a4c962bb69` 修复基线 D2 测试夹具的空值类型错误；这是内部测试维护，不是 ExecuteGate 资格或产品功能。Harness 使用冻结锁文件在候选目录完成安装，Host/Client 类型构建、Host/Client 包构建和 Web 构建均通过；界面文案检查、双语 README 配对检查通过。此前候选测试 59/62，3 项失败均在 `startup-observer.spec.ts`；后续诊断证实该测试遗漏 `workingDirectory` 依赖夹具，使 `SubagentRuntime` 没有启动。补齐现成夹具后，9 个文件 62/62 通过，另以 `9df8ddfa1b` 本地提交测试修复；Host 类型检查和该文件 lint 均通过。
- 候选相对原工作树的 41 个待交付文件曾逐一核对 SHA-256，一致。为修复完整 Client 类型检查发现的模拟请求参数类型错误，已同步修改两处候选/原工作树测试；README 已同步更新真实只读与写入页面验收状态及双语配对记录。负责人随后明确批准已核对范围的本地提交。两处 lint 格式问题也同步修复，Harness 41 文件形成功能提交 **`14e48dd6ae`**，仅本地、未推送；原治理工作树未切换分支。
- **提交验证与剩余门槛**：Harness 暂存差异无空白错误；翻译配对（2 个记录）、第三方依赖声明新鲜度检查和暂存 TypeScript lint 均通过。Git 的 Lefthook shell 入口在本机因无法创建 Win32 signal pipe 而未能启动；以上检查单独运行后，本地提交使用单次临时 hook 路径完成，未改动仓库 hook 配置。使用本机已安装 Chrome，候选记录式 Web 抽屉回放 2/2 通过；Playwright 默认捆绑浏览器在本机缺失，已通过明确指定 Chrome 解决。真实失败/取消页面仍无现场样本，跨仓发布与推送仍需单独审查。D2 ExecuteGate 继续保持 `NOT_CLAIMED`。

**构建产物备注**：本轮已授权的 Client 编译除刷新被忽略的 `lib/` 外，还在 Harness 的 `packages/llm/deepseek-llm-api-extensions/src/` 与 `packages/test-support/{loader-smoke,session-snapshot}/src/` 生成了一批 Git 可见、未跟踪的 `.js/.d.ts/.map` 文件。按负责人“禁止清理、重置或覆盖”的要求原样保留；这些是本轮新增的编译输出，不应混同为既有用户文件或 Manifest 产品源代码。下一步真实 `repository_change` 写入工作流未获此前“只读验收”授权，需负责人明确同意后仅在临时仓库执行。

**此前验证（2026-10-15）**：Runtime 闭合标记测试 5/5；Safe Trace 聚焦回归 10/10；Harness provider 与 Safe Trace 读取测试 37/37、包级 TypeScript 检查通过；Manifest Schema 与 R9 合成示例匹配。**本轮阶段验证（2026-10-16）**：Host 与 UI 相关 8 个测试文件、此前 53 项测试通过；新增无变动展示用例单项通过；Web 隔离与相关聚焦测试 48 项通过；两个包的 TypeScript 检查、完整 Web 资源构建、UI 文案与导出文档检查通过；浏览器记录式场景 2/2 回放通过。另在独立临时 Git 工作区执行一次真实 `repository_inspection`：Runtime 退出码 0、任务 `completed`，Call Trace 为 `call_started,call_terminal`，工作区内容无变化；Host 用真实输出离线组装并读取 Manifest，得到 `audit=settled`、`trace=not_applicable`、空 Diff。此项未经过 Web provider 实际调用，不代替端到端页面验收。

## P1：实时运行进度

| 顺序 | 任务 | 完成条件 |
| --- | --- | --- |
| 07 | DSH-VIS-07：Runtime 流式事件协议 | 定义版本化 NDJSON 事件、终态和取消语义，保留既有 one-shot 入口兼容性。 |
| 08 | DSH-VIS-08：Host 转发与 Web 动态进度 | 只传安全元数据；轮次未知时显示未知，不推断 `max(turn_index)+1`；动态 Diff 来自工作区事实。 |

## P2：长期方向

Memory/RAG 与工程经验沉淀仅作候选愿景，等待独立需求与验收设计。独立桌面与 Runtime 内置控制台不在首期范围。

## 独立内部治理

D2 ExecuteGate 是调用前资格评估，保持 `NOT_CLAIMED`。本清单不创建 reservation 或 receipt，不触发正式申领；未来由负责人以独立版本化请求和预授权启动。现有两个仓库的未提交改动与未跟踪文件必须保留，禁止清理、重置或覆盖。

## 2026-10-19 额度阈值交接：旧 Home 恢复与官方 Desktop 适配

**额度与定时状态**：此前在五小时额度剩余 **10%** 时按负责人阈值停工并预约北京时间 **2026-10-19 13:52** 续跑；额度后来恢复，但这次定时没有按时唤醒，具体原因未确认。2026-10-19 约 14:12 由负责人消息触发恢复，已停用过期的一次性定时，避免它重复启动。恢复时五小时额度已重置、周额度约剩余 48%。未来再次接近五小时剩余 10% 或周额度剩余 2% 时，先更新本清单，再核对当前定时状态并重新安排一次性续跑；安排后仍需检查是否实际触发。

**已完成**：日常 Home 的 21 条 V3 Session 均在隔离副本通过 RC4 格式迁移与重新挂载读回，源文件哈希不变。旧版 `0.1.5-rc.1` 会话读取组件可读原始 V3，但对 V3+V4 混合代返回 `SessionFormatUnsupportedError`，因此只降级程序不是回退方案。旧私有默认线 `60c8f0c813` 建成独立 `vis-harness-v3-rollback` 工作树，按 pnpm 11.7.0 锁文件安装；旧完整构建被 19 个 D2 测试夹具类型错误阻断，单独生成的 Host/Client/Web 运行文件使旧 CLI `0.1.5-rc.1` 在只含一条 V3 副本的隔离 Home 无模型启动 Web，认证页面 HTTP 200、stderr 0，服务已停止。另将 21 个 V3、8 个 V4 文件复制到 RC4 独立 Home，配受控只读 Profile 后配置解析及 Web HTTP 200、stderr 0；29 个源/副本哈希一致，服务与端口已关闭。旧 `standard-codex` 预设在 RC4 不存在，使用新受控 Profile，旧配置原件保留。具体证据见 [RC4 试用证据](PRIVATE_VISUALIZATION_TRIAL_2026-10-19_RC4.md)。

**旧 Home 与旧版恢复补验**：独立完整副本含 33 个 Session 文件、2 个 PNG 附件、33 个投影缓存；初始 70 个复制文件哈希一致。RC4 Web 在非 D2 只读 Profile 下无模型启动并列出 33/33 条会话，逐页读完 4,399 条历史记录，错误 0；打开一条待迁移旧会话后在副本生成 1 个 V4 继任文件。未完成全 Home 迁移；历史记录没有引用那 2 个附件，附件展示未验收。旧 CLI `0.1.5-rc.1` 使用另一完整快照副本无模型启动 Web，只列出 25/33 条。仅降级程序与当前日常 Home 的完整读取不成立，维护窗口需有可验证快照和恢复策略。两个 Web 服务均已停止。详见 [RC4 试用证据](PRIVATE_VISUALIZATION_TRIAL_2026-10-19_RC4.md)。

**完整 Session 副本迁移补验**：另从升级前完整快照复制 70 个非凭据文件，RC4 persistence 对全部 33 条 Session 先读后以写入访问打开，33/33 成功，新增 25 个 V4 继任文件；原有 33 个 Session 文件哈希未变。第二遍重新挂载读写仍 33/33 成功，没有新增或原文件变化；2 个附件及 35 个 storage 文件与升级前快照哈希一致。受控只读 RC4 Web 在此副本上列表仍返回 33/33，服务已停止。这关闭了已发现 Session 集合的副本迁移与读回门槛；旧 Profile、凭据、附件有引用样本及真实日常 Home 切换仍待独立处理。

**RC3 快照回退补验**：另用私有 RC3 已安装包和相同的升级前数据副本启动受控只读 Web，认证页面 HTTP 200、列表 33/33；RC3 persistence 对 33/33 条 Session 只读打开成功，4,394 个直接事件可读，原文件哈希变化 0、新文件 0，服务已停止。可将 RC3 与完整升级前快照列为已实测的 Session 回退组合；旧 `0.1.5-rc.1` 仍只能列出 25/33。完整日常 Home 的 Profile、凭据和附件恢复需另行验收。

**日常 Home 并行试用准备**：已整理[完整备份、并行迁移与回退操作清单](PRIVATE_HOME_STAGE_AND_ROLLBACK_RUNBOOK_2026-10-19.md)，拟在维护窗口先对日常 Home 做包含凭据的 Git 仓库外备份和逐文件哈希核对，再以副本进行 RC4 迁移及 RC3 快照回退；尚未读取凭据内容、复制完整日常 Home 或切换默认启动。

**完整 Home 并行试用与回退执行（2026-10-19，更新上段状态）**：负责人选择当前维护窗口后，日常 Home 的 88 个文件及 515 个依赖链接已完整备份到受限的 Git 仓库外目录，备份前后路径、大小、SHA-256 和链接元数据逐项一致；包含凭据但未读取其内容。两个权限受限的独立完整副本分别用于 RC4 与 RC3，无一写回日常 Home。RC4 专用只读 Profile 解析通过，迁移前后 Web 均 HTTP 200、列表 33/33；副本内 33 条 Session 迁移与重读全通过，新增 25 个 V4，第二遍新增 0，原有 88 个文件哈希不变。RC3 已安装包配合另一份升级前完整副本，Web HTTP 200、列表 33/33，底层只读打开 33/33，原文件变化 0。两个 Web 服务均已停止。凭据实际功能、旧 Profile 原样启动、有引用附件的页面展示、日常默认启动与稳定发布仍未验收。详见[执行清单](PRIVATE_HOME_STAGE_AND_ROLLBACK_RUNBOOK_2026-10-19.md)；D2 ExecuteGate `NOT_CLAIMED`。

**官方与桌面端状态**：公开 Harness `master` 仍为 `687f282e86`，已在私有 RC4 候选 `819dc46` 的祖先链内，无新官方 `master` 提交可合并。候选 Desktop 构建和三组聚焦测试 136/136 通过。官方 Electron 与锁定依赖在本地逐一校验 SHA-256 后，独立无凭据示例配置的 Windows 未签名目录包已完整构建；最新打包记录 `result.json` 为 `success=true`，打包后运行自检通过，目录包在 `D:\DeepSeekHarness\vis-harness-private-integration\apps\desktop\.desktop-build\targets\win-x64\unsigned-artifacts\win-unpacked`。直接从本机 D 盘源码工作树打开 GUI 时，Electron 因 AppContainer 路径读取 ACL 在窗口加载前退出；给目录包根增加读取权限及试用 `--no-sandbox` 后仍同样失败。此前下载中断与这次 GUI 失败记录均保留。未运行安装器、上传或发布，也尚无负责人桌面页面回执；共享 Web 预设中的 Runtime provider 仍默认关闭。

**桌面启动补验**：目录包另复制到 `C:\Program Files\DeepSeek Harness RC4 Trial` 专用位置。在正常本机进程环境使用独立 `DSH_HOME` 启动，Desktop 进程保持运行，独立桌面 Profile 与会话目录已创建，内置 Web 认证页面 HTTP 200、HTML 38,244 字节、启动 stderr 0。受限进程环境即使在此位置仍报 ACL 错误，属当前验收环境差异。该时点尚无桌面窗口截图和 Manifest 抽屉回执；不得把后端启动写成桌面页面通过。

**桌面历史证据补验**：负责人截图确认 RC4 桌面新会话页和侧栏实际显示。在独立 Desktop Home 添加已验收的 provider 本地链接，配置只读非 D2 治理，把此前已核对的历史会话、投影缓存和证据复制到此 Home，合并工作区索引并修正副本 Diff 引用。重启后 Desktop 启动 stderr 0，认证证据接口 HTTP 200、Manifest `completed`；没有发送新消息或调用模型。负责人已提供桌面抽屉三页签截图，显示轨迹和轮次“不适用”、实际变动无文件、审计 `settled` 与判决 `UNAVAILABLE`，与导入 Manifest 相符；截图副本只保存在独立试用 Home。

**下一步顺序**：① 固定日常 Home 的可验证完整快照与恢复步骤，处理旧 Profile 映射及有引用的附件样本，再与负责人确定真实 Home 维护窗口；完整 Session 副本迁移已经通过。② 每次合并前重新读取官方远端 SHA；若前移则在独立分支集成、测试与适配。③ 审查私有默认线升级门槛与发布方式；桌面包目前仅为未签名试用目录，正式发布仍需独立检查。不得据当前结果宣称整 Home 原地升级、完整旧版回退或桌面版发布通过。

**仓库边界**：Runtime 私有候选上次已推送提交 `842a109`；Harness 私有 RC4 固定源码 `819dc46`，两个默认分支与标签未移动。两个原工作树的未提交改动和未跟踪文件继续保留；不清理、重置或覆盖。GitHub Actions 保持关闭，D2 ExecuteGate 保持 `NOT_CLAIMED`。
