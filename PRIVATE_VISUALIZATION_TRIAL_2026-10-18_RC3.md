# 运行可视化上游适配私有试用 RC3

状态：**成对源码候选已固定，尚未发布稳定版**。本记录对应 2026-10-18 的更新后适配验收；原始 R9 基线及任务顺序见 [RUNTIME_VISUALIZATION_BACKLOG.md](RUNTIME_VISUALIZATION_BACKLOG.md)。D2 ExecuteGate 保持 `NOT_CLAIMED`。

## 成对版本与来源

| 项目 | 私有候选分支 | 本轮固定源码提交 | 本机固定检出 |
| --- | --- | --- | --- |
| DeepSeekHarness | `codex/private-consolidation-20261017` | `a5473ce995617dfbc3194bf7876eaa13eb49da44` | `D:\DeepSeekHarness\vis-harness-rc3-fixed` |
| DSH Runtime | `codex/vis-manifest-mvp-20261016` | `15d871d1d960291fe7ab5ed22eb39a9c1d3b9a17` | `D:\DeepSeekHarness\vis-runtime-rc3-fixed` |

两提交已在各自私有远端核对。Harness 包含公开上游 `master` 的 `687f282e8625c6b8d11ff58211a90524be2e4317`；2026-10-18 现场查询时公开上游仍指向该提交。两个固定检出均为 detached HEAD、Git 状态干净，不引用原有脏工作树作为源码。Harness 根版本为 `0.2.1-rc.2`；Runtime provider 包仍为 `0.2.1-alpha.2`，与 RC2 相比，provider 的产品源码与包声明未变，只有测试文件调整。试用仍应按上述 Git 提交识别，不能仅凭 provider 的包版本号区分 RC2/RC3。

## 更新后验收

真实 `dsh web` 成功完成独立临时仓库的只读 `repository_inspection` 和另一个独立临时仓库的写入 `repository_change`，父会话均收到子任务终态并完成回复。只读 Manifest 为 `completed`、审计 `settled`、无工作区变化；写入 Manifest 为 `completed`、审查 `PASS`、审计 `settled`、Safe Trace 已闭合，仅新增 37 字节的 `result.txt`。两次认证浏览器页面均打开 Evidence Manifest 抽屉并核对轨迹、实际变动、审计三栏。无模型的真实 Runtime 子进程失败与取消经 Web scaffold 贯通测试 2/2 通过。运行 ID、文件哈希与测试边界详见任务清单“更新后适配现场验收”，不把 scaffold 负向测试称为同一次 CLI 现场运行。

从固定 Harness 检出按相同 `pnpm-lock.yaml` 独立安装依赖，供应链锁文件检查通过。首次正式构建 **8/9**：Web build 两次均在 esbuild 删除 Windows 临时输入文件时遇到 `Access is denied`，包括改用固定检出内全新临时目录后仍失败。以独立 2 MB 输入分别调用已安装的三个 esbuild 版本均复现失败；同哈希可执行文件从整合检出运行成功，或复制到固定检出的新路径后也成功，说明失败跟随原安装路径。仅在固定检出的忽略 `node_modules` 内将三个可执行文件各自备份为 `.rc3-original`，再放回 SHA-256 相同的独立副本；探针 3/3 和固定检出正式构建 **9/9**。没有改功能源码或锁文件。此前为私有试用烟测复制的 156 个 Web 资源已经逐文件核对哈希，但不计作后来独立构建通过的证据；这项构建依赖于上述本机依赖文件路径处理，仍需在目标机器重复验证。

专用 `DSH_HOME` 为 `D:\DeepSeekHarness\vis-trial-rc3-home`，Profile 为 `vis-trial-rc3`。Profile 的 provider `link:` 指向上述固定 Harness 检出，其独立 `node_modules` 已在固定检出内安装，不借用可变整合树的 junction；`runtimeRoot` 指向固定 Runtime 检出，治理为非 D2 `v2`，默认仅开放 `repository_inspection`。临时凭据只在本机试用 Home，未提交到源码仓库。使用固定 CLI 与该 Profile 启动 `dsh web`，认证页面 HTTP 200；浏览器在 `D:\DeepSeekHarness\vis-trial-rc3-repo` 登记并新建会话，核对会话路径准确、编辑器可用，未调用模型。烟测结束后已停止本次 Web 服务，测试 Git 仓库保持干净。

**早期试用权限边界**：Runtime 默认只读治理只约束 `dsh_runtime` 子任务。首个 `vis-trial-rc3` Profile 的标准父 Agent 仍装载 PowerShell 和文件工具，新会话默认显示“工作区内修改”；该旧试用 Profile 用于只读任务时仍须手动切到“仅可查看”。后续 `vis-trial-rc3-current` 专用 Profile 已单独设置并验收父会话只读默认。曾用于写入验收的 `write-only.overlay.yml` 只属于前一临时 Home，不在此 RC3 Profile 的默认配置中。

