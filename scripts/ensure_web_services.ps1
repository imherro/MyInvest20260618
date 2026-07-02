[CmdletBinding()]
param(
    [switch]$NoStart,
    [int]$StartupWaitSeconds = 15,
    [int]$HttpTimeoutSeconds = 4
)

$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptRoot "..")).Path
$DocumentsRoot = (Resolve-Path (Join-Path $RepoRoot "..")).Path
$LogRoot = Join-Path $RepoRoot "temp\web_service_monitor"

function ProjectPath {
    param([string]$Name)
    return (Join-Path $DocumentsRoot $Name)
}

function New-Service {
    param(
        [string]$Id,
        [string]$ProjectPath,
        [int]$Port,
        [string]$HealthPath,
        [string[]]$Arguments
    )
    return [pscustomobject]@{
        Id = $Id
        ProjectPath = $ProjectPath
        Port = $Port
        HealthPath = $HealthPath
        Arguments = $Arguments
    }
}

$Services = @(
    (New-Service "home" $RepoRoot 8888 "/api" @("server.py", "--host", "127.0.0.1", "--port", "8888")),
    (New-Service "market" (ProjectPath "MyInvestMarket") 8011 "/api" @("scripts\serve_market_web.py")),
    (New-Service "cycle" (ProjectPath "MyInvestCycle") 8021 "/api" @("-m", "web.app")),
    (New-Service "theme" (ProjectPath "MyInvestTheme") 8012 "/api" @("scripts\run_web.py", "--host", "127.0.0.1", "--port", "8012")),
    (New-Service "leader" (ProjectPath "MyInvestLeader") 8014 "/api" @("scripts\run_web.py", "--host", "127.0.0.1", "--port", "8014")),
    (New-Service "shadow" (ProjectPath "MyInvestShadow") 8013 "/health" @("scripts\run_web.py")),
    (New-Service "position" (ProjectPath "MyInvestPosition") 8018 "/health" @("-m", "app.server", "--host", "127.0.0.1", "--port", "8018")),
    (New-Service "etf" (ProjectPath "MyInvestETF") 8017 "/api" @("scripts\run_web.py", "--host", "127.0.0.1", "--port", "8017")),
    (New-Service "stock" (ProjectPath "MyInvestStock") 8016 "/api" @("scripts\run_web.py", "--host", "127.0.0.1", "--port", "8016")),
    (New-Service "short" (ProjectPath "MyShortTerm") 8009 "/" @("-m", "shortterm_trader.webapp", "--host", "127.0.0.1", "--port", "8009")),
    (New-Service "picking" (ProjectPath "MyInvestPicking") 8019 "/api" @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8019")),
    (New-Service "ten" (ProjectPath "MyInvestTenBagger") 8020 "/api" @("scripts\serve_web.py", "--host", "127.0.0.1", "--port", "8020"))
)

function Get-PythonLaunch {
    param([string]$ProjectPath)

    $localPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"
    if (Test-Path $localPython) {
        return [pscustomobject]@{ FilePath = $localPython; Prefix = @() }
    }

    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($python) {
        return [pscustomobject]@{ FilePath = $python.Source; Prefix = @() }
    }

    $py = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($py) {
        return [pscustomobject]@{ FilePath = $py.Source; Prefix = @("-3.11") }
    }

    throw "No Python launcher found. Install Python 3.11 or add python.exe to PATH."
}

function Test-TcpPort {
    param([int]$Port)

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(1000, $false)
        if (-not $connected) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($async -and $async.AsyncWaitHandle) {
            $async.AsyncWaitHandle.Close()
        }
        $client.Close()
    }
}

function Test-ServiceHttp {
    param([object]$Service)

    $url = "http://127.0.0.1:$($Service.Port)$($Service.HealthPath)"
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $HttpTimeoutSeconds -ErrorAction Stop
        return [pscustomobject]@{
            Ok = $true
            StatusCode = [int]$response.StatusCode
            Url = $url
            Error = $null
        }
    }
    catch {
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        return [pscustomobject]@{
            Ok = $false
            StatusCode = $statusCode
            Url = $url
            Error = $_.Exception.Message
        }
    }
}

