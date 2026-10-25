param(
  [Parameter(Mandatory=$true)][string]$KitRoot,
  [Parameter(Mandatory=$true)][string]$QualifiedRunnerRoot,
  [Parameter(Mandatory=$true)][string]$QualifiedNodePath,
  [string]$OldNodePath = ''
)
$ErrorActionPreference = 'Stop'
$kit = (Resolve-Path -LiteralPath $KitRoot).Path
$installer = Join-Path $kit 'Install-ApiReviewerPreview.ps1'
$manifest = Get-Content -LiteralPath (Join-Path $kit 'manifest.json') -Raw | ConvertFrom-Json
if ($manifest.official_host -notmatch '^@deepseek-ai/dsh@(?<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$') {
  throw 'The test kit has no exact official Host version.'
}
$expectedVersion = $Matches.version
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\', '/')
$fixture = [System.IO.Path]::GetFullPath((Join-Path $temporaryRoot ("dsh-host-preflight-" + [Guid]::NewGuid().ToString('N'))))
if (-not $fixture.StartsWith($temporaryRoot + [System.IO.Path]::DirectorySeparatorChar,
    [StringComparison]::OrdinalIgnoreCase)) { throw 'Temporary fixture escaped the intended root.' }

function Invoke-PreflightCase([string]$name, [string]$runner, [string]$node,
    [string]$expectedError) {
  $probeHome = Join-Path $fixture "$name-home"
  $probeRuntime = Join-Path $fixture "$name-runtime"
  $message = ''
  try {
    & $installer -KitRoot $kit -HomeRoot $probeHome -RuntimeRoot $probeRuntime `
      -HostRunnerRoot $runner -NodePath $node -ConnectionPath (Join-Path $fixture 'absent-connection.json') `
      -PythonPath (Join-Path $fixture 'absent-python.exe') -PnpmPath (Join-Path $fixture 'absent-pnpm.cmd') | Out-Null
  } catch { $message = $_.Exception.Message }
  if ($message -notlike "*$expectedError*" -or (Test-Path -LiteralPath $probeHome) -or
      (Test-Path -LiteralPath $probeRuntime)) {
    throw "$name failed its prewrite assertion: $message"
  }
  Write-Output "$name=PASS"
}

function New-FakeRunner([string]$name, [string]$runnerJson, [string]$hostJson,
    [bool]$includeBin) {
  $runner = Join-Path $fixture $name
  $packageRoot = Join-Path $runner 'node_modules\@deepseek-ai\dsh'
  New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
  [System.IO.File]::WriteAllText((Join-Path $runner 'package.json'), $runnerJson)
  [System.IO.File]::WriteAllText((Join-Path $packageRoot 'package.json'), $hostJson)
  if ($includeBin) {
    New-Item -ItemType Directory -Path (Join-Path $packageRoot 'lib') -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $packageRoot 'lib\bin.js'), '// fixture')
  }
  return $runner
}

New-Item -ItemType Directory -Path $fixture -Force | Out-Null
try {
  $runnerJson = '{"dependencies":{"@deepseek-ai/dsh":"' + $expectedVersion + '"}}'
  $qualifiedPackage = Join-Path $QualifiedRunnerRoot 'node_modules\@deepseek-ai\dsh\package.json'
  $hostJson = Get-Content -LiteralPath $qualifiedPackage -Raw
  $wrongVersion = New-FakeRunner 'wrong-version' $runnerJson '{"name":"@deepseek-ai/dsh","version":"0.3.0"}' $true
  Invoke-PreflightCase 'wrong-version' $wrongVersion $QualifiedNodePath 'not the qualified package'
  $malformed = New-FakeRunner 'malformed' '{broken' $hostJson $true
  Invoke-PreflightCase 'malformed' $malformed $QualifiedNodePath 'metadata is invalid'
  $missingBin = New-FakeRunner 'missing-bin' $runnerJson $hostJson $false
  Invoke-PreflightCase 'missing-bin' $missingBin $QualifiedNodePath 'runner is incomplete'
  $tampered = New-FakeRunner 'same-version-tampered-code' $runnerJson $hostJson $true
  Invoke-PreflightCase 'same-version-tampered-code' $tampered $QualifiedNodePath 'not the qualified package'
  if ($OldNodePath -and (Test-Path -LiteralPath $OldNodePath -PathType Leaf)) {
    Invoke-PreflightCase 'old-node' $QualifiedRunnerRoot $OldNodePath 'requires Node 24.19.0'
  }
  Invoke-PreflightCase 'qualified-runner' $QualifiedRunnerRoot $QualifiedNodePath 'Missing dependency'
} finally {
  $resolved = [System.IO.Path]::GetFullPath($fixture)
  if ($resolved.StartsWith($temporaryRoot + [System.IO.Path]::DirectorySeparatorChar,
      [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolved)) {
    Remove-Item -LiteralPath $resolved -Recurse -Force
  }
}
