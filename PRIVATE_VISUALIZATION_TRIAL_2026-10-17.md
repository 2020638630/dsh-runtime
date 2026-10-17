# 运行可视化首期私有试用候选 RC1

状态：私有试用候选，非默认分支、非稳定版。设计依据为 `PROJECT_TARGET_AND_RUNTIME_VISUALIZATION.md` R9 正式基线，任务与验收记录见 `RUNTIME_VISUALIZATION_BACKLOG.md`。

## 固定版本与回退

| 仓库 | 私有远端 | 候选分支 | 本次固定标记 | 前一可回退提交 |
| --- | --- | --- | --- | --- |
| DSH Runtime | `origin` (`2020638630/dsh-runtime`) | `codex/vis-manifest-mvp-20261016` | `vis-manifest-mvp-20261017-rc1` | `fc5b252` |
| DeepSeekHarness | `private` (`2020638630/deepseek-harness-private`) | `codex/vis-manifest-mvp-20261016` | `vis-manifest-mvp-20261017-rc1` | `9f799daad1` |

两个仓库各自用相同标记名固定配套代码。按标记检出即可复现本候选，不依赖活动分支随后如何移动。若要撤回本轮新增的负向验收脚本和部署说明，可分别回到表中前一提交；该回退点保留此前已验收的可视化功能。原治理工作树中的未提交改动和未跟踪文件不属于候选，也不得因部署或回退而清理。

## 试用部署

1. 在独立部署目录检出两仓的同名标记，安装 Harness 冻结依赖并按仓库要求构建；使用受支持的 Node 24 和可运行的 Python。
2. 将 `@deepseek-ai/dsh-subagent-dsh-runtime` Bundle 安装到专用 Web Profile。按 Harness 中该 Bundle 的双语 README 配置绝对 `runtimeRoot`、治理 v2 policy/hash、仅所需 `enabledWorkloads`、工作区外独占的 `auditPath` 和 `evidenceRoot`。
3. 标准 Web Agent Preset 的 `delegation` 组里，`tool-subagent-dsh-runtime` 默认关闭；复制该 preset、在副本中启用嵌套工具行，并让试用会话使用副本。仅配置 Host provider 或在顶层插入同名工具行，不会让标准 Web 会话获得该工具。先用 `dsh --profile web --patch <patch-path> --dump-config` 核对组合，再启动 `dsh web --patch <patch-path>`。
4. 首次试用先只启用 `repository_inspection` 并指向测试仓库。只有在明确授权的任务与独立配置中才加入 `repository_change`。D2 ExecuteGate 属内部治理，仍为 `NOT_CLAIMED`。

## 验收范围

- Runtime 聚焦测试 170/170；Harness 证据 provider 与抽屉聚焦测试 62/62；受控 Web 回放 3/3；Web 工具经真实 Runtime 子进程到浏览器的无模型失败/取消 2/2。
- 真实只读及写入成功路径、Safe Trace `.closed`、证据 Manifest 三视图已有独立验收记录。无模型负向用独立临时 Git 仓库和非 D2 配置：失败为 `error`、取消为 `aborted`，两者均不虚构 Manifest。
- 直接启动 `dsh web --no-open --port 0` 的隔离 CLI 烟测取得认证页面 HTTP 200。该 CLI 烟测与 Web 工具负向验收是两个独立运行，不声称在同一次 CLI 会话内触发了负向子任务。
- Harness 完整 `pnpm run typecheck` 通过；本次部署说明的英中配对检查通过。`pnpm run doc-sync` 为 41/43：既有 `packages/extensions/cordis-client-runner/src/client/slot-catalog.ts` 目录过期，以及 `packages/llm/llm-deepseek/README.i18n.yaml` 两节英文配对记录过期；稳定发布前须修复并重跑。

## 后续顺序

1. 在专用试用环境进行一次实际 `dsh web` 会话内的只读任务与负向页面手工复核，记录所用配置和版本；如要覆盖需要模型的业务失败，另行确定调用范围和额度。
2. 清除上述文档总检查漂移，完成稳定版发布门槛与部署回退演练。P1 实时流在首期终态 Manifest 稳定后进行，Memory/RAG 留在远期愿景。
3. 再审查默认分支与旧分支收拢。Harness 的 `codex/d2-replayonly-repair-20261010` 有 5 个候选未包含提交，`codex/upstream-sync-20261012` 有 1 个；原治理工作树仍有未提交文件。本候选不删除分支、不改默认分支。
