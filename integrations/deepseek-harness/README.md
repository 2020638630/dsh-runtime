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

Create a separate official Host Profile with `pinRoot` set to the new Home's `pins/`, and provide its other required paths independently. Verify SessionQuery and Web replay in the copied Home before considering it for daily use. Rollback is to stop that isolated Host and launch the existing daily entry with the untouched original Home. Do not run two Hosts against one Home concurrently.
