#requires -Version 7.0
<##
REL-01 local synthetic trial launcher.

PowerShell 7 only.  The script creates fresh owned profiles, binds both
listeners to loopback, launches server.exe hidden and two normal client.exe
windows, then keeps the Process objects until both clients exit or the user
cancels.  It never reads the real prefs/home, changes system environment,
firewall, or execution policy, and never kills by an arbitrary PID.

Dry run:
  pwsh -NoProfile -File .\trial_start.ps1 -DryRun
Run after the final integrated EXEs are present in .\dist:
  pwsh -NoProfile -File .\trial_start.ps1
#>

[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "trial_start.ps1 requires PowerShell 7 or newer (pwsh)."
}

$Root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$ServerExe = Join-Path $Root "dist\server.exe"
$ClientExe = Join-Path $Root "dist\client.exe"
$Flags = [ordered]@{
    MOYU_BIND_HOST       = "127.0.0.1"
    MOYU_DISCOVERY       = "0"
    MOYU_TRAY            = "0"
    MOYU_GLOBAL_HOTKEYS  = "0"
    MOYU_HARDWARE        = "0"
    MOYU_WEB_HTTPS       = "0"
}
$SyntheticNicks = @("REL_trial_alpha", "REL_trial_beta")

function Get-FreeLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Parse("127.0.0.1"), 0)
    try {
        $listener.Start()
        return [int]$listener.LocalEndpoint.Port
    }
    finally {
        $listener.Stop()
        $listener.Dispose()
    }
}

