# Independent Runtime plugin continuation

## 2026-10-26 rc.30 six-workspace no-model sample

The previously open rc.30 six-workspace historical UI sample passed in a new isolated Home with official rc.3 Host and rc.30 installed dependencies. Six real workspaces showed session rows `[2,3,3,5,10,12]`, visible composer inputs and zero page errors. The Host was stopped. The run modified only its disposable Home copy (six new compressed Session files and one changed copied Session file); original source Home data was not an output target. The bounded model-backed trial and second-device raw PASS evidence remain open. See `RC30_RC3_ALIGNMENT_2026-10-25.md` and `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-six-workspace-sample-20261026.json`. D2 ExecuteGate remains `NOT_CLAIMED`.

## 2026-10-26 second independent scanner review

The GLM follow-up audit of `b8fbe67` confirmed a two-argument dynamic `import()` omission. It also exposed a Profile-side virtual-store fallback that could count stale packages. The isolated candidate now scans imports with one or more arguments and follows declared Host/Profile dependency links; bare pnpm store entries no longer count as installed. The inventory contract is schema 3, so schema 1/2 reports are historical and cannot be used as upgrade baselines. Source and installed Profile read-only rc.3 inventories are saved as `rc30-host-inventory-v3-20261026.json` and `rc30-installed-host-inventory-v3-20261026.json` under `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025`; both show 10 imports and zero issues. A missing repository-local TypeScript development dependency now emits a clear CLI error. The rc.30 six-workspace sample, bounded live task and second-device evidence remain open; D2 stays `NOT_CLAIMED`.

## 2026-10-26 compatibility-audit follow-up

Isolated candidate `codex/evidence-relocation-20261025` is now at `82c7ace` after the read-only GLM audit was independently checked and the inventory scanner hardened. The original Runtime and Harness worktrees remain at 16 and 106 Git-visible entries; none were edited or cleaned. D2 ExecuteGate remains `NOT_CLAIMED`.

- Fixed CLI execution through a Windows junction, metadata-only gate level, package-wide file coverage, syntax-aware import discovery, active Host dependency resolution and missing pnpm-lock rejection. Exact Host dependency pinning is intentional and documented. The compatibility snapshot is now schema 2; schema 1 comparisons fail closed.
- Focused tests pass 14/14, including the junction child-process case. Fresh read-only schema 2 source and installed Profile inventories of official rc.3 each show 10 imported packages and zero issues; see `rc30-host-inventory-v2-20261026.json` and `rc30-installed-host-inventory-v2-20261026.json` under `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025`. The old schema 1 files remain historical evidence.
- The rc.30 `HOST_DEPENDENCY_CHANGED` gate still lacks its own six-workspace historical session sample. Its prior single-session drawer replay and these new inventories do not qualify it for daily use. The prepared bounded live trial remains unstarted, and second-device raw PASS evidence remains deferred.

Latest update 2026-10-25: the active isolated candidate is `D:\DeepSeekHarness\vis-evidence-relocation-candidate-20261025` on `codex/evidence-relocation-20261025`, HEAD `a58f9c7` after the rc.30 package and acceptance commits. The original `D:\PythonProject\dsh-runtime` and `D:\DeepSeekHarness\deepseek-harness` worktrees still have respectively 16 and 106 Git-visible entries; preserve every uncommitted and untracked item. Do not clean, reset, overwrite or move them. Formal D2 ExecuteGate remains `NOT_CLAIMED`.

## Latest experimental candidate and next gate

- Historical evidence relocation, exact-byte receipt verification and the visible `历史证据副本` label are implemented in the isolated candidate. The authentic old r9 Session was visually replayed in the unmodified official rc.3 Host with three drawer tabs; see `EVIDENCE_RELOCATION_ACCEPTANCE_2026-10-25.md`. The original evidence root was preserved.
- rc.29's visual replay used a mixed rc.2 plugin / rc.3 Host dependency graph. The rc.30 private tarball pins plugin dependencies to rc.3, retains identical 20 `lib` files, two CLI scripts and patch, and has SHA-256 `2F6EB8D2BB03A4759CF9CC158BB3EAEA6EFEC22A096E1F39490598DD41CC2EB3`. Commit `541153f` records its exact package source; `a58f9c7` adds later acceptance documents.
- The source and freshly installed Profile inventories both show `HOST_DEPENDENCY_CHANGED`, zero imported code/type artifact digest changes and zero issues. The inventory scanner now handles stale pnpm store entries and Windows-shortened store names; 8/8 focused inventory tests pass. rc.30 typecheck/build and focused entry, Host core, tool, client evidence and terminal evidence tests pass. Its separate official Host launch passed authenticated page 200, anonymous evidence 401, parent-owned relocated evidence 200 and wrong-child 404. No model-backed task or D2 call was sent. Details: `RC30_RC3_ALIGNMENT_2026-10-25.md`.
- A separate rc.30 old-session visual launch passed: the tool card showed `历史证据副本`, the drawer opened all three tabs, the changes tab showed one added file, and the audit tab showed `settled` / `PASS`. The rc.30 isolated Host was stopped after acceptance. The rc.29 browser tab and its separate Host were left available for the user's visual review. No daily Home or official Host installation was replaced.
- Next: decide whether the experimental relocation feature enters a private parallel daily candidate. Before any promotion, run a bounded real Host worker/reviewer trial for the rc.30 release gate and obtain the deferred second-device raw PASS evidence separately. Keep the rc.2 qualified daily path and rollback intact. API worker write remains disabled because the Windows hard-link race has no accepted proof of atomic safety.
- The next local live trial is prepared, but not started: `RC30_LIVE_TRIAL_READY_2026-10-25.md` fixes a fresh clean trial repo, separate `host-home-r30-live`, exact archive/lock hashes and a one-call prompt. Do not conflate this preparation with a model-backed PASS.

