[CmdletBinding()]
param(
    [switch]$NoStart,
    [switch]$Restart,
    [switch]$LegacyServices,
    [string[]]$Only,
    [ValidateSet('monorepo', 'legacy')]
    [string]$Layout = 'monorepo',
    [string]$BindHost = "0.0.0.0",
    [int]$StartupWaitSeconds = 60,
    [int]$HttpTimeoutSeconds = 4
)

$ErrorActionPreference = "Stop"
if ($NoStart -and $Restart) { throw '-NoStart and -Restart cannot be combined.' }
if ($Restart -and -not $Only) { throw '-Restart requires an explicit -Only service list.' }

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptRoot "..")).Path
$DocumentsRoot = (Resolve-Path (Join-Path $RepoRoot "..")).Path
$LogRoot = Join-Path $RepoRoot "temp\web_service_monitor"
$StateRoot = Join-Path $RepoRoot 'runtime\service-processes'
$mutex = New-Object System.Threading.Mutex($false, 'Local\MyInvestUnifiedWebMonitor')
if (-not $mutex.WaitOne(0)) { Write-Error 'Another MyInvest monitor is already running.'; exit 1 }
# The owning handle is released when this script process exits.

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
    (New-Service "home" $RepoRoot 8888 "/healthz" @('-u', (Join-Path $RepoRoot 'server.py'), "--host", $BindHost, "--port", "8888")),
    (New-Service "test" (ProjectPath "MyInvestTest") 8024 "/index.html" @("-m", "http.server", "8024", "--bind", $BindHost, "--directory", "output")),
    (New-Service "taa" (ProjectPath "MyInvestTAA") 8025 "/" @("-m", "uvicorn", "backend.main:app", "--host", $BindHost, "--port", "8025"))
)

# Default deployment has one listener for the hub and all 13 modules.
# Test/TAA retain their existing paths and ports, outside the migration scope.
$Registry = Get-Content (Join-Path $RepoRoot 'subsystems.json') -Raw | ConvertFrom-Json
$Services = @($Services | Where-Object { $_.Id -notin $Registry.systems.id })
if ($LegacyServices) { foreach ($system in $Registry.systems) {
    $project = if ($Layout -eq 'legacy') { ProjectPath $system.directory } else { Join-Path (Join-Path $RepoRoot 'apps') $system.directory }
    $launcher = Join-Path $RepoRoot 'scripts\production_service.py'
    $Services += New-Service $system.id $project $system.port $system.health @('-u', $launcher, '--system', $system.id, '--layout', $Layout, '--host', $BindHost)
} }
if ($Only) {
    foreach ($id in $Only) { if ($id -notin $Services.Id) { throw "Unknown service: $id" } }
    $Services = @($Services | Where-Object { $_.Id -in $Only })
}

