# rc.31 / official rc.4 second-device acceptance — 2026-10-27

## Bounded result

An independent Wuying Windows Server 2022 device installed the frozen rc.31 private kit with an exact qualified `@deepseek-ai/dsh@0.2.1-rc.4` runner. The installed Home and Runtime were new and separate from the existing rc.30 entry. PowerShell was 5.1.20348.5622, Node 24.22.1, Python 3.12.10 and pnpm 11.25.0. The globally installed CodeBuddy was 2.176.0; the rc.31 Host process selected an isolated CodeBuddy 2.164.0 shim through process-scoped `PATH`. The authenticated page, model selector, composer and enabled `@dsh-runtime/harness-plugin` were visible.

The frozen kit ZIP SHA-256 was `323928F8FBE4272474D071C93772240171EA1214864272D3D258CCA0F6C0C9FB`. The separate operator runbook SHA-256 was `F2299A7D876433DAE83B8754F4EBF3682A2AB9DDB86A11027C5BBE2475B735A1`. The external connection file remained outside the kit and Home; its contents were not transferred.

The user initialized `C:\DSH-RC31\second-device-trial-20261027` at empty root commit `38b4474` and confirmed a clean Git status. The rc.31 UI selected that workspace. Exactly one bounded `repository_change` request was sent, without D2. Run ID `dsh-runtime-24a03582-07b9-4f1d-a3b6-51ea03951b8c` settled `completed` with reviewer `PASS`. Call ID was `50a2c0b9-f37d-4a74-a7af-bae19a9c47e3`. All three Runtime drawer tabs opened. The execution tab showed Read 1, Edit 2, Write 1, Bash 1; the changes tab showed one added file and no modified or deleted files; the API review tab showed `completed` and one `read_file` call.

## Independent reconciliation

- The target `rc31-second-device-trial.txt` contains exactly ASCII `RC31_SECOND_DEVICE_OK` plus one LF: 22 bytes, no BOM or CR. SHA-256: `937A119B10C6E2140F4BB46C4E8221F51A9E1A1D935ECA68774A523E55F2DD06`.
- Cloud read-only verification reported exact bytes, only `?? rc31-second-device-trial.txt` in Git, and zero other top-level entries. The copied target has the same hash. The settled Manifest records one addition, `afterBytes: 22`, and that hash.
- The 8,054-byte handoff ZIP is `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\handoff-rc31-second-device-24a03582.zip`. Its SHA-256 was `77E4D91EC3B93F001D812B39BE722C321CE6FA9EFBD4F86D3C9BBF8A4F4F6B26` on both the cloud and local machine. It contains only this run's evidence directory, the governance audit, and the target file; it does not contain the connection JSON or a full Home.
- The copied run has Manifest, Diff, run state, Runtime call trace and both worker/reviewer safe traces with `.closed` markers. The read-only `verify-raw-host-run.mjs` returned `RAW_EVIDENCE_CONSISTENT`, `target_file_verified: true`, one matching governance `ALLOW`, and the same target hash. The audit link is by Session and task kind only because governance records have no unique run ID. This consistency check does not establish exclusive actor attribution.

After stopping the rc.31 Host, the user reopened the original cloud rc.30 Home through its own qualified rc.3 runner. The historical `trial-repo-codebuddy-r5` workspace and saved `创建cloud-rc30验证文件` conversation were visible; the composer and enabled plugin were also visible. No model task was sent for this return check. The older Home, rc.31 Home and trial workspace remain separate.

## Decision and limits

**PASS for this exact second-device, single-task private Windows acceptance and separate no-model return check.** This adds a second rc.31 device to the local bounded trial. It does not qualify arbitrary workloads, in-place upgrade or uninstall, the globally installed CodeBuddy 2.176.0 as a worker, general/public distribution, daily-entry promotion, or a formal D2 ExecuteGate. Keep the frozen ZIP, both Homes, trial workspace and raw evidence unchanged pending retention and release decisions.
