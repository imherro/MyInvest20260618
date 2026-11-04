param(
    [string[]]$Symbols = @("000001.SZ", "510300.SH"),
    [double]$Interval = 3,
    [int]$Iterations = 0
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$symbolList = ($Symbols -join ",")

$commandArgs = @(
    "-3.11",
    "-m",
    "shortterm_trader.cli",
    "qmt-watch",
    "--symbols",
    $symbolList,
    "--interval",
    "$Interval"
)

if ($Iterations -gt 0) {
    $commandArgs += @("--iterations", "$Iterations")
}

Push-Location $RepoRoot
try {
    py @commandArgs
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
