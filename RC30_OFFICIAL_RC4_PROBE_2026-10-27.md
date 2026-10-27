# Official DeepSeekHarness rc.4 compatibility probe — 2026-10-27

Scope: isolated, no-model first stage for official `@deepseek-ai/dsh@0.2.1-rc.4`. It does not change the qualified rc.3 runner, rc.30 ZIP, daily Home or fallback. The rc.4 runner and a **temporary source-only copy** of the plugin with its eight `@deepseek-ai/dsh-*` dependency pins changed to rc.4 live under `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\official-host-rc4-probe-20261027`. This copy is not a released plugin package.

The official runner installed with pnpm 11.25.0 using `--ignore-scripts`, exact dependency `0.2.1-rc.4` and a new lockfile. The temporary plugin copy installed its exact rc.4 pins with `--ignore-scripts`. Native/postinstall code was not run. The schema-3 inventory compared that installed graph to the previous qualified rc.3 schema-3 snapshot and reported:

| Field | Result |
| --- | --- |
| Host | `0.2.1-rc.4` |
| Imported packages | 10 |
| Inventory issues | 0 |
| Classification | `HOST_DEPENDENCY_CHANGED` |
| Changed packages | 9 (`dsh`, `dsh-brand`, `dsh-client-connection`, `dsh-llm`, `dsh-session`, `dsh-session-query`, `dsh-subagent`, `dsh-subprocess`, `dsh-tools`) |
| Changed imported artifact digests | 0 |
| Minimum gate | `focused-or-higher` |

The full source-copy report is `rc4-inventory-v3.json` in the isolated probe directory. A second scan of the **installed** temporary Profile with source imports in `rc4-installed-profile-inventory-v3.json` also reported 10 imports, zero issues, `HOST_DEPENDENCY_CHANGED` and zero imported artifact digest changes. The isolated runner package/lock SHA-256 values are `8c323a830347f512517f6a0ce5616af5a6412a7aefbc0984f3dbb865fb96ef76` / `8970c8d2769d1ee7fca3d97dfeffca984c8a59d62bec697d46a50cde9696b24d`. The temporary plugin tarball SHA-256 is `8B42A6B7041CEB0D7EA8C5099B7BD71B7269CAE65C2274CBEFC614F33F3AF373`. It retains the rc.30 version label only for the disposable probe and must not be published as rc.30. A version/metadata change with equal imported artifact digest is not a functional compatibility verdict. The runner's lock and package metadata changed, so the `HOST_DEPENDENCY_CHANGED` row of `HOST_COMPATIBILITY_GATE.md` applies.

The temporary plugin passed `typecheck`, `build`, and focused `test:entry` (4), `test:host-core` (1), `test:tool` (3), `test:provider` (3), `test:client-evidence-scope` (3), `test:terminal-evidence` (2). The inventory suite first passed 15 and skipped two child-process checks under the restricted process sandbox; a single permitted rerun passed **17/17 with zero skips**. These are source/focused checks, not a Host Web smoke or a model-backed run.

## Installed Profile and HTTP smoke

A temporary plugin tarball was packed from the rc.4-pinned source copy, then installed with `--ignore-scripts` into a new Profile/Home against the isolated official rc.4 runner. The Home reused the known Runtime source and external API connection **path** but did not copy the connection JSON. `--dump-config` exited 0 with empty stderr; its potentially sensitive output stayed in the local probe directory. The first Web launch served the Host page but the plugin did not activate because the hand-built Home lacked the installer's `audit` directory. This was a probe setup omission. After stopping that instance and creating the same `audit`, `pins` and `evidence` directories as the installer, the corrected launch had zero stderr, authenticated page 200, `session/list` 200, anonymous `/api/dsh-runtime.evidence` 401 and authenticated request with deliberately invalid IDs 400. It stopped and its one-time URL token was redacted from the local log.

For a non-UI historical read check, exactly 90 Session files and the `workspace.json` index were copied from the earlier isolated six-workspace sample to this new Home; no source `.credentials.yaml` was copied (the Host generated its own local file during startup). The copy initially matched all 90 Session file hashes. A second rc.4 launch returned authenticated page 200, `session/list` 200 with 90 rows, six workspace records in the copied index and empty stderr. The Host stopped, its port closed, its local URL token was redacted, and all 90 copied Session file hashes still matched the source sample. This checks API and stored-session readability only; it does **not** demonstrate visible composer inputs, six individual workspace views or the three-tab historical Runtime drawer.

**Next gate:** build the exact rc.4 installer/preflight and run the browser six-workspace historical UI sample and saved three-tab Runtime drawer replay. Browser control returned `nodeRepl.fetch request failed` during the old-entry check, so no alternative UI automation was substituted in this turn. Only after those UI checks may rc.4's no-model Host compatibility be classified. A bounded live task is not automatically required by this inventory class, but any changed imported API or failed check escalates the gate. The existing rc.3 pin stays in force meanwhile. D2 ExecuteGate remains `NOT_CLAIMED`.
