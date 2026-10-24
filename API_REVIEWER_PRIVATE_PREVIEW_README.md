# API reviewer 私有并行试用包

本包配合**未修改的官方 DeepSeekHarness `0.2.1-rc.2`**。它安装独立 Home/Profile 和 Runtime 源码快照；已有日常 Home 不作为安装目标。worker 可选 CodeBuddy 或 Codex CLI；reviewer/inspector 为只读模型 API。API worker 写工具仍关闭；D2 ExecuteGate 为 `NOT_CLAIMED`。

包内 `manifest.json` 列出插件 TGZ、Runtime ZIP 的 SHA-256 与固定源码提交。`Install-ApiReviewerPreview.ps1` 在写入前核对这两个摘要、目标目录不存在、Home/Runtime 不互相嵌套且外部连接文件不在二者内；它还用包内 Runtime 解析器核对连接文件、引用名和 provider，失败时只给固定错误提示，不输出 key。随后离线或在线安装插件。包不含 API key、Home、会话或已有 Profile；安装器只把外部 `ConnectionPath` 路径写入新 Profile，不复制文件内容。

安装参数：`-KitRoot` 为解包目录；`-HomeRoot` 和 `-RuntimeRoot` 必须是两个不存在的独立目录；`-ConnectionPath` 指向用户自己保管的连接 JSON；`-PythonPath`、`-PnpmPath` 指向本机程序。`-WorkerAdapter` 只能为 `codebuddy`（默认）或 `codex`；`-WorkerModel` 默认为空，即使用 CLI 自身默认模型，也可填写该 CLI 支持的模型 ID。所选 CLI 必须在运行机器上可用，安装器不会安装 CLI 或探测其账户额度。`-Provider` 只能为 `siliconflow` 或 `openrouter`；`-ConnectionRef`、`-ReviewerModel`、`-InspectorModel` 必须与外部连接配置和实际供应商能力一致。安装器先校验 Manifest 中的七个 Python wheel 摘要，再在新 Runtime 目录创建专用 Python venv，从包内 wheelhouse 安装 `httpx==0.28.1` 及固定依赖；**不会访问 Python 包索引或修改共享 Python**。`-Offline` 仅控制 pnpm，它要求本机 pnpm 缓存已有插件依赖。安装器当前不自动验证官方 Host 程序版本，启动前须核对为 `0.2.1-rc.2`；建议先在没有真实会话的新 Home 中安装和配置检查，再做独立临时仓库验收。

启动时设置 `DSH_HOME` 为新 Home，并用官方宿主的 `--profile runtime-api-reviewer-preview`；不要同时启动两个指向同一 Home 的进程。回退仅需停止该独立 Host，再启动原日常入口。安装器拒绝覆盖，卸载或清理须另行审查，不属于本包自动操作。

验收范围：rc19 隔离官方 Host 的 CodeBuddy worker + API reviewer `repository_change` 已有一次 `completed/PASS` 现场，双轨迹、审计和精确字节一致；本机全新 Home 的无模型安装/启动已通过。第二设备回执报告基础包和 rc19 均在独立临时仓库最终 `PASS`，但所交调试包只含 rc19 早期失败 run，最终成功 run 的 Manifest/Safe Trace 仍需另附后才能完成独立证据复核。单次现场不表示所有模型、供应商或 API worker 已获资格。

第二设备曾遇到缺少 `httpx` 的 `http_client_unavailable`；本修订安装器补齐依赖。还观察到开启系统代理时 `reviewer_no_file_read`、关闭后成功，但这**仅是时间相关的现场观察**，不是已证实根因：固定源码的 API transport 使用非流式请求并设置 `trust_env=False`，不自动读取常见代理环境变量。出现同类失败时先保留失败 run、检查所用 provider/模型与请求证据，再在隔离环境对照网络路径；不要默认永久关闭系统代理或把缺少工具调用归咎于代理。
