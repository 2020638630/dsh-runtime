# 私有默认线升级审查与运行可视化发布顺序

状态：2026-10-18 的**审查计划**，尚未移动默认分支或发布稳定版。依据 [R9 设计基线](PROJECT_TARGET_AND_RUNTIME_VISUALIZATION.md)、[任务清单](RUNTIME_VISUALIZATION_BACKLOG.md)与 [RC3 验收记录](PRIVATE_VISUALIZATION_TRIAL_2026-10-18_RC3.md)。D2 ExecuteGate 继续为 `NOT_CLAIMED`。

## 固定输入与实际差异

| 引用 | 本地已核对提交 | 作用 |
| --- | --- | --- |
| Harness 私有默认线 `integration/dsh-runtime-d1-q2-closeout` | `60c8f0c813a55754338d1e53a655f480a5f62f02` | 当前用户可拉取的既有私有默认线 |
| Harness 公开上游 `origin/master` | `687f282e8625c6b8d11ff58211a90524be2e4317` | 2026-10-18 现场远端查询也指向此提交 |
| Harness 固定 RC3 标签 `vis-manifest-mvp-20261018-rc3` | `a6e8d20476450be8c48b27e310d760034610b15a` | RC3 精确验收来源，未随候选分支前移 |
| Harness 私有候选 `codex/private-consolidation-20261017` | `819dc46ea7953598b239a82e25abe7d87c64add3` | 当前私有远端与 RC4 试用源码；静态、打包安装和无模型 Web 入口已复验 |
| Runtime 私有候选 `codex/vis-manifest-mvp-20261016` | `f4bb685056c0f52f7f22dd18cddd8b3fb1c10034` | 本轮审查开始时的远端头部；后续审查文档提交继续前移 |
| Runtime 既有默认线 `master` | `ebb191ae998af6251731f02e28ba16d4ce733fac` | 尚未移动 |

**2026-10-19 来源复核**：公开上游 `master` 仍为 `687f282e86`，Harness 私有默认线仍为 `60c8f0c813`，Runtime `master` 仍为 `ebb191ae99`，均未漂移。按当前 Harness RC4 `819dc46` 对私有默认线的精确提交范围为 **6080 个提交、12929 个路径**；对公开上游为 **64 个提交、241 个路径**。这取代下段 RC3 的 6077/12927 和 61/236 统计口径。Git 报告大差异未做穷尽的重命名检测，路径数是当前 `diff --name-only` 口径，不能当作语义变更数量。

Harness 候选同时包含私有默认线和公开上游。与私有默认线相比，它领先 **6077** 个提交、涉及 **12927** 个文件；与当前公开上游相比，它领先 **61** 个提交、涉及 **236** 个文件。私有默认线与公开上游并非线性关系：两者共同祖先之后，私有默认线独有 2 个提交，上游独有 6018 个提交。`dae159ae1f` 把截至公开上游 `d743267388` 的一波更新并入了 D2 整合，`77cbead5fc` 再把上游 `687f282e86` 并入可视化候选。因此直接快进私有默认线会一次交付大量上游变化及 D2 内部治理代码，不能作为单一 Evidence Manifest 更新审查。

本轮受限环境内首次刷新私有远端时，Git 凭据辅助程序无法启动，Runtime TLS 凭据也不可用。随后通过已授权的正常 Git 远端访问重新读取三条私有分支及公开上游：SHA 均与上表一致，**截至这次查询无来源漂移**。发布分支或标签时仍须以远端原 SHA 为并发保护，避免查询后发生竞态更新。

**路径级审查结果**：以公开上游到 Harness 候选的差异为口径，`.agents`、`scripts`、`.github`、`docs` 合计 114 个文件（约 8230 行新增）；三个 Runtime 相关 subagent 包合计 42 个文件（约 7597 行新增）；Web/CLI、工具行及 DeepSeek 适配合计 27 个文件（约 3130 行新增、55 行删除）；根锁文件、桌面、bundle 与 boot 等 11 个文件（约 814 行新增、289 行删除）。这些是有交叉可能的审查分组，不能相加当作 236 个文件的完整分割。`packages/subagent/subagent-dsh-runtime` 和 `subagent-governance-python` 的包版本已是 `0.2.1-rc.2`。候选 `.github/workflows/ci.yml` 对私有仓库改用托管 runner，并让 Python release 形态矩阵与 benchmark 在私有 PR 中跳过；`.github/workflows/release.yml` 仅允许私有仓库手动触发发布演练。因此当前本地通过的构建、测试与打包不能代替这些被跳过或仅手动运行的远端门槛。默认线切换前须逐项确认私有 CI 的实际必需检查，明确未跑的检查由哪一项证据补足或保留为发布限制。

