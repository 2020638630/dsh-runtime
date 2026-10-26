# rc.30 private parallel kit: local installation record

Date: 2026-10-26. Scope: isolated Windows local installation and no-model official Host launch. This is not a cross-device or daily-release approval. D2 ExecuteGate stays `NOT_CLAIMED`.

## Fixed inputs

- Kit: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-private-preview-kit-20261026`.
- Private ZIP: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-private-preview-kit-20261026.zip`, SHA-256 `738E79152E3A34EB0343214851BA93F170918FCB83BB1F4F2C49AA1D7CB14DD9` (14 entries, 1,242,253 bytes). It contains no file with the exact sensitive names listed below. The ZIP is local only; it was not published.
- Official Host: unmodified `@deepseek-ai/dsh@0.2.1-rc.3`; the installer and launcher checked the selected runner's exact package/artifact identity against `manifest.json`.
- Plugin: `@dsh-runtime/harness-plugin@0.1.0-rc.30`, tarball SHA-256 `2F6EB8D2BB03A4759CF9CC158BB3EAEA6EFEC22A096E1F39490598DD41CC2EB3`.
- Runtime source: commit `d3af857bb87babb0f96b87adc2839f8761b45eba`, ZIP SHA-256 `AF4A06184FE4DCDB6FF65CAF3B6AF771FD1CB23C794F975DB11816AD07964E55`.
- Seven pinned wheel files, including `httpx==0.28.1`, all matched the manifest hashes. The external connection JSON was passed by path; it was not opened for this report or copied into the kit.

## Attempts and result

1. `-Offline` installation into the isolated `rc30-kit-install-home-20261026` and `rc30-kit-install-runtime-20261026` directories failed when pnpm could not resolve the official rc.3 `@deepseek-ai/dsh-brand` dependency from cached mirror metadata. The Python wheelhouse installation had succeeded. Both partial directories remain untouched as failed-attempt evidence. This establishes a cache prerequisite, not a defect in the fixed plugin tarball and not proof of a network request.
2. Online installation into **different fresh** `rc30-kit-install-home-online-20261026` and `rc30-kit-install-runtime-online-20261026` directories passed. The installer used its configured official npm registry. The installed plugin was rc.30; its tarball hash and the Runtime ZIP hash matched the kit. The installed Profile lockfile SHA-256 was `38378A0495853F67B1BE8DABDF274E0701D830359D1FAF62C37D454764612A21`.
3. The installed Profile's `-DumpConfig` exited 0; stdout was retained locally as `rc30-kit-config-dump-20261026.log` and stderr was empty. The dump was not copied into the kit or quoted here because it may contain configuration paths.
4. The isolated official Host launched on local port 55889. Authenticated home returned 200; anonymous evidence endpoint returned 401. In the isolated Web page, the composer, workspace selector and `工作区内修改` mode were visible. No model task or D2 call was sent from this kit installation. The Host was stopped after the check; the port was no longer listening.
5. The kit/plugin/Runtime/wheel hashes were checked again after installation. No exact sensitive filename (`connections.local.json`, `.env`, `service-account.json`, `api-key.json`) was found inside the new Home. This filename check does not prove the absence of every possible secret in every installed package.

The prior rc.30 bounded live worker/reviewer task and six-workspace historical UI sample are documented separately in `RC30_LIVE_TRIAL_RESULT_2026-10-26.md` and `RC30_RC3_ALIGNMENT_2026-10-25.md`; they were not repeated for this kit installation.

## Remaining gate

The second Windows device's final PASS run raw Manifest, two `.jsonl.closed` traces and matching governance audit have not been received. The read-only verifier in `CROSS_DEVICE_RAW_EVIDENCE_HANDOFF_2026-10-26.md` is ready but cannot replace that evidence. The old private daily entry and Home were not modified. A full old-entry rollback exercise is still pending; stopping this isolated preview Host alone does not prove that rollback. Do not mark this kit stable or the daily replacement from the local checks above.

Read-only rollback preflight found the original desktop shortcuts still present: `DeepSeek Harness RC4 (日常工作).lnk` points to `D:\DeepSeekHarness\vis-trial-rc4-home\artifacts\START_RC4_DAILY_WORK.cmd`, and the read-only entry points to `START_RC4_DAILY_READONLY.cmd` in the same artifact directory. Their targets were not executed during this preflight; presence is not a full rollback result.
