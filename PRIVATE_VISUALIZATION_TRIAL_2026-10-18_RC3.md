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

从固定 Harness 检出按相同 `pnpm-lock.yaml` 独立安装依赖，供应链锁文件检查通过。正式构建 **8/9**：Host 编译、Host bundle、Desktop bundle、客户端编译与 bundle、Host/Client 聚合检查等八项通过；Web build 两次均在 esbuild 删除 Windows 临时输入文件时遇到 `Access is denied`，包括改用固定检出内全新临时目录后仍失败。另以独立 2 MB 输入直接调用相同 esbuild 版本复现删除失败，随后手动删除该探针文件成功；因此问题尚不能归因于 Web 产品源码。此失败保留为**正式发布门槛未通过**。仅为私有试用烟测，将已在整合工作树成功构建、且与固定源码和锁文件相同的 156 个 Web 资源复制到固定检出；逐文件 SHA-256 对比 156/156 一致。该复制不等于固定检出的独立 Web build 通过，也不证明完整安装包可复现。

专用 `DSH_HOME` 为 `D:\DeepSeekHarness\vis-trial-rc3-home`，Profile 为 `vis-trial-rc3`。Profile 的 provider `link:` 指向上述固定 Harness 检出，其独立 `node_modules` 已在固定检出内安装，不借用可变整合树的 junction；`runtimeRoot` 指向固定 Runtime 检出，治理为非 D2 `v2`，默认仅开放 `repository_inspection`。临时凭据只在本机试用 Home，未提交到源码仓库。使用固定 CLI 与该 Profile 启动 `dsh web`，认证页面 HTTP 200；浏览器在 `D:\DeepSeekHarness\vis-trial-rc3-repo` 登记并新建会话，核对会话路径准确、编辑器可用，未调用模型。烟测结束后已停止本次 Web 服务，测试 Git 仓库保持干净。

**权限边界**：Runtime 默认只读治理只约束 `dsh_runtime` 子任务。标准父 Agent 仍装载 PowerShell 和文件工具，新会话默认显示“工作区内修改”；若用于只读试用，必须在发起任务前把父会话切到“仅可查看”。曾用于写入验收的 `write-only.overlay.yml` 只属于前一临时 Home，不在此 RC3 Profile 的默认配置中。

## 回退与发布边界

当前私有默认线未移动：Runtime `master` 与 Harness 私有 `integration/dsh-runtime-d1-q2-closeout` 仍是原引用。若暂停此功能，先停用试用 Profile 的 `tool-subagent-dsh-runtime`，RC2 已验收此配置开关的关闭与恢复；若退回前一功能候选，成对保留 `vis-manifest-mvp-20261017-rc2` 标签及其固定检出。RC2 不包含本轮上游更新，不能当作“保留新上游且功能完全等价”的回退包。本轮仅完成 RC3 固定 Profile 的启动烟测，尚未完成 RC3↔RC2 整包安装和页面回退演练。

进入稳定版前至少需要：① 解决固定检出 Web build 的临时文件删除失败，并从同一固定提交重新产出正式资源；② 对成对包执行打包、独立安装与回退演练，记录归档哈希；③ 明确父 Agent 默认权限与目标部署方式；④ 对 Harness 私有默认线相对候选约 6075 个独有提交（第一父链 56 个）的广泛上游差异进行独立升级审查。另有旧 D2 治理分支的 5 个和 1 个独有提交，仍应保留并单独处理。调用模型的业务失败现场样本依负责人决策不属于首版稳定版门槛。
