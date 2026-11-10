# DSH Runtime for official DeepSeekHarness (private preview)

## Fast official Host update triage

`node scripts/host-compat-report.mjs --host ABS_HOST_RUNNER --plugin ABS_PLUGIN_ROOT --baseline ABS_BASELINE_JSON` reads installed package metadata and the code/type artifacts of official packages imported by this plugin. Without `--baseline`, it emits a baseline JSON document. The comparison distinguishes imported code changes from version-only package metadata, Host dependency/lock changes, and missing or ambiguous installations. This is a **change inventory**, not a compatibility verdict: run the no-model Host smoke and use the risk-based escalation procedure before adding a new official version to a supported matrix. `pnpm test:host-compat-report` exercises synthetic changed/missing/ambiguous package cases. The fixed r9 candidate is qualified only for the recorded `0.2.1-rc.2` Host.

The [official Host update gate](HOST_COMPATIBILITY_GATE.md) specifies the minimum checks for each classification and records the historical evidence relocation boundary. The [support matrix](SUPPORTED_HOSTS.md) lists the exact Host/Plugin combinations and their observed acceptance level.

This package is an independently installable Host and Web bundle for the unmodified public `@deepseek-ai/dsh@0.2.1-rc.2`. It is still a private preview. The authenticated terminal Evidence Manifest route and three-tab Web drawer passed isolated real Host read-only and write tasks. Keep the private RC4 Harness as the parallel daily fallback.

## Build and install in an isolated Profile

Run `pnpm build` and `pnpm pack`. The tarball contains the Host entry, `lib/client.js`, `cordis.patch.yml`, and the copy-only Home migration CLI; its `dsh.bundle.patch` inserts the external plugin and `dsh.client` declares the Web entry. Install the tarball in an isolated consumer/Profile. The plugin requires a complete Profile config before activation:

```yaml
- id: dsh-runtime-standalone
  config:
    runtimeRoot: D:/path/to/dsh-runtime
    python: C:/path/to/python.exe
    policySource: D:/path/to/dsh-runtime/dsh_runtime/resources/selection_policy/selection-v2.json
    expectedPolicyHash: <pinned-lowercase-sha256>
    enabledWorkloads: [repository_inspection]
    auditPath: D:/isolated/audit/governance.jsonl
    pinRoot: D:/isolated/pins
    evidenceRoot: D:/isolated/evidence
```

The Runtime root and policy file must exist. The audit parent, pin directory and evidence directory must exist. The worker confirms policy identity before either provider or the tool is registered. The Host-owned pin store writes one immutable policy identity per Session before evaluating a Runtime start; the official Session log receives no private event type. The caller's parent Session supplies the target workspace. Workspaces overlapping Runtime control state are rejected. Profile paths never redirect a task into either source checkout. No D2 ExecuteGate claim is made.

## Desktop 0.2.2-rc.1 preview

Run `pnpm install --frozen-lockfile --ignore-scripts` and then
`pnpm run pack:desktop-rc1 ABS_OUTPUT_DIRECTORY` in this package. The output
directory must already exist. This builds the `0.1.0-rc.35` Desktop bundle,
which declares its exact Harness version and uses the host's shared packages.
The frozen RC.31 tarball targets the earlier Web setup. Installing that
tarball in Desktop 0.2.2-rc.1 can replace core host dependencies and leave the
window blank even while the bundle is disabled.

Import the RC.35 tarball by its absolute `file:` path in an isolated Desktop
Profile. Apply the Profile configuration above before enabling the bundle.
Start with only `repository_inspection` enabled for a read-only smoke test.
Use the matching Runtime source to display repository-change review verdicts.
With an older Runtime, tasks can still run and the verdict is shown as unavailable.

## Role and model selection (preview)

The optional `roleConfig` belongs in the plugin's Profile config, alongside `runtimeRoot`. It is frozen into one Runtime child invocation. Omit it to keep the existing CodeBuddy write stage and Codex review/inspection stages:

```yaml
    roleConfig:
      schema_version: 1
      roles:
        worker: { adapter: codebuddy, model: null }
        reviewer: { adapter: codex, model: null }  # replace null with a supported model ID
        inspector: { adapter: codex, model: null } # may use a different model ID
```

On Desktop, open **插件 → DSH Runtime → 默认 CLI 与模型** to edit the CLI roles. Saving updates the existing `roleConfig` through the Host's settings service. Existing API roles stay managed by the Profile. Each new Runtime task takes a snapshot of the saved role settings. Check the requested and reported worker and reviewer models in the task's evidence drawer.

The Windows Desktop plugin detail also has a **CLI 登录** section. Each CLI reports its local login state. Use the login button to open that CLI's own window and complete its browser flow. Codex writes to the Runtime's managed Codex home, and CodeBuddy uses the credential store from the Runtime's CodeBuddy environment. In the CodeBuddy window, follow the startup login prompt or enter `/login`, then close the window. Status refreshes when the window closes and can also be checked manually. The plugin page receives status labels only. A local sign-in state does not test model access.

With the matching Runtime source, a running tool card shows the current stage, its executor and the most recent safe activity observed in that stage. The elapsed and activity times update while the task is running. The settled evidence drawer still provides the verified result and workspace changes.

### API connections on Windows Desktop

Use **插件 → DSH Runtime → API 连接** with a matching Runtime source that includes the connection administration module. The plugin uses the Profile's existing `apiAgentConnectionsPath` when configured. Otherwise it saves to the file named by appending `.api-connections.json` to `auditPath`. To use a new reference in a task, set the existing v2 role's `connection_ref` and point `apiAgentConnectionsPath` at that catalog.

On Desktop, the model field supports manual IDs and a searchable catalog for Codex and existing OpenRouter or SiliconFlow roles. An API role's model can be edited without changing its provider, connection reference or budgets. Refresh uses the saved connection and sends a model catalog request without generating a response. Listed models are candidates and their invocation permissions may vary. CodeBuddy uses manual IDs or its CLI default.

Each new connection has a reference, a provider and a key. OpenRouter and SiliconFlow use their fixed official endpoints. A saved reference and its provider are fixed. Leave the key field empty to keep the existing key. Saving changes only the connection catalog. The stored key is never returned to the form.

**试连 API** checks the current draft without saving it. OpenRouter checks the key endpoint. SiliconFlow checks that the chat model catalog can be read. Both checks use non-generation requests and report only the result category. Check a selected model separately when testing a Runtime task.

The three roles are required when the config is present. Under schema v1, a `codex` worker is also accepted and receives workspace write authority only for the existing write stage; reviewer and inspector remain read-only and require `codex`. Codex model IDs are passed to its app-server `thread/start` request; model availability still depends on the installed Codex account. A CodeBuddy worker model ID is passed as `--model` to the installed CLI in both JSON and stream JSON modes. The current local CLI (`2.164.0`) advertises this flag, and one isolated direct worker trial observed the requested `deepseek-v4.1-flash` model. A model ID unsupported by the installed CLI or account can still fail at invocation time. Leaving `model` as `null` preserves each adapter's own default. Reasoning overrides are not part of this schema. This configuration cannot add stages, raise read-only authority, or enable D2. Do not put credentials in `roleConfig`.

The API Agent candidate adds an explicit schema v2 route. The connection file is outside every Git worktree and contains the provider key; the Profile contains only its absolute path and a connection reference. The rc15 trial qualified a real **inspector** run; rc18 and rc19 separately exercised worker plus API reviewer. The fixed r8 private package completed an isolated official Host Codex worker plus API reviewer run with two closed traces, a settled audit, and the exact requested file. The r8 reviewer still could not independently establish that no other file changed; the Host's bounded pre/post snapshot supplied separate file-change evidence. Keep this route in private preview pending the remaining release gates. API worker remains disabled:

