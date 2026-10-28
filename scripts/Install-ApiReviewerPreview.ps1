param(
  [Parameter(Mandatory=$true)][string]$KitRoot,
  [Parameter(Mandatory=$true)][string]$HomeRoot,
  [Parameter(Mandatory=$true)][string]$RuntimeRoot,
  [Parameter(Mandatory=$true)][string]$ConnectionPath,
  [Parameter(Mandatory=$true)][string]$PythonPath,
  [Parameter(Mandatory=$true)][string]$PnpmPath,
  [Parameter(Mandatory=$true)][string]$HostRunnerRoot,
  [Parameter(Mandatory=$true)][string]$NodePath,
  [string]$ProfileName = 'runtime-api-reviewer-preview',
  [ValidateSet('codebuddy', 'codex')][string]$WorkerAdapter = 'codebuddy',
  [string]$WorkerModel = '',
  [string]$Provider = 'siliconflow',
  [string]$ConnectionRef = 'trial_siliconflow',
  [string]$ReviewerModel = 'Qwen/Qwen3-Coder-30B-A3B-Instruct',
  [string]$InspectorModel = 'Qwen/Qwen3-Coder-30B-A3B-Instruct',
  [switch]$Offline
)
$ErrorActionPreference = 'Stop'

function QuoteYaml([string]$value) {
  return "'" + $value.Replace('\', '/').Replace("'", "''") + "'"
}
function FullPath([string]$value) {
  return [System.IO.Path]::GetFullPath($value).TrimEnd('\', '/')
}
function ContainsPath([string]$parent, [string]$child) {
  return $child.Equals($parent, [StringComparison]::OrdinalIgnoreCase) -or
    $child.StartsWith($parent + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}
function AssertNoReparseAncestor([string]$path) {
  $cursor = $path
  while ($cursor) {
    if (Test-Path -LiteralPath $cursor) {
      $entry = Get-Item -LiteralPath $cursor -Force
      if ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "Refusing a path through a link or junction: $cursor"
      }
    }
    $parent = [System.IO.Path]::GetDirectoryName($cursor)
    if (-not $parent -or $parent -eq $cursor) { break }
    $cursor = $parent
  }
}

$kit = (Resolve-Path -LiteralPath $KitRoot).Path
$manifest = Get-Content -LiteralPath (Join-Path $kit 'manifest.json') -Raw | ConvertFrom-Json
. (Join-Path $kit 'Assert-QualifiedHost.ps1')
$qualifiedHost = Assert-QualifiedHost -Manifest $manifest -HostRunnerRoot $HostRunnerRoot -NodePath $NodePath
Assert-QualifiedGraph -KitRoot $kit -NodePath $NodePath -Root $qualifiedHost.RunnerPath -Kind host
if ($manifest.schema_version -ne 3 -or $manifest.channel -ne 'private-api-reviewer-preview' -or
    $manifest.d2_execute_gate -ne 'NOT_CLAIMED') { throw 'Kit manifest is not an API reviewer preview.' }
$pluginFile = Join-Path $kit $manifest.plugin.file
$policyPlugin = Join-Path $kit 'install\rc31\plugin-artifacts\dsh-runtime-harness-plugin-0.1.0-rc.31.tgz'
if (-not (Test-Path -LiteralPath $policyPlugin -PathType Leaf) -or
    (Get-FileHash -LiteralPath $policyPlugin -Algorithm SHA256).Hash -ne $manifest.plugin.sha256) {
  throw 'Kit plugin does not match the locked Profile artifact.'
}
$runtimeFile = Join-Path $kit $manifest.runtime.file
foreach ($item in @(@($pluginFile, $manifest.plugin.sha256), @($runtimeFile, $manifest.runtime.sha256))) {
  if (-not (Test-Path -LiteralPath $item[0] -PathType Leaf)) { throw "Missing kit artifact: $($item[0])" }
  if ((Get-FileHash -LiteralPath $item[0] -Algorithm SHA256).Hash -ne $item[1]) {
    throw "Kit artifact hash mismatch: $($item[0])"
  }
}
$wheelRoot = Join-Path $kit 'wheels'
if (-not (Test-Path -LiteralPath $wheelRoot -PathType Container) -or
    @($manifest.python_wheels).Count -ne 7) { throw 'Kit Python wheelhouse is incomplete.' }
$wheelNames = @()
foreach ($wheel in $manifest.python_wheels) {
  if ($wheel.file -notmatch '^[A-Za-z0-9_.-]+\.whl$' -or $wheel.file.Contains('..') -or
      $wheel.sha256 -notmatch '^[A-Fa-f0-9]{64}$') { throw 'Kit Python wheel entry is invalid.' }
  $wheelPath = Join-Path $wheelRoot $wheel.file
  if (-not (Test-Path -LiteralPath $wheelPath -PathType Leaf) -or
      (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash -ne $wheel.sha256) {
    throw 'Kit Python wheel hash mismatch.'
  }
  $wheelNames += $wheel.file
}
if (@($wheelNames | Select-Object -Unique).Count -ne 7 -or
    @((Get-ChildItem -LiteralPath $wheelRoot -File).Name).Count -ne 7) {
  throw 'Kit Python wheel list is ambiguous.'
}
if ($ProfileName -notmatch '^[a-z][a-z0-9-]{2,50}$') { throw 'Invalid ProfileName.' }
if ($Provider -notin @('siliconflow', 'openrouter')) { throw 'Unsupported Provider.' }
if ($ConnectionRef -notmatch '^[A-Za-z][A-Za-z0-9_-]{0,63}$') { throw 'Invalid ConnectionRef.' }
$modelPattern = '^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,127}$'
foreach ($entry in @(@($ReviewerModel, 'ReviewerModel'), @($InspectorModel, 'InspectorModel'))) {
  if ($entry[0] -notmatch $modelPattern) { throw "Invalid $($entry[1])." }
}
if ($WorkerModel -ne '' -and $WorkerModel -notmatch $modelPattern) { throw 'Invalid WorkerModel.' }
foreach ($required in @($ConnectionPath, $PythonPath, $PnpmPath)) {
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing dependency: $required" }
}
$pnpmVersion = & $PnpmPath --version
if ($LASTEXITCODE -ne 0 -or $pnpmVersion -ne '11.25.0') { throw 'Profile installation requires pnpm 11.25.0.' }
$homePath = FullPath $HomeRoot
$runtimePath = FullPath $RuntimeRoot
$connectionFile = (Resolve-Path -LiteralPath $ConnectionPath).Path
AssertNoReparseAncestor $homePath
AssertNoReparseAncestor $runtimePath
if ((ContainsPath $homePath $runtimePath) -or (ContainsPath $runtimePath $homePath) -or
    (ContainsPath $homePath $connectionFile) -or (ContainsPath $runtimePath $connectionFile)) {
  throw 'Home, Runtime and connection file must be separate paths.'
}
$profilePath = Join-Path $homePath "profiles\$ProfileName"
$installedPlugin = Join-Path $homePath ("plugin-artifacts\" + $manifest.plugin.file)
foreach ($target in @($homePath, $runtimePath, $profilePath, $installedPlugin)) {
  if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite existing path: $target" }
}

$checkConnection = @'
import sys
from pathlib import Path
try:
    sys.path.insert(0, sys.argv[1])
    from dsh_runtime.api_agent_connections import ConnectionCatalog
    ConnectionCatalog.from_file(Path(sys.argv[2])).get(sys.argv[3], sys.argv[4])
except Exception:
    sys.exit(1)
'@
& $PythonPath -c $checkConnection $runtimeFile $connectionFile $ConnectionRef $Provider
if ($LASTEXITCODE -ne 0) { throw 'Connection configuration validation failed.' }

Expand-Archive -LiteralPath $runtimeFile -DestinationPath $runtimePath
if (-not (Test-Path -LiteralPath (Join-Path $runtimePath 'dsh_runtime\entrypoint.py'))) {
  throw 'Runtime snapshot is incomplete.'
}
$requirements = Join-Path $runtimePath 'requirements-api-agent.txt'
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
  throw 'Runtime API dependency list is missing.'
}
$venvPath = Join-Path $runtimePath '.api-agent-venv'
& $PythonPath -m venv $venvPath
if ($LASTEXITCODE -ne 0) { throw "Python venv creation failed with exit code $LASTEXITCODE" }
$effectivePython = Join-Path $venvPath 'Scripts\python.exe'
& $effectivePython -m pip install --no-index --find-links $wheelRoot --disable-pip-version-check --no-input -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Bundled API Python dependency install failed with exit code $LASTEXITCODE" }
$httpxMetadata = & $effectivePython -m pip show httpx
if ($LASTEXITCODE -ne 0 -or @($httpxMetadata | Where-Object { $_ -ceq 'Version: 0.28.1' }).Count -ne 1) {
  throw 'API Python dependency verification failed.'
}

New-Item -ItemType Directory -Path (Join-Path $homePath 'plugin-artifacts') -Force | Out-Null
New-Item -ItemType Directory -Path $profilePath -Force | Out-Null
foreach ($dir in @('audit', 'pins', 'evidence')) {
  New-Item -ItemType Directory -Path (Join-Path $homePath $dir) -Force | Out-Null
}
Copy-Item -LiteralPath $pluginFile -Destination $installedPlugin

$utf8 = [System.Text.UTF8Encoding]::new($false)
if ($manifest.plugin.file -ne 'dsh-runtime-harness-plugin-0.1.0-rc.31.tgz') { throw 'Unexpected locked plugin filename.' }
foreach ($name in @('package.json', 'pnpm-workspace.yaml', 'pnpm-lock.yaml')) {
  Copy-Item -LiteralPath (Join-Path $kit "install\rc31\profiles\template\$name") -Destination (Join-Path $profilePath $name)
}
[System.IO.File]::WriteAllText((Join-Path $profilePath 'cordis.yml'), "[]`n", $utf8)
$workerModelYaml = if ($WorkerModel -eq '') { 'null' } else { QuoteYaml $WorkerModel }
$patch = @"
- id: dsh-runtime-standalone
  config:
    runtimeRoot: $(QuoteYaml $runtimePath)
    python: $(QuoteYaml $effectivePython)
    policySource: $(QuoteYaml (Join-Path $runtimePath 'dsh_runtime\resources\selection_policy\selection-v2.json'))
    expectedPolicyHash: $($manifest.policy_hash)
    enabledWorkloads: [ repository_inspection, repository_change ]
    auditPath: $(QuoteYaml (Join-Path $homePath 'audit\governance.jsonl'))
    pinRoot: $(QuoteYaml (Join-Path $homePath 'pins'))
    evidenceRoot: $(QuoteYaml (Join-Path $homePath 'evidence'))
    apiAgentConnectionsPath: $(QuoteYaml $connectionFile)
    roleConfig:
      schema_version: 2
      roles:
        worker: { adapter: $WorkerAdapter, model: $workerModelYaml }
        reviewer:
          adapter: api_agent
          provider: $(QuoteYaml $Provider)
          model: $(QuoteYaml $ReviewerModel)
          connection_ref: $(QuoteYaml $ConnectionRef)
          max_requests: 5
          max_tool_calls: 4
          max_output_tokens: 1024
        inspector:
          adapter: api_agent
          provider: $(QuoteYaml $Provider)
          model: $(QuoteYaml $InspectorModel)
          connection_ref: $(QuoteYaml $ConnectionRef)
          max_requests: 3
          max_tool_calls: 3
          max_output_tokens: 512
"@
[System.IO.File]::WriteAllText((Join-Path $profilePath 'cordis.patch.yml'), $patch + "`n", $utf8)

$installArgs = @('install', '--frozen-lockfile', '--ignore-scripts')
if ($Offline) { $installArgs += '--offline' }
else { $installArgs += '--registry=https://registry.npmjs.org/' }
Push-Location -LiteralPath $profilePath
$previousPath = $env:PATH
try {
  $env:PATH = (Split-Path -Parent (Resolve-Path -LiteralPath $NodePath).Path) + [IO.Path]::PathSeparator + $previousPath
  & $PnpmPath @installArgs
  if ($LASTEXITCODE -ne 0) { throw "pnpm install failed with exit code $LASTEXITCODE" }
} finally { $env:PATH = $previousPath; Pop-Location }
Assert-QualifiedGraph -KitRoot $kit -NodePath $NodePath -Root $profilePath -Kind profile

Write-Output "Installed profile=$profilePath"
Write-Output "Runtime commit=$($manifest.runtime.commit)"
Write-Output "Qualified Host=$($manifest.official_host)"
Write-Output "Host runner=$($qualifiedHost.RunnerPath)"
Write-Output 'No connection file or credential was copied into the Home or kit.'