function Get-ServiceIdentity {
    param([object]$Service)
    $owners = @(Get-NetTCPConnection -State Listen -LocalPort $Service.Port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    if (-not $owners.Count) { return [pscustomobject]@{ Ok=$true; LayoutMatch=$true; Pids=@(); Error=$null } }
    $layoutMatch = $true
    foreach ($owner in $owners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $owner"
        $command = $process.CommandLine
        $migrated = $Service.Id -in $Registry.systems.id
        if ($migrated) {
            $ok = $command -and $command.Contains((Join-Path $RepoRoot 'scripts\production_service.py')) -and
                $command -match ('--system\s+' + [regex]::Escape($Service.Id) + '(\s|$)') -and
                $command -match '--layout\s+(monorepo|legacy)(\s|$)'
            $layoutMatch = $command -match ('--layout\s+' + $Layout + '(\s|$)')
        } else {
            $expectedPath = if ($Service.Id -eq 'home') { Join-Path $RepoRoot 'server.py' } else { $Service.ProjectPath }
            $ok = $command -and $command.Contains($expectedPath)
            $stateFile = Join-Path $StateRoot ($Service.Id + '.json')
            if (-not $ok -and (Test-Path -LiteralPath $stateFile)) {
                $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
                $ok = $state.pid -eq $owner -and $state.created -eq $process.CreationDate.ToString('o') -and $state.command -eq $command
            }
        }
        if (-not $ok) { return [pscustomobject]@{ Ok=$false; Pids=$owners; Error="Port owned by an unverified process $owner; refusing to stop or claim it." } }
    }
    return [pscustomobject]@{ Ok=$true; LayoutMatch=$layoutMatch; Pids=$owners; Error=$null }
}

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

function Stop-ServiceListener {
    param([object]$Service)

    $identity = Get-ServiceIdentity $Service
    if (-not $identity.Ok) { throw $identity.Error }
    foreach ($owner in $identity.Pids) {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $owner" | Where-Object { $_.CommandLine -match 'multiprocessing.spawn' })
        Stop-Process -Id $owner -Force -ErrorAction Stop
        # Workers watch the parent sentinel. Wait before another process opens data.
        foreach ($child in $children) {
            $deadline = (Get-Date).AddSeconds(10)
            do {
                $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($child.ProcessId)"
                if (-not $current -or $current.CreationDate -ne $child.CreationDate) { break }
                Start-Sleep -Milliseconds 200
            } while ((Get-Date) -lt $deadline)
            if ($current -and $current.CreationDate -eq $child.CreationDate) { throw "Worker $($child.ProcessId) did not exit; refusing overlapping startup." }
        }
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
    $arguments = @($arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } })
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

    $identity = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
    if ($identity) {
        New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
        @{pid=$process.Id; created=$identity.CreationDate.ToString('o'); command=$identity.CommandLine} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StateRoot ($Service.Id + '.json')) -Encoding utf8
    }

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

    $identity = Get-ServiceIdentity $service
    if (-not $identity.Ok -or (-not $identity.LayoutMatch -and -not $Restart)) {
        $result.status = 'unverified_listener'
        $result.error = if ($identity.Error) { $identity.Error } else { 'Managed process has different layout; explicit -Restart -Only is required.' }
        $results += [pscustomobject]$result
        continue
    }
    if ($identity.Pids.Count) { $result.process_id = $identity.Pids[0] }
    if ($Restart) {
        Stop-ServiceListener $service
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
            $verified = Get-ServiceIdentity $service
            if ($verified.Ok -and $start.ProcessId -in $verified.Pids) { $result.status = "started" }
            else { $result.status = 'failed_to_start'; $result.error = 'HTTP responded but listener identity does not match launched process.' }
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

$moduleResults = @()
$moduleProbeFailures = @()
if (-not $LegacyServices -and 'home' -in $Services.Id -and @($results | Where-Object { $_.id -eq 'home' -and $_.status -in @('running', 'started') }).Count) {
    foreach ($system in $Registry.systems) {
        $slug = if ($system.id -eq 'strategyindex') { 'strategy' } else { $system.id }
        $path = if ($system.health -eq '/api') { "/api/$slug" } else { "/$slug$($system.health)" }
        if (-not $NoStart) {
            # A request revives a dead IPC worker without starting a second web service.
            try { Invoke-WebRequest -Uri "http://127.0.0.1:8888$path" -UseBasicParsing -TimeoutSec $StartupWaitSeconds | Out-Null }
            catch { $moduleProbeFailures += $system.id; Write-Warning "Module probe failed: $($system.id)" }
        }
    }
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8888/api/health' -TimeoutSec $HttpTimeoutSeconds
        foreach ($system in $Registry.systems) {
            $state = $health.modules.($system.id)
            $moduleResults += [pscustomobject]@{ id=$system.id; ready=([bool]$state.ready -and [bool]$state.alive); pid=$state.pid; transport=$state.transport }
        }
        if (-not $health.ok -or $moduleResults.Count -ne 13 -or $moduleProbeFailures.Count) { throw "Unified module health is incomplete. Failed probes: $($moduleProbeFailures -join ', ')" }
    } catch {
        $results += [pscustomobject]@{ id='unified-modules'; port=8888; status='failed_to_start'; error=$_.Exception.Message }
    }
}
$failureStatuses = @("missing_path", "port_busy_unhealthy", "failed_to_start", "unverified_listener", "stopped")
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
    modules = $moduleResults
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