function Start-WebService {
    param(
        [object]$Service,
        [string]$RunLogDir
    )

    $python = Get-PythonLaunch $Service.ProjectPath
    $arguments = @($python.Prefix) + @($Service.Arguments)
    $stdout = Join-Path $RunLogDir "$($Service.Id).out.log"
    $stderr = Join-Path $RunLogDir "$($Service.Id).err.log"

    $process = Start-Process `
        -FilePath $python.FilePath `
        -ArgumentList $arguments `
        -WorkingDirectory $Service.ProjectPath `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru

    return [pscustomobject]@{
        ProcessId = $process.Id
        Command = "$($python.FilePath) $($arguments -join ' ')"
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Wait-ServiceHttp {
    param([object]$Service)

    $deadline = (Get-Date).AddSeconds($StartupWaitSeconds)
    do {
        Start-Sleep -Seconds 2
        $check = Test-ServiceHttp $Service
        if ($check.Ok) {
            return $check
        }
    } while ((Get-Date) -lt $deadline)

    return (Test-ServiceHttp $Service)
}

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$RunStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunLogDir = Join-Path $LogRoot $RunStamp
New-Item -ItemType Directory -Force -Path $RunLogDir | Out-Null

$results = @()
foreach ($service in $Services) {
    $result = [ordered]@{
        id = $service.Id
        port = $service.Port
        project_path = $service.ProjectPath
        health_url = "http://127.0.0.1:$($service.Port)$($service.HealthPath)"
        status = $null
        http_status = $null
        process_id = $null
        command = $null
        stdout = $null
        stderr = $null
        error = $null
    }

    if (-not (Test-Path $service.ProjectPath)) {
        $result.status = "missing_path"
        $result.error = "Project path does not exist."
        $results += [pscustomobject]$result
        continue
    }

    $initial = Test-ServiceHttp $service
    $result.http_status = $initial.StatusCode
    if ($initial.Ok) {
        $result.status = "running"
        $results += [pscustomobject]$result
        continue
    }

    if (Test-TcpPort $service.Port) {
        $result.status = "port_busy_unhealthy"
        $result.error = $initial.Error
        $results += [pscustomobject]$result
        continue
    }

    if ($NoStart) {
        $result.status = "stopped"
        $result.error = $initial.Error
        $results += [pscustomobject]$result
        continue
    }

    try {
        $start = Start-WebService $service $RunLogDir
        $result.process_id = $start.ProcessId
        $result.command = $start.Command
        $result.stdout = $start.Stdout
        $result.stderr = $start.Stderr

        $after = Wait-ServiceHttp $service
        $result.http_status = $after.StatusCode
        if ($after.Ok) {
            $result.status = "started"
        }
        else {
            $result.status = "failed_to_start"
            $result.error = $after.Error
        }
    }
    catch {
        $result.status = "failed_to_start"
        $result.error = $_.Exception.Message
    }

    $results += [pscustomobject]$result
}

$failureStatuses = @("missing_path", "port_busy_unhealthy", "failed_to_start")
$failures = @($results | Where-Object { $failureStatuses -contains $_.status })
$summary = [ordered]@{
    checked_at = (Get-Date).ToString("o")
    no_start = [bool]$NoStart
    log_dir = $RunLogDir
    counts = [ordered]@{
        total = @($results).Count
        running = @($results | Where-Object { $_.status -eq "running" }).Count
        started = @($results | Where-Object { $_.status -eq "started" }).Count
        failed = @($failures).Count
    }
    services = $results
}

$summaryPath = Join-Path $RunLogDir "summary.json"
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $summaryPath -Encoding utf8

$results | Sort-Object id | Format-Table -AutoSize id, port, status, http_status, process_id
Write-Host "summary: $summaryPath"

if (@($failures).Count -gt 0) {
    Write-Host "failures: $(@($failures | ForEach-Object { $_.id }) -join ', ')"
    exit 1
}

exit 0
