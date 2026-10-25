function Get-HostArtifactDigest([string]$PackageRoot) {
  $entries = @()
  foreach ($directory in @('lib', 'dist')) {
    $path = Join-Path $PackageRoot $directory
    if (Test-Path -LiteralPath $path -PathType Container) {
      $entries += Get-ChildItem -LiteralPath $path -Recurse -File | Where-Object {
        $_.Name -match '\.(?:js|mjs|cjs|d\.ts|json)$'
      }
    }
  }
  $payload = [System.Text.StringBuilder]::new()
  foreach ($entry in @($entries | Sort-Object { [System.IO.Path]::GetRelativePath($PackageRoot, $_.FullName).Replace('\', '/') })) {
    $relative = [System.IO.Path]::GetRelativePath($PackageRoot, $entry.FullName).Replace('\', '/')
    $fileHash = (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    [void]$payload.Append($relative).Append([char]0).Append($fileHash).Append([char]0)
  }
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload.ToString())
  return [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($bytes))
}

function Assert-QualifiedHost {
  param(
    [Parameter(Mandatory=$true)]$Manifest,
    [Parameter(Mandatory=$true)][string]$HostRunnerRoot,
    [Parameter(Mandatory=$true)][string]$NodePath
  )
  if ($Manifest.official_host -notmatch '^@deepseek-ai/dsh@(?<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)$') {
    throw 'Kit Host compatibility identity is invalid.'
  }
  $expectedVersion = $Matches.version
  if ($Manifest.official_host_package_sha256 -notmatch '^[A-Fa-f0-9]{64}$' -or
      $Manifest.official_host_artifacts_sha256 -notmatch '^[A-Fa-f0-9]{64}$') {
    throw 'Kit Host compatibility identity is invalid.'
  }
  if (-not (Test-Path -LiteralPath $NodePath -PathType Leaf)) { throw 'Node executable is missing.' }
  $nodeVersionText = & $NodePath --version
  $nodeExit = $LASTEXITCODE
  if ($nodeExit -ne 0 -or $nodeVersionText -notmatch '^v\d+\.\d+\.\d+$') {
    throw 'Node version could not be verified.'
  }
  if ([Version]($nodeVersionText.Substring(1)) -lt [Version]'24.19.0') {
    throw 'Official Host requires Node 24.19.0 or newer.'
  }
  $runnerPath = (Resolve-Path -LiteralPath $HostRunnerRoot).Path
  $runnerPackage = Join-Path $runnerPath 'package.json'
  $hostPackage = Join-Path $runnerPath 'node_modules\@deepseek-ai\dsh\package.json'
  $hostEntry = Join-Path $runnerPath 'node_modules\@deepseek-ai\dsh\lib\bin.js'
  if (-not (Test-Path -LiteralPath $runnerPackage -PathType Leaf) -or
      -not (Test-Path -LiteralPath $hostPackage -PathType Leaf) -or
      -not (Test-Path -LiteralPath $hostEntry -PathType Leaf)) {
    throw 'Official Host runner is incomplete.'
  }
  try {
    $runnerInfo = Get-Content -LiteralPath $runnerPackage -Raw | ConvertFrom-Json
    $hostInfo = Get-Content -LiteralPath $hostPackage -Raw | ConvertFrom-Json
  } catch { throw 'Official Host package metadata is invalid.' }
  if ($runnerInfo.dependencies.'@deepseek-ai/dsh' -ne $expectedVersion -or
      $hostInfo.name -ne '@deepseek-ai/dsh' -or $hostInfo.version -ne $expectedVersion -or
      (Get-FileHash -LiteralPath $hostPackage -Algorithm SHA256).Hash -ne $Manifest.official_host_package_sha256 -or
      (Get-HostArtifactDigest (Split-Path -Parent $hostPackage)) -ne $Manifest.official_host_artifacts_sha256) {
    throw 'Official Host is not the qualified package for this kit.'
  }
  return [pscustomobject]@{
    RunnerPath = $runnerPath
    EntryPath = $hostEntry
    NodePath = (Resolve-Path -LiteralPath $NodePath).Path
    Version = $hostInfo.version
  }
}
