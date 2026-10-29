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
if ($ProfileName -notmatch '^[a-z][a-z0-9-]{2,50}$') { throw 'Invalid ProfileName.' }
$manifest = Get-Content -LiteralPath (Join-Path $kit 'manifest.json') -Raw | ConvertFrom-Json
. (Join-Path $kit 'Assert-QualifiedHost.ps1')
$qualifiedHost = Assert-QualifiedHost -Manifest $manifest -HostRunnerRoot $HostRunnerRoot -NodePath $NodePath
Assert-QualifiedGraph -KitRoot $kit -NodePath $NodePath -Root $qualifiedHost.RunnerPath -Kind host
[void](Assert-Rc31Completion -Root $qualifiedHost.RunnerPath -Kind host)
$homePath = Get-Rc31Path $HomeRoot
$profilePath = Get-Rc31Path (Join-Path $homePath "profiles\$ProfileName")
$profileRecord = Assert-Rc31Completion -Root $profilePath -Kind profile -KitRoot $kit -NodePath $NodePath -HostRunnerRoot $qualifiedHost.RunnerPath
Assert-Rc31Paths -Runner $qualifiedHost.RunnerPath -HomePath $homePath -Runtime $profileRecord.runtime -Connection $profileRecord.connection
$installedPlugin = Get-Rc31Path (Join-Path $homePath 'plugin-artifacts\dsh-runtime-harness-plugin-0.1.0-rc.31.tgz')
if ($manifest.plugin.file -ne 'dsh-runtime-harness-plugin-0.1.0-rc.31.tgz' -or
    -not (Test-Path -LiteralPath $installedPlugin -PathType Leaf) -or
    (Get-FileHash -LiteralPath $installedPlugin -Algorithm SHA256).Hash -ne $manifest.plugin.sha256) {
  throw 'Installed Profile plugin artifact does not match the kit.'
}
if (-not (Test-Path -LiteralPath (Join-Path $homePath "profiles\$ProfileName\package.json") -PathType Leaf)) {
  throw 'Installed Profile is missing.'
}
Assert-QualifiedGraph -KitRoot $kit -NodePath $NodePath -Root $profilePath -Kind profile
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
