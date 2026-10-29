# 第二台 Windows 设备：最终 PASS 原始证据交接

状态：已从第二台 Windows 云桌面取得 rc.30 CodeBuddy worker/API reviewer 最终 run 的原始文件；本机只读检查返回 `RAW_EVIDENCE_CONSISTENT`，云桌面与本机 ZIP SHA-256 完全一致。详见 `RC30_CLOUD_CODEBUDDY_R5_RESULT_2026-10-26.md`。一致性检查不构成发布批准。本说明不会把本机 rc.19/rc.30 样本当作跨设备证据。正式 D2 ExecuteGate 仍为 `NOT_CLAIMED`。

## 设备可用时只带回这些文件

在第二台设备找到**最终成功**的 `dsh-runtime-<UUID>` 运行目录，复制这个目录本身，保留其中的 `evidence-manifest.v1.json`、`run-state.json`、`diff.patch`、`*-runtime-call-trace.jsonl` 以及 `safe-trace-dsh-runtime-<UUID>` 子目录内的两份 `.jsonl` 和两份 `.jsonl.closed`。再单独复制对应 Home 的 `audit\governance.jsonl`。如果验收仓库中的目标文件仍在，可一并复制该单个目标文件，以核对 Manifest 所记的字节数与 SHA-256。

将上述内容放在一个新的**私有**目录，只把该目录路径告诉 Codex。无需复制整个 Home、Profile、连接 JSON、API key、登录态或源码仓库。原设备上的 run 和仓库不要删除、重置或重新执行。若不确定哪条是最终成功的 run，先保留候选 run 目录，再由 Codex 逐条核对；不要只凭页面上的 `PASS` 字样选取。

## 本机只读核验

仓库内工具：`integrations/deepseek-harness/scripts/verify-raw-host-run.mjs`。给它复制后的完整 run 目录和审计文件路径；若目标文件也复制了，再传 `--target-file`。它针对本次单文件 `repository_change` 验收，检查终态 Manifest 与 run-state 的身份、`completed`/`PASS`、唯一新增文件及完整可应用 Diff、同一 run 的 worker 与 API reviewer 轨迹及 `.closed` 字节数、对应 call trace、同一 Session 的治理 `ALLOW` 审计。提供目标文件时，还核对 Manifest 所记的字节数与 SHA-256。它只输出状态、ID、计数和哈希，不输出模型正文、密钥或文件内容。

`RAW_EVIDENCE_CONSISTENT` 只表示这份复制材料通过有限的一致性检查。治理审计记录不含 run ID，因此 `ALLOW` 只能按 Session 和任务类型关联，不能单凭它证明与该 run 一一对应；未提供目标文件时也无法核对其字节。哈希不能证明模型判断正确，更不能单独构成发布批准。若文件缺失、错配或目标文件不符，保留带回材料并报告错误码，不补造文件、不重跑业务任务。

该工具不在固定的 rc.30 插件 tarball 中，不改变官方 Host 或日常 Profile。本机以 rc.19 CodeBuddy worker/API reviewer 和 rc.30 Codex worker/API reviewer 两份既有隔离 run 校验过，七项针对性测试通过；新脚本纳入源码扫描后，官方 rc.3 兼容库存仍为 schema 3、10 个导入包、零问题。它尚未读取第二台设备文件。
