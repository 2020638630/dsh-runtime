# Desktop test.10 development baseline

The plugin and Python Runtime are in this repository. Deploying bounded activity
history B requires both artifacts from the same source tree. This build does not
install a Host, update a Profile, copy a user home, log in, or call a model.

## Dependencies

- Node.js >=24.19.0. The Windows baseline validation uses 24.22.2.
- pnpm 11.25.0 for dependency installation. Use the committed lockfile.
- TypeScript 6.0.3 and the other plugin dependencies are pinned in
  `integrations/deepseek-harness/package.json` and `pnpm-lock.yaml`.
- Python >=3.12 for the standard-library build script. No Python package is
  needed to build. This baseline's keyless regressions use pytest 9.2.0 and the
  optional transport dependency in `requirements-api-agent.txt`.
- Desktop artifact compatibility target: DeepSeek Harness 0.2.2-rc.1. Shared
  Host services remain peer dependencies; only zod is a plugin dependency.

Recreate dependencies on the target OS. Do not transfer a Windows virtual
environment, `node_modules`, credentials, or a daily Profile to Fish.

## Build from a checkout

Choose a fresh output directory outside the checkout and a separate dependency
store. On the Windows development machine, use the designated temporary area.
The following shell variables are operator-selected paths, not repository or
daily configuration settings:

```sh
cd integrations/deepseek-harness
pnpm --version # 11.25.0
pnpm install --frozen-lockfile --ignore-scripts --store-dir "$DSH_DEPENDENCY_STORE"
cd ../..
python3 -I -S -B scripts/build_desktop_baseline.py --output "$DSH_BUILD_OUTPUT"
```

On Windows, invoke `python` instead of `python3` and use PowerShell environment
variable syntax. If pnpm is absent or has a different version, prepare the
pinned version in a separate tools directory, without changing daily tools.
The old `pack:desktop-rc1` command retains its legacy version behavior; use the
new build script for this baseline.

The output directory must not exist. The script compiles the current TypeScript
source with LF output and creates:

- `dsh-runtime-harness-plugin-0.1.0-rc.37-test.10.tgz`
- `dsh-runtime-source-0.1.0-rc.37-test.10.tar.gz`
- `runtime-source/dsh_runtime/`: matching Python files and selection policy
- `plugin-stage/package/`: inspectable plugin payload
- `build-manifest.json`: toolchain, LF-normalized source hashes, source-tree
  digest, archive hashes, and every plugin/Runtime payload hash

The Runtime allowlist is Python source below `dsh_runtime` and
`resources/selection_policy/selection-v2.json`. Cache files, credential/config
stores, environment files, homes, evidence and installed dependencies are not
copied. Source links are rejected. There is no recursive cleanup: failed or
partial output remains for inspection, and existing output is never replaced.

The source manifest remains the development manifest; the script explicitly
sets the desktop version, peer dependencies, client injection and payload list.
It does not use a previously installed test.9 package as a seed. Archive headers
and gzip timestamps are fixed, and text payloads normalize CRLF to LF. Compare
the source-tree and per-file hashes as well as the archive hashes. Exact gzip
bytes across different Python/zlib or compiler versions are not guaranteed.

## Historical candidate and validation boundaries

The original accepted test.10 package has SHA-256
`7899f2239939d1552d04ce6cb921dbbe9ae4cc125b2fa4c46103a0c96a970435`.
It was made by a temporary staging process seeded from a local test.9 package.
This clean build does not claim byte identity with that historical archive:
headers, line endings and the explicit activity-contract payload metadata can
differ. Keep the historical package and compare payloads; never replace it just
because the version string is the same.

Historical bounded-activity regressions passed 74 selected Node checks and
159 selected Python checks, with one known Windows cancellation check excluded.
These counts are historical, not a claim that a new checkout has been tested.
The real isolated smoke Run's original Reviewer verdict remains FAIL because
the Windows command startup chain was blocked. Neither building nor committing
this baseline changes that verdict. Windows package identity, real cancellation,
and pause/reconnect recovery with actual missed events require their separate
Windows acceptance. No model task is part of this build.

The baseline verification selects the following checks. Set temporary-directory
environment variables to a separate test directory before running them, and set
`PYTHONDONTWRITEBYTECODE=1`. `DSH_TEST_RUNTIME_ROOT` is the checkout root and
`DSH_TEST_PYTHON` is the selected Python executable (not a daily CLI executable).

```sh
cd integrations/deepseek-harness
node node_modules/typescript/bin/tsc --noEmit
node node_modules/typescript/bin/tsc -p tsconfig.test.json
node --test .build/test/activity-history.test.js .build/test/activity-run.test.js .build/test/api-agent-trace.test.js .build/test/client-evidence-scope.test.js .build/test/read-terminal-evidence.test.js test/evidence-route.test.mjs test/copy-terminal-evidence.test.mjs
cd ../..
python3 -B -m pytest -q -p no:cacheprovider --basetemp "$DSH_TEST_TEMP" -k 'not test_windows_cancellation_settles_owned_descendant' tests/test_build_desktop_baseline.py tests/test_activity_history.py tests/test_codex_plugin.py tests/test_codebuddy_plugin.py tests/test_entrypoint.py tests/test_m5_repository_change_workflow.py
```

The explicit cancellation exclusion preserves the known Windows test boundary;
it is not evidence that cancellation works. The source-link rejection check may
be skipped on Windows when the current account cannot create symbolic links.

For keyless verification, typecheck and compile the plugin test project, run the
activity/history, evidence, route, client and evidence-copy tests, and run the
Python packaging/activity/adapter/workflow regressions in a separate test root.
Record exact selections, failures, skips, platform and toolchain. Do not describe
synthetic protocol tests as real Worker/Reviewer model execution. The current
CI workflows target Windows; Fish/Linux and a fresh cloud dependency installation
need their own recorded verification.