```yaml
    apiAgentConnectionsPath: D:/isolated-config/connections.local.json
    roleConfig:
      schema_version: 2
      roles:
        worker: { adapter: codebuddy, model: null }
        reviewer: { adapter: codex, model: null }
        inspector:
          adapter: api_agent
          provider: siliconflow
          model: Qwen/Qwen3-Coder-30B-A3B-Instruct
          connection_ref: trial_siliconflow
          max_requests: 3
          max_tool_calls: 3
          max_output_tokens: 512
```

The Runtime accepts only the configured provider, endpoint and model, with no automatic model fallback. A completed API inspection writes a metadata-only Safe Trace and a run-bound `.closed` marker. The Host labels that source `api_agent_safe_event_trace`; a missing expected trace is `unavailable`. The rc15 bundle completed one real API inspection in an isolated official Host, with a settled audit, complete trace, no file changes and a clean temporary Git repository. The API inspector currently exposes explicit `read_file`; directory listing and search are withheld pending handle-bound enumeration verification.

For an isolated reviewer trial, schema v2 may put the same `api_agent` role shape under `reviewer` while leaving the worker as `codebuddy` or `codex`. The terminal Manifest reports `execution_trajectory` for the worker and `review_trajectory` for the API reviewer; a missing or wrong-role reviewer trace is never substituted with worker evidence. A configured reviewer that was not reached because the worker failed is marked `not_applicable`. The verdict comes from Runtime's exact final-line contract. The Manifest's `evidence_scope` records that this is a model report, while `workspace_changes` is a bounded Git tracked/nonignored file snapshot delta. Neither the model PASS nor that delta proves who made a change in a shared workspace. Missing or unrecognized snapshot metadata is shown as unknown in the Web drawer. The r8 fixed package passed one real Host run; this new evidence-scope presentation requires its own packaged Host acceptance before release.

The API worker remains disabled even if a caller requests write authority. The candidate has a pure `plan_text_patch` function for expected-hash and exact-match conflict checks; it cannot write a file. `apply_patch` is absent from the model-facing tool schema until workspace-bound atomic writes and their evidence have passed separately.

The isolated official Host acceptance Profile is `D:/DeepSeekHarness/vis-stable-release-artifacts/official-plugin-probe-20261020/home/profiles/runtime-official`; the tarball is beside the consumer. This Profile enables inspection only. Its full config is local acceptance state, not a production template. In a fresh temporary Git repository, a real official Host model task called `dsh_runtime` for `repository_inspection`: the child completed, the governance audit recorded one `ALLOW`, the terminal Manifest reported no file changes, and the repository stayed clean. After a Host restart, the authenticated evidence route still returned HTTP 200 for that Session; anonymous, malformed and other-Session requests returned 401, 400 and 404 respectively.

## Verified gates

`pnpm typecheck`, `pnpm build`, `pnpm test:entry`, `pnpm test:pin-store`, `pnpm test:worker`, and `pnpm test:host-core` pass. Earlier focused tests also cover fail-closed admission, both fixed provider routes, parent Session cwd, Host startup rollback, and dedicated tool route. The worker tests use isolated audit paths; the provider and tool tests use Host doubles.

The first isolated trial exposed an official Host incompatibility: a private, required `subagent/governance-policy-pin` Session event prevented replay after restart. That test Session remains as failure evidence. This adapter now stores the immutable policy pin in its own Host directory before pre-start evaluation and writes no private Session event. The second fresh trial and post-restart evidence read passed.

The private preview `0.1.0-rc.4` loaded in the unmodified official Web Host. A browser reopened the completed read-only Session, expanded its process group, opened the external drawer, and verified the execution, observed changes, and audit tabs. No model call was needed for this replay. The screenshot is in the isolated acceptance consumer's `runtime-profile/official-rc4-evidence-drawer.png`.

Write, failure, cancellation, missing evidence, uninstall, and old Home copy replay have passed in isolated Profiles. The copied Home contained three old Sessions with private pin events; after copy-only migration and sequence repair, the unmodified official Host read all 33 Sessions. This does not switch the daily entry.

## Copy an old Home for official Host replay

