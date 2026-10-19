# 运行可视化私有 RC4 试用证据

状态：2026-10-19 的**私有试用候选**，不是稳定版、默认线更新或 D2 ExecuteGate 声明。两个仓库的 GitHub Actions 均由负责人关闭；以下均为本地验收，不称作远端 CI。

## 固定源码

| 仓库 | 私有注释标签 | 解析后的源码提交 |
| --- | --- | --- |
| DeepSeekHarness | `vis-manifest-mvp-20261019-rc4` | `819dc46ea7953598b239a82e25abe7d87c64add3` |
| DSH Runtime | `vis-manifest-mvp-20261019-rc4` | `15d871d1d960291fe7ab5ed22eb39a9c1d3b9a17` |

两个标签已推送并从私有远端复核。Harness 当前 draft PR #13 的候选分支同为 `819dc46`；Runtime 的 RC4 源码与 RC3 相同，后续文档分支提交不改变标签。RC3 成对标签继续保留，供旧试用与回退核对。

## 本轮验收

Harness 在隔离的 `vis-harness-private-integration` 工作树中使用 Node 24.19.0、仓库自带 pnpm 11.28.5：

- 修复后 `check:ci:static`：**64 passed、0 failed、0 skipped**，并行度 4。先前 6 项失败均在整组运行中通过；CLI 帮助检查另外单独运行通过。Cordis 配置读取器的 Windows 符号链接占位文本聚焦测试 **3/3**，配置门槛 **277/277**。
- 推送钩子类型检查：**5/5**。`build:artifacts --profile official`：**7/7**，记录 325 个客户端产物及 4 个公开构建值。
- 发布相关测试：**194 passed、3 skipped**；冻结、离线、仅锁文件安装检查通过，1698 个条目符合供应链策略。
- 发布打包：vendor **9** 包、DSH **345** 包，均从同一 Harness 提交构建；独立 npm 12.2.0 消费者标准安装全部 **354** 包，确认 658 个默认产品包隔离实验包，安装后 `dsh --version` 为 `0.2.1-rc.2`。

**安装包 Web 入口补验**：另建 `D:\DeepSeekHarness\vis-harness-private-integration\dist\rc4-packed-consumer`，使用 RC4 的 354 个本地归档及 npm 12.2.0 安装，包含 Windows 可选依赖，共新增 884 包。独立 `D:\DeepSeekHarness\vis-trial-rc4-home` 的 `packed-rc4-readonly` Profile 链接已安装的 RC4 provider，指向固定 Runtime `15d871d`；配置解析退出码 0，确认父会话 `read-only`、非 D2 `repository_inspection`、审计和证据各在 RC4 Home 独立路径。已安装 CLI 从此 Profile 启动 Web，在本机随机端口以启动时的一次性访问令牌请求页面，HTTP **200**、HTML 37448 字节、启动 stderr **0 字节**；随后停止服务并确认端口关闭。未发送会话消息、未调用模型或 Runtime，也未通过浏览器目视核对 Manifest 抽屉；因此此项只证明安装包 Web 与配置入口可启动，不扩大为任务或页面交互验收。访问令牌仅留在本机试用 Home 的日志中，不写入本仓库。

归档位于隔离候选下 `dist/npm-819dc46-vendor` 与 `dist/npm-819dc46-dsh`，逐包 SHA-256 清单位于忽略文件 `dist/npm-819dc46-sha256.txt`，清单 SHA-256 为 `96d85dd6f297fe61c84f4e1f891b728ecb70f2c5d9df57962578523368f88c12`。这三个本地产物路径没有推送；标签固定的是源码。首次 DSH 打包因普通客户端构建缺正式配置被脚本拒绝，随后使用 `--profile official` 重建才完成打包；该首次失败不算归档验收。pnpm 执行前依赖状态检查仍提示本地 `node_modules` 可能与锁文件不同步，冻结锁文件检查及实际门槛均通过；这不等于在全新工作树重装全部开发依赖。

## 负责人页面回执与补充验证

2026-10-19，负责人在已安装 RC4 的独立 `packed-rc4-readonly` Web 中检查了新会话入口和一条**导入的历史只读任务**。入口显示“仅可查看”；历史会话“**一次性只读检查工作区**”的 `dsh_runtime` 行可以打开 Evidence Manifest 抽屉，负责人提供的三张截图分别显示“执行轨迹”“实际变动”“审计”页签。页面显示任务 `completed`、审查判决 `UNAVAILABLE`、轨迹与轮次“不适用”、新增/修改/删除均无、审计 `settled`；这些值与该次 `repository_inspection` 的保存 Manifest 一致。截图副本保存在本机独立试用 Home 的 `artifacts/manual-rc4-page-review/`，不包含访问令牌，未推送到源码仓库。此项是负责人实际浏览器回执，不是自动化浏览器通过记录。

