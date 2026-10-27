# rc.31 / official rc.4 private Windows operator runbook — 2026-10-27

This companion is the current handoff for the frozen `rc31-official-rc4-private-kit-20261027.zip`. The README **inside that ZIP** was written before the later visual, live-task and fallback checks. Its statements that those checks are still pending are historical, not the current gate result. Preserve the ZIP unchanged so its recorded SHA-256 and trial evidence remain valid. This is an opt-in private Windows candidate; the old daily shortcut stays in place. Formal D2 ExecuteGate is `NOT_CLAIMED`.

## Exact configuration and evidence boundary

| Component | Qualified combination | Boundary |
| --- | --- | --- |
| Host | Unmodified `@deepseek-ai/dsh@0.2.1-rc.4` in an exact-digest runner | `Assert-QualifiedHost.ps1` checks runner package metadata, Host package and compiled artifact digests. A version string alone is insufficient. |
| Plugin / Runtime | `@dsh-runtime/harness-plugin@0.1.0-rc.31`; Runtime snapshot `d3af857bb87babb0f96b87adc2839f8761b45eba` | Exact ZIP and tarball hashes below. No automatic update claim. |
| Windows / PowerShell | Local Windows and PowerShell 5.1 install/start passed | A second device/account with rc.31 remains to be tested. Other operating systems are outside this gate. |
| Node / pnpm | Explicit Node executable at least `24.19.0`; local acceptance used `24.19.0` and pnpm `11.25.0` | Check the **path passed to the script**. A different `node` on `PATH` can be older. Other pnpm versions are unqualified. |
| Python | 3.12; local acceptance used Python 3.12 with bundled offline `httpx==0.28.1` wheels | Installer creates its own `.api-agent-venv`. Other Python versions are unqualified. |
| Worker | Logged-in CodeBuddy CLI `2.164.0`; parent model chosen in official Host UI | CLI login was supplied by the local environment. Codex worker option exists but has no rc.31 live acceptance in this record. |
| Reviewer / inspector | Read-only API agent via external SiliconFlow connection, `Qwen/Qwen3-Coder-30B-A3B-Instruct`, request/tool/output caps | The connection file stays outside kit and Home. Other providers/models need their own qualification. |

The local rc.31 `repository_change` had one 27-byte target and consistent raw Manifest/Diff/closed traces. The UI showed `completed`/`PASS` and all three Runtime tabs. This is bounded evidence, not proof for arbitrary workloads. See `RC31_OFFICIAL_RC4_LIVE_TRIAL_RESULT_2026-10-27.md`. The earlier rc.30/official rc.3 run on a separate Windows device does not count as rc.31 second-device acceptance.

## Before installation

1. Keep the current daily Host stopped for the isolated check. Preserve every existing Home, Session and evidence directory. Use **new, empty** Home and Runtime paths; the installer refuses to overwrite either path.
2. Obtain the frozen ZIP and check its SHA-256: `323928F8FBE4272474D071C93772240171EA1214864272D3D258CCA0F6C0C9FB`. Check that the exact official rc.4 runner and explicit Node 24.19.0+ executable are present. `node --version` from an arbitrary shell is not a substitute for checking the selected executable.
3. Keep `connections.local.json` in a separate protected location. Do not place it under the kit, Home or Runtime, and do not send its contents, API keys or login tokens with acceptance evidence. The connection must contain the selected `ConnectionRef`/provider pair. Verify Python 3.12, pnpm 11.25.0 and CodeBuddy 2.164.0 separately.
4. Installation needs access to the official npm registry unless all exact package metadata and tarballs are already cached for `-Offline`. The bundled Python wheel install itself uses `--no-index`.

PowerShell 5.1 template; replace every `REPLACE_*` path and use a fresh suffix for each attempt. It does not alter old Homes:

```powershell
$ErrorActionPreference = 'Stop'
$zipPath = 'REPLACE_WITH_ABSOLUTE_ZIP_PATH'
$stageRoot = 'REPLACE_WITH_NEW_EMPTY_EXTRACT_DIRECTORY'
$homeRoot = 'REPLACE_WITH_NEW_HOME_DIRECTORY'
$runtimeRoot = 'REPLACE_WITH_NEW_RUNTIME_DIRECTORY'
$connectionPath = 'REPLACE_WITH_EXTERNAL_CONNECTIONS_LOCAL_JSON'
$hostRunnerRoot = 'REPLACE_WITH_EXACT_OFFICIAL_RC4_RUNNER_DIRECTORY'
$nodePath = 'REPLACE_WITH_NODE_24_19_0_OR_NEWER_EXE'
$pythonPath = 'REPLACE_WITH_PYTHON_3_12_EXE'
$pnpmPath = 'REPLACE_WITH_PNPM_CMD'

$expectedZip = '323928F8FBE4272474D071C93772240171EA1214864272D3D258CCA0F6C0C9FB'
if ((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash -ne $expectedZip) { throw 'ZIP hash mismatch; stop.' }
foreach ($target in @($stageRoot, $homeRoot, $runtimeRoot)) {
    if (Test-Path -LiteralPath $target) { throw "Target already exists; stop: $target" }
}
if (-not (Test-Path -LiteralPath $connectionPath -PathType Leaf)) { throw 'External connection file missing; stop.' }
& $nodePath --version
& $pythonPath --version
& $pnpmPath --version
Expand-Archive -LiteralPath $zipPath -DestinationPath $stageRoot
$kitRoot = Join-Path $stageRoot 'rc31-official-rc4-private-kit-20261027'
$installParams = @{
    KitRoot = $kitRoot
    HomeRoot = $homeRoot
    RuntimeRoot = $runtimeRoot
    ConnectionPath = $connectionPath
    PythonPath = $pythonPath
    PnpmPath = $pnpmPath
    HostRunnerRoot = $hostRunnerRoot
    NodePath = $nodePath
    WorkerAdapter = 'codebuddy'
}
Set-ExecutionPolicy -Scope Process Bypass -Force
& (Join-Path $kitRoot 'Install-ApiReviewerPreview.ps1') @installParams
```

The installer validates the Host and kit hashes before writing Home/Runtime, then creates the Runtime venv and Profile. A failed install **may leave a partial fresh target**. Keep the error output and partial path for diagnosis; do not rerun against the same path and do not remove it until evidence has been captured. Resolve the cause and choose new Home/Runtime/stage suffixes for the next attempt. This fresh-path procedure passed one controlled pnpm-failure exercise with a no-model recovered Host probe; see `RC31_PARTIAL_INSTALL_RECOVERY_2026-10-27.md` in the source candidate. The scripts do not provide an in-place repair or uninstall operation.

## Start, check and stop

Start only the new Profile from a dedicated PowerShell window, using the exact paths installed above:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
& (Join-Path $kitRoot 'Start-QualifiedHost.ps1') -KitRoot $kitRoot -HomeRoot $homeRoot -HostRunnerRoot $hostRunnerRoot -NodePath $nodePath
```

Open the local URL printed by that Host. Check the page, default workspace, composer input, plugin activation and model selector. For a no-model check, do not send a prompt. Record any startup error and stop there. Stop the Host with Ctrl+C in its own terminal, then wait for that process to exit. If a model task was run, first wait for its terminal result and capture all three DSH Runtime tabs. Keep the Home, Runtime, Git workspace and raw evidence intact. Do not infer success from a model `PASS` alone; independently reconcile target bytes and raw evidence as in the live-trial report.

## Parallel return and removal boundary

If rc.31 cannot start or the check fails, stop its isolated Host, leave its Home/evidence untouched, and reopen the existing daily entry with its **own** original Home. A separate fresh rc.30/official rc.3 install and authenticated no-model start passed locally after rc.31 use. This proves a parallel fallback, not in-place downgrade or Session/credential migration. Never point the older Host at the rc.31 Home or merge the Homes. There is no verified one-click uninstall; removing any trial directory is a later retention decision after its evidence is archived and checked.

## Second-device acceptance handoff

Send only the frozen kit ZIP and this companion runbook. On the second Windows device/account, record:

- ZIP SHA-256; selected PowerShell, Node, Python, pnpm and CodeBuddy versions/paths; exact official Host preflight result; fresh installer result. Do not include the connection JSON or token values.
- Authenticated local page and Session list availability, composer/model selector, plugin presence, and clean stop. Report errors exactly if any; do not keep retrying a failing model task.
- If the no-model gate passes, create a fresh isolated Git repository with an initial empty commit and confirm `git status --porcelain` is empty. Select that repository in the new Host UI. Send exactly one request: `只调用一次 dsh_runtime，执行 repository_change；只在当前工作区创建 rc31-second-device-trial.txt，内容恰好为 RC31_SECOND_DEVICE_OK 加一个 LF 换行。不使用 D2，不改其他文件；等待子任务状态回执。` The expected final file is 22 ASCII bytes (21 content bytes and one LF), with no BOM or CR; measure it independently rather than relying on model prose. Record task ID, terminal status, reviewer verdict, three drawer tabs, actual file bytes and Git delta. Preserve Manifest, Diff, worker/reviewer closed traces and governance audit for independent read-only reconciliation. The audit currently lacks a unique run ID, so do not claim exclusive attribution.
- Whether the old daily entry and its Home still start independently after stopping rc.31. Do not switch the default shortcut during this acceptance.

The requested return package is a short status plus sanitized command output/screenshots and hashes, followed by raw non-secret run evidence through the established evidence handoff path. A second-device `PASS` is not declared until those records are independently checked.