**上游分批可行性**：对公开上游 `687f282e86` 与私有默认线 `60c8f0c813` 做只读三方合并探测，结果有三个冲突：`docs/config-catalog.md`、已被上游删除的旧 `packages/preset/agent-presets/presets/standard/agent.cordis.yml`、`pnpm-lock.yaml`。旧默认线在该已删除预设中新增的只是默认关闭的 `tool-subagent-dsh-runtime` 行；当前候选已将默认关闭的工具行移到新布局 `packages/bundle/web-app/presets/standard.patch.yml`。因此若建立“先上游、后产品”的新集成分支，应保留上游删除、在新预设位置保留 opt-in 工具行，随后按新依赖重新生成锁文件和配置目录，并核对生成内容。不能把三方合并的自动产物直接作为可用升级批次；本探测没有写入任一工作树。

**独立预备分支验证**：另建 `D:\DeepSeekHarness\vis-harness-upstream-stage`，本地分支 `codex/private-upstream-stage-20261018` 从公开上游出发，合入旧私有默认线并解决上述三处文本冲突；配置目录双语生成、锁文件重新计算，旧预设工具行迁至新 Web 预设且继续默认关闭。旧 provider 的目录校验与测试夹具适配上游服务 API。聚焦 provider/bridge/Web 测试 **54/54**，`build:artifacts` **7/7**，Host 与 Client 类型检查均通过，配置目录校验通过。此分支仍保持**本地、未提交的合并状态**，没有推送或用于试用；它是升级拆分的审查实验，不是 RC3 或新的可用版本。

文档总检查在该预备分支为 **35/43**，余下 8 项失败，集中在旧默认线带来的 `AGENTS.md` 篇幅/段落、Runtime README 缺中文配对且文档种类仍为旧值、旧 Agent Note 状态/双语记录、插件包目录生成及仓库引用校验。配置目录本身已通过生成器检查。要发布独立的上游批次，须先完成这批旧文档迁移并重新通过 43 项检查；直接复用已经完整通过验收的 RC3 候选，仍是当前更短的试用路径。预备分支的失败不倒推 RC3 候选的验收失效。

## 私有 CI 与默认线切换门槛

以下是从 Harness 候选 `.github/workflows/ci.yml` 和 `.github/workflows/release.yml` 读取的**工作流定义**，并非远端运行结果或仓库分支保护规则。`CI` 只在 pull request 触发；单纯推送候选分支不会产生这组 PR 判定。私有 PR 的汇总 `all checks passed` 必须看到 `node-24` 静态检查、`node-24-coverage`、`node-24-consumers`、Node 22.19/24.9/26 兼容矩阵、Python 3.10 SDK、`windows-build` 和 `windows-native-tests` 成功。上游专用的 `node-24-bench` 与 `python-runtime` 在私有仓库按设计跳过，汇总允许这两项跳过；`windows-coverage` 不在汇总依赖中，需单独阅读结果。具体是否被远端分支保护列为 required check，仍须从私有仓库设置或 PR 状态核对，不能从 YAML 推断。

私有仓库的 `Release (dsh)` 在普通 PR 与默认分支推送时，`dependencies` 和 `pack` 工作均按条件跳过；完整的依赖布局、`release:verify`、正式构建、全包打包与安装布局复验，需要对确定的候选引用手动触发 `workflow_dispatch`。本地 RC3 的标准安装、51/51 发布测试及 Web 现场验收已有证据，但不能写成私有远端 Release 工作流通过。Runtime 候选的 `.github/workflows/python-tests.yml` 会对 PR 和目标分支 push 运行 Windows Python 测试，也需核对其远端状态。

切换前按以下顺序收口：