为使保存的历史样本可在 RC4 Web 查看，本轮只向 RC4 试用 Home 复制一条 V4 Session、对应投影缓存和四个证据文件，补入该独立 Home 的工作区会话索引，并将**副本** Manifest 的 `diff_content_ref` 从旧 Home 改为副本 Diff 的绝对路径；旧 Home 的会话与证据保持原样。修正前页面正确显示“终态证据不可用”；修正后认证的证据接口 HTTP **200**，返回 `completed` 和审计 `settled`，负责人随后确认三页签内容。页面回执证明 RC4 安装包能读取并展示此历史只读样本，**不等于在 RC4 上重新执行该任务或模型**。验收服务结束后已停止。

RC4 安装包另使用临时 `--patch` 将 `subagent-dsh-runtime` 设为 `disabled: true`：最终配置解析退出码 **0**、明确显示该行已关闭；同一安装包 Web 启动 HTTP **200**、stderr **0 字节**，服务随后停止。固定 Harness 源码的 V3→V4 转换、JSONL 重启迁移及迁移拒绝路径聚焦测试 **3 文件、158/158 通过**。这些测试覆盖代码路径，不证明用户现有 Home 原地升级与旧版降级；该项仍需在复制的真实旧数据上独立验收。

**复制的旧数据迁移抽样（2026-10-19）**：只读盘点日常 `C:\Users\Administrator\.dsh`，其中有 21 条 V3 和 8 条 V4 压缩 Session；未复制或读取凭据。选择其中一条 16,674 字节的 V3 Session，仅将该文件按原相对路径复制到 `D:\DeepSeekHarness\vis-trial-rc4-home\artifacts\legacy-v3-session-migration`，源与副本 SHA-256 一致。固定 RC4 的 JSONL persistence 对副本只读打开得到 V4 逻辑头与 19 条事件；写入打开生成 15,494 字节的 V4 继任文件，重新挂载后仍可读到 V4 与 19 条事件；前后 V3 副本 SHA-256 不变。全过程无模型调用，未写日常 Home。这是**一条真实旧会话的隔离迁移抽样**，不是全部 21 条或整个 Home 的迁移通过。

**全部 V3 会话副本补验**：另建 `artifacts/legacy-v3-batch-20261019`，只复制上述日常 Home 的 21 个 V3 文件，逐条用 RC4 persistence 完成读取、写入 V4 继任文件、重新挂载读回：**21/21 通过**，生成 21 个 V4 文件，事件数范围 19–1615；21 个日常 V3 文件与副本的 SHA-256 在验收后仍相同。第一次批量调用把 persistence 根目录误设为测试 Home 而非其 `sessions` 子目录，出现 21 个 `NotFound`，保留原始失败摘要；修正参数后的通过摘要也留在独立测试 Home。此项验证全部已发现 V3 文件的 Session 格式迁移，但仍未覆盖 Profile、索引、投影缓存、附件、凭据及旧版整包回退。

另将日常 `profiles/web` 的四个非凭据文本文件复制到独立测试 Home，用已安装 RC4 CLI 解析旧 Profile，退出码 **0**；stderr 提示旧 `cordis.patch.yml` 中的 `agent-presets` 补丁条目未找到。最终配置中的 Runtime provider 只有 `runtimeRoot`，缺少当前试用所需治理与证据路径。故解析成功不代表旧 Profile 可直接启动为受控只读产品配置；未用该配置启动服务或调用模型，也未在原 Home 改配置。跨版回退尚未用旧版二进制加升级后 Home 验证；当前安全回退路径仍是保留升级前 Home 快照，并用旧版整包在**独立恢复副本**上验证读取。

**旧版读取组件回退探针**：从官方 npm 仓库将 `@deepseek-ai/dsh-session-persistence-jsonl`、`dsh-session`、格式转换等会话组件固定安装为 `0.1.5-rc.1`，Cordis 固定为 `4.0.2`，置于独立消费者目录；没有使用候选源码的工作区依赖。第一次消费者安装解析出候选源码的本地依赖和较新的传递依赖，已弃用，不计入回退证据；最终从新的独立目录安装并核对版本。用同一条真实旧会话分别制作“仅升级前 V3”和“V3 加 RC4 生成的 V4”两个副本。旧版组件对前者只读打开得到 V3、19 条事件；对后者返回 `SessionFormatUnsupportedError`，明确指出该版本只读 V3、遇到 V4 需升级；两组文件前后哈希不变。这个实测确认**只降级程序而保留混合代 Home 不可作为回退方案**，升级前快照恢复才是候选路径；但它只验证旧会话读取组件的一条样本，尚未验证完整旧版 CLI/Web、Profile、索引与附件恢复。日常 Home 本来已有 8 条 V4，会进一步限制旧版整包的全量读取能力。

