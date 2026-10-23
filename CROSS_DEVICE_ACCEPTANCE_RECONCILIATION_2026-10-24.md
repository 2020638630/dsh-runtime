# 第二台设备验收回执核对（2026-10-24）

来源：`E:\DeepSeekHarness-第二台机验收\CODEX_RESULT.md`、`ACCEPTANCE_RECEIPT.md`、`验收速查.md` 和 `rc19-debug-bundle/`，均保持只读。回执由第二台设备操作者生成；本机没有登录该设备或重做模型调用。本文件不复制连接 JSON、key 或原始调试日志。

## 包身份

E 盘基础包 SHA-256 `A20D0E42479CD36A531390C05C4FD33E219A72AF025D41C0529C7C2CC1FF0AC0`；rc19-r2 包 SHA-256 `72F0F7CEE601D7E6A74171E382BA8D47D5181C30893C4A32D48687A083D7E9BC`，均与原发布记录一致。回执报告官方 Host `0.2.1-rc.2`，Windows 11 Build 26300、Node 24.21.0、Python 3.12.10、pnpm 12.15.0。D2 ExecuteGate 未 claim。

## 回执与证据等级

| 路线 | 操作者回执 | 本机可独立复核 | 尚缺 |
| --- | --- | --- | --- |
| 基础包 rc14，CodeBuddy worker + Codex CLI reviewer | 非 D2 inspection 与 change 完成；run `dsh-runtime-b6b7f3c8-71d3-42d4-9dc3-f47ca6fb2d32` 为 `completed / PASS / ALLOW`，唯一新文件 `acceptance-proof.txt` 为 6 字节 `dsh-ok`，重启后会话保留。 | 包 ZIP 哈希匹配；详细回执列出 Manifest、diff、执行轨迹和审计的观察结果。 | 本次未附该 run 的原始 Manifest/Safe Trace；新设备没有旧日常 Home，故未做“切回旧日常入口”的现场。 |
| rc19-r2，CodeBuddy worker + SiliconFlow API reviewer | `CODEX_RESULT.md` 报最终 run `dsh-runtime-7c9ea461-a9ab-48b9-be57-9bb890b818c1` 为 `completed / PASS / ALLOW`，`read_file=1`，唯一新文件 `acceptance-proof-rc19.txt` 为 11 字节 `dsh-rc19-ok`。 | 包 ZIP 哈希匹配；附带调试包的前两次失败 Manifest 分别确认为 `http_client_unavailable` 和 `reviewer_no_file_read`。 | 调试包只含失败 run `0c255f81`、`def63370`；最终 PASS run 的 Manifest、两条 `.closed`、审计和文件字节证据尚未附。已向用户请求脱敏补充。 |

`ACCEPTANCE_RECEIPT.md` 的第 6 节已经写入 rc19 关闭代理后的 PASS，但第 7 节仍称 “reviewer verdict 未达 PASS”；这是回执内部未同步的旧结论。按明确 run ID 保留前两次 `UNAVAILABLE`，最终 PASS 记为**操作者报告**，在收到最终原始证据前不提升为独立复核通过。

## 发现的问题与修正范围

1. **可证实的安装缺口**：rc19-r2 Runtime 归档含 `requirements-api-agent.txt`，旧安装器只装 pnpm 依赖。第二台设备首轮 `http_client_unavailable`，手动安装 `httpx==0.28.1` 后不再出现。候选安装器已改为私有 r3 包内七个 hash 校验的 wheels、专用 venv、无 Python 索引访问。新的 r3 仅完成本机全新 Home 的**无模型**离线安装；不能把 r2 的第二设备模型 PASS 直接归给 r3。
2. **代理归因仍未确认**：回执观察到 Clash 系统代理开启时 `reviewer_no_file_read`，关闭后同模型通过。但固定 Runtime `5f43570` 的 `ChatCompletionsTransport` 发送 `stream: false`，创建 `httpx.AsyncClient(..., trust_env=False)`；常见环境代理不会由该客户端自动读取。因此“系统代理干扰流式 tool-calling”与固定源码不符。可能涉及请求环境、响应差异、模型非确定性或其他进程；暂不改为全局禁代理，也不在文档宣称根因已证实。保留失败样本，最终证据到齐后再比较。
3. **工作区边界**：回执首轮在非 Git default-workspace 未生成 Manifest，切到临时 Git 仓库后有 Manifest。该情形应在试用说明中要求先选择 Git 工作区，并将非 Git 运行的证据缺失作为单独产品行为处理。

## 新候选包 r3（仅安装修正）

路径 `D:\DeepSeekHarness\api-agent-host-artifacts-20261023\rc19-private-preview-kit-20261024-r3.zip`；SHA-256 `5A244EF1817F5D917145EF5860AAB657A453BE8120C2E2A5E93B3D9D5BF5E9CE`。功能插件 rc.19 与 Runtime `5f43570` 归档未变；Manifest schema 3 新增七个 PyPI wheel 的 SHA-256 校验，安装器在新 Runtime 内建 venv，并用 `--no-index --find-links` 安装。新全新 Home 离线安装成功，venv `httpx==0.28.1`，Profile 引用该 venv；篡改 httpx wheel 的负向测试在创建 Home/Runtime 前拒绝。ZIP 的 12 个文件及内层归档共扫描 401 个 blob，本机两项 key 命中 0；外部连接文件未打包。**r3 尚未做真实模型或第二设备验收，也未升为日常稳定包。**

后续优先：补收最终 PASS run 证据、对照失败/成功的 provider 与请求路径；再在隔离环境对 r3 做一次安装后官方 Host 配置/页面检查。API worker 写工具仍关闭，正式 D2 ExecuteGate 为 `NOT_CLAIMED`。两个原源码工作树的全部未提交和未跟踪内容继续保留。