1. Harness 审查请求已建立为 draft PR #13；Actions 关闭期间，以固定来源的本地门槛记录替代远端运行记录。先修复下列静态检查失败，再复验，不把 PR 的 `mergeable_state` 当作检查通过。
2. `Release (dsh)` 目前无法手动运行；将其列为缺失的远端发布证据。保留现有标准安装、打包和回退现场记录，发布决策须明确离线替代的边界。
3. Runtime 固定源码 `15d871d` 的本地 pytest 已通过；Windows Python 工作流未执行成功且 Actions 已关闭。正式部署仍须引用固定源码；文档提交可在候选头部继续前移，但不能悄悄改变验收源。
4. 复核远端候选与默认线 SHA、分支保护、使用者拉取与回退说明后，单独批准默认线切换。Harness 默认线的快进会带入 6077 个提交和 D2 内部治理代码；Runtime `master` 应单独审查。切换前保留所有旧分支和 RC2 回退包。

当前门槛状态：本地 RC3 功能和归档验收已完成；两个仓库的 Actions 均已由负责人关闭，远端 CI 与手动 Release 在此策略下无法执行。分支保护仍未核实。因此保持两个默认线不动，RC3 私有候选可继续用于专用只读试用。离线验收的剩余项见下文，不能把本地结果写成远端 CI 通过。