**官方 Desktop 来源与聚焦检查**：2026-10-19 直接查询官方 `deepseek-ai/deepseek-harness` 远端 `master`，仍为 `687f282e86`，且该提交是私有 RC4 `819dc46` 的祖先；官方 Desktop 源码已经在候选中，本轮没有新的官方 `master` 提交可合并。候选的 `apps/desktop` 构建通过，Desktop bundle imports、Profile MCP、main startup 三组聚焦测试 **136/136 通过**；首次构建因子进程落到 Node 20 缺 `node:sqlite`，改为全程 Node 24 后受限环境拒绝启动 Git 子进程，最终在已授权的正常进程环境通过。测试第一次同样受限于进程启动，正常环境复验通过。共享 Web 预设中的 `dsh_runtime` 工具仍为 `disabled: true`，Desktop 尚未安装独立只读 Runtime provider 或完成打包后 Manifest 页面验收。构建与聚焦测试不等于桌面安装包可用。

**旧版完整 Web 恢复烟测**：从旧私有默认线固定提交 `60c8f0c813` 新建 `D:\DeepSeekHarness\vis-harness-v3-rollback` 独立工作树，按其 pnpm 11.7.0 锁文件安装依赖。旧仓库完整构建在 Host 类型检查处出现 19 个旧 D2 子代理测试夹具错误；随后只为恢复诊断按原打包配置分别生成 Host、Client 和 Web 运行文件，不把该绕过类型检查的产物称为合格发布包。CLI 报 `0.1.5-rc.1`。它在另建的、只含一条原始 V3 会话的隔离 Home 上无模型启动 Web，认证页面 HTTP **200**、HTML **27,659 字节**、启动 stderr **0 字节**，停止后端口关闭，来源 V3 与副本哈希仍一致。首次尝试查看旧 Web 帮助时未设置隔离 `DSH_HOME`，CLI 试图准备日常 Home 的配置文件，被沙箱 `EPERM` 在写入前阻断；随后所有旧版 CLI 调用均显式设置隔离 Home。此烟测证明旧版完整 Web 壳可从一条 V3 恢复副本启动，未验证旧 Profile、自带的 8 条 V4、索引、附件或历史页面读取。

**RC4 受控 Profile 与旧 Session 文件同场启动**：另建 `artifacts/legacy-rc4-profile-reconciled-20261019`，只从日常 Home 复制 21 个 V3、8 个 V4 压缩 Session 文件，不复制凭据；从已验收的 RC4 只读 Profile 复制配置，并把审计和证据路径改到这个独立 Home。因 Profile 换位置，锁文件中的链接相对路径需在副本内重新计算。最终配置解析退出 **0**、stderr **0**，父会话 `read-only`，治理 v2 只启用 `repository_inspection`。首次受限启动的治理 worker 报 `spawn EPERM`，不计入通过；正常权限复验的 Web 认证页面 HTTP **200**、HTML **37,448 字节**、启动 stderr **0 字节**。29 份 Session 副本与日常源文件 SHA-256 均一致，服务和端口随后关闭。此项只证明配置与旧数据文件同场可启动，未在页面逐条打开会话、未迁移完整 Home，也未调用模型。旧 `agent-presets` 中的 `standard-codex` 在 RC4 新预设中不存在；迁移路线是保留旧 Profile 原件，建立受控新 Profile，并单独决定替代预设，不直接套用旧补丁。

**完整旧 Home 副本读取与原地迁移（2026-10-19）**：从日常 Home 仅复制 `sessions`、`attachments`、`storages` 到独立 `artifacts/legacy-full-home-20261019`，初始 70 个文件逐一核对 SHA-256 一致，不复制凭据。副本含 33 个 Session 文件（21 个 V3、8 个 V4、4 个未标注旧格式）、2 个 PNG 附件、33 个投影缓存；工作区索引含 5 个工作区、29 条普通会话索引。已安装 RC4 使用独立的非 D2 只读 Profile 启动 Web，认证页面 HTTP 200、stderr 0；会话列表返回全部 33 条，29 条普通会话与工作区索引相符。分页读取全部 33 条历史会话，共 4,399 条记录，读取错误 0。打开其中一条需迁移的旧会话后，副本生成一条 V4 继任文件；21 个 V3 文件保留，V4 文件由 8 个变为 9 个，投影缓存有刷新。原始 Home 未作为运行 Home，未写入。该验收证明副本上的历史列表、分页读取和单条原地迁移；其余 24 条待迁移会话仍需逐条或批量迁移。全部 4,399 条记录未发现对这 2 个 PNG 附件的引用，因此不能据此认定附件展示已通过。

