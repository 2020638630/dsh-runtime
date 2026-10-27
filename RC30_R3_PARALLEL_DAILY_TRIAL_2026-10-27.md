# rc.30 r3 parallel daily trial handoff — 2026-10-27

Status: **prepared, awaiting one user-visible Host task**. This is a private non-D2 trial, not a default-entry switch or stable release. The old RC4 daily work shortcut remains separate and passed a bounded no-model fallback check.

## Fixed local inputs

- Private kit directory: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-private-preview-kit-20261027-ps51-r3`; ZIP SHA-256 `25C8CBC1209256F4BBD141FD4713827EEC7B266670BA0002F4DC26E21E53A826`. It changes only README from r2.
- Parallel launcher: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\START_RC30_R3_PARALLEL_PREVIEW.cmd`. It invokes the r3 `Start-QualifiedHost.ps1`, leaves RC4 alone, and prints a local authenticated URL in its command window. The URL token must stay on this device.
- Preview Home: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-kit-install-home-online-20261026`; official Host runner: `D:\DeepSeekHarness\host-compat-artifacts-20261025\host-runner-0.2.1-rc.3`; Node v24.19.0. The installed Profile is `runtime-api-reviewer-preview` with rc.30 plugin. Its worker adapter is CodeBuddy CLI (model delegated to CLI config); API reviewer/inspector are read-only SiliconFlow `Qwen/Qwen3-Coder-30B-A3B-Instruct` with per-role request/tool/output limits. The external connection JSON path exists outside Home/kit. CodeBuddy CLI `2.164.0` exists locally. This preflight did **not** check local CodeBuddy login or send a model request.
- Fresh isolated Git workspace: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-r3-daily-trial-repo-20261027`, `main` initial commit `c425ecd`, clean at preparation.

## No-model check already completed

The r3 launcher started official rc.3 Host against the isolated preview Home. Authenticated home returned 200 with 38,144 HTML bytes, `session/list` returned 200 with one Session, stderr was empty. The identified launcher and Host stopped; port 49449 closed. Seven selected Home data/config files retained identical hashes and no file was added. The local stdout log was redacted after the check. This verifies r3's unchanged launcher/payload and local return path; it does not qualify a CodeBuddy/API model call.

## Single live acceptance step

1. Keep the RC4 daily work window closed. Open the separate rc.30 launcher and its printed local URL. In the unmodified official Host, choose the fresh trial repository above as the workspace, use `工作区内修改`, and select an available parent model. If login or model selection is unavailable, stop and report that state without repeated calls.
2. Send exactly one bounded request: `只调用一次 dsh_runtime，执行 repository_change；只在当前工作区创建 rc30-r3-daily-trial.txt，内容恰好为 RC30_R3_DAILY_TRIAL_OK 加一个 LF 换行。不使用 D2，不改其他文件；等待子任务状态回执。`
3. Record the task ID, terminal status and model review verdict. Open its `DSH Runtime` card and check `执行轨迹 / 实际变动 / 审计`; keep any failure evidence. Stop the rc.30 launcher afterward. Keep RC4 stopped during this trial even though its Home is separate, so task attribution stays clear.
4. Independently check the repository's exact target bytes and Git delta, terminal Manifest/run state, both closed traces, Diff and governance audit. Treat reviewer prose as a report, not a byte-count oracle. Reconcile any mismatch before a daily-use decision. A completed/PASS task with a correct bounded delta is a prerequisite, not by itself a public release.

No connection JSON, key, Home or full profile should be copied into a handoff. Formal D2 ExecuteGate remains `NOT_CLAIMED`.
