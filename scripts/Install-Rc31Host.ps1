param(
  [Parameter(Mandatory=$true)][string]$KitRoot,
  [Parameter(Mandatory=$true)][string]$HostRunnerRoot,
  [Parameter(Mandatory=$true)][string]$NodePath,
  [Parameter(Mandatory=$true)][string]$PnpmPath,
  [switch]$Offline
)
$ErrorActionPreference = 'Stop'
$kit = (Resolve-Path -LiteralPath $KitRoot).Path
. (Join-Path $kit 'Assert-QualifiedHost.ps1')
$HostRunnerRoot = Get-Rc31Path $HostRunnerRoot
if (Test-Path -LiteralPath $HostRunnerRoot) { throw 'Refusing to overwrite Host runner.' }
if (-not (Test-Path -LiteralPath $PnpmPath -PathType Leaf)) { throw 'pnpm executable is missing.' }
$version = & $PnpmPath --version
if ($LASTEXITCODE -ne 0 -or $version -ne '11.25.0') { throw 'Host installation requires pnpm 11.25.0.' }
$nodeVersion = & $NodePath --version
if ($LASTEXITCODE -ne 0 -or $nodeVersion -cne 'v24.22.1') { throw 'Node 24.22.1 is required.' }
$oldPath = $env:PATH
try {
  $env:PATH = (Split-Path -Parent (Resolve-Path -LiteralPath $NodePath).Path) + [IO.Path]::PathSeparator + $oldPath
  New-Item -ItemType Directory -Path $HostRunnerRoot | Out-Null
  foreach ($name in @('package.json','pnpm-workspace.yaml','pnpm-lock.yaml')) {
    Copy-Item -LiteralPath (Join-Path $kit "install\rc31\host\$name") -Destination (Join-Path $HostRunnerRoot $name)
  }
  $args = @('install','--frozen-lockfile')
  if ($Offline) { $args += '--offline' } else { $args += '--registry=https://registry.npmjs.org/' }
  Push-Location -LiteralPath $HostRunnerRoot
  try { & $PnpmPath @args; if ($LASTEXITCODE -ne 0) { throw "Host installation failed: $LASTEXITCODE" } } finally { Pop-Location }
  . (Join-Path $kit 'Assert-QualifiedHost.ps1')
  $manifest = Get-Content -LiteralPath (Join-Path $kit 'manifest.json') -Raw | ConvertFrom-Json
  $hostInfo = Assert-QualifiedHost -Manifest $manifest -HostRunnerRoot $HostRunnerRoot -NodePath $NodePath
  Assert-QualifiedGraph -KitRoot $kit -NodePath $NodePath -Root $hostInfo.RunnerPath -Kind host
  Write-Rc31Completion -Root $hostInfo.RunnerPath -Kind host
  Write-Output "Installed Host runner=$($hostInfo.RunnerPath)"
} finally { $env:PATH = $oldPath }
