# rc.31 / official rc.4 bounded trial handoff — 2026-10-27

Status: **ready for one opt-in private trial; no model task has been sent from rc.31.** This is separate from formal D2 ExecuteGate, which remains `NOT_CLAIMED`. Do not change the default daily entry.

## Fixed inputs

- User visually confirmed the fresh rc.31 installed Home has a visible page, default workspace and composer. Its earlier authenticated HTTP check returned page/session API 200, anonymous evidence 401 and zero stderr.
- Isolated launcher: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\START_RC31_OFFICIAL_RC4_PRIVATE_UI.cmd`. The launcher now uses process-scoped PowerShell execution-policy bypass because the user's first launch was blocked before Host startup. A `-DumpConfig` invocation of the same script with that process-scoped policy exited 0 with empty stderr. This does not change machine or user policy.
- Exact kit ZIP SHA-256: `323928F8FBE4272474D071C93772240171EA1214864272D3D258CCA0F6C0C9FB`; official Host rc.4; plugin rc.31; Runtime source `d3af857bb87babb0f96b87adc2839f8761b45eba`.
- Fresh isolated Git workspace: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc31-official-rc4-trial-repo-20261027`, `main` initial commit `31a341f`. It was clean when prepared; the target file did not exist. This directory is distinct from the rc.30 trial and all daily workspaces.
- Installed role configuration: CodeBuddy CLI worker, model delegated to its login/configuration; read-only SiliconFlow Qwen API reviewer and inspector, each bounded by request/tool/output limits. Local CodeBuddy CLI `2.164.0` exists. Login was not independently rechecked. Credentials remain external to the kit and Home.

## One bounded trial, after closing other Host windows

1. Launch the rc.31 isolated entry. Open its local URL, select the fresh trial repository above as the workspace, keep `工作区内修改`, and choose an available parent model. If login, model selection, workspace selection or plugin activation fails, stop and report the state without retrying the task.
2. Send exactly one request: `只调用一次 dsh_runtime，执行 repository_change；只在当前工作区创建 rc31-official-rc4-trial.txt，内容恰好为 RC31_OFFICIAL_RC4_TRIAL_OK 加一个 LF 换行。不使用 D2，不改其他文件；等待子任务状态回执。`
3. Record the task ID, terminal status, reviewer verdict and all three `DSH Runtime` tabs (`执行轨迹 / 实际变动 / 审计`). Do not repeat the call merely because a tab fails to load. Stop the isolated launcher after capturing the result; keep its Home and evidence.
4. The independent post-run check will compare the actual target bytes and Git delta with the settled Manifest, Diff, dual closed traces and governance audit. A model `PASS` alone is insufficient. The target should be 26 ASCII bytes for `RC31_OFFICIAL_RC4_TRIAL_OK` plus one LF, total 27 bytes; recalculate independently during verification.

The existing rc.30/official rc.3 parallel entry and older RC4 daily entry remain separate. Their earlier bounded no-model fallback evidence still stands; no claim is made here that an rc.31-to-rc.30 in-place upgrade/rollback cycle has passed.

The single trial subsequently completed with a bounded `PASS`. Independent read-only reconciliation found the requested 27-byte file and a consistent raw evidence chain; the child report's 26-byte total was wrong. See `RC31_OFFICIAL_RC4_LIVE_TRIAL_RESULT_2026-10-27.md`. Do not repeat the trial for the prose count.
