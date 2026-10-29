function Get-HostArtifactDigest([string]$PackageRoot) {
  # Windows PowerShell 5.1 uses .NET Framework, which has neither
  # Path.GetRelativePath nor SHA256.HashData/Convert.ToHexString.
  $rootPrefix = [System.IO.Path]::GetFullPath($PackageRoot).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
  $entries = @()
  foreach ($directory in @('lib', 'dist')) {
    $path = Join-Path $PackageRoot $directory
    if (Test-Path -LiteralPath $path -PathType Container) {
      $entries += Get-ChildItem -LiteralPath $path -Recurse -File | Where-Object {
        $_.Name -match '\.(?:js|mjs|cjs|d\.ts|json)$'
      }
    }
  }
  $pathsByRelative = @{}
  foreach ($entry in $entries) {
    $fullPath = [System.IO.Path]::GetFullPath($entry.FullName)
    if (-not $fullPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
      throw 'Official Host artifact path escapes package root.'
    }
    $relative = $fullPath.Substring($rootPrefix.Length).Replace('\', '/')
    if ($pathsByRelative.ContainsKey($relative)) { throw 'Duplicate official Host artifact path.' }
    $pathsByRelative[$relative] = $fullPath
  }
  # Sort-Object compares punctuation differently in Windows PowerShell 5.1.
  $relativePaths = [string[]]@($pathsByRelative.Keys)
  [Array]::Sort($relativePaths, [StringComparer]::Ordinal)
  $payload = [System.Text.StringBuilder]::new()
  foreach ($relative in $relativePaths) {
    $fileHash = (Get-FileHash -LiteralPath $pathsByRelative[$relative] -Algorithm SHA256).Hash.ToLowerInvariant()
    [void]$payload.Append($relative).Append([char]0).Append($fileHash).Append([char]0)
  }
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload.ToString())
  $hasher = [System.Security.Cryptography.SHA256]::Create()
  try {
    return [BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace('-', '')
  } finally {
    $hasher.Dispose()
  }
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
  if ($nodeVersionText -cne 'v24.22.1') {
    throw 'Official Host requires Node 24.22.1.'
  }
  $runnerPath = Get-Rc31Path $HostRunnerRoot
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

function Assert-QualifiedGraph {
  param([string]$KitRoot, [string]$NodePath, [string]$Root, [ValidateSet('host','profile')][string]$Kind)
  $template = if ($Kind -eq 'host') { 'install\rc31\host' } else { 'install\rc31\profiles\template' }
  & $NodePath (Join-Path $KitRoot 'check-rc31-graph.mjs') (Join-Path $KitRoot $template) $Root $Kind
  if ($LASTEXITCODE -ne 0) { throw "$Kind dependency graph is not qualified." }
}

# Paths through reparse points are rejected, including ancestors of paths not yet created.
function Get-Rc31Path([string]$Path) {
  if (-not [IO.Path]::IsPathRooted($Path)) { throw 'Installation paths must be absolute.' }
  $full = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
  if (-not $full) { throw 'A volume root is not an installation path.' }
  $cursor = $full
  while ($cursor) {
    if (Test-Path -LiteralPath $cursor) {
      if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Refusing a path through a link or junction: $cursor"
      }
    }
    $parent = [IO.Path]::GetDirectoryName($cursor)
    if (-not $parent -or $parent -eq $cursor) { break }
    $cursor = $parent
  }
  return $full
}
function Test-Rc31Contains([string]$Parent, [string]$Child) {
  return $Child.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or
    $Child.StartsWith($Parent + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}
function Assert-Rc31Paths([string]$Runner, [string]$HomePath, [string]$Runtime, [string]$Connection) {
  $roots = @((Get-Rc31Path $Runner), (Get-Rc31Path $HomePath), (Get-Rc31Path $Runtime))
  $connectionPath = Get-Rc31Path $Connection
  for ($i = 0; $i -lt $roots.Count; $i++) {
    for ($j = $i + 1; $j -lt $roots.Count; $j++) {
      if ((Test-Rc31Contains $roots[$i] $roots[$j]) -or (Test-Rc31Contains $roots[$j] $roots[$i])) {
        throw 'Host runner, Home and Runtime must be separate paths.'
      }
    }
    if (Test-Rc31Contains $roots[$i] $connectionPath) { throw 'Connection must be outside all installation roots.' }
  }
}
function Get-Rc31Identity([string]$Root, [string]$Kind) {
  $identity = [ordered]@{ schema = 1; kind = $Kind; root = (Get-Rc31Path $Root) }
  foreach ($name in @('package.json', 'pnpm-workspace.yaml', 'pnpm-lock.yaml')) {
    $identity[$name] = (Get-FileHash -LiteralPath (Join-Path $Root $name) -Algorithm SHA256).Hash
  }
  if ($Kind -eq 'profile') {
    foreach ($name in @('cordis.patch.yml')) {
      $identity[$name] = (Get-FileHash -LiteralPath (Join-Path $Root $name) -Algorithm SHA256).Hash
    }
  }
  return $identity
}
function Get-Rc31ProfileDigest([string]$Root, [string]$KitRoot, [string]$NodePath, [string]$HostRunnerRoot) {
  $patch = Get-Rc31Path (Join-Path $Root 'cordis.patch.yml')
  $digest = & $NodePath (Join-Path $KitRoot 'check-rc31-profile.mjs') $HostRunnerRoot $patch
  if ($LASTEXITCODE -ne 0 -or $digest -cnotmatch '^[A-F0-9]{64}$') { throw 'Profile patch structural validation failed.' }
  return $digest
}
function Write-Rc31Completion([string]$Root, [string]$Kind, [string]$Runtime = '', [string]$Connection = '', [string]$KitRoot = '', [string]$NodePath = '', [string]$HostRunnerRoot = '') {
  $record = Get-Rc31Identity $Root $Kind
  if ($Kind -eq 'profile') {
    $record.schema = 2
    $record['cordis.patch.yml'] = Get-Rc31ProfileDigest $Root $KitRoot $NodePath $HostRunnerRoot
    $record['runtime'] = $Runtime; $record['connection'] = $Connection
  }
  $path = Join-Path $Root '.rc31-install-complete.json'
  if (Test-Path -LiteralPath $path) { throw 'Completion record already exists.' }
  [IO.File]::WriteAllText($path, (($record | ConvertTo-Json) + "`n"), [Text.UTF8Encoding]::new($false))
}
function Assert-Rc31Completion([string]$Root, [string]$Kind, [string]$KitRoot = '', [string]$NodePath = '', [string]$HostRunnerRoot = '') {
  $path = Join-Path $Root '.rc31-install-complete.json'
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "$Kind installation completion record is missing." }
  [void](Get-Rc31Path $path)
  try { $record = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json } catch { throw "$Kind installation completion record is invalid." }
  $expected = Get-Rc31Identity $Root $Kind
  if ($Kind -eq 'profile' -and $record.schema -eq 2) {
    $expected.schema = 2
    $expected['cordis.patch.yml'] = Get-Rc31ProfileDigest $Root $KitRoot $NodePath $HostRunnerRoot
  }
  foreach ($key in $expected.Keys) {
    if ($record.$key -cne $expected[$key]) { throw "$Kind installation completion record does not match $key." }
  }
  if ($Kind -eq 'profile' -and (-not $record.runtime -or -not $record.connection)) { throw 'Profile completion paths are missing.' }
  return $record
}
