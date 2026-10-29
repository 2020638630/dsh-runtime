# rc.30 to RC4 old-entry rollback preflight — 2026-10-27

Scope: read-only preflight for the still-active fallback, followed by one bounded no-model exercise if the process and Home checks permit it. This is distinct from the 2026-10-19 RC3 snapshot rollback test. Do not use a model task or formal D2 ExecuteGate for this exercise.

## Checked old entry

| Item | Observed target |
| --- | --- |
| Desktop work shortcut | `DeepSeek Harness RC4 (日常工作).lnk` → `D:\DeepSeekHarness\vis-trial-rc4-home\artifacts\START_RC4_DAILY_WORK.cmd` |
| Desktop read-only shortcut | `DeepSeek Harness RC4 (只读日常入口).lnk` → `D:\DeepSeekHarness\vis-trial-rc4-home\artifacts\START_RC4_DAILY_READONLY.cmd` |
| Both scripts' `DSH_HOME` | `D:\DeepSeekHarness\vis-trial-rc4-home\private-full-home-stage-20261019` |
| Both scripts' Node | `D:\PythonProject\reverse-workspace\.node-v24\node.exe` |
| Both scripts' Host | `D:\DeepSeekHarness\vis-harness-private-integration\dist\rc4-packed-consumer\node_modules\@deepseek-ai\dsh\lib\bin.js` |
| Read-only Profile | `packed-rc4-full-home-stage`; write Profile: `packed-rc4-daily-write` |

Both Profile files, the two existing audit files, Node executable and Host entry were present at preflight. Scripts create an audit directory/file only if missing, then start the old Host on `127.0.0.1` with dynamic port. Their post-exit `pause` is a command-window convenience, not a Host health result.

A process inventory with elevated read-only `Win32_Process` showed no `node.exe` or `cmd.exe` command line naming the old Host, RC4 entry, old parallel Home or rc.30 preview Home at the time of preflight. Other Node processes belonged to unrelated Chrome DevTools helpers. Recheck immediately before launch; this observation is time-bound. No process was stopped or changed during preflight.

## Bounded exercise and return criteria

1. Record prelaunch file inventory and hashes of the RC4 parallel Home without following links or reading credentials into logs. Confirm again that no process uses its Host/Home. Keep the rc.30 preview Host stopped and its Home separate.
2. Launch the actual read-only RC4 script in a hidden command window with redirected local output. Identify the new Host process by **both** its old `bin.js` path and `packed-rc4-full-home-stage` argument; never stop a generic `node.exe` by image name.
3. Wait for the Host's dynamic loopback URL. Confirm one authenticated old Home page/session listing using only this local instance. Do not send a model task, modify a repository or use the write Profile. A readiness message alone does not prove the page works.
4. Stop only the identified process spawned for the exercise. Confirm its port closes and the script exits. Compare Home file inventory/hashes; classify any ordinary cache/audit change and require old Session/profile/credential bytes to remain stable. Do not erase logs or generated files.
5. Recheck the rc.30 preview's separate Home and fixed kit; an old-entry PASS supports rollback availability only. It does not promote rc.30 to daily use or qualify the old write Profile.

Stop if the old entry is already in use, the process cannot be identified, the Host serves the wrong Home, an old Session/profile/credential changes unexpectedly, or the instance cannot be cleanly stopped. Preserve artifacts and diagnose before any daily promotion.

## Bounded exercise result (same day)

- Prelaunch hash inventory recorded 165 regular files in the parallel RC4 Home under `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc4-old-entry-check-20261027`. A second process check found no old or preview Host instance.
- The first launch from the restricted execution environment failed at `profiles\packed-rc4-full-home-stage\cordis.yml` with filesystem `EPERM`; it made zero Home file changes. The test command window was identified and stopped. This was an environment denial, not a product verdict.
- One elevated launch of the **actual** `START_RC4_DAILY_READONLY.cmd` started the old Host under the intended Profile. The identified Host PID listened on `127.0.0.1:58129`; an anonymous request returned 401. Both identified test processes were stopped and the port closed. No model task was sent.
- The Host did not print an authenticated URL in this launcher mode. Browser UI inventory failed with `nodeRepl.fetch request failed`, so authenticated page and the old Session list were **not verified**. Do not infer the previous 33/33 result from this run.
- Comparing Home hashes after shutdown found no additions or removals but two changed files: `sessions\--D-DeepSeekHarness-vis-rc4-daily-write-acceptance-20261019--\session-cac6e853-8067-4937-81df-212dc5dbb3aa\session.v4.jsonl.zstd` (343→423 bytes), and `storages\session_projcache\sessions\session-cac6e853-8067-4937-81df-212dc5dbb3aa.json` (4815→4814 bytes). They belong to an earlier isolated acceptance workspace, but the precise event-level cause is not yet established. Pre/post hash inventories and launch stderr/stdout were preserved in the local artifact directory. No automatic repair or deletion was attempted.

The first no-browser follow-up received 401 from `session/list` because its HTTP client did not retain the login redirect's cookie; it left all 165 Home files unchanged. After fixing this probe-only cookie handling, the same old Host/Node/read-only Profile returned authenticated page 200 (37,448 HTML bytes), `session/list` 200 with 39 rows and stderr 0. It closed its dynamic port; all 165 Home file hashes stayed identical. The URL token was kept in process memory.

The actual **daily work** fallback script was then launched once from a fresh 165-file hash baseline. It started the intended `packed-rc4-daily-write` Host on loopback. Using its local one-time URL, authenticated page and `session/list` both returned 200, with 37,448 HTML bytes, 39 rows and stderr 0. Its identified Host and launcher were stopped; port 59923 closed. The before/after Home file list and all 165 hashes matched exactly. No model task or repository write was sent. The local launcher logs were redacted after the check so no one-time URL token remains in them.

**Verdict: the existing RC4 daily work entry is available as a bounded no-model fallback.** The two file changes from the earlier automatic-browser read-only launch remain preserved and unexplained at event level; they were in the 2026-10-19 acceptance workspace, not the original `C:\Users\Administrator\.dsh` Home. They do not appear in either subsequent no-browser probe or the actual daily work entry's before/after snapshot. This result does not qualify rc.30 for daily promotion, the old write Profile's model behavior, or a public release.

## rc.30 kit note

The immutable PS5.1-r2 private ZIP SHA-256 is `EAB3C3B0BEF0D1CB4CCC9786D4402B2EC5BB74295F8B7764FDE22AB9D38F5D98`. Its manifest's plugin/runtime and seven wheel hashes were rechecked on 2026-10-27 and matched. The bundled README is a 2026-10-26 snapshot and still says the second-device final evidence is pending; the later `RC30_CLOUD_CODEBUDDY_R5_RESULT_2026-10-26.md` supersedes that status. Repackage a corrected README only as a new, newly hashed kit revision; never edit the existing ZIP in place.
