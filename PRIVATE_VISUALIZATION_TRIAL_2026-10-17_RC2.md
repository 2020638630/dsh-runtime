# 运行可视化首期私有试用候选 RC2

状态：私有试用候选，仍非默认分支或稳定版。完整部署步骤、首期功能范围及回退说明见 [RC1 记录](PRIVATE_VISUALIZATION_TRIAL_2026-10-17.md)；本记录只描述 RC2 的增量与固定引用。

| 仓库 | 候选分支 | RC2 固定标记 | 前一回退标记 |
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

试用 Profile 的 `runtimeRoot` 已改指独立 detached 检出 `D:\DeepSeekHarness\vis-runtime-rc2-fixed`，HEAD 为 RC2 标记提交 `3a1a89c`；配置解析复核仍仅允许 `repository_inspection`，证据仍在独立 Home。Harness provider 仍通过 `link:` 引用 `D:\DeepSeekHarness\vis-harness-candidate`，其 HEAD 当前为 RC2 `26c11095f9`；后续若该候选工作树变化，须先固定 Harness 包或重新核对版本再继续试用。Web 会话 UI 仍显示 `Workspace Write`，这是父 Agent 的一般工具权限，不能把 Runtime 的只读治理配置解释为整个 Web 会话只读。稳定版仍需复核这层权限边界并完成成对发布/回退演练。