## Earlier stable candidate record

The earlier isolated candidate was `D:\DeepSeekHarness\vis-api-agent-stable-candidate-20261024` on `codex/api-agent-stable-20261024`, HEAD `b21cf28` at its last check. The following sections preserve that earlier record.

## Completed in the isolated candidate

- `92e0afc`: read-only official Host package/artifact inventory.
- `217c11a`: distinguish package metadata changes from imported code/type artifact changes; document risk-based upgrade gate.
- `275d099`: read-only historical evidence Home diagnostic. It reports `READY` for the original r9 root and `RELOCATED_ABSOLUTE_REFERENCE` for its byte-identical copied root.
- `1ed90b3`: carry the tested exact Host preflight, launch recheck and official npm registry selection back into installer source. The old fixed r9/r10 package bytes were not changed.
- `30b3e87`: reusable six-case preflight regression, passing for both official rc.2 and rc.3 isolated kits.
- `9c152e5`: exact Host support matrix, with rc.3 explicitly no-model only.
- `be80579`: this continuation record and fixed probe coordinates.
- `43a1798`: historical evidence relocation sidecar design and acceptance matrix, with no reader relaxation.
- `cf9db1e`: original evidence read, copied-root rejection, wrong-parent rejection and missing-run regression. `pnpm test:terminal-evidence` passes 1/1.
- `b21cf28`: direct `CreateFileW`/`CreateHardLinkW` counterexample recorded; API worker write remains disabled.

Focused inventory tests pass 5/5, evidence Home tests 2/2, TypeScript typecheck passes, and the PowerShell source scripts parse. The original r10 private ZIP hash remains `1729C4ADB89CCE2733724A5F4CB74AC2EC4C127AFDCB91C5C8CC79F174BFB159`.

## Official rc.3 probe

Report: `D:\DeepSeekHarness\host-compat-artifacts-20261025\RC3_FAST_COMPAT_PROBE.md`; inventory: `rc3-diff-report-v2.json`; private probe ZIP: `rc22-official-rc3-private-probe.zip` (SHA-256 `9AB2D55BC6E131547B2951D0ACC000DEFB21BE9610D7C62A9213E8815BD12A84`). The 14-member ZIP matched the kit and Manifest, and two configured credential values were absent across 256 package, nested archive, Profile and dump blobs. The external connection JSON was not copied into the kit.

The unmodified official `@deepseek-ai/dsh@0.2.1-rc.3` passed fresh install, config, authenticated Web and anonymous evidence denial. A six-workspace old-session UI sample showed row counts `[2,3,3,3,8,10]`, visible input boxes and no page errors. The authentic r9 Runtime drawer showed all three tabs, model verdict and provenance labels on rc.3 with no page errors, provided the Profile pointed to the **original** r9 evidence root. The original eight evidence files retained identical hashes before and after; the Profile was restored and the Host stopped. A copied evidence root alone fails because the historical Manifest holds an absolute Diff reference. No rc.3 model task was called, and rc.3 is not a daily release.

## Next independent tasks

1. Design a verifiable relocation format for historical evidence without rewriting original Manifest bytes. A sidecar or new Manifest version needs source/copy digest binding, explicit UI provenance and adversarial tests. Until then, replay only from the original evidence root.
2. Keep the official update gate small: compare exact installed packages first, then run only the tier required by changed surfaces. If official tool/subagent/reviewer artifacts change, use a fresh bounded trial repository and retain both terminal traces, Manifest, audit, exact bytes and drawer result. Do not repeat a model task for a metadata-only change without a concrete regression signal.
3. API worker write remains closed. The Windows create-only experiment found that another path could hardlink the staged file even with an exclusive handle; the last link-count check and commit cannot currently be proven atomic. Preserve this safety boundary and the CLI worker fallback while researching a stronger primitive.
   A separate direct Win32 reproduction is recorded at `D:\DeepSeekHarness\hardlink-share-probe-20261025\RESULT.md`: `CreateFileW` with share mode zero followed by `CreateHardLinkW` succeeded on this machine, producing the same inode with two links. Adding `FILE_FLAG_DELETE_ON_CLOSE` also allowed a new hard link; after handle close its alias remained. This conflicts with the broad wording in Microsoft documentation, so do not treat that wording as a safety proof for this environment.
4. The second Windows device's final PASS run raw Manifest, `.closed` traces and audit remain unavailable. Do not claim independent cross-device proof or promote a stable/daily replacement on that basis. The user deferred second-device work; progress on local work without asking for it again.
5. Keep the old private Harness branch and daily Home as rollback until the independent plugin has its full release evidence. Review old branches one at a time only after this gate; do not batch-delete or reset worktrees.
