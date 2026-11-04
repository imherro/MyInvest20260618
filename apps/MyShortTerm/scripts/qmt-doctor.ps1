param(
    [string[]]$Symbols = @("000001.SZ", "510300.SH")
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $RepoRoot
try {
    $symbolList = ($Symbols -join ",")
    py -3.11 -m shortterm_trader.cli qmt-doctor --symbols $symbolList
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
