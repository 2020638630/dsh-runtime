param([Parameter(Mandatory=$true)][string]$KitRoot, [Parameter(Mandatory=$true)][string]$NodePath,
      [Parameter(Mandatory=$true)][string]$PnpmPath, [Parameter(Mandatory=$true)][string]$PythonPath,
      [Parameter(Mandatory=$true)][string]$FixtureRoot)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $FixtureRoot) { throw 'Fixture path already exists.' }
New-Item -ItemType Directory -Path $FixtureRoot | Out-Null
$fixture = (Resolve-Path -LiteralPath $FixtureRoot).Path
$kit = (Resolve-Path -LiteralPath $KitRoot).Path
$connection = Join-Path $fixture 'connection.json'
[IO.File]::WriteAllText($connection, '{"schema_version":1,"connections":{"trial_siliconflow":{"provider":"siliconflow","base_url":"https://api.siliconflow.cn/v1","api_key":"synthetic-test-key"}}}')
$failurePnpm = Join-Path $fixture 'fail-after-install.cmd'
[IO.File]::WriteAllText($failurePnpm, "@echo off`r`nif `"%1`"==`"--version`" (call `"$PnpmPath`" --version & exit /b %errorlevel%)`r`ncall `"$PnpmPath`" %*`r`nif errorlevel 1 exit /b %errorlevel%`r`nexit /b 17`r`n")
$installer = Join-Path $kit 'Install-ApiReviewerPreview.ps1'
$start = Join-Path $kit 'Start-QualifiedHost.ps1'
$hostInstaller = Join-Path $kit 'Install-Rc31Host.ps1'
function Expect-Failure([scriptblock]$Action, [string]$Text) {
  $message = ''
  try { & $Action | Out-Null } catch { $message = $_.Exception.Message }
  if ($message -notlike "*$Text*") { throw "Expected '$Text', got '$message'" }
}
$failed = Join-Path $fixture 'failed-host'
Expect-Failure { & $hostInstaller -KitRoot $kit -HostRunnerRoot $failed -NodePath $NodePath -PnpmPath $failurePnpm } 'Host installation failed'
if (-not (Test-Path (Join-Path $failed 'node_modules\@deepseek-ai\dsh\lib\bin.js')) -or (Test-Path (Join-Path $failed '.rc31-install-complete.json'))) { throw 'Failure did not leave extracted packages without a record.' }
$failedHome = Join-Path $fixture 'failed-home'; $failedRuntime = Join-Path $fixture 'failed-runtime'
Expect-Failure { & $installer -KitRoot $kit -HostRunnerRoot $failed -HomeRoot $failedHome -RuntimeRoot $failedRuntime -ConnectionPath $connection -PythonPath $PythonPath -PnpmPath $PnpmPath -NodePath $NodePath } 'completion record is missing'
Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $failed -HomeRoot $failedHome -NodePath $NodePath -DumpConfig } 'completion record is missing'
if ((Test-Path $failedHome) -or (Test-Path $failedRuntime)) { throw 'Failed Host caused writes.' }
$runner = Join-Path $fixture 'host'; $homeDir = Join-Path $fixture 'home'; $runtime = Join-Path $fixture 'runtime'
& $hostInstaller -KitRoot $kit -HostRunnerRoot $runner -NodePath $NodePath -PnpmPath $PnpmPath
Expect-Failure { & $installer -KitRoot $kit -HostRunnerRoot $runner -HomeRoot (Join-Path $runner 'nested') -RuntimeRoot $runtime -ConnectionPath $connection -PythonPath $PythonPath -PnpmPath $PnpmPath -NodePath $NodePath } 'must be separate paths'
$insideConnection = Join-Path $runner 'fake-connection.json'
Copy-Item $connection $insideConnection
Expect-Failure { & $installer -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -RuntimeRoot $runtime -ConnectionPath $insideConnection -PythonPath $PythonPath -PnpmPath $PnpmPath -NodePath $NodePath } 'Connection must be outside'
$alias = Join-Path $fixture 'runner-alias'
New-Item -ItemType Junction -Path $alias -Target $runner | Out-Null
Expect-Failure { & $installer -KitRoot $kit -HostRunnerRoot $alias -HomeRoot $homeDir -RuntimeRoot $runtime -ConnectionPath $connection -PythonPath $PythonPath -PnpmPath $PnpmPath -NodePath $NodePath } 'link or junction'
if ((Test-Path $homeDir) -or (Test-Path $runtime)) { throw 'Path rejection caused writes.' }
& $installer -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -RuntimeRoot $runtime -ConnectionPath $connection -PythonPath $PythonPath -PnpmPath $PnpmPath -NodePath $NodePath
& $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Dump config failed: $LASTEXITCODE" }
$hostRecord = Join-Path $runner '.rc31-install-complete.json'
$profileRecord = Join-Path $homeDir 'profiles\runtime-api-reviewer-preview\.rc31-install-complete.json'
$original = [IO.File]::ReadAllText($hostRecord)
try {
  $changed = $original | ConvertFrom-Json
  $changed.root = Join-Path $fixture 'different-host'
  [IO.File]::WriteAllText($hostRecord, ($changed | ConvertTo-Json))
  Expect-Failure { & $installer -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $failedHome -RuntimeRoot $failedRuntime -ConnectionPath $connection -PythonPath $PythonPath -PnpmPath $PnpmPath -NodePath $NodePath } 'completion record does not match root'
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'completion record does not match root'
} finally { [IO.File]::WriteAllText($hostRecord, $original) }
$originalProfile = [IO.File]::ReadAllText($profileRecord)
try {
  $changed = $originalProfile | ConvertFrom-Json
  $changed.'cordis.patch.yml' = 'invalid'
  [IO.File]::WriteAllText($profileRecord, ($changed | ConvertTo-Json))
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'completion record does not match cordis.patch.yml'
} finally { [IO.File]::WriteAllText($profileRecord, $originalProfile) }
& $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Second dump config failed: $LASTEXITCODE" }
Write-Output "Completion and path boundary regression PASS; preserved fixture=$fixture"