## 回退与发布边界

当前私有默认线未移动：Runtime `master` 与 Harness 私有 `integration/dsh-runtime-d1-q2-closeout` 仍是原引用。若暂停此功能，先停用试用 Profile 的 `tool-subagent-dsh-runtime`，RC2 已验收此配置开关的关闭与恢复；若退回前一功能候选，成对保留 `vis-manifest-mvp-20261017-rc2` 标签及其固定检出。RC2 不包含本轮上游更新，不能当作“保留新上游且功能完全等价”的回退包。本轮仅完成 RC3 固定 Profile 的启动烟测，尚未完成 RC3↔RC2 整包安装和页面回退演练。

固定试用之后，Harness 隔离整合分支新增两个提交：`88b9221f89` 将 `dsh-subagent-dsh-runtime` 与 `dsh-subagent-governance-python` 两个遗留 `0.2.1-alpha.2` 包声明对齐全家族 `0.2.1-rc.2`；`a6e8d20476` 修正发布测试对 pnpm 先执行 `prepare` 的误判，仍禁止空打包触发 `prepack`/`postpack`。两提交已由正常 pre-commit 和 pre-push 钩子提交、推送到私有 `codex/private-consolidation-20261017`；未移动默认分支，原工作树和固定试用源码对未动。整合分支在版本提交上正式构建 **9/9**；发布测试使用隔离临时目录和 30 秒用例上限 **51/51**，类型检查 **5/5**，推送钩子的类型检查也通过。构建时的产物记录与归档指向版本提交 `88b9221f89`；后一个提交只改测试，若以 `a6e8d20476` 正式制包仍须重新构建。从版本提交构建的 DSH **345** 个归档与 vendor **9** 个归档通过逐包校验；按文件名排序的 SHA-256 清单在整合检出的忽略文件 `node_modules/rc3-pack-sha256.txt`，清单本身 SHA-256 为 `19e8435ea0532427175d486f92b063d700708b353fe2fbe1e2530c4574b89caa`。独立临时消费者的标准 npm 10.7.0 安装先在依赖解析中报 `Cannot read properties of null (reading 'edgesOut')`；开启 legacy peer 模式后到达 `koffi` 安装脚本，又因本机没有 CMake 而失败。再加 `ignore-scripts` 的**诊断模式**完整安装 354 个归档、确认 611 个默认产品包隔离、并运行安装后的 `dsh --version` 得到 `0.2.1-rc.2`。这证明打包载荷可启动，但不等于标准安装通过。两次标准失败均保留，不发布稳定版。

为核对**已推送的准确提交**，另建干净 detached 检出 `D:\DeepSeekHarness\vis-harness-rc3-current-fixed`，固定在 `a6e8d20476450be8c48b27e310d760034610b15a`。冻结锁文件安装采用 `--package-import-method=copy --ignore-scripts`；三个 esbuild 版本的大输入探针 3/3 通过，未手动替换依赖文件，正式构建 **9/9**。从该提交重新打包 DSH **345** 个与 vendor **9** 个归档，逐包校验通过；哈希清单为忽略文件 `D:\DeepSeekHarness\vis-harness-rc3-current-fixed\node_modules\rc3-current-pack-sha256.txt`，其 SHA-256 为 `880d604b053213783f17bdbd3160315e53011a35cdacad178b630973a2f70deb`。先以 legacy peer 与 ignore-scripts 的诊断模式在临时消费者安装全部 354 个归档，默认产品隔离检查 **611** 个包、安装后的 CLI 版本 `0.2.1-rc.2`。随后复用 RC2 验收时安装在试用目录的 npm **12.2.0**，不改全局 npm，运行同一官方 `verify-packed-install.ts`，**无 legacy peer、无 ignore-scripts 的标准安装通过**：354 个归档、默认产品隔离 **658** 个包、安装后 CLI 版本 `0.2.1-rc.2`。npm 10.7.0 的 `edgesOut` 错误以及使用其 legacy peer 模式时的 CMake 错误仅适用于先前失败路径，不再作为全部目标环境的发布阻断。该准确提交的打包与标准独立安装门槛已关闭。