function New-TrialEnvironment {
    param(
        [Parameter(Mandatory)] [string]$Profile,
        [Parameter(Mandatory)] [int]$TcpPort,
        [Parameter(Mandatory)] [int]$WebPort
    )
    $profilePath = (New-Item -ItemType Directory -Force -Path $Profile).FullName
    $appData = (New-Item -ItemType Directory -Force -Path (Join-Path $profilePath "AppData\Roaming")).FullName
    $localAppData = (New-Item -ItemType Directory -Force -Path (Join-Path $profilePath "AppData\Local")).FullName
    $temp = (New-Item -ItemType Directory -Force -Path (Join-Path $profilePath "Temp")).FullName

    # Only stable OS paths are copied.  PATH is deliberately reduced to the
    # Windows system directories so external tool integrations cannot leak in.
    $systemRoot = [Environment]::GetEnvironmentVariable("SystemRoot")
    if ([string]::IsNullOrWhiteSpace($systemRoot)) { $systemRoot = "C:\Windows" }
    $envMap = [System.Collections.Generic.Dictionary[string,string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($pair in @{
        SystemRoot = $systemRoot
        WINDIR = $systemRoot
        SystemDrive = ([Environment]::GetEnvironmentVariable("SystemDrive") ?? "C:")
        ComSpec = (Join-Path $systemRoot "System32\cmd.exe")
        PATHEXT = ".COM;.EXE;.BAT;.CMD"
        OS = "Windows_NT"
        PROCESSOR_ARCHITECTURE = ([Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITECTURE") ?? "AMD64")
        NUMBER_OF_PROCESSORS = ([Environment]::GetEnvironmentVariable("NUMBER_OF_PROCESSORS") ?? "1")
    }.GetEnumerator()) {
        if ($null -ne $pair.Value) { $envMap[$pair.Key] = [string]$pair.Value }
    }
    $envMap["PATH"] = "$systemRoot\System32;$systemRoot"
    # client.exe keys its singleton mutex by USERNAME.  Use one synthetic key
    # per owned profile so two clients cannot wake/replace each other.
    $profileHash = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData(
        [System.Text.Encoding]::UTF8.GetBytes($profilePath))).ToLowerInvariant()
    $envMap["USERNAME"] = "trial_" + $profileHash.Substring(0, 20)
    $envMap["USERPROFILE"] = $profilePath
    $envMap["HOMEDRIVE"] = $profilePath.Substring(0, 2)
    $envMap["HOMEPATH"] = $profilePath.Substring(2)
    $envMap["APPDATA"] = $appData
    $envMap["LOCALAPPDATA"] = $localAppData
    $envMap["TEMP"] = $temp
    $envMap["TMP"] = $temp
    foreach ($pair in $Flags.GetEnumerator()) { $envMap[$pair.Key] = [string]$pair.Value }
    $envMap["MOYU_TCP_PORT"] = [string]$TcpPort
    $envMap["MOYU_WEB_PORT"] = [string]$WebPort
    return $envMap
}

function Write-SyntheticPrefs {
    param([Parameter(Mandatory)] [string]$Profile)
    $prefsDir = New-Item -ItemType Directory -Force -Path (Join-Path $Profile "moeyu_helper")
    $prefs = [ordered]@{
        trusted_nicks = @($SyntheticNicks)
        muted = @("public")
        dnd = $true
        ui_sound = $false
        notify_sound = "off"
        voice_autoplay = $false
    }
    $prefsPath = Join-Path $prefsDir.FullName "prefs.json"
    $prefs | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $prefsPath -Encoding utf8
}

function Start-TrialProcess {
    param(
        [Parameter(Mandatory)] [string]$Executable,
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [string[]]$Arguments,
        [Parameter(Mandatory)] [System.Collections.Generic.Dictionary[string,string]]$Environment,
        [Parameter(Mandatory)] [bool]$Hidden
    )
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Executable
    $start.WorkingDirectory = $Root
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $Hidden
    $start.WindowStyle = if ($Hidden) {
        [System.Diagnostics.ProcessWindowStyle]::Hidden
    } else {
        [System.Diagnostics.ProcessWindowStyle]::Normal
    }
    foreach ($arg in $Arguments) { [void]$start.ArgumentList.Add($arg) }
    $start.Environment.Clear()
    foreach ($entry in $Environment.GetEnumerator()) {
        $start.Environment[$entry.Key] = $entry.Value
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw "Failed to start $Executable" }
    return $process
}

function Stop-OwnedProcess {
    param([System.Diagnostics.Process]$Process)
    if ($null -eq $Process) { return [bool]$true }
    try {
        if ($Process.HasExited) { return [bool]$true }
        try {
            $Process.Kill($true)
        }
        catch {
            # A tree kill that cannot be confirmed is an infrastructure
            # failure; never fall back to killing only the parent.
            return [bool]$false
        }
        [void]$Process.WaitForExit(5000)
        return [bool]$Process.HasExited
    }
    catch { return [bool]$false }
}

function Test-LoopbackReady {
    param([int]$Port)
    try {
        $tcp = [System.Net.Sockets.TcpClient]::new()
        try {
            $task = $tcp.ConnectAsync("127.0.0.1", $Port)
            return $task.Wait(300)
        }
        finally { $tcp.Dispose() }
    }
    catch { return $false }
}

if ($DryRun) {
    [ordered]@{
        mode = "DryRun"
        powershell = "pwsh 7+"
        root = $Root
        server = "dist\server.exe"
        client = "dist\client.exe"
        profiles = @("trial-server", "trial-client-alpha", "trial-client-beta")
        ports = @{ tcp = "random loopback IPv4"; web = "random loopback IPv4" }
        flags = $Flags
        synthetic_nicks = $SyntheticNicks
        user_input = $false
        real_prefs = $false
        devices = $false
        external_network = $false
        system_changes = $false
        cleanup = "owned Process objects only"
    } | ConvertTo-Json -Depth 6
    exit 0
}

if (-not (Test-Path -LiteralPath $ServerExe -PathType Leaf) -or
    -not (Test-Path -LiteralPath $ClientExe -PathType Leaf)) {
    throw "Missing final integrated EXEs under dist\ (run build after integration)."
}

$tcpPort = Get-FreeLoopbackPort
$webPort = Get-FreeLoopbackPort
while ($webPort -eq $tcpPort) { $webPort = Get-FreeLoopbackPort }
$runId = "trial-start-{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"),
    ([guid]::NewGuid().ToString("N").Substring(0, 10))
$runDir = New-Item -ItemType Directory -Force -Path (Join-Path $Root "_tmp_gui\trial-start\$runId")
$profiles = @{
    server = (New-Item -ItemType Directory -Force -Path (Join-Path $runDir.FullName "trial-server")).FullName
    alpha = (New-Item -ItemType Directory -Force -Path (Join-Path $runDir.FullName "trial-client-alpha")).FullName
    beta = (New-Item -ItemType Directory -Force -Path (Join-Path $runDir.FullName "trial-client-beta")).FullName
}
foreach ($profile in @($profiles.alpha, $profiles.beta)) { Write-SyntheticPrefs -Profile $profile }
$envServer = New-TrialEnvironment -Profile $profiles.server -TcpPort $tcpPort -WebPort $webPort
$envAlpha = New-TrialEnvironment -Profile $profiles.alpha -TcpPort $tcpPort -WebPort $webPort
$envBeta = New-TrialEnvironment -Profile $profiles.beta -TcpPort $tcpPort -WebPort $webPort
$children = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()
$server = $null
$summary = [ordered]@{
    mode = "Run"
    run_id = $runId
    ports = @{ tcp = $tcpPort; web = $webPort }
    profiles = @{ server = "trial-server"; alpha = "trial-client-alpha"; beta = "trial-client-beta" }
    flags = $Flags
    synthetic_nicks = $SyntheticNicks
    processes = @{}
    cancelled = $false
}

try {
    $server = Start-TrialProcess -Executable $ServerExe -Arguments @() -Environment $envServer -Hidden $true
    [void]$children.Add($server)
    $summary.processes.server = @{ pid = $server.Id; image = "dist\server.exe"; hidden = $true }
    $deadline = (Get-Date).AddSeconds(12)
    while ((Get-Date) -lt $deadline -and -not (Test-LoopbackReady -Port $tcpPort)) {
        Start-Sleep -Milliseconds 200
    }
    if (-not (Test-LoopbackReady -Port $tcpPort)) { throw "server.exe did not open loopback TCP" }
    $alpha = Start-TrialProcess -Executable $ClientExe -Arguments @("--host", "127.0.0.1", "--port", "$tcpPort", "--nick", $SyntheticNicks[0]) -Environment $envAlpha -Hidden $false
    [void]$children.Add($alpha)
    $beta = Start-TrialProcess -Executable $ClientExe -Arguments @("--host", "127.0.0.1", "--port", "$tcpPort", "--nick", $SyntheticNicks[1]) -Environment $envBeta -Hidden $false
    [void]$children.Add($beta)
    $summary.processes.alpha = @{ pid = $alpha.Id; image = "dist\client.exe"; hidden = $false }
    $summary.processes.beta = @{ pid = $beta.Id; image = "dist\client.exe"; hidden = $false }
    $summary.profile_roots = @("trial-server", "trial-client-alpha", "trial-client-beta")
    $summaryPath = Join-Path $runDir.FullName "summary.json"
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8
    $summary | ConvertTo-Json -Depth 8
    Write-Host "两个 client.exe 已启动；关闭两个客户端或按 Ctrl+C 清理本次子进程。"
    while ($true) {
        $alive = @(@($alpha, $beta) | Where-Object { -not $_.HasExited })
        if ($alive.Count -eq 0) { break }
        Start-Sleep -Milliseconds 500
    }
}
catch {
    $summary.error = $_.Exception.GetType().Name
    throw
}
finally {
    $clean = @()
    foreach ($child in $children) {
        $clean += [bool](Stop-OwnedProcess -Process $child)
        try { $child.Dispose() } catch { }
    }
    $summary.cleanup_ok = [bool]($clean.Count -eq 0 -or ($clean -notcontains $false))
    try {
        $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runDir.FullName "summary.json") -Encoding utf8
    } catch { }
}
