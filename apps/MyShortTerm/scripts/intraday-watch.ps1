param(
    [double]$Interval = 3,
    [int]$Iterations = 0,
    [string]$Plan = "",
    [switch]$WriteReports,
    [switch]$NoAlerts
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

$commandArgs = @(
    "-m",
    "shortterm_trader.cli",
    "intraday-watch",
    "--interval",
    "$Interval"
)

if ($Iterations -gt 0) {
    $commandArgs += @("--iterations", "$Iterations")
}

if ($Plan) {
    $commandArgs += @("--plan", "$Plan")
}

if ($WriteReports) {
    $commandArgs += "--write-reports"
}

if ($NoAlerts) {
    $commandArgs += "--no-alerts"
}

Push-Location $RepoRoot
try {
    python @commandArgs
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
