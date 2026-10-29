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
$patchPath = Join-Path $homeDir 'profiles\runtime-api-reviewer-preview\cordis.patch.yml'
$originalPatch = [IO.File]::ReadAllText($patchPath)
[IO.File]::WriteAllText((Join-Path $fixture 'patch-installed.yml'), $originalPatch)
try {
  $model = "`n- id: agent-default-model`n  name: '@deepseek-ai/dsh-agent-default-model'`n  config: { provider: deepseek-official, model: deepseek-flash, reasoningEffort: off }`n"
  $modelUpdated = "`n- id: agent-default-model`n  name: '@deepseek-ai/dsh-agent-default-model'`n  config: { provider: example, model: other }`n"
  $welcomeTest = "`n- id: ui-settings-general`n  name: '@deepseek-ai/dsh-client-ui-settings-general'`n  config: { welcomeNoticeVersion: '2026-09-28.1' }`n"
  foreach ($suffix in @('', $model, $modelUpdated, $welcomeTest, ($welcomeTest + $model), ($model + $welcomeTest))) {
    [IO.File]::WriteAllText($patchPath, $originalPatch + $suffix)
    & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Schema 3 mutable settings failed.' }
  }
  foreach ($suffix in @(($model + $model), ($model + "`n- id: unknown`n  config: {}`n"), ($model.Replace('model: deepseek-flash', 'model: 42')), ($model.Replace('config: {', "insert: true`n  config: {")), ($model.Replace('reasoningEffort: off', 'reasoningEffort: off, unexpected: true')))) {
    [IO.File]::WriteAllText($patchPath, $originalPatch + $suffix)
    Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'structural validation failed'
  }
  [IO.File]::WriteAllText($patchPath, $originalPatch)
  $homePatch = Join-Path $homeDir 'cordis.patch.yml'
  try {
    [IO.File]::WriteAllText($homePatch, "[]`n")
    & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Empty Home patch rejected.' }
    [IO.File]::WriteAllText($homePatch, "- id: dsh-runtime-standalone`n  config: { enabled: false }`n")
    Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'Home patch must be absent or an empty list'
  } finally { Remove-Item -LiteralPath $homePatch -ErrorAction SilentlyContinue }
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig -UnapprovedOverlay foo } 'parameter'
  $v2 = $originalProfile | ConvertFrom-Json
  $v2.schema = 2
  $v2.'cordis.patch.yml' = & $NodePath (Join-Path $kit 'check-rc31-profile.mjs') $runner $patchPath 2
  [IO.File]::WriteAllText($profileRecord, ($v2 | ConvertTo-Json))
  [IO.File]::WriteAllText($patchPath, $originalPatch + $welcomeTest)
  & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Schema 2 welcome failed.' }
  [IO.File]::WriteAllText($patchPath, $originalPatch + $model)
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'structural validation failed'
  $v2.schema = 99
  [IO.File]::WriteAllText($profileRecord, ($v2 | ConvertTo-Json))
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'Unknown completion record schema'
} finally { [IO.File]::WriteAllText($patchPath, $originalPatch); [IO.File]::WriteAllText($profileRecord, $originalProfile) }
try {
  & $NodePath (Join-Path $PSScriptRoot 'test-rc31-welcome-host.mjs') $kit $runner $homeDir $NodePath
  if ($LASTEXITCODE -ne 0) { throw 'Real Host welcome write failed.' }
  Copy-Item -LiteralPath $patchPath -Destination (Join-Path $fixture 'patch-after-host.yml')
  & $NodePath (Join-Path $PSScriptRoot 'test-rc31-welcome-host.mjs') $kit $runner $homeDir $NodePath restart
  if ($LASTEXITCODE -ne 0) { throw 'Host server restart after welcome write failed.' }
  & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Restart after Host welcome write failed.' }
  $welcome = "`n- id: ui-settings-general`n  name: '@deepseek-ai/dsh-client-ui-settings-general'`n  config:`n    welcomeNoticeVersion: 2026-09-28.1`n"
  [IO.File]::WriteAllText($patchPath, $originalPatch + $welcome)
  & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Welcome state restart failed.' }
  $reordered = "`n- name: '@deepseek-ai/dsh-client-ui-settings-general'`n  config: { welcomeNoticeVersion: '2026-09-28.1' }`n  id: ui-settings-general`n"
  $lines = $originalPatch -split "`n"
  $runtimeLine = [Array]::FindIndex($lines, [Predicate[string]]{ param($line) $line.TrimStart().StartsWith('runtimeRoot:') })
  $pythonLine = [Array]::FindIndex($lines, [Predicate[string]]{ param($line) $line.TrimStart().StartsWith('python:') })
  if ($runtimeLine -lt 0 -or $pythonLine -lt 0) { throw 'Expected installed config keys missing.' }
  $swap = $lines[$runtimeLine]; $lines[$runtimeLine] = $lines[$pythonLine]; $lines[$pythonLine] = $swap
  [IO.File]::WriteAllText($patchPath, ($lines -join "`n") + $reordered)
  & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Reordered YAML restart failed.' }
  foreach ($pair in @(
    @('runtimeRoot:', 'runtimeRoot: altered #'),
    @('apiAgentConnectionsPath:', 'apiAgentConnectionsPath: altered #'),
    @('expectedPolicyHash:', 'expectedPolicyHash: altered #'),
    @('max_requests: 5', 'max_requests: 6')
  )) {
    [IO.File]::WriteAllText($patchPath, $originalPatch.Replace($pair[0], $pair[1]) + $welcome)
    Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'completion record does not match cordis.patch.yml'
  }
  [IO.File]::WriteAllText($patchPath, $originalPatch + $welcome + '    otherSetting: true' + "`n")
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'structural validation failed'
  [IO.File]::WriteAllText($patchPath, $originalPatch + $welcome + '    welcomeNoticeVersion: duplicate' + "`n")
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'structural validation failed'
  [IO.File]::WriteAllText($patchPath, '- invalid: [' + "`n")
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'structural validation failed'
  [IO.File]::WriteAllText($patchPath, $originalPatch)
  $legacy = $originalProfile | ConvertFrom-Json
  $legacy.schema = 1
  $legacy.'cordis.patch.yml' = (Get-FileHash -LiteralPath $patchPath -Algorithm SHA256).Hash
  [IO.File]::WriteAllText($profileRecord, ($legacy | ConvertTo-Json))
  & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Unchanged legacy record failed.' }
  [IO.File]::WriteAllText($patchPath, $originalPatch + $welcome)
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'completion record does not match cordis.patch.yml'
  [IO.File]::WriteAllText($patchPath, $originalPatch)
  Remove-Item -LiteralPath $profileRecord
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'completion record is missing'
} finally { [IO.File]::WriteAllText($patchPath, $originalPatch); [IO.File]::WriteAllText($profileRecord, $originalProfile) }
try {
  $changed = $originalProfile | ConvertFrom-Json
  $changed.'cordis.patch.yml' = 'invalid'
  [IO.File]::WriteAllText($profileRecord, ($changed | ConvertTo-Json))
  Expect-Failure { & $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig } 'completion record does not match cordis.patch.yml'
} finally { [IO.File]::WriteAllText($profileRecord, $originalProfile) }
& $start -KitRoot $kit -HostRunnerRoot $runner -HomeRoot $homeDir -NodePath $NodePath -DumpConfig | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Second dump config failed: $LASTEXITCODE" }
Write-Output "Completion and path boundary regression PASS; preserved fixture=$fixture"