Run the CLI with Node.js 24.19 or newer, which provides the Zstd APIs used for Session files. Use `dsh-runtime-migrate-home --source-home ABS --destination-home ABS` to inspect the migration plan without writing anything. Add `--apply` only after reviewing the plan. The destination must be a **new, nonexistent directory** outside the source Home. The tool copies only `sessions/`; it does not copy credentials, settings, or Profiles. For each Session containing the retired private event, it archives the original compressed file under `archive/`, writes the policy identity under `pins/`, removes the event from the destination copy, and repairs known sequence references. It rejects unknown sequence fields and leaves the source Home unchanged. The destination also contains `migration-report.json`. If migration fails, discard the partial destination and start with a fresh destination; never point the official Host at a partial copy.

### Experimental historical evidence copy

The private experimental package includes `dsh-runtime-copy-evidence`. Invoke it explicitly with `--source-evidence-root ABS --target-evidence-root ABS --run-id dsh-runtime-UUID --workspace-id SESSION_ID` after creating an empty destination evidence root. It copies one settled run and writes a separate `evidence-relocation.v1.json` receipt; it never rewrites the original Manifest and refuses to overwrite a target run. It does not copy Sessions or configure the Host. An interrupted copy leaves a named staging directory for manual inspection. The Host reader labels a verified copy as historical evidence and does not treat its hashes as proof that the original task or model review was correct. This path passed isolated no-model HTTP checks but has not completed visible drawer replay; do not use it as a daily Home migration yet. See [the evidence relocation record](EVIDENCE_RELOCATION_DESIGN.md).

## Review summary

Settled evidence has a copyable summary in the drawer. It contains a local Run reference, task category and permission constraints, outcome, model evidence sources, observed change counts, and evidence availability. The preview and clipboard use the same text. Raw task text, model IDs, paths, source, diffs, and logs remain in their original views.

New Manifests may contain `target_observation` v1 under the existing Session ownership check. It describes regular file bytes observed in the worktree at settlement using the existing tracked and non-ignored untracked scope. The content hash uses UTF-8, the prefix `dsh-post-run-worktree-v1\ndsh_controlled_snapshot_v1\n`, then one JSON array `[relativePath, byteCount, sha256]` per line in ascending path order, terminated by LF. File names and per-file hashes are absent from the observation field. A null digest denotes limited coverage. An absent field denotes a run with no saved observation. Git HEAD is recorded independently when available. Patch completeness is a separate fact.

The observation records a bounded walk of the worktree. It does not record index contents separately or freeze a copy of the material the model reviewed. The summary keeps the actual review target unbound and the current workspace unchecked. A later review flow must verify the selected target and freshness independently.

Completed repository-change runs with a bound PASS can preview material for a later supplemental review. The authenticated evidence route checks the owning Session, the saved patch digest, and a fresh worktree observation. The base commit and observed bytes must both match. The preview accepts complete UTF-8 text patches up to 24 KiB and checks at most 16 MiB of worktree bytes, with a 2 MiB per-file limit. Historical copies, records without the binding fields, and unsupported worktrees are ineligible. This local check does not submit a review.

On Desktop, an API reviewer configured in the Profile can receive the previewed patch after explicit confirmation. The source must belong to a live parent Agent and the inspection workload must be enabled. The Host rechecks the material at confirmation, records one durable claim and a frozen patch per source run, then admits an isolated child through the existing inspection gate. Its single API request includes the patch and fixed review instructions, with zero tools and no inherited conversation. A settled result can be reopened under the same Session. A claim with no recovered result is unknown and cannot be replayed. The worker and returned reviewer models must establish different known model families and the reported reviewer must match the selected model. The supplemental verdict applies only to the frozen patch. A freshness change or disagreement is shown alongside the preserved original evidence.

Create a separate official Host Profile with `pinRoot` set to the new Home's `pins/`, and provide its other required paths independently. Verify SessionQuery and Web replay in the copied Home before considering it for daily use. Rollback is to stop that isolated Host and launch the existing daily entry with the untouched original Home. Do not run two Hosts against one Home concurrently.