**旧版整包对完整快照的读取（2026-10-19）**：在独立 `artifacts/legacy-full-old-rollback-20261019` 恢复相同旧数据副本，用旧版 CLI `0.1.5-rc.1` 无模型启动 Web；认证页面可用、stderr 0，但会话列表只返回 33 条中的 25 条。旧版读取组件此前已对 V3+V4 混合副本返回 `SessionFormatUnsupportedError`。因此仅回退程序不能恢复完整 Home，且即使恢复升级前快照，当前旧版也无法完整读取这份本来已有 V4 的日常数据。需将可读取的旧版范围和快照恢复步骤作为维护窗口前的单独门槛。两个服务已停止并确认端口关闭。

**Windows Desktop 未签名目录包（2026-10-19）**：官方 Electron `44.7.0` 与锁定的 Node/Python/Wheel 依赖均按固定来源下载并核对 SHA-256，写入独立打包缓存；先前的直连下载 `ECONNRESET` 不再阻断。使用独立无凭据示例配置和 Node 24，`package:win:x64:dir --unsigned` 完整运行成功；打包记录 `2026-10-19T07-11-40.770Z` 的 `result.json` 标记 `success=true`，源码构建、354 个 DSH 与 9 个 vendor 归档、runtime 准备、Electron 打包及打包后运行自检均通过。产物位于私有 Harness 候选工作树 `apps/desktop/.desktop-build/targets/win-x64/unsigned-artifacts/win-unpacked/`，其中 `DeepSeek Harness.exe` 与 `resources/app.asar` 均存在。本轮未运行安装器或发布桌面版，也未取得负责人桌面页面回执；共享 Web 预设的 Runtime provider 仍为 `disabled: true`，不能把目录包自检写成 Desktop Manifest 页面验收。

**目录包 GUI 启动边界**：在独立 `DSH_HOME` 和 Electron 用户数据目录中直接打开上述未签名目录包时，Electron 在窗口加载前退出，stderr 指向 Windows AppContainer 对该 D 盘工作树目录的读取 ACL。仅给目录包根增加 `ALL APPLICATION PACKAGES` 读取权限后复验仍报同一错误；`--no-sandbox` 也未改变结果。原日常 Home 没有被选为启动目录。该故障发生在本机源码工作树的目录包启动环境，不推翻打包后运行自检，也不能据此宣称 GUI 启动通过。后续应在专用安装或复制位置核对完整路径权限，再由负责人进行桌面页面验收。

**正常本机进程环境启动补验**：把上述目录包复制到 `C:\Program Files\DeepSeek Harness RC4 Trial` 专用位置。在受限进程环境里直接启动仍遇到相同 ACL 错误；以正常本机进程环境、独立 `D:\DeepSeekHarness\vis-trial-rc4-home\desktop-programfiles-trial-20261019c` 作为 `DSH_HOME` 与 Electron 用户数据目录启动后，Desktop 进程保持运行，创建独立 `profiles/desktop`、`sessions` 和 `storages`，启动 stderr **0 字节**，其内置 Web 认证页面 HTTP **200**、HTML **38,244 字节**。此项证明安装位置与正常进程环境下的首次启动和后端页面可用；窗口内容尚待负责人截图确认，桌面 Profile 尚未接入只读 Runtime provider，也未在桌面端查看 Manifest 抽屉。

## 适用边界与下一步

RC4 相比 RC3 的 Harness 源码只改 9 个文件：发布清单/依赖约束、双语生成模块图、D2 证据脚本中的多余类型断言，以及 Windows Cordis 配置检查器与测试。Runtime 源码未变。此前 RC3 的真实任务、Safe Trace 和 RC2 往返现场仍属于 RC3 证据；本轮补齐了 RC4 安装包对导入历史样本的页面目视、只读入口、provider 关闭验证及一条真实 V3 会话的隔离迁移抽样，但没有在 RC4 上重复模型调用或完成用户现有 Home 的整体原地迁移与跨版回退验收。

接下来按 [私有默认线升级审查与发布顺序](PRIVATE_DEFAULT_UPGRADE_PLAN_2026-10-18.md) 的 P1/P2 审查大范围上游与 D2 内部治理差异；确认默认线的分支保护和离线发布门槛由负责人单独决策。两个原工作树的未提交改动与未跟踪文件继续保留；不清理、重置或覆盖。D2 ExecuteGate 保持 `NOT_CLAIMED`。
