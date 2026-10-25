# rc.30 official Host live trial: prepared, not started

Date: 2026-10-25. This handoff is for a future **single bounded model-backed trial**. No rc.30 model task has been sent yet. Do not infer PASS from installation or no-model drawer replay. Formal D2 ExecuteGate remains `NOT_CLAIMED`.

## Fixed inputs

- Official unmodified Host runner: `D:\DeepSeekHarness\host-compat-artifacts-20261025\host-runner-0.2.1-rc.3` with Node `24.22.1` at `C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`.
- Private plugin archive: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\package\dsh-runtime-harness-plugin-0.1.0-rc.30.tgz`, SHA-256 `2F6EB8D2BB03A4759CF9CC158BB3EAEA6EFEC22A096E1F39490598DD41CC2EB3`.
- New isolated Home: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\host-home-r30-live`; Profile `runtime-api-reviewer-preview`; Profile lockfile SHA-256 `38378A0495853F67B1BE8DABDF274E0701D830359D1FAF62C37D454764612A21`. It has no copied sessions or credential file. The external API connection file and configured Python interpreter exist; their contents were not read in this preparation.
- New trial repository: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-live-trial-repo`, clean `main` at `916943f`, containing only a committed `README.md`. `rc30-live-check.txt` was absent at preparation.
- The plugin install and official Host config dump passed, with zero stderr bytes from dump. No Host server is running for this live Home.

## Next bounded run

1. Recheck five-hour and weekly usage, exact archive hash, Profile lock hash, clean trial repository and absent target file. Verify no other process is using `host-home-r30-live`.
2. Launch the official Host with `DSH_HOME` set to that isolated Home and `--profile runtime-api-reviewer-preview`. Confirm the governance worker mounts before sending any task. Keep the old daily Home and the rc.29 user-review Host untouched.
3. In a new Session with this exact trial repository and “工作区内修改” access, send once: `只调用一次 dsh_runtime，执行 repository_change；只在当前工作区创建 rc30-live-check.txt，内容恰好为 RC30_LIVE_OK 加一个 LF 换行。不使用 D2，不改其他文件；等待子任务状态回执。` Do not retry blindly if the task fails or leaves a partial file.
4. Independently check task terminal status, reviewer verdict, both worker/reviewer `.jsonl.closed` traces, settled Manifest and audit, exact target bytes, `git status --porcelain` and the three drawer tabs. Keep a failed run and its residual state for diagnosis. The intended file content is `RC30_LIVE_OK\n` (13 bytes: 12 ASCII characters plus LF); verify this count before running.

The previous rc.30 no-model acceptance is in `RC30_RC3_ALIGNMENT_2026-10-25.md`. The second-device raw PASS evidence remains deferred; this local trial cannot replace it.
