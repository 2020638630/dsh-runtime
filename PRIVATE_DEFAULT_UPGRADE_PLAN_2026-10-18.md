# 私有默认线升级审查与运行可视化发布顺序

状态：2026-10-18 的**审查计划**，尚未移动默认分支或发布稳定版。依据 [R9 设计基线](PROJECT_TARGET_AND_RUNTIME_VISUALIZATION.md)、[任务清单](RUNTIME_VISUALIZATION_BACKLOG.md)与 [RC3 验收记录](PRIVATE_VISUALIZATION_TRIAL_2026-10-18_RC3.md)。D2 ExecuteGate 继续为 `NOT_CLAIMED`。

## 固定输入与实际差异

| 引用 | 本地已核对提交 | 作用 |
| --- | --- | --- |
| Harness 私有默认线 `integration/dsh-runtime-d1-q2-closeout` | `60c8f0c813a55754338d1e53a655f480a5f62f02` | 当前用户可拉取的既有私有默认线 |
| Harness 公开上游 `origin/master` | `687f282e8625c6b8d11ff58211a90524be2e4317` | 2026-10-18 现场远端查询也指向此提交 |
| Harness 私有候选 `codex/private-consolidation-20261017` | `a6e8d20476450be8c48b27e310d760034610b15a` | RC3 精确验收来源；私有远端已重新核对 |
| Runtime 私有候选 `codex/vis-manifest-mvp-20261016` | `a5531cf4c6e32231e05872063e58b4c64193c33d` | 本轮文档提交前的远端来源；后续文档已推进该候选 |
| Runtime 既有默认线 `master` | `ebb191ae998af6251731f02e28ba16d4ce733fac` | 尚未移动 |

Harness 候选同时包含私有默认线和公开上游。与私有默认线相比，它领先 **6077** 个提交、涉及 **12927** 个文件；与当前公开上游相比，它领先 **61** 个提交、涉及 **236** 个文件。私有默认线与公开上游并非线性关系：两者共同祖先之后，私有默认线独有 2 个提交，上游独有 6018 个提交。`dae159ae1f` 把截至公开上游 `d743267388` 的一波更新并入了 D2 整合，`77cbead5fc` 再把上游 `687f282e86` 并入可视化候选。因此直接快进私有默认线会一次交付大量上游变化及 D2 内部治理代码，不能作为单一 Evidence Manifest 更新审查。

本轮受限环境内首次刷新私有远端时，Git 凭据辅助程序无法启动，Runtime TLS 凭据也不可用。随后通过已授权的正常 Git 远端访问重新读取三条私有分支及公开上游：SHA 均与上表一致，**截至这次查询无来源漂移**。发布分支或标签时仍须以远端原 SHA 为并发保护，避免查询后发生竞态更新。

**路径级审查结果**：以公开上游到 Harness 候选的差异为口径，`.agents`、`scripts`、`.github`、`docs` 合计 114 个文件（约 8230 行新增）；三个 Runtime 相关 subagent 包合计 42 个文件（约 7597 行新增）；Web/CLI、工具行及 DeepSeek 适配合计 27 个文件（约 3130 行新增、55 行删除）；根锁文件、桌面、bundle 与 boot 等 11 个文件（约 814 行新增、289 行删除）。这些是有交叉可能的审查分组，不能相加当作 236 个文件的完整分割。`packages/subagent/subagent-dsh-runtime` 和 `subagent-governance-python` 的包版本已是 `0.2.1-rc.2`。候选 `.github/workflows/ci.yml` 对私有仓库改用托管 runner，并让 Python release 形态矩阵与 benchmark 在私有 PR 中跳过；`.github/workflows/release.yml` 仅允许私有仓库手动触发发布演练。因此当前本地通过的构建、测试与打包不能代替这些被跳过或仅手动运行的远端门槛。默认线切换前须逐项确认私有 CI 的实际必需检查，明确未跑的检查由哪一项证据补足或保留为发布限制。

**上游分批可行性**：对公开上游 `687f282e86` 与私有默认线 `60c8f0c813` 做只读三方合并探测，结果有三个冲突：`docs/config-catalog.md`、已被上游删除的旧 `packages/preset/agent-presets/presets/standard/agent.cordis.yml`、`pnpm-lock.yaml`。旧默认线在该已删除预设中新增的只是默认关闭的 `tool-subagent-dsh-runtime` 行；当前候选已将默认关闭的工具行移到新布局 `packages/bundle/web-app/presets/standard.patch.yml`。因此若建立“先上游、后产品”的新集成分支，应保留上游删除、在新预设位置保留 opt-in 工具行，随后按新依赖重新生成锁文件和配置目录，并核对生成内容。不能把三方合并的自动产物直接作为可用升级批次；本探测没有写入任一工作树。

