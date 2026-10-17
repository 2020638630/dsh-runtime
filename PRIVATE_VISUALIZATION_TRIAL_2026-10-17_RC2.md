# 运行可视化首期私有试用候选 RC2

状态：私有试用候选，仍非默认分支或稳定版。完整部署步骤、首期功能范围及回退说明见 [RC1 记录](PRIVATE_VISUALIZATION_TRIAL_2026-10-17.md)；本记录只描述 RC2 的增量与固定引用。

| 仓库 | 候选分支 | RC2 固定标记 | 前一候选标记 |
| --- | --- | --- | --- |
| DSH Runtime 私有 `origin` | `codex/vis-manifest-mvp-20261016` | `vis-manifest-mvp-20261017-rc2` | `vis-manifest-mvp-20261017-rc1` |
| DeepSeekHarness 私有 `private` | `codex/vis-manifest-mvp-20261016` | `vis-manifest-mvp-20261017-rc2`（含 `26c11095f9`） | `vis-manifest-mvp-20261017-rc1` |

RC2 补齐了 Harness 的生成式 client slot catalog 与 DeepSeek LLM 说明配对记录；`dsh_runtime` 抽屉槽位现已登记。完整 `pnpm run doc-sync` 复核 **43/43 通过**，此前 RC1 记录的两项文档检查失败已关闭。Web 工具真实负向路径 2/2、`dsh web` 独立启动烟测、完整类型检查等功能证据沿用 RC1，未重新命名为单次 CLI 端到端验收。

稳定发布仍需专用部署环境中的试用会话复核及发布/回退演练。负责人已决定：**需要模型的业务失败现场样本不列为首版稳定版门槛**；真实业务失败终态保留 Manifest 的可重复测试仍是门槛，模型现场样本列为后续专项验证。若将来对外承诺模型失败也一定提供完整证据，应先补做相应现场样本。D2 ExecuteGate 保持 `NOT_CLAIMED`。Harness 两条旧 D2 分支有 6 个不在本候选内的内部治理提交，因此继续保留，不合并到用户可视化分支，也不删除或修改默认分支。两个原治理工作树的未提交和未跟踪文件继续保留。

## 专用试用 Profile 现场记录（2026-10-17）

按负责人选择，已在本机另建 `D:\DeepSeekHarness\vis-trial-rc2-home`，Profile 为 `vis-trial-rc2`，配置文件为 `profiles\vis-trial-rc2\cordis.patch.yml`；独立 Git 测试仓库为 `D:\DeepSeekHarness\vis-trial-rc2-repo`。Profile 链接当前 Harness RC2 候选包，以 Runtime RC2 候选目录为执行根，启用标准 Web Preset 内的 `dsh_runtime`，治理字段仅允许 `repository_inspection`，证据写在独立 Home 内。该链接随候选工作树变化，不是不可变部署包；试用时须先核对双仓工作树仍位于本表 RC2 标记对应提交。`dsh vis-trial-rc2 --no-open --port 0` 启动与认证页面 HTTP 200 已通过；浏览器自动化另外叠加了目录浏览器 overlay，以避开本机原生目录选择框。

真实 Web 试用会话 `session-a4d070d3-1755-4dae-8961-b227499725cf` 的 `data-conversation-session` 已与独立测试仓库的会话身份核对，然后提交一次只读请求。Runtime 运行 `dsh-runtime-2698f480-1c1c-4886-84c2-1f2d33b7b004` 终态 `completed`，`manifest_available=true`；同一父会话回放中展开过程组后，“View evidence”按钮和终态抽屉可见，抽屉显示完成状态、执行轨迹、观察变化与审计页签。Manifest 的工作区变化为 `+0 -0`，审计状态 `settled`，测试仓库 Git 状态干净。执行轨迹标为 `not_applicable`，核验判决为 `UNAVAILABLE`；这次 `repository_inspection` 不提供可声称的 Safe Trace 或 PASS 判决。测试脚本在 Runtime 结算后关闭 Web 服务，父 Agent 的后续回复因此中断，**本样本验证 Web 工具与终态抽屉，不作为父 Agent 完整回复验收**。此前两次误落默认工作区的调用及其中一次未结算运行均不计入此样本。

随后已完成父 Agent 完整回复试用并固定 Runtime 检出，见下节。待办是 Harness 包固定、Profile 的非 Runtime 工具权限复核与成对回退演练。RC2 标记不移动，D2 ExecuteGate 继续 `NOT_CLAIMED`。

## 完整父会话试用与 Runtime 版本固定（2026-10-17）

第二次现场试用先核对页面活动会话 `session-0488f2d2-585f-4f66-a919-efd8b329b7ad` 属于专用 Git 仓库，再发起单次只读 `repository_inspection`。父 Agent 两轮均已完成：首轮发起 `dsh_runtime`，次轮接收子任务结果并准确概述仅有的 `README.md`、单个初始提交及干净工作树；没有再调用其他工具。Runtime `dsh-runtime-2b680d44-b432-49ad-861b-5ab5187f0e87` 结算 `completed`、`manifest_available=true`、审计 `settled`、观察变化 `+0 -0`；仓库 Git 状态仍干净。此样本补齐上一节未完成的父会话回复验收，仍只代表独立仓库的只读工作负载，不代表 D2 或需要模型的业务失败。

