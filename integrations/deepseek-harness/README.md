# DSH Runtime for official DeepSeekHarness (private preview)

This package is an independently installable Host and Web bundle for the unmodified public `@deepseek-ai/dsh@0.2.1-rc.2`. It is still a private preview. The authenticated terminal Evidence Manifest route and three-tab Web drawer passed an isolated real Host read-only task. Keep the private RC4 Harness as the parallel daily fallback.

## Build and install in an isolated Profile

Run `pnpm build` and `pnpm pack`. The tarball contains the Host entry, `lib/client.js`, and `cordis.patch.yml`; its `dsh.bundle.patch` inserts the external plugin and `dsh.client` declares the Web entry. Install the tarball in an isolated consumer/Profile. The plugin requires a complete Profile config before activation:

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

The isolated official Host acceptance Profile is `D:/DeepSeekHarness/vis-stable-release-artifacts/official-plugin-probe-20261020/home/profiles/runtime-official`; the tarball is beside the consumer. This Profile enables inspection only. Its full config is local acceptance state, not a production template. In a fresh temporary Git repository, a real official Host model task called `dsh_runtime` for `repository_inspection`: the child completed, the governance audit recorded one `ALLOW`, the terminal Manifest reported no file changes, and the repository stayed clean. After a Host restart, the authenticated evidence route still returned HTTP 200 for that Session; anonymous, malformed and other-Session requests returned 401, 400 and 404 respectively.

## Verified gates

`pnpm typecheck`, `pnpm build`, `pnpm test:entry`, `pnpm test:pin-store`, `pnpm test:worker`, and `pnpm test:host-core` pass. Earlier focused tests also cover fail-closed admission, both fixed provider routes, parent Session cwd, Host startup rollback, and dedicated tool route. The worker tests use isolated audit paths; the provider and tool tests use Host doubles.

The first isolated trial exposed an official Host incompatibility: a private, required `subagent/governance-policy-pin` Session event prevented replay after restart. That test Session remains as failure evidence. This adapter now stores the immutable policy pin in its own Host directory before pre-start evaluation and writes no private Session event. The second fresh trial and post-restart evidence read passed. Existing Sessions already containing that private event still need a copy-only migration study.

The private preview `0.1.0-rc.4` loaded in the unmodified official Web Host. A browser reopened the completed read-only Session, expanded its process group, opened the external drawer, and verified the execution, observed changes, and audit tabs. No model call was needed for this replay. The screenshot is in the isolated acceptance consumer's `runtime-profile/official-rc4-evidence-drawer.png`.

Next: test write, failure, cancellation, missing evidence, uninstall, and old Home copy migration. Do not enable this Profile as the daily entry until those gates pass.
