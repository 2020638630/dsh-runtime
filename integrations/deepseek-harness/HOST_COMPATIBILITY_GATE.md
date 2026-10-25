# Official Host update gate

The public `@deepseek-ai/dsh` is an external Host. A new version never replaces a qualified daily entry merely because its package installs or its version number is newer. Keep the previous pinned Host and Home available while probing a new version in a separate runner, Home, Runtime and trial repository. Do not modify the official Host package.

## Inventory before any model call

1. Install the proposed official version and this plugin's corresponding dependencies into a disposable directory. Record the exact package name, version, `package.json` hash, code/type artifact digest, runner lockfile hash and plugin tarball hash.
2. Run `node scripts/host-compat-report.mjs --host ABS_HOST_RUNNER --plugin ABS_PLUGIN_ROOT --baseline ABS_PREVIOUS_JSON`. Preserve its JSON. An issue, an ambiguous package, a missing package or a runner/package version mismatch stops the gate. The report is a change inventory, not proof that the new Host works.
3. Typecheck and build the plugin against the proposed packages. Run the plugin's focused Host entry, route, tool, client and inventory tests.
4. Use an installer that refuses an unknown Host before it writes to the new Home. Start the new Host using that same checked runner. Confirm the authenticated Web page loads, an anonymous evidence request is refused, old sessions and the input box render, and a known settled Runtime drawer shows all three tabs. These are no-model checks.

## Escalation by observed change

| Inventory result | Minimum additional acceptance |
| --- | --- |
| `SAME_ARTIFACTS` | Fresh isolated launch, authentication fence and a small UI/session sample. |
| `PACKAGE_METADATA_CHANGED` | The same checks plus package dependency review and focused plugin tests. |
| `HOST_SHELL_CHANGED` or `HOST_DEPENDENCY_CHANGED` | Fresh install and focused tests plus the six-workspace historical session sample and saved Runtime drawer replay. |
| `IMPORTED_ARTIFACT_CHANGED` or `PLUGIN_IMPORT_SET_CHANGED` | Review the changed API/types and affected runtime calls, then run one bounded real Host trial for each affected role or surface. A new write/review trial is required if the tool, subagent, reviewer or evidence boundary changed. |
| `BLOCKED_INPUT` | Diagnose the inventory. Do not promote the version. |

Any failure raises the gate regardless of the initial class. A no-model gate does not establish that a new model-backed worker/reviewer chain passes. Record the exact scope in the support matrix: inventory-only, no-model Host smoke, bounded live task, or daily-qualified. Promotion to a parallel daily entry is a separate decision after the required gates pass. Formal D2 ExecuteGate remains `NOT_CLAIMED` unless separately authorized and executed.

## Evidence portability boundary

Existing `evidence-manifest.v1.json` files contain an absolute `workspace_changes.diff_content_ref`. The authenticated evidence reader checks that this resolves to the `diff.patch` in the selected evidence root. Copying the evidence directory to a new Home without preserving that path yields HTTP 500 by design, even when the session and manifest were copied correctly. Keep the original evidence root for historical read-only replay. A future migration format must define verifiable relocation provenance and digest checks; changing an old manifest in place would invalidate its original bytes. This limitation is distinct from a Host version regression.

