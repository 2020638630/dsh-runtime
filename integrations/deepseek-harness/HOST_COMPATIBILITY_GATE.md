# Official Host update gate

The public `@deepseek-ai/dsh` is an external Host. A new version never replaces a qualified daily entry merely because its package installs or its version number is newer. Keep the previous pinned Host and Home available while probing a new version in a separate runner, Home, Runtime and trial repository. Do not modify the official Host package.

## Inventory before any model call

1. Install the proposed official version and this plugin's corresponding dependencies into a disposable directory. Record the exact package name, version, `package.json` hash, code/type artifact digest, runner lockfile hash and plugin tarball hash.
2. Run `node scripts/host-compat-report.mjs --host ABS_HOST_RUNNER --plugin ABS_PLUGIN_ROOT --baseline ABS_PREVIOUS_JSON`. For a packed plugin whose installed Profile has no `src`, point `--plugin` at that installed Profile root and add `--imports-from ABS_SOURCE_ROOT`; this inventories the installed graph against the source import set. Preserve its JSON. An issue, an ambiguous package, a missing package or a runner/package version mismatch stops the gate. The report is a change inventory, not proof that the new Host works.
   The runner must have a `pnpm-lock.yaml` and an exact `dependencies["@deepseek-ai/dsh"]` pin equal to the installed version; ranges, catalogs and `devDependencies` are outside this release gate. Snapshot schema 3 hashes all regular files in each installed imported package except its separately hashed root `package.json`. It includes CLI entry files, assets and configuration, so a documentation-only package change can conservatively raise the gate. The scanner follows declared runner/Profile dependency links and plugin-root direct links; a package found only in an unreferenced pnpm store is missing, not installed. Schema 1 and 2 reports cannot be compared with schema 3: capture a new baseline from the previously qualified installation before using `--baseline` for an upgrade. The repository-local scanner needs its `typescript` development dependency to inspect source imports; it is not part of the packed plugin.
3. Typecheck and build the plugin against the proposed packages. Run the plugin's focused Host entry, route, tool, client and inventory tests.
   Run `tests/Test-HostPreflight.ps1 -KitRoot ABS_KIT -QualifiedRunnerRoot ABS_HOST_RUNNER -QualifiedNodePath ABS_NODE24 -OldNodePath ABS_NODE20` when forming a new kit. Its negative cases verify that the installer rejects wrong version, malformed metadata, missing CLI, changed same-version code and old Node before creating a Home/Runtime target.
4. Use an installer that refuses an unknown Host before it writes to the new Home. Start the new Host using that same checked runner. Confirm the authenticated Web page loads, an anonymous evidence request is refused, old sessions and the input box render, and a known settled Runtime drawer shows all three tabs. Before replaying copied evidence, run `node scripts/check-evidence-home.mjs --evidence-root ABS_EVIDENCE_ROOT --run-id dsh-runtime-UUID --workspace-id SESSION_ID`. `READY` means its stored Diff reference is usable at that root; `RELOCATED_ABSOLUTE_REFERENCE` means use the original evidence root or plan a separate verified migration. These are no-model checks.

## Escalation by observed change

| Inventory result | Minimum additional acceptance |
| --- | --- |
| `SAME_ARTIFACTS` | Fresh isolated launch, authentication fence and a small UI/session sample. |
| `PACKAGE_METADATA_CHANGED` | The same checks plus package dependency review and focused plugin tests. |
| `HOST_SHELL_CHANGED` or `HOST_DEPENDENCY_CHANGED` | Fresh install and focused tests plus the six-workspace historical session sample and saved Runtime drawer replay. |
| `IMPORTED_ARTIFACT_CHANGED` or `PLUGIN_IMPORT_SET_CHANGED` | Review the changed API/types and affected runtime calls, then run one bounded real Host trial for each affected role or surface. A new write/review trial is required if the tool, subagent, reviewer or evidence boundary changed. |
| `BLOCKED_INPUT` | Diagnose the inventory. Do not promote the version. |

`minimum_gate` is a coarse machine-readable hint: `fast-smoke` applies only to `SAME_ARTIFACTS`; `focused-or-higher` includes `PACKAGE_METADATA_CHANGED` and all higher change classes. The detailed table above remains the acceptance contract.

Any failure raises the gate regardless of the initial class. A no-model gate does not establish that a new model-backed worker/reviewer chain passes. Record the exact scope in the support matrix: inventory-only, no-model Host smoke, bounded live task, or daily-qualified. Promotion to a parallel daily entry is a separate decision after the required gates pass. Formal D2 ExecuteGate remains `NOT_CLAIMED` unless separately authorized and executed.

## Evidence portability boundary

Existing `evidence-manifest.v1.json` files contain an absolute `workspace_changes.diff_content_ref`. The qualified daily evidence reader checks that this resolves to the `diff.patch` in the selected evidence root. Copying the evidence directory to a new Home without a migration receipt yields HTTP 500 by design, even when the session and manifest were copied correctly. Keep the original evidence root for qualified historical read-only replay. The isolated evidence-relocation candidate adds an explicit copy receipt, exact-byte verification and a visible provenance label; it is not a daily release. Changing an old manifest in place would invalidate its original bytes. This limitation is distinct from a Host version regression.

`check-evidence-home.mjs` is a local, read-only diagnostic. It checks one run's bounded Manifest and Diff under the supplied root and prints only a status code. It never repairs or rewrites evidence, and `READY` does not claim that a model judgment is correct.

A separate [relocation design and experimental implementation record](EVIDENCE_RELOCATION_DESIGN.md) specifies the sidecar copy receipt and remaining gates before moved historical evidence may be replayed in a daily Home.