## 按顺序推进的审查批次

### P0：保持 RC3 可复现，关闭来源漂移

- 以 Harness `a6e8d20476`、Runtime `15d871d` 的干净固定检出和已记录的归档哈希为验收来源；保留 Runtime 私有候选 `a5531cf4c6` 为设计与任务记录来源。
- 私有远端已重新核对上述引用；若后来前移，仅审查新提交，不重跑已通过的 9/9 构建、51/51 发布测试或模型现场样本。
- 成对候选已建立不可变 RC3 引用；正式版本和正式部署路径须指向同一对已验收提交。现有 RC1/RC2 标签保持原样。

已完成：两个私有远端现均有注释标签 `vis-manifest-mvp-20261018-rc3`，Harness 标签解析为 `a6e8d20476450be8c48b27e310d760034610b15a`，Runtime 标签解析为 `15d871d1d960291fe7ab5ed22eb39a9c1d3b9a17`。Runtime 标签固定验收所用源码，后续仅文档的候选提交不改变这对来源。此标签是**私有试用候选**，不是稳定版承诺或默认线更新。

### P1：独立审查公开上游升级

- 先审查 `d743267388` 和 `687f282e86` 两个上游落点的版本、锁文件、发布脚本、桌面与 Web 启动变化。以现有两次 merge 为证据节点，**不把 `dae159ae1f` 或 `77cbead5fc` 称为纯上游提交**；它们的第一父链中已有私有变更。
- 将 `origin/master...a6e8d` 的 236 个私有差异文件单独列为后续审查范围。发布门槛：能解释安装与 Web 启动的版本变化，并保留 RC2→RC3→RC2/RC3 的整包回退证据边界。
- 若需要给私有默认线做分阶段升级，应在独立新分支重放上游与必要私有适配，再审查差异；不能把当前混合历史中的中间 merge 直接当作可部署的纯上游批次。

### P2：私有集成和 D2 内部治理审查

- 将 `packages/subagent/subagent-dsh-runtime`、`packages/subagent/subagent-governance-python`、`packages/llm/llm-deepseek`、CLI 宿主及 `.agents`/`scripts` 治理文件列为独立审查面。确认版本对齐、工具允许表和来源绑定；D2 代码虽在候选中，ExecuteGate 仍未获业务执行声明。
- 旧 D2 分支另有 5 个和 1 个独有提交；保留原引用，逐项判定是否仍适用。不得为“只留最新分支”强行并入或删除。
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

两个原工作树仍有未提交改动与未跟踪文件；只在隔离候选中写本计划。未清理、重置或覆盖原树；未移动默认线、删除旧分支、宣称 D2 ExecuteGate 或创建稳定版标签。成对 RC3 试用标签已固定；下一项工作是完成 P1/P2 的路径级审查，形成可单独批准的默认线升级提案。

**安装包 Profile 补验（本轮）**：`D:\DeepSeekHarness\vis-trial-rc3-home\profiles\packed-rc3-readonly` 使用已标准安装的 RC3 provider，`sandbox-policy.mode: read-only`，Runtime 治理只允许 `repository_inspection`，审计和证据各有独立路径。配置解析通过。已安装的 RC3 CLI 用此 Profile 启动真实 Web，HTTP 200、启动错误日志为空；浏览器在新会话入口选定现有的独立 `vis-trial-rc3-readonly3-repo`，页面显示“访问模式，当前：仅可查看”。未发消息、未调用模型或 Runtime，故这证明新会话**入口默认值**，不证明已运行的任务权限。服务已停止。最初在完全独立的 `rc3-packed-home` 下建立的同名 Profile 也通过配置解析、HTTP 200 和只读入口显示，但浏览器文件选择器未完成新仓库登记；因此改用已有试用 Home 的独立 Profile 完成工作区选择。首次受限启动出现 `spawn EPERM`、provider 未激活；最终 HTTP 200 和空错误日志来自允许治理 worker 启动的正式复验，不混同两次结果。