试用 Profile 的 `runtimeRoot` 已改指独立 detached 检出 `D:\DeepSeekHarness\vis-runtime-rc2-fixed`，HEAD 为 RC2 标记提交 `3a1a89c`；配置解析复核仍仅允许 `repository_inspection`，证据仍在独立 Home。此时 Harness provider 尚通过 `link:` 引用候选工作树；下节记录了后续的固定处理。Web 会话 UI 仍显示 `Workspace Write`，这是父 Agent 的一般工具权限，不能把 Runtime 的只读治理配置解释为整个 Web 会话只读。

## Provider 固定与回退边界（2026-10-17）

已为 Harness RC2 标记 `26c11095f9` 建立独立 detached 检出 `D:\DeepSeekHarness\vis-harness-rc2-fixed`。将当前 RC2 候选构建出的 provider `lib/` 复制到该检出，`lib/index.js` 前后 SHA-256 均为 `24D60D2B42777799E8B2F21AD8061634C0F6299C22E018C81F5E238C5DD8FD31`；试用 Profile 的包声明和锁文件已改为链接此固定检出，实际模块导入与真实 CLI 认证浏览器启动均通过，未调用模型。源码检出和 provider 产物现有固定引用；依赖仍通过指向现有 Harness 候选 `node_modules` 的 junction 解析，**整个本机部署尚非完全自包含或不可变**。另保存 pnpm 打包归档 `D:\DeepSeekHarness\vis-trial-rc2-home\artifacts\dsh-runtime-provider-rc2-pnpm.tgz`，SHA-256 为 `5CC4C4CA9C490F57CBA62E11D856E5CB39EE47E9B83DA4FD8D1BABAA018EE87D`。该归档的离线安装因内部依赖缓存元数据缺失而失败，Profile 的原包声明及锁文件在失败后经哈希核对未变化，随后才改为固定检出链接。

权限复核确认：Profile 只把 `dsh_runtime` 子任务限制为 `repository_inspection`；标准父 Agent Preset 在 Windows 上仍启用 PowerShell 与文件工具，页面显示 `Workspace Write`。因此专用试用仅对独立测试仓库使用，不能向使用者描述为“整个 Web 会话只读”。RC1→RC2 差异显示 Harness RC2 补登记 `dsh_runtime` 的 client slot catalog；**RC1 不能作为保留同等抽屉能力的回退点**。首版正式发布前应以发布前的现行版本作为功能回退目标，或建立经过完整启动和页面验收的成对回退包；不移动现有 RC1/RC2 标签。

## 配置回退演练（2026-10-17）

当前双仓默认线的本地远端引用分别为 Runtime `origin/master` 与 Harness 私有 `private/integration/dsh-runtime-d1-q2-closeout`。在专用 Profile 中将标准 Preset 的 `tool-subagent-dsh-runtime.disabled` 暂置 `true`，解析配置确认关闭，真实 CLI 与认证浏览器页面无模型启动通过；随后恢复 `false`，配置再次解析且页面再次启动通过。Profile patch 恢复后 SHA-256 与演练前同为 `D831253072A542E4F100DE74D943E3249C01AC07F1DE5CD53E9C533C5F37AA14`，测试仓库仍干净。此项只证明**可关闭并恢复功能开关且 Web 可启动**，不等于已对默认线代码和完整依赖包做版本回退验收。正式发布前还需针对成对版本与依赖做独立启动、页面和回退验证；当前不合并默认分支、不移动标签，也不删除旧分支。

## 完整打包与独立安装（2026-10-17）

本轮 Harness 发布验证脚本修复提交为 `f5884996c5`，已推送到私有候选分支；它不改变 RC2 产品代码标签。

在未改动产品代码的 Harness RC2 候选上运行官方构建，记录 357 个客户端产物；官方发布脚本将 DSH 家族 334 个包、配套 vendor 家族 9 个包打入专用试用目录。343 个 tarball 的 SHA-256 清单为 `D:\DeepSeekHarness\vis-trial-rc2-home\artifacts\release-rc2-sha256sums.txt`，清单本身 SHA-256 为 `9CB06411C599F6E71FE8FDE60F6C232B235280C30745EC2F941DC0C2C3DA789C`。原始 RC2 标记未移动。

首次独立安装验证暴露 Windows `spawnSync('npm')` 无法启动 `.cmd` shim。Harness 候选中的发布脚本现改为在 Windows 上找到 npm 的 JavaScript 入口并交由当前 Node 执行；聚焦测试 4/4、聚焦 lint、完整 `pnpm run typecheck` 通过。使用本机 npm 10.7 时安装进入依赖解析但报内部 `edgesOut` 错误；仅在专用试用目录安装 npm 12.2.0 后，对同一批 tarball 重跑官方 `release:verify-packed-install` **通过**：343 包安装到临时 consumer，601 个默认产品包不包含实验包，安装后的 `@deepseek-ai/dsh` 报告 `0.2.1-alpha.2`。npm 12 只用于本次本机验证，没有改全局工具或仓库依赖版本。打包产物与安装验证均不代表默认线已部署；正式版本回退仍待实测。
