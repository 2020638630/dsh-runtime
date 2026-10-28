param(
  [Parameter(Mandatory=$true)][string]$AssetRoot,
  [Parameter(Mandatory=$true)][string]$OutputRoot
)
$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
$assets = (Resolve-Path -LiteralPath $AssetRoot).Path
if (Test-Path -LiteralPath $OutputRoot) { throw 'Refusing to overwrite kit output.' }
$manifest = Get-Content -LiteralPath (Join-Path $assets 'manifest.json') -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne 3 -or $manifest.channel -ne 'private-api-reviewer-preview' -or
    $manifest.d2_execute_gate -ne 'NOT_CLAIMED' -or $manifest.plugin.file -ne 'dsh-runtime-harness-plugin-0.1.0-rc.31.tgz') { throw 'Unexpected input manifest.' }
foreach ($item in @($manifest.runtime) + @($manifest.python_wheels)) {
  if ($item.file -notmatch '^[A-Za-z0-9_.-]+$' -or $item.file.Contains('..') -or $item.sha256 -notmatch '^[A-Fa-f0-9]{64}$') { throw 'Invalid artifact identity.' }
}
$runtime = Join-Path $assets $manifest.runtime.file
if ((Get-FileHash -LiteralPath $runtime -Algorithm SHA256).Hash -ne $manifest.runtime.sha256) { throw 'Runtime hash mismatch.' }
foreach ($wheel in $manifest.python_wheels) {
  if ((Get-FileHash -LiteralPath (Join-Path $assets "wheels\$($wheel.file)") -Algorithm SHA256).Hash -ne $wheel.sha256) { throw 'Wheel hash mismatch.' }
}
$plugin = Join-Path $source 'install\rc31\plugin-artifacts\dsh-runtime-harness-plugin-0.1.0-rc.31.tgz'
$manifest.plugin.sha256 = (Get-FileHash -LiteralPath $plugin -Algorithm SHA256).Hash
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
foreach ($script in @('Install-Rc31Host.ps1','Install-ApiReviewerPreview.ps1','Assert-QualifiedHost.ps1','Start-QualifiedHost.ps1','check-rc31-graph.mjs')) {
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot $script) -Destination $OutputRoot
}
New-Item -ItemType Directory -Path (Join-Path $OutputRoot 'install') | Out-Null
Copy-Item -LiteralPath (Join-Path $source 'install\rc31') -Destination (Join-Path $OutputRoot 'install\rc31') -Recurse
Copy-Item -LiteralPath $plugin -Destination (Join-Path $OutputRoot $manifest.plugin.file)
Copy-Item -LiteralPath $runtime -Destination $OutputRoot
Copy-Item -LiteralPath (Join-Path $assets 'wheels') -Destination (Join-Path $OutputRoot 'wheels') -Recurse
[IO.File]::WriteAllText((Join-Path $OutputRoot 'manifest.json'), ($manifest | ConvertTo-Json -Depth 20) + "`n", [Text.UTF8Encoding]::new($false))
Write-Output "Prepared kit: $OutputRoot; Runtime commit: $($manifest.runtime.commit); no acceptance claimed."
