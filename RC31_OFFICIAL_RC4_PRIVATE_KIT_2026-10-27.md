# rc.31 / official rc.4 private kit acceptance — 2026-10-27

## Artifact and scope

- Source worktree: `D:\DeepSeekHarness\rc31-official-rc4-candidate-20261027`, branch `codex/rc31-official-rc4-20261027`. Original Runtime and Harness worktrees were not changed.
- Plugin: `@dsh-runtime/harness-plugin@0.1.0-rc.31`, exact `@deepseek-ai/dsh-*` rc.4 dependencies. The final tarball SHA-256 is `FA82F7DFB438CCAECBB87CDFC30C0936C063F8C49E4C156142093E0473322828`.
- Kit: `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc31-official-rc4-private-kit-20261027.zip`, SHA-256 `323928F8FBE4272474D071C93772240171EA1214864272D3D258CCA0F6C0C9FB`. All 14 ZIP entries matched their source bytes. There is one Manifest and one plugin tarball; the manifest plugin digest matches the contained tarball.
- Official Host exact pin: `@deepseek-ai/dsh@0.2.1-rc.4`, package SHA-256 `AB0994EF7FC70A9974D39735D6E30B500B4BE3435012B53CAB1DF149F39BBC5C`, artifact digest `04277235EB38088C0074D46E5ADFBD61A11CC86D191DF4498C43174B316CE4C0`. Runtime snapshot remains `d3af857bb87babb0f96b87adc2839f8761b45eba`; D2 ExecuteGate is `NOT_CLAIMED`.

An earlier preliminary tarball is preserved separately under `rc31-official-rc4-package-20261027` and is **not** the kit payload. The final kit uses the tarball under `rc31-official-rc4-package-v2-20261027`.

## Checks performed

- Node 24.19.0 and pnpm 11.25.0: typecheck, build, host compatibility tests (15 passed, two process-sandbox skips), client evidence (3), entry (4), Host core (1), and evidence copy (5 passed, one process-sandbox skip) all passed.
- The kit preflight passed six cases: wrong Host version, malformed metadata, missing Host entry, changed code with the same version, old Node, and exact qualified runner. No install paths were written in the rejection cases.
- Fresh isolated kit install completed in `rc31-kit-install-home-20261027` and `rc31-kit-install-runtime-20261027` using the external connection file. Python wheel installation passed; the installed plugin is rc.31. Installed Profile inventory: 10 imports, zero issues, official Host rc.4. Config dump exited 0 with empty stderr.
- The first Web launch in a restricted process sandbox displayed `spawn EPERM` while activating the plugin. A second launch with child-process permission started without the activation warning. An automated authenticated check against the actual installed Profile returned Web page 200 (38,144 bytes), Session list 200 (zero Sessions in this fresh Home), anonymous evidence 401 and zero stderr bytes. Its isolated Host child exited cleanly afterward. No model task was sent.
- The unchanged final ZIP was later extracted into a second fresh directory and installed from those extracted bytes into `rc31-zip-install-home-20261027` / `rc31-zip-install-runtime-20261027`. That Profile returned authenticated page 200 (38,144 bytes), Session list 200 (zero Sessions), anonymous evidence 401 and zero stderr. A second `pnpm pack` from the unchanged source reproduced the kit plugin SHA-256 `FA82F7DFB438CCAECBB87CDFC30C0936C063F8C49E4C156142093E0473322828` exactly.
- pnpm 11.25.0 generated 38 `minimumReleaseAgeExclude` entries for the exact official rc.4 package versions during source and Profile installation. The source candidate records those exact-version exceptions; no wildcard exception is present. The lockfile supply-chain check passed.

## Gate result and open work

**GO for isolated, no-model packaged-install candidate.** The prior temporary rc.4 Profile passed authenticated historical UI review: six original workspaces had visible history and composer inputs, and the seventh copied trial Session had all three Runtime drawer tabs. The user then confirmed this new packaged Home's page, default workspace and composer were visible. It has also passed installation, preflight, inventory, config and authenticated HTTP checks, but has not received a bounded worker/reviewer task, an in-place upgrade/rollback cycle, or second-device validation. Do not switch the default daily entry, claim stable/public support, or infer a formal D2 result from this record. Keep the rc.30/official rc.3 entry and existing fallback available.
