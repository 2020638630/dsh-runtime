# DSH Runtime for official DeepSeekHarness (private preview)

This package is an independently installable Host bundle for the unmodified public `@deepseek-ai/dsh@0.2.1-rc.2`. It is still a private preview. It does not provide the authenticated Evidence Manifest route or Web drawer yet, and has not passed a real official Host model task. Keep the private RC4 Harness as the parallel daily fallback.

## Build and install in an isolated Profile

Run `pnpm build` and `pnpm pack`. The tarball contains `lib/` and `cordis.patch.yml`; its `dsh.bundle.patch` inserts the external plugin. Install the tarball in an isolated consumer/Profile. The plugin requires a complete Profile config before activation:

```yaml
- id: dsh-runtime-standalone
  config:
    runtimeRoot: D:/path/to/dsh-runtime
    python: C:/path/to/python.exe
    policySource: D:/path/to/dsh-runtime/dsh_runtime/resources/selection_policy/selection-v2.json
    expectedPolicyHash: <pinned-lowercase-sha256>
    enabledWorkloads: [repository_inspection]
    auditPath: D:/isolated/audit/governance.jsonl
    evidenceRoot: D:/isolated/evidence
```

The Runtime root and policy file must exist. The audit parent and evidence directory must exist. The worker confirms the policy identity and audit availability before either provider or the tool is registered. The caller's parent Session supplies the target workspace. Profile paths never redirect a task into either source checkout. No D2 ExecuteGate claim is made.

The current isolated official Host acceptance Profile is `D:/DeepSeekHarness/vis-stable-release-artifacts/official-plugin-probe-20261020/home/profiles/runtime-official`; the tarball is beside the consumer. This Profile enables inspection only. Its full config is local acceptance state, not a production template. The official Host booted with a real Python governance worker, zero activation warnings and an authenticated HTTP 200. A sandboxed launch first returned Windows `spawn EPERM`; a narrow elevated retry succeeded. No real model task or Runtime child was run in this gate.

## Verified gates

`pnpm typecheck`, `pnpm build`, and `pnpm test:entry` pass. Earlier focused tests also cover fail-closed admission, real Python worker ALLOW/DENY and durable audit, both fixed provider routes, parent Session cwd, Host startup rollback, and dedicated tool route. The worker tests use isolated audit paths; the provider and tool tests use Host doubles.

Next: verify official Host tool/provider state and a non-D2 read-only Runtime task in a fresh temporary Git repository, add an authenticated terminal Manifest route and Web drawer, then test write, failure, cancellation, missing evidence and uninstall. Do not enable this Profile as the daily entry until those gates pass.
