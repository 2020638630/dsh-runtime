# DSH Runtime for official DeepSeekHarness (private preview)

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

The three roles are required when the config is present. A `codex` worker is also accepted and receives workspace write authority only for the existing write stage; reviewer and inspector remain read-only and currently require `codex`. Codex model IDs are passed to its app-server `thread/start` request; model availability still depends on the installed Codex account. CodeBuddy model overrides are rejected until its CLI model-selection contract and observed result can be verified; leaving its `model` as `null` preserves its own default. Reasoning overrides are not part of this schema. This configuration cannot add stages, raise read-only authority, or enable D2. Do not put credentials in `roleConfig`.

The isolated official Host acceptance Profile is `D:/DeepSeekHarness/vis-stable-release-artifacts/official-plugin-probe-20261020/home/profiles/runtime-official`; the tarball is beside the consumer. This Profile enables inspection only. Its full config is local acceptance state, not a production template. In a fresh temporary Git repository, a real official Host model task called `dsh_runtime` for `repository_inspection`: the child completed, the governance audit recorded one `ALLOW`, the terminal Manifest reported no file changes, and the repository stayed clean. After a Host restart, the authenticated evidence route still returned HTTP 200 for that Session; anonymous, malformed and other-Session requests returned 401, 400 and 404 respectively.

## Verified gates

`pnpm typecheck`, `pnpm build`, `pnpm test:entry`, `pnpm test:pin-store`, `pnpm test:worker`, and `pnpm test:host-core` pass. Earlier focused tests also cover fail-closed admission, both fixed provider routes, parent Session cwd, Host startup rollback, and dedicated tool route. The worker tests use isolated audit paths; the provider and tool tests use Host doubles.

The first isolated trial exposed an official Host incompatibility: a private, required `subagent/governance-policy-pin` Session event prevented replay after restart. That test Session remains as failure evidence. This adapter now stores the immutable policy pin in its own Host directory before pre-start evaluation and writes no private Session event. The second fresh trial and post-restart evidence read passed.

The private preview `0.1.0-rc.4` loaded in the unmodified official Web Host. A browser reopened the completed read-only Session, expanded its process group, opened the external drawer, and verified the execution, observed changes, and audit tabs. No model call was needed for this replay. The screenshot is in the isolated acceptance consumer's `runtime-profile/official-rc4-evidence-drawer.png`.

Write, failure, cancellation, missing evidence, uninstall, and old Home copy replay have passed in isolated Profiles. The copied Home contained three old Sessions with private pin events; after copy-only migration and sequence repair, the unmodified official Host read all 33 Sessions. This does not switch the daily entry.

## Copy an old Home for official Host replay

Run the CLI with Node.js 24.19 or newer, which provides the Zstd APIs used for Session files. Use `dsh-runtime-migrate-home --source-home ABS --destination-home ABS` to inspect the migration plan without writing anything. Add `--apply` only after reviewing the plan. The destination must be a **new, nonexistent directory** outside the source Home. The tool copies only `sessions/`; it does not copy credentials, settings, or Profiles. For each Session containing the retired private event, it archives the original compressed file under `archive/`, writes the policy identity under `pins/`, removes the event from the destination copy, and repairs known sequence references. It rejects unknown sequence fields and leaves the source Home unchanged. The destination also contains `migration-report.json`. If migration fails, discard the partial destination and start with a fresh destination; never point the official Host at a partial copy.

Create a separate official Host Profile with `pinRoot` set to the new Home's `pins/`, and provide its other required paths independently. Verify SessionQuery and Web replay in the copied Home before considering it for daily use. Rollback is to stop that isolated Host and launch the existing daily entry with the untouched original Home. Do not run two Hosts against one Home concurrently.
