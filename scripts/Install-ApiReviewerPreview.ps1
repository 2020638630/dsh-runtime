param(
  [Parameter(Mandatory=$true)][string]$KitRoot,
  [Parameter(Mandatory=$true)][string]$HomeRoot,
  [Parameter(Mandatory=$true)][string]$RuntimeRoot,
  [Parameter(Mandatory=$true)][string]$ConnectionPath,
  [Parameter(Mandatory=$true)][string]$PythonPath,
  [Parameter(Mandatory=$true)][string]$PnpmPath,
  [string]$ProfileName = 'runtime-api-reviewer-preview',
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
if ($manifest.schema_version -ne 2 -or $manifest.channel -ne 'private-api-reviewer-preview' -or
    $manifest.d2_execute_gate -ne 'NOT_CLAIMED') { throw 'Kit manifest is not an API reviewer preview.' }
$pluginFile = Join-Path $kit $manifest.plugin.file
$runtimeFile = Join-Path $kit $manifest.runtime.file
foreach ($item in @(@($pluginFile, $manifest.plugin.sha256), @($runtimeFile, $manifest.runtime.sha256))) {
  if (-not (Test-Path -LiteralPath $item[0] -PathType Leaf)) { throw "Missing kit artifact: $($item[0])" }
  if ((Get-FileHash -LiteralPath $item[0] -Algorithm SHA256).Hash -ne $item[1]) {
    throw "Kit artifact hash mismatch: $($item[0])"
  }
}
if ($ProfileName -notmatch '^[a-z][a-z0-9-]{2,50}$') { throw 'Invalid ProfileName.' }
foreach ($entry in @(@($Provider, 'Provider'), @($ConnectionRef, 'ConnectionRef'))) {
  if ($entry[0] -notmatch '^[A-Za-z][A-Za-z0-9_-]{1,63}$') { throw "Invalid $($entry[1])." }
}
foreach ($entry in @(@($ReviewerModel, 'ReviewerModel'), @($InspectorModel, 'InspectorModel'))) {
  if ($entry[0] -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]{1,127}$') { throw "Invalid $($entry[1])." }
}
foreach ($required in @($ConnectionPath, $PythonPath, $PnpmPath)) {
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing dependency: $required" }
}
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

New-Item -ItemType Directory -Path (Join-Path $homePath 'plugin-artifacts') -Force | Out-Null
New-Item -ItemType Directory -Path $profilePath -Force | Out-Null
foreach ($dir in @('audit', 'pins', 'evidence')) {
  New-Item -ItemType Directory -Path (Join-Path $homePath $dir) -Force | Out-Null
}
Copy-Item -LiteralPath $pluginFile -Destination $installedPlugin
Expand-Archive -LiteralPath $runtimeFile -DestinationPath $runtimePath
if (-not (Test-Path -LiteralPath (Join-Path $runtimePath 'dsh_runtime\entrypoint.py'))) {
  throw 'Runtime snapshot is incomplete.'
}

$profilePackage = [ordered]@{
  name = "dsh-profile-$ProfileName"
  private = $true
  dependencies = @{ '@dsh-runtime/harness-plugin' = "file:../../plugin-artifacts/$($manifest.plugin.file)" }
  dsh = @{ profile = @{ bundles = @('@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app', '@dsh-runtime/harness-plugin') } }
}
$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText((Join-Path $profilePath 'package.json'), ($profilePackage | ConvertTo-Json -Depth 8) + "`n", $utf8)
[System.IO.File]::WriteAllText((Join-Path $profilePath 'cordis.yml'), "[]`n", $utf8)
$patch = @"
- id: dsh-runtime-standalone
  config:
    runtimeRoot: $(QuoteYaml $runtimePath)
    python: $(QuoteYaml (FullPath $PythonPath))
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
        worker: { adapter: codebuddy, model: null }
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

$installArgs = @('install', '--ignore-scripts')
if ($Offline) { $installArgs += '--offline' }
Push-Location -LiteralPath $profilePath
try {
  & $PnpmPath @installArgs
  if ($LASTEXITCODE -ne 0) { throw "pnpm install failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }

Write-Output "Installed profile=$profilePath"
Write-Output "Runtime commit=$($manifest.runtime.commit)"
Write-Output 'No connection file or credential was copied into the Home or kit.'
