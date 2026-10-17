# 运行可视化首期私有试用候选 RC2

状态：私有试用候选，仍非默认分支或稳定版。完整部署步骤、首期功能范围及回退说明见 [RC1 记录](PRIVATE_VISUALIZATION_TRIAL_2026-10-17.md)；本记录只描述 RC2 的增量与固定引用。

| 仓库 | 候选分支 | RC2 固定标记 | 前一回退标记 |
| --- | --- | --- | --- |
| DSH Runtime 私有 `origin` | `codex/vis-manifest-mvp-20261016` | `vis-manifest-mvp-20261017-rc2` | `vis-manifest-mvp-20261017-rc1` |
| DeepSeekHarness 私有 `private` | `codex/vis-manifest-mvp-20261016` | `vis-manifest-mvp-20261017-rc2`（含 `26c11095f9`） | `vis-manifest-mvp-20261017-rc1` |

RC2 补齐了 Harness 的生成式 client slot catalog 与 DeepSeek LLM 说明配对记录；`dsh_runtime` 抽屉槽位现已登记。完整 `pnpm run doc-sync` 复核 **43/43 通过**，此前 RC1 记录的两项文档检查失败已关闭。Web 工具真实负向路径 2/2、`dsh web` 独立启动烟测、完整类型检查等功能证据沿用 RC1，未重新命名为单次 CLI 端到端验收。

稳定发布仍需专用部署环境中的试用会话复核及发布/回退演练；需要模型的业务失败样本若列为发布条件，须单独确定调用范围。D2 ExecuteGate 保持 `NOT_CLAIMED`。Harness 两条旧 D2 分支有 6 个不在本候选内的内部治理提交，因此继续保留，不合并到用户可视化分支，也不删除或修改默认分支。两个原治理工作树的未提交和未跟踪文件继续保留。