**2026-10-18 远端审查入口与阻断**：Harness 已建 [draft PR #13](https://github.com/2020638630/deepseek-harness-private/pull/13)，`a6e8d20476` 对 `60c8f0c813`；Runtime 已建 [draft PR #2](https://github.com/2020638630/dsh-runtime/pull/2)，创建时 `3dce8776f2` 对 `ebb191ae99`。两者均未合并。负责人关闭 Actions 后，权限接口对两个私有仓库均返回 `enabled: false`。因此当前策略下不会有新的远端 PR 检查或手动 Release 运行，`mergeable_state: clean` 只说明 GitHub 未报告合并冲突，不代表 CI 通过。Runtime 关闭前的 [Python tests 运行](https://github.com/2020638630/dsh-runtime/actions/runs/39135705574)为 `failure`，但 job **0 个步骤、无 runner**；唯一注释明确写明 GitHub 因近期付款失败或支出上限需要提高而未启动 job。同一原因也出现在候选 push [运行](https://github.com/2020638630/dsh-runtime/actions/runs/39135427054)。这是账户/账务层阻断，不是 pytest 失败；现在改由固定源码本地测试提供替代证据，且不能称作远端 Windows CI 通过。当前 Git 凭据读取两个仓库分支保护接口均返回 403，不能据此断言保护规则有无。

**Actions 关闭后的离线门槛现场**：Runtime 固定 RC3 源码 `15d871d` 在隔离干净工作树运行 `python -m pytest -q`，结果 **511 passed in 13.19s**（Python 3.12.2、pytest 9.1.1）。Harness 固定 RC3 源码 `a6e8d` 使用 Node 24.19.0 运行 `pnpm run check:ci:static`，汇总为 **58 passed、6 failed、0 skipped**。六项失败是：`constraints`（Runtime subagent 包的 `files` 清单）、`verify-package-dependencies`（`ui-tool` 重复声明 React 类型）、`verify-cordis-config`（`apps/cli/tests/profiles/acp/cordis.yml` 根结构）、`verify-no-unknown-casts`（D2 evidence producer 断言）、`verify-cli-help`（子进程 `SIGKILL`，需独立复核）、`verify-module-graph`（双语模块图过期）。这是实际门槛失败，不可归为 GitHub 账务问题，也不能因为 RC3 功能验收通过就忽略。测试运行后两个固定源码工作树仍干净。下一步在独立候选中逐项修复并重跑失败项；若修复导致源码 SHA 变化，必须重新固定验收来源与必要的产品回归，再讨论默认线或稳定版。远端 Windows 矩阵、发布工作流、分支保护仍缺平台证据，需由负责人决定是否接受离线替代及其限制。

**额度阈值交接（2026-10-18）**：五小时额度到 10% 时暂停进一步验收。Harness 隔离候选从固定 RC3 `a6e8d` 前移两个**仅本地**提交：`aae4aeb42e` 移除 `ui-tool` 重复 React 类型声明及锁文件对应 importer，删除 D2 evidence producer 的多余 `as unknown`；`d6b7fad4dd` 将 Manifest schema 加入包发布清单策略并重生成双语模块图。对应单项检查已通过：`verify-package-dependencies`、`verify-no-unknown-casts`、`check-workspace-constraints`、`gen-module-graph --check`；提交时 staged lint 与 whitespace 也通过。尚未推送这两个 Harness 修复提交，也未重跑完整 64 项静态门槛，RC3 标签继续指向旧固定源码。剩余待查两项：`verify-cordis-config` 在 Windows 检出中读取到 mode `120000` 的符号链接占位文本，应验证真实符号链接检出或让检查器按 Git 链接目标解析；`verify-cli-help` 先脱离并行门槛独立重跑以判定 `SIGKILL` 是否为资源竞争。随后复跑完整静态门槛和相关产品回归，审查候选源码新 SHA，再决定是否推送、固定新的试用引用。Runtime 候选文档提交 `82661bf` 已推送至 draft PR #2；Harness draft PR #13 仍指向旧远端 `a6e8d`。两个原始仓库工作树与固定 RC3 工作树均不应清理或覆盖，D2 ExecuteGate 保持 `NOT_CLAIMED`。

**续跑结果（2026-10-19，取代上段的“尚未推送/未复验”状态）**：五小时额度恢复后，`verify-cli-help` 脱离并行门槛运行通过（7 个帮助页）；Windows 检出的符号链接文本由 Cordis 配置读取器解析为仓库内目标文件，聚焦测试 **3/3**、全部配置检查 **277/277** 通过。Harness 私有候选另增 `819dc46ea7`，三项修复提交已推送到现有 draft PR #13，远端与本地均为 `819dc46ea7953598b239a82e25abe7d87c64add3`。使用 Node 24.19.0、仓库自带 pnpm 11.28.5、`DSH_GATE_CONCURRENCY=4` 完整运行 `check:ci:static`，结果 **64 passed、0 failed、0 skipped**；推送钩子类型检查 **5/5**，在该 SHA 重建 `build:artifacts` **7/7**，发布相关测试 **194 passed、3 skipped**，冻结离线锁文件校验通过且工作树干净。pnpm 的执行前依赖状态检查仍提示本地 `node_modules` 可能与锁文件不同步并尝试安装失败；实际门槛继续运行成功，冻结锁文件校验只证明清单一致，不能替代全新依赖安装。未对新 SHA 重复模型现场、整包安装或 RC2 往返；原 RC3 成对标签仍固定 Harness `a6e8d` / Runtime `15d871d`，不得把新候选自动称作已完整验收的新 RC 或稳定版。两个仓库 Actions 仍关闭，未产生远端 CI 结论。下一步若要以 `819dc46` 发布新的候选引用，先完成该 SHA 的打包与安装形态复验，并审查 P1/P2 的大范围上游及 D2 内部治理差异；默认分支切换仍单独决策。

**定时任务复核**：上一轮在 2026-10-18 23:11（北京时间）设置的一次性 heartbeat 到 2026-10-19 00:26（北京时间）仍为 `ACTIVE`，本线程没有收到预期续跑。规则未写入时区，不能仅凭现有记录断言调度器按 UTC 解释；因此本轮已将旧任务 `dsh` 暂停，避免之后重复启动。此次由负责人主动发消息触发续跑。下次限额续排必须核对应用显示的下一次触发时间与任务运行记录，不能只凭 RRULE 文本宣称安排成功。

**RC4 成对私有试用引用（2026-10-19）**：在整组静态门槛、official 构建、发布测试及 npm 12 独立安装通过后，新注释标签 `vis-manifest-mvp-20261019-rc4` 已推送并从两个私有远端核对：Harness 解析至 `819dc46ea7953598b239a82e25abe7d87c64add3`，Runtime 解析至不变的 `15d871d1d960291fe7ab5ed22eb39a9c1d3b9a17`。354 个本地归档的哈希清单和验收边界见 [RC4 试用证据](PRIVATE_VISUALIZATION_TRIAL_2026-10-19_RC4.md)。RC4 安装包的专用只读 Profile 已完成配置解析与认证后的 Web HTTP 200；未重复 Manifest 页面目视或模型现场。RC3 标签保留；两个默认线未动。P1 宽范围上游审查仍未收口，因此不宣称稳定版或默认线就绪。

**P1 发布与启动接口复核（2026-10-19，第一批）**：旧 Harness 私有默认线 `60c8f0c813` 的根版本是 `0.1.5-rc.1`、pnpm `11.7.0`；公开上游 `687f282e86` 与 RC4 均是 `0.2.1-rc.2`、pnpm `11.28.5`。公开上游从 `dsh-v0.2.1-rc.1` 到 `rc.2` 的核心发行改动是版本更新、Base Bundle 新增共用 `DEEPSEEK_API_KEY` 的 DeepSeek Search/Fetch API、Web Bundle 新增 1017 模型标签 UI；此区间未改 `apps/cli/src`、`packages/boot/app-boot/src` 或 `scripts/release`，故不能把 RC4 的启动诊断改动误写为上游 `rc.2` 自带。RC4 相比上游另改 CLI `profile-boot.ts` 启动阶段诊断、`stdin-stop.ts`，以及发行打包进程、安装验证和对应测试；标准 Web 预设还增加默认关闭的 Runtime 子代理工具行。直接运行固定源码 `819dc46` 的 `scripts/release/verify.ts --family dsh` 通过：**345 个 DSH 包**均为 `0.2.1-rc.2`，发布顺序解析成功、未排序 peer 声明 0 项。普通 pnpm 入口先因当前依赖目录状态尝试安装并在非交互终端退出，随后直接调用同一校验脚本通过；没有刷新或清理现有依赖目录。RC4 的 354 包安装与只读 Web 启动证据见试用记录。这关闭**版本一致性、打包清单与新安装入口**的审查点；旧默认线到上游的 6080 提交跨度、旧会话数据兼容、跨版原地升级和远端 CI 仍未验证，不据此批准默认线切换。

**下一批执行顺序**：先对 RC4 已安装包复核浏览器中的 Manifest 抽屉、只读新会话入口及 provider 关闭开关（沿用独立试用 Home，不触碰原工作树）；再按 `0.1.5-rc.1` 到 `0.2.1-rc.2` 的 Session/配置迁移文档核对原地升级风险，给出新装优先与回退说明；最后复核私有默认线的保护规则与远端 SHA，形成一次性发布决定。两个仓库 Actions 关闭期间，远端检查维持“未运行”，不得把本地通过改写为 CI 通过。

**RC4 页面验收尝试与迁移审查（2026-10-19）**：已安装 RC4 用独立 `packed-rc4-readonly` Profile 再次启动本地 Web，进程正常、stderr 为 0；Codex 浏览器枚举返回 `nodeRepl.fetch request failed`，无法读取页面，因此 Manifest 抽屉、只读新会话入口和 provider 关闭开关本轮均**未通过页面目视验收**。服务已停止，未调用模型或 Runtime。旧默认线的 `SESSION_FORMAT_VERSION` 为 **3**，RC4 为 **4**；当前发布记录确认 V4 已随 `dsh-v0.2.0-rc.2` 发布，RC4 具有 V3→V4 相邻迁移实现和聚焦测试。迁移设计明确保留旧代文件，但不承诺降级或旧版本自动读取新代。由此把“现有 Home 原地升级并可回退”列为独立风险：RC4 的新 Home 安装和 Web 启动证据不能覆盖旧会话迁移；正式试用先使用独立新 Home，保留旧 Home 与 RC2/RC3 归档，待在复制的测试数据上验证迁移、旧版回退和 Profile 补丁兼容后再讨论原地升级。浏览器连接恢复后优先补做 RC4 页面三项检查。

**分支保护现场提示**：负责人提供的 2026-10-18 内置浏览器截图显示 Runtime 私有仓库 `master` 页面提示 `Your master branch isn't protected`。这是截图观察，尚未通过仓库设置或平台接口独立复核；默认线切换前须确认 `master` 的保护规则与实际 required checks，并先建立适合私有发布的保护策略。不要把截图提示误写成 Harness 私有默认线的状态。

## 按顺序推进的审查批次

### P0：保持 RC3 可复现，关闭来源漂移

- 以 Harness `a6e8d20476`、Runtime `15d871d` 的干净固定检出和已记录的归档哈希为验收来源；保留 Runtime 私有候选 `f4bb685056` 为设计与任务记录来源，后续文档提交单独追踪。
- 私有远端已重新核对上述引用；若后来前移，仅审查新提交，不重跑已通过的 9/9 构建、51/51 发布测试或模型现场样本。
- 成对候选已建立不可变 RC3 引用；正式版本和正式部署路径须指向同一对已验收提交。现有 RC1/RC2 标签保持原样。

已完成：两个私有远端现均有注释标签 `vis-manifest-mvp-20261018-rc3`，Harness 标签解析为 `a6e8d20476450be8c48b27e310d760034610b15a`，Runtime 标签解析为 `15d871d1d960291fe7ab5ed22eb39a9c1d3b9a17`。Runtime 标签固定验收所用源码，后续仅文档的候选提交不改变这对来源。此标签是**私有试用候选**，不是稳定版承诺或默认线更新。

### P1：独立审查公开上游升级

- 先审查 `d743267388` 和 `687f282e86` 两个上游落点的版本、锁文件、发布脚本、桌面与 Web 启动变化。以现有两次 merge 为证据节点，**不把 `dae159ae1f` 或 `77cbead5fc` 称为纯上游提交**；它们的第一父链中已有私有变更。
- 将 `origin/master...a6e8d` 的 236 个私有差异文件单独列为后续审查范围。发布门槛：能解释安装与 Web 启动的版本变化，并保留 RC2→RC3→RC2/RC3 的整包回退证据边界。
- 若需要给私有默认线做分阶段升级，应在独立新分支重放上游与必要私有适配，再审查差异；不能把当前混合历史中的中间 merge 直接当作可部署的纯上游批次。

### P2：私有集成和 D2 内部治理审查

- 将 `packages/subagent/subagent-dsh-runtime`、`packages/subagent/subagent-governance-python`、`packages/llm/llm-deepseek`、CLI 宿主及 `.agents`/`scripts` 治理文件列为独立审查面。确认版本对齐、工具允许表和来源绑定；D2 代码虽在候选中，ExecuteGate 仍未获业务执行声明。
- 已核对候选两个 Runtime 子代理包均为 `0.2.1-rc.2`；标准 Web 预设在 `delegation` 内提供 `tool-subagent-dsh-runtime`，但明确 `disabled: true`。产品试用 Profile 需另行显式启用并将治理任务限于 `repository_inspection`。Provider 源码的通用任务默认值仍是 `repository_change`，所以不能把仅安装 Bundle 或打开工具行等同于只读部署；必须检查实际 Profile 解析结果。现有安装包只读 Profile 已通过此项入口核对。D2 的 `NOT_CLAIMED` 是独立治理状态，不随这项产品配置改变。
- 来源与治理绑定进一步核对：Provider 的用户工作区始终取父会话 `header.cwd`；配置的 `runtimeRoot` 只负责子进程模块定位。组合配置默认治理 v1，v2 必须显式选择已随 Runtime 部署的 policy locator 和固定 SHA-256；治理 worker 返回 READY 后才注册 provider。Bridge 对会话 policy identity 做 pin，按队列执行 bind 与 pre-start evaluate，异常返回 FAILURE。这些源码约束支持当前隔离试用的边界，但不能代替真实 Profile、远端 CI 或 D2 ExecuteGate 的独立验收。
- 旧 D2 分支另有 5 个和 1 个独有提交；保留原引用，逐项判定是否仍适用。不得为“只留最新分支”强行并入或删除。

**P2 旧治理分支逐项筛选（2026-10-19）**：相对 Harness RC4 候选，`codex/d2-replayonly-repair-20261010` 有 5 个独有提交（`8b3237`、`3edc41`、`31a20c`、`b46c81`、`2d9096`），覆盖 replay-only 夹具、进程分类、直接 Runtime MCP 子进程、旧证据窗口和发行时重验；`codex/d2-no-listener-error-guard-20261013` 有 1 个独有提交 `57f6a8`，绑定 R8 预授权及最多三次尝试。当前候选已演进到 R12 预授权和**一次**尝试，发行时会重新读取现场并二次评估门槛，进程分类器也已有 Runtime MCP 分类。Git patch-id 仍判定上述 6 个提交独有，不能因此认定每项细节都被完整替代；但直接合入 R8/三次尝试会与当前一次尝试合同冲突。结论：这六项全部暂缓移植，保留旧分支；以后若 D2 内部治理正式重启，再按当前 R12 合同逐项提取仍适用的测试或边界修复。此筛选不改变 ExecuteGate 的 `NOT_CLAIMED`，也不是删除旧分支的依据。
- 将私有治理 CI 对公开上游的影响单独核对，不以产品可视化验收替代 D2 门槛。

### P3：Evidence Manifest 产品增量审查

- 核对 `14e48dd6ae` 及其后续负向状态、Web 预设修复、打包依赖和测试修复，按 Runtime provider → Web 抽屉 → 宿主 Profile → 发布归档四个接口审查。
- 首版只交付终态 Manifest 抽屉；轮次缺失、失败/取消、轨迹缺失均按已验收的降级文案呈现。实时流和 Memory/RAG 不进入当前稳定版范围。
- 引用 RC3 现场与归档级验收作为门槛：真实读写、负向失败/取消、Safe Trace `.closed`、标准 npm 12 安装、安装包 Web/provider 开关及父会话只读默认。业务失败的模型现场样本按负责人已批准的首版边界不作为阻断项。

### P4：部署与默认线切换

- 正式试用先沿用专用 `vis-trial-rc3-current` 的只读父会话默认和非 D2 `repository_inspection` 配置。安装包形态已新增独立 `packed-rc3-readonly` Profile，在原试用 Home 的新会话入口及既有独立仓库选择下显示“仅可查看”；这关闭了安装包部署 Profile 的默认权限检查。当前 `packed-rc3` 只完成安装包 Web/provider 启用验收，不能自动视作只读正式配置。
- 先固定一对私有发布引用并验证功能关闭开关；再确定使用者的拉取指令、Profile 路径、保留的 RC2 回退包及数据兼容边界。RC2 整包往返只证明 Web 壳可启动，不证明跨版会话或 Manifest 数据迁移。
- 上述审查关闭且私有远端 SHA 复核后，才提交私有默认线的更新方案供最后确认。若选择快进，明确告知该操作将一次引入 6077 个提交；优先保持候选线可用，并将默认线切换作为单独发布动作。Runtime `master` 同理独立处理。

## 本轮操作边界

两个原工作树仍有未提交改动与未跟踪文件；只在隔离候选中写本计划。未清理、重置或覆盖原树；未移动默认线、删除旧分支、宣称 D2 ExecuteGate 或创建稳定版标签。成对 RC3/RC4 私有试用标签与两个 draft PR 均已建立。负责人已选择关闭两个仓库的 Actions；RC4 离线静态、构建、打包与安装门槛已记录，下一步继续 P1 上游升级审查、RC4 专用只读 Web 复验与私有默认线发布条件核对。默认线切换仍是单独的最终决策。

**安装包 Profile 补验（本轮）**：`D:\DeepSeekHarness\vis-trial-rc3-home\profiles\packed-rc3-readonly` 使用已标准安装的 RC3 provider，`sandbox-policy.mode: read-only`，Runtime 治理只允许 `repository_inspection`，审计和证据各有独立路径。配置解析通过。已安装的 RC3 CLI 用此 Profile 启动真实 Web，HTTP 200、启动错误日志为空；浏览器在新会话入口选定现有的独立 `vis-trial-rc3-readonly3-repo`，页面显示“访问模式，当前：仅可查看”。未发消息、未调用模型或 Runtime，故这证明新会话**入口默认值**，不证明已运行的任务权限。服务已停止。最初在完全独立的 `rc3-packed-home` 下建立的同名 Profile 也通过配置解析、HTTP 200 和只读入口显示，但浏览器文件选择器未完成新仓库登记；因此改用已有试用 Home 的独立 Profile 完成工作区选择。首次受限启动出现 `spawn EPERM`、provider 未激活；最终 HTTP 200 和空错误日志来自允许治理 worker 启动的正式复验，不混同两次结果。
