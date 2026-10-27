# rc.31 / official rc.4 bounded live trial — 2026-10-27

## Scope and visible result

The user sent the single bounded `repository_change` request prepared in `RC31_OFFICIAL_RC4_TRIAL_READY_2026-10-27.md` from the separately installed rc.31 / official rc.4 Home. Subtask/run ID: `b1f10b67-6266-46b6-aa21-16fe3a9b2d62`. The three `DSH Runtime` tabs opened and showed `completed` / model review `PASS`; the changes tab listed one added file, no modifications or deletions; the audit tab showed `settled`, API review `completed`, two `read_file` calls and call ID `7cdde5e3-d36e-4f91-a146-9cea9dcde7c0`.

This is an opt-in private test, not formal D2 ExecuteGate. No second model call was made for this verification.

## Independent read-only reconciliation

- Workspace: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc31-official-rc4-trial-repo-20261027`. It was initialized clean at commit `31a341f` and the target did not exist at preparation. After the task, `git status --porcelain` listed only `?? rc31-official-rc4-trial.txt`.
- Target bytes exactly match ASCII `RC31_OFFICIAL_RC4_TRIAL_OK` plus a single LF (`0x0A`): **26 content bytes + 1 LF = 27 bytes**. Hex: `524333315F4F4646494349414C5F5243345F545249414C5F4F4B0A`. SHA-256: `8A57D149BC386C3773076D94ED2C25A08395BE1FCCA331A052FE02DE2B972F20`. No CR, BOM or extra newline.
- The settled Manifest records exactly one added file, zero modified and zero deleted, an applicable Diff, `afterBytes: 27`, and the same target hash. The run-state is `settled` / `completed`; the reviewer verdict is `PASS`.
- The Runtime call trace has one `call_started` at `06:49:16Z` with `invocation_count: 1`, then one successful `call_terminal` at `06:50:52Z` with exit code 0. The target filesystem creation time is `06:49:40Z`, between those events. The complete CodeBuddy safe trace records successful `Write`, `Bash` and `Read` events; both worker and API review traces have valid `.closed` markers.
- `verify-raw-host-run.mjs` returned `RAW_EVIDENCE_CONSISTENT` with `target_file_verified: true`, matching Manifest/Diff/closed traces/audit/target hashes. One governance `ALLOW` matched the Session and task kind. The audit still lacks a unique run ID, so that audit link is not exclusive proof of run attribution. The shared workspace snapshot also does not prove exclusive actor attribution.

## Discrepancy and gate

The child/reviewer prose says the target was already present when checked and reports **26 bytes total**. The independent target, Manifest and Diff show **27 bytes total**. Because the target was absent at preparation, the safe trace shows a successful `Write`, and its creation time falls within the call interval, the prose likely describes the later verification state. This is an inference, not a stronger physical attribution claim. Do not change the correct target to match the wrong prose count.

**GO for the single bounded rc.31 / official rc.4 private live-task check.** This does not switch the default daily entry or establish stable/public support. The rc.30 / official rc.3 parallel entry and older RC4 daily entry remain separate fallbacks. An isolated upgrade/rollback cycle, broader environment coverage, stronger audit run linkage and any second-device rc.31 result remain open.
