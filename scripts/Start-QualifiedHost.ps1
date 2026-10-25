param(
  [Parameter(Mandatory=$true)][string]$KitRoot,
  [Parameter(Mandatory=$true)][string]$HomeRoot,
  [Parameter(Mandatory=$true)][string]$HostRunnerRoot,
  [Parameter(Mandatory=$true)][string]$NodePath,
  [string]$ProfileName = 'runtime-api-reviewer-preview',
  [switch]$DumpConfig,
  [ValidateRange(0,65535)][int]$Port = 0
)
$ErrorActionPreference = 'Stop'
$kit = (Resolve-Path -LiteralPath $KitRoot).Path
$manifest = Get-Content -LiteralPath (Join-Path $kit 'manifest.json') -Raw | ConvertFrom-Json
. (Join-Path $kit 'Assert-QualifiedHost.ps1')
$qualifiedHost = Assert-QualifiedHost -Manifest $manifest -HostRunnerRoot $HostRunnerRoot -NodePath $NodePath
$homePath = (Resolve-Path -LiteralPath $HomeRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $homePath "profiles\$ProfileName\package.json") -PathType Leaf)) {
  throw 'Installed Profile is missing.'
}
$arguments = @('--profile', $ProfileName)
if ($DumpConfig) { $arguments += '--dump-config' }
else { $arguments += @('--no-open', '--port', "$Port") }
$previousHome = $env:DSH_HOME
try {
  $env:DSH_HOME = $homePath
  & $qualifiedHost.NodePath $qualifiedHost.EntryPath @arguments
  $status = $LASTEXITCODE
} finally {
  $env:DSH_HOME = $previousHome
}
exit $status
