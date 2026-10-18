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

归档位于隔离候选下 `dist/npm-819dc46-vendor` 与 `dist/npm-819dc46-dsh`，逐包 SHA-256 清单位于忽略文件 `dist/npm-819dc46-sha256.txt`，清单 SHA-256 为 `96d85dd6f297fe61c84f4e1f891b728ecb70f2c5d9df57962578523368f88c12`。这三个本地产物路径没有推送；标签固定的是源码。首次 DSH 打包因普通客户端构建缺正式配置被脚本拒绝，随后使用 `--profile official` 重建才完成打包；该首次失败不算归档验收。pnpm 执行前依赖状态检查仍提示本地 `node_modules` 可能与锁文件不同步，冻结锁文件检查及实际门槛均通过；这不等于在全新工作树重装全部开发依赖。

## 适用边界与下一步

RC4 相比 RC3 的 Harness 源码只改 9 个文件：发布清单/依赖约束、双语生成模块图、D2 证据脚本中的多余类型断言，以及 Windows Cordis 配置检查器与测试。Runtime 源码未变。此前 RC3 的真实任务、Safe Trace、安装包 Web、只读 Profile 和 RC2 往返现场仍属于 RC3 证据；本轮没有在 RC4 上重复模型调用、Web 页面现场或跨版本数据迁移验收。若将 RC4 部署给新用户，先以 RC4 归档启动一次专用只读 Web Profile，核对 provider 开关及 Manifest 页面，再更新试用指引。

接下来按 [私有默认线升级审查与发布顺序](PRIVATE_DEFAULT_UPGRADE_PLAN_2026-10-18.md) 的 P1/P2 审查大范围上游与 D2 内部治理差异；确认默认线的分支保护和离线发布门槛由负责人单独决策。两个原工作树的未提交改动与未跟踪文件继续保留；不清理、重置或覆盖。D2 ExecuteGate 保持 `NOT_CLAIMED`。