在同一个独立 `DSH_HOME` 新增 `vis-trial-rc3-current` Profile，provider `link:` 指向上述当前固定检出，Runtime 继续指向 `15d871d` 的固定检出；非 D2 v2 配置仍仅开放 `repository_inspection`，审核与证据路径独立于旧 Profile。配置解析无失效预设项；当前固定 CLI 启动真实 `dsh web` 后，浏览器无模型烟测得到 HTTP 200，复核先前独立测试仓库的既有会话、工作区路径和编辑器，父 Agent 默认仍显示“工作区内修改”。该浏览器回归复用了既有会话，未创建新的 Runtime 运行。另建互不覆盖的 `vis-trial-rc3-disabled` Profile，仅把 `subagent-dsh-runtime` 设为 `disabled: true`；配置解析确认关闭，实际 Web HTTP 200。此项证明当前候选的功能关闭开关可用，不等于 RC3↔RC2 整包回退。两次 Web 服务均已停止，当前固定检出 Git 状态干净。

**归档级 Web 壳回退**：在 `vis-trial-rc3-home/artifacts/rc3-packed-consumer` 与 `vis-trial-rc2-home/artifacts/rc2-packed-consumer` 分别用隔离 npm 12 对准确 RC3 的 354 个归档、保留 RC2 的 343 个归档进行标准持久安装；安装后 CLI 分别报 `0.2.1-rc.2`、`0.2.1-alpha.2`。官方安装校验使用 `--omit=optional`，足以验证 CLI 版本，但 Web 启动实际需要 `node-addon-require-builtin-win32-x64-msvc` 等平台可选原生包；两个独立消费者均追加正常 `--include=optional` 安装，各新增 13 包。随后分别使用自己的全新 `DSH_HOME`，按 **RC3→RC2→RC3** 顺序启动已安装归档中的 `dsh web`，三次 HTTP 均为 **200**，每次结束都停止所属进程。此项证明整包的默认 Web 壳可往返启动；未给这两个打包消费者配置 Runtime provider、未运行模型或业务任务，也未证明既有会话或 Evidence Manifest 数据可跨版本读取。

**安装包 provider 开关**：在准确 RC3 归档的持久消费者中另建 `packed-rc3` Profile，将该消费者安装的 `@deepseek-ai/dsh-subagent-dsh-runtime` 链入 Web bundle，并应用只开放 `repository_inspection` 的非 D2 v2 配置，Runtime 指向固定 `15d871d`。配置解析成功，实际安装包 Web HTTP **200**。再建独立的 `packed-rc3-disabled` Profile，仅将 provider 设为 `disabled: true`；解析确认关闭，Web 仍 HTTP **200**。两服务均已停止。这验证安装包形态的启动及功能关闭路径，未运行模型或 Runtime 业务任务。

**专用试用 Profile 的父会话只读默认**：由产品原有 `sandbox-policy` 与 `permission` 预设配合实现。诊断时曾把 `permission` 整段配置替换为单一 `defaultPreset`，导致预设表丢失、页面无权限控件；该诊断层已废弃。只覆盖 `sandbox-policy.mode: read-only` 并保留原权限预设后，在新独立 Git 仓库的浏览器会话 `session-60b569ba-bdba-4d38-bea9-26f147d2889b` 首次观察到“访问模式，当前：仅可查看”。随后将同一沙箱默认值写入专用 `vis-trial-rc3-current` Profile，本身不再依赖临时权限叠加；再用全新仓库 `D:\DeepSeekHarness\vis-trial-rc3-readonly3-repo` 创建会话 `session-32df28e3-bb31-42a1-a877-e1dedc88d8b0`，浏览器仍显示“仅可查看”，仓库 Git 状态干净。两次均未调用模型或 Runtime，Web 服务已停止。原试用 Profile、打包消费者及源码配置均未被这项试用 Profile 调整覆盖。

**私有默认线只读审查**：远端 `integration/dsh-runtime-d1-q2-closeout` 为 `60c8f0c813a55754338d1e53a655f480a5f62f02`，当前候选 `a6e8d20476450be8c48b27e310d760034610b15a`；默认线是候选祖先，技术上可快进，但候选独有 **6077** 个提交（第一父链 **58** 个），与默认线相比 **12927** 个文件、约 **162.9 万新增行与 21.4 万删除行**。候选已包含公开上游 `687f282e8625c6b8d11ff58211a90524be2e4317`；相对该上游仅 61 个提交、236 个文件变化。广泛差异主要是私有默认线尚未升级上游，不能将此次快进当作单一 Manifest 功能合并。旧 D2 分支仍有 5 个和 1 个独有提交，均保留。

进入稳定版前至少需要：① 将私有默认线升级范围拆成可审查批次，明确何时移动默认线与是否创建 RC3 标签；② 确定正式部署的 Profile 路径与父会话只读默认是否沿用专用试用配置。调用模型的业务失败现场样本依负责人决策不属于首版稳定版门槛。五小时额度剩余 10% 时已停止新增执行，续跑依据任务清单顶部交接。
