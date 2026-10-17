# DSH Runtime 运行可视化开发任务

状态：已批准的 R9 设计基线之实施清单（2026-10-15）。设计依据：[PROJECT_TARGET_AND_RUNTIME_VISUALIZATION.md](PROJECT_TARGET_AND_RUNTIME_VISUALIZATION.md)。四项负责人决策均选 A。

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
