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

The full machine report is `rc4-inventory-v3.json` in the isolated probe directory. A version/metadata change with equal imported artifact digest is not a functional compatibility verdict. The runner's lock and package metadata changed, so the `HOST_DEPENDENCY_CHANGED` row of `HOST_COMPATIBILITY_GATE.md` applies.

The temporary plugin passed `typecheck`, `build`, and focused `test:entry` (4), `test:host-core` (1), `test:tool` (3), `test:provider` (3), `test:client-evidence-scope` (3), `test:terminal-evidence` (2). The inventory suite first passed 15 and skipped two child-process checks under the restricted process sandbox; a single permitted rerun passed **17/17 with zero skips**. These are source/focused checks, not a Host Web smoke or a model-backed run.

**Next gate:** prepare a genuinely installed rc.4 Profile against the built temporary plugin and a fresh Home; run the exact Host installer/preflight, authenticated page and anonymous evidence fence, six-workspace historical Session sample and saved three-tab Runtime drawer replay. Only then classify rc.4's no-model Host compatibility. A bounded live task is not automatically required by this inventory class, but any changed imported API or failed check escalates the gate. The existing rc.3 pin stays in force meanwhile. D2 ExecuteGate remains `NOT_CLAIMED`.
