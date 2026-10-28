# rc.31 installation source and reproduction

This is implementation and test evidence, not a final security or behavioral acceptance. The previous frozen kit and its runbook remain historical artifacts; do not use their npm Host bootstrap or their embedded scripts for this new policy. The old kit's Runtime snapshot predates subsequent security fixes.

## Topology and resolution

* A fresh **Host runner** contains only `@deepseek-ai/dsh@0.2.1-rc.4` as a direct dependency. The official rc.4 `profile-boot` uses its own package as installation anchor. Its app-boot resolver tries installation bundles before Profile bundles and gives installation packages precedence. The Host does not need a direct dependency on this plugin.
* A separate **Home** contains `profiles/<name>/` and `plugin-artifacts/`. The Profile manifest directly installs only `@dsh-runtime/harness-plugin`, whose bundle is loaded from that Profile. Its relative specifier is `file:../../plugin-artifacts/dsh-runtime-harness-plugin-0.1.0-rc.31.tgz`; these two directories move together. Host and Profile each have their own package, workspace policy, lock and pnpm store links.
* A separate **Runtime** contains the supplied source snapshot and its Python venv. The Profile patch points to it; it is not an npm installation root. A connection file stays outside all three roots. `New-Rc31InstallKit.ps1` accepts a supplied Runtime manifest and wheelhouse; the caller must choose and separately qualify the Runtime snapshot. Supplying an old manifest does not turn it into a new Runtime.

Host policy permits only the five explicitly listed native/build packages; Profile policy grants no builds and its installer additionally uses `--ignore-scripts`. Both use pnpm 11.25.0, Node >=24.19.0 and frozen lockfiles. Overrides fix zod 4.6.6, the rc.4 proxy and web-fetch undici 8.12.2, libreoffice-kit fflate 0.8.3, and rc.4 MCP client 2.3.0 with core 2.3.0. See `integrations/deepseek-harness/DEPENDENCY_SECURITY_RC31.md`, which is included in the locked tarball. Node's bundled undici is separate.

## Actual entry points

Prepare a **new, empty output path** from this checkout and a separately prepared asset directory containing `manifest.json`, its named Runtime ZIP, and `wheels/`:

```powershell
& .\scripts\New-Rc31InstallKit.ps1 -AssetRoot $assetRoot -OutputRoot $kitRoot
& (Join-Path $kitRoot 'Install-Rc31Host.ps1') -KitRoot $kitRoot -HostRunnerRoot $hostRunnerRoot -NodePath $nodePath -PnpmPath $pnpmPath
& (Join-Path $kitRoot 'Install-ApiReviewerPreview.ps1') -KitRoot $kitRoot -HostRunnerRoot $hostRunnerRoot -HomeRoot $homeRoot -RuntimeRoot $runtimeRoot -ConnectionPath $connectionPath -PythonPath $pythonPath -PnpmPath $pnpmPath -NodePath $nodePath
& (Join-Path $kitRoot 'Start-QualifiedHost.ps1') -KitRoot $kitRoot -HostRunnerRoot $hostRunnerRoot -HomeRoot $homeRoot -NodePath $nodePath -DumpConfig
```

Use absolute paths and a trusted asset manifest, and follow the connection, Python and fresh-directory prerequisites in the historical operator runbook. `-Offline` requires a populated pnpm cache. Installation failures can leave partial fresh directories: retain them as evidence and use a new path for another attempt. The assembly script copies the versioned scripts, policies, locks and plugin into the new kit, checks the supplied Runtime and wheel hashes, and updates the plugin hash. Never edit the old kit in place.

The Host and Profile installers do not regenerate locks. Before install and before launch the checks compare the installed root manifests, policies and locks byte-for-byte with the kit, verify the official Host digest, and traverse actual installed consumer dependencies within their own roots to reject wrong versions or outside-root resolution. Startup also checks the Home plugin tarball against the kit manifest. These checks depend on a trusted, intact kit; they do not authenticate the kit or hash every installed source file.

## Reproducing and refreshing the policy

With Node 24 and pnpm 11.25.0, `node tests/test-rc31-install.mjs` copies the layout to a fresh directory, performs both frozen installations without lifecycle scripts, checks consumer resolution and unchanged locks, rejects a changed lock, and rejects a real old graph even after its root policy and lock are replaced. CI runs this regression. The actual Host entry also needs a separate test with its allowed lifecycle scripts enabled.

The committed plugin tarball is a controlled input to the Profile lock. When plugin source or the packaged security note changes, rebuild it with `pnpm pack --pack-destination ../../install/rc31/plugin-artifacts` from `integrations/deepseek-harness`, intentionally regenerate the Profile lock against those bytes, and rerun the regression and entry tests. Review the changed tarball, lock, policy and source together. Do not run lock regeneration during ordinary installation or modify `node_modules`.

The 2026-10-28 local entry exercise used a synthetic connection and the historical Runtime only as a fixture; Host installation, Profile installation and `-DumpConfig` succeeded without model calls. Tests do not establish MCP redirects, web-fetch, archive attack handling, deployed Node security, second-device operation, or final acceptance. ExecuteGate remains `NOT_CLAIMED`.

## Completion and path boundaries

Host installation writes `.rc31-install-complete.json` only after pnpm succeeds and Host identity and graph checks pass. Profile installation requires that Host record and writes its own record only after pnpm and Profile graph checks succeed. Startup requires both records. Each binds the absolute installation root and hashes of its package, workspace policy and lock; the Profile record also binds its configuration and Runtime and connection paths. A moved, incomplete or mismatched installation must be replaced with a fresh installation. Records guard against accidental use of partial installations; they do not resist same-user tampering and are neither D2 authorization nor run receipts.

Host runner, Home and Runtime must be distinct and non-nested, with the connection file outside all three. Absolute paths through links or junctions are refused, including existing ancestors of new paths, on install and startup. Preserve failed directories and logs; do not retry in place. The kit and installation inputs must remain trusted and unchanged during these checks.

For the Windows entry regression, assemble a fresh kit from separately qualified fixture assets, then run `tests/Test-Rc31Completion.ps1` with `-KitRoot`, `-NodePath`, `-PnpmPath`, `-PythonPath`, and a new absolute `-FixtureRoot`. It uses a synthetic credential, performs real frozen installs, injects a failure after pnpm returns, checks missing and mismatched records and path rejection, and leaves its fixture directory intact. Capture its output to a separate log. The supplied Runtime fixture is not thereby qualified for production.
