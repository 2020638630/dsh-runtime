# Relocation plugin rc.30 and official rc.3 Host alignment

Date: 2026-10-25. Isolated candidate `codex/evidence-relocation-20261025`. The original Runtime and Harness development worktrees were not edited. D2 ExecuteGate remains `NOT_CLAIMED`.

## Why rc.30 exists

The rc.29 historical-copy UI replay passed in a separate official `@deepseek-ai/dsh@0.2.1-rc.3` Host, but the rc.29 plugin still declared eight `@deepseek-ai/dsh-*` dependencies at `0.2.1-rc.2`. The installed graph contained both rc.2 and rc.3 variants. That mixed graph is not an exact release inventory for a proposed rc.3 daily entry.

The rc.30 package changes only its version and those eight declared dependency pins to `0.2.1-rc.3`. Its 20 installed `lib` files, two packaged CLI scripts and `cordis.patch.yml` are byte-identical to rc.29. The earlier rc.29 archive and isolated Home remain intact. The archive was packed before the later documentation update; commit `541153f` records the exact rc.30 package source and the inventory scanner changes.

## Exact package and Host inventory

- Private archive: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\package\dsh-runtime-harness-plugin-0.1.0-rc.30.tgz`; SHA-256 `2F6EB8D2BB03A4759CF9CC158BB3EAEA6EFEC22A096E1F39490598DD41CC2EB3`.
- Official Host runner: `D:\DeepSeekHarness\host-compat-artifacts-20261025\host-runner-0.2.1-rc.3`; exact package version `0.2.1-rc.3`, runner `package.json` SHA-256 `d2db8b230af036825dd6198e214303a8b16ee54eb38e58ff9c3bd76c6fcda94e`, lockfile SHA-256 `1e7a54c406e85a1f8be67073700d2479c5cadc662d6c9a062c07cfe181c6d45e`.
- Source inventory JSON: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-host-inventory-20261025.json`. Installed Profile inventory JSON: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc30-installed-host-inventory-20261025.json`, using the source import set and the fresh Profile's actual package store. Both report `HOST_DEPENDENCY_CHANGED` against the exact rc.2 baseline, nine changed imported package records, zero changed code/type artifact digests and zero unresolved/ambiguous packages. The new Profile lockfile SHA-256 is `38378A0495853F67B1BE8DABDF274E0701D830359D1FAF62C37D454764612A21`.
- The inventory initially reported five false ambiguities after the local plugin dependency upgrade because pnpm left stale rc.2 virtual-store directories. The scanner now uses a direct installed package link when present and searches the virtual store only when no direct link exists. It resolves Windows-shortened pnpm folder names by checking their nested package paths. Regression fixtures cover stale store entries, separate source/installed roots and shortened folder names; genuine Host/plugin direct-link conflicts still fail closed.

## Focused no-model acceptance

- `pnpm test:host-compat-report` 8/8, `pnpm typecheck`, `pnpm build`, and focused entry, Host core, tool, client evidence and terminal evidence tests passed on the aligned plugin source.
- The rc.30 archive was installed into a new `host-home-r30` Profile. An offline attempt failed because registry metadata for `@deepseek-ai/cordis@4.0.5` was absent; the explicit official npm registry attempt installed successfully. No source package or existing Home was overwritten.
- The official rc.3 Host config dump exited 0 and loaded the rc.30 plugin. A first sandboxed launch could not mount the Runtime governance worker because Windows child-process creation returned `spawn EPERM`; it was stopped and its log retained. The same isolated Host was relaunched with child-process permission. It printed a local Web URL and remained running for the checks. Its stderr later contained one Host model-catalog listing message, with no startup failure.
- On that permitted launch, the authenticated page returned 200, anonymous evidence returned 401, parent-owned copied r9 evidence returned 200 with `relocation.status=verified_copy`, wrong-child evidence returned 404, Manifest status was `completed`, and the Diff length was 74 characters. The rc.30 archive has 28 members and no connection JSON or credential file. No model-backed task or D2 call was sent. The isolated rc.30 Host was stopped after checks; the separate rc.29 visual-review tab was left alone.

## Gate

This qualifies an **experimental, no-model rc.30 alignment**, not a daily release. The rc.30 Profile has not received its own visible old-session drawer check or a bounded live worker/reviewer run. The rc.29 visual replay is relevant because its runtime files are identical, but it cannot substitute for rc.30's own release qualification. The second-device raw PASS evidence is deferred. Keep the qualified rc.2 daily candidate and its rollback Home unchanged.
