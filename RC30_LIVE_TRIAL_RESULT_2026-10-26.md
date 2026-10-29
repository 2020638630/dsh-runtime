# rc.30 official Host bounded live trial

Date: 2026-10-26. This is one non-D2 `repository_change` run in a fresh isolated repository and Home. The official `@deepseek-ai/dsh@0.2.1-rc.3` Host was not modified. Formal D2 ExecuteGate remains `NOT_CLAIMED`.

## Inputs and boundary

- Fixed package and Profile are recorded in `RC30_LIVE_TRIAL_READY_2026-10-25.md`. The archive and lockfile hashes were checked before launch.
- Isolated Home: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\host-home-r30-live`; isolated repository: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-live-trial-repo`, clean at `916943f` with the target absent before submission.
- The prepared repository was registered in the isolated Home's `storages/workspace.json`; the official Web UI selected `rc30-live-trial-repo` and displayed `工作区内修改`. One prompt was sent. The one-call marker is `rc30-live-one-call-20261026.json` in the artifacts directory. A first headless inspection did not submit because the workspace label had not loaded; the successful submission followed explicit menu selection. There was no second submission.
- A sandboxed Host restart initially showed `spawn EPERM` for the Runtime worker; that Host was stopped. Relaunch with child-process permission mounted the plugin. This was an environment permission failure before task submission, not a model or Runtime run failure.

## Observed result

| Check | Result |
| --- | --- |
| Runtime task ID | `5599633c-f087-42e9-8769-68c54f68d7b6` |
| Manifest terminal status | `completed`, exit code `0` |
| Reviewer terminal reason and verdict | `completed`, `PASS` |
| Execution / review traces | both `available`, both `trace_complete: true`, both have `.jsonl.closed` markers |
| Audit | `settled` call trace, governance authorization `ALLOW` |
| Workspace delta | one added `rc30-live-check.txt`; no modified or deleted files; applicable patch |
| Independent file check | 13 bytes, hex `524333305F4C4956455F4F4B0A` (`RC30_LIVE_OK` + one LF) |
| Git status | only `?? rc30-live-check.txt` |
| Web evidence drawer | rendered `completed` / `PASS` and `执行轨迹`, `实际变动`, `审计` tabs |

The terminal Manifest is `host-home-r30-live\evidence\dsh-runtime\dsh-runtime-5599633c-f087-42e9-8769-68c54f68d7b6\evidence-manifest.v1.json`. The matching worker and API reviewer `.closed` traces, Diff, run state and call trace are alongside it; the Home's `audit\governance.jsonl` records the authorization. The browser's older turn content was virtualized with `hidden="until-found"`; the headless check triggered the already rendered `查看证据` button through the DOM and confirmed the drawer's content. This verifies drawer rendering and data, but does not claim an ordinary pointer click through that virtualized item. The Host was stopped after the run; port `64505` was no longer listening.

This closes the local rc.30 bounded worker/reviewer live trial. It does not supply the deferred second-device raw PASS evidence, authorize a daily replacement, or claim D2 ExecuteGate. The previous qualified rc.2 route and rollback Home remain in place. The trial repository's new file and all evidence are retained.
