[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$originals = Split-Path -Parent $root
$registry = Get-Content (Join-Path $root 'subsystems.json') -Raw | ConvertFrom-Json
$planned = @()
foreach ($system in $registry.systems) {
    $app = Join-Path (Join-Path $root 'apps') $system.directory
    $legacy = Join-Path $originals $system.directory
    foreach ($relative in $system.runtime_paths) {
        $target = Join-Path $legacy $relative
        $link = Join-Path $app $relative
        if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw "Missing original data: $target" }
        $item = Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue
        if ($item) {
            if ($item.LinkType -ne 'Junction' -or [IO.Path]::GetFullPath([string]$item.Target) -ne [IO.Path]::GetFullPath($target)) {
                throw "Refusing to replace existing content or unexpected link: $link"
            }
        } else {
            $planned += [pscustomobject]@{system=$system.id; link=$link; target=$target}
        }
    }
}
# Preflight every binding before creating any. Never move/delete original data.
foreach ($binding in $planned) {
    if ($Apply) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $binding.link) | Out-Null
        New-Item -ItemType Junction -Path $binding.link -Target $binding.target | Out-Null
    }
    $binding
}
Write-Host "Bindings planned: $($planned.Count); applied: $([bool]$Apply)"
