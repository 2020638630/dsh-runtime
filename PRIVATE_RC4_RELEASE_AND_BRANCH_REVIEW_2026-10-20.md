# RC4 并行日常后的发布与分支审查

状态：2026-10-20 本地只读核对与下一步建议。本文不发布稳定版、不删除分支，也不改变日常 Home。依据 [RC4 现场证据](PRIVATE_VISUALIZATION_TRIAL_2026-10-19_RC4.md)及[下一阶段任务](PRIVATE_VISUALIZATION_NEXT_PHASE_2026-10-19.md)；D2 ExecuteGate 继续为 `NOT_CLAIMED`。

## 当前可用边界

- 私有 Harness 默认分支 `integration/dsh-runtime-d1-q2-closeout` 与 RC4 标签均指向 `819dc46ea7953598b239a82e25abe7d87c64add3`。公开上游 `master` 本次核对仍为 `687f282e8625c6b8d11ff58211a90524be2e4317`，已在私有候选祖先链中。
- 私有 Runtime 默认分支 `master` 为 `b57a8294f386`；RC4 标签固定功能源码 `15d871d1d960291fe7ab5ed22eb39a9c1d3b9a17`。两者之间只有六份 Markdown 记录的变化。可视化候选分支 `codex/vis-manifest-mvp-20261016` 为 `4a4278f`，比默认线多一条并行日常入口记录。
- 独立 RC4 Home 的读、写两种入口和非 D2 `repository_inspection` 已做现场验收。写入只针对临时仓库；终态 Manifest 为 `completed`、审计 `settled`、无 Runtime 文件变动，用户确认抽屉三页可见。原日常 Home 和两处原源码工作树均未迁移或清理。
- `unknown tool "wait"` 是父会话在 Runtime 子代理启动后调用不存在的工具；同一会话的 Runtime 子任务最终成功且审计已结算。保留为单次模型编排异常，观察是否复现；它不是已证实的 Runtime 或 Manifest 失败。

## 稳定版发布门槛

| 顺序 | 事项 | 当前判断 / 完成条件 |
| --- | --- | --- |
| 1 | 确定发布含义 | 推荐先明确为“私有、Windows、并行日常可用”的受限发布；不把桌面安装器、自动更新、公开 npm 或 D2 纳入这次声明。 |
| 2 | 版本与来源 | Harness 根、CLI 和 Desktop 仍是 `0.2.1-rc.2`。正式稳定版不能仅在现有提交上改贴稳定标签：若按仓库发布机制发布，需在隔离分支执行 DSH 版本提升，连同锁文件和所有工作区包版本一致性审查后固定新提交。Runtime 没有独立的包版本清单；以源码提交和成对来源表固定。 |
| 3 | 构建与安装 | 新版本提交必须重新跑受影响的版本/依赖门槛、完整打包安装和真实消费者启动；RC4 的 354 个归档、本地安装与 Windows 未签名目录包只能证明固定的 RC4 提交。若交付桌面安装器，另做安装、启动、卸载/回退和签名策略验收。 |
| 4 | 现场功能 | 在新版本安装产物、独立 Home 和临时仓库复验读写入口、Runtime 成功/失败或取消终态及三页抽屉。已有 RC4 历史证据可作回归基线；仅针对新提交与包形态重验。记录 `wait` 异常是否再次发生。 |
| 5 | 发布控制 | 两仓 Actions 关闭且没有生效的分支保护或 Rulesets；无远端 CI 结论。发布前需要人工逐项签收精确 SHA、离线检查与回退包。稳定标签、默认启动入口替换和旧分支删除各自另行决策。 |

当前建议：继续使用 RC4 并行日常入口；先完成第 1 项的范围决定，再在隔离分支准备版本提交与可安装产物供审查。现有 `vis-manifest-mvp-20261019-rc4` 标签维持试用候选含义。未完成上述门槛前不称为“稳定版”。

## 旧分支收拢盘点

以下为本地远端跟踪引用相对各私有默认线的祖先关系，删除前仍需核对 GitHub PR、工作树占用和远端实时 SHA。`gh` CLI 在本机不可用，本次未独立读取 PR 状态。

| 仓库 | 分支类别 | 相对默认线 | 建议 |
| --- | --- | --- | --- |
| Harness | `codex/d2-preflight04-preparation`、`codex/private-consolidation-20261017`、`codex/vis-manifest-mvp-20261016` | 均已完全包含，独有提交 0 | 可列入将来候选删除清单；先核对 draft PR 和回退引用。当前保留。 |
| Harness | `codex/d2-replayonly-repair-20261010` | 独有提交 5 | 属内部 D2 旧合同，按既有逐项筛选结论保留；不为减少分支数强并入。 |
| Harness | `codex/upstream-sync-20261012` | 独有提交 1 | 核对该提交实际内容和对应 PR 后单独决定；当前保留。 |
| Harness | 11 条 `dependabot/*` | 各有独有提交 1 | Actions 已关闭；需逐条核对安全/依赖价值与 PR 状态，不批量删除或合并。 |
| Runtime | `codex/runtime-workflow-governance-closeout` | 已完全包含，独有提交 0 | 保留到原工作树改动、D2 内部治理和回退引用完成审查。 |
| Runtime | `codex/vis-manifest-mvp-20261016` | 比默认线多 1 条并行日常文档提交 | 可在下一次文档发布时普通快进默认线；推送前核对远端 SHA。 |

两个原工作树的未提交改动和未跟踪文件必须保留；不清理、重置或覆盖。分支收拢仅操作远端引用，且要在版本和 PR 依赖核对后另行执行。
