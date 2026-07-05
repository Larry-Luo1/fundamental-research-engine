#Requires -Version 5
<#
  Start a read-only local log server and optionally expose it to the VPS via ssh -R.

  Default one-click use:
    powershell -ExecutionPolicy Bypass -File start-remote-log-channel.ps1

  If auto config is not available:
    powershell -ExecutionPolicy Bypass -File start-remote-log-channel.ps1 -VpsUser claude -VpsHost <host> -VpsPort 8443

  VPS usage after the tunnel is connected:
    curl http://127.0.0.1:19024/logs
    curl "http://127.0.0.1:19024/tail?file=all&lines=100"
#>
param(
  [int]$LocalPort = 19024,
  [int]$RemotePort = 19024,
  [string]$VpsHost = $env:FRE_VPS_HOST,
  [string]$VpsUser = $env:FRE_VPS_USER,
  [int]$VpsPort = 0,
  [string]$SshKeyPath = $env:FRE_VPS_KEY,
  [string]$ClaudeConfigPath = $env:FRE_CLAUDE_CONFIG,
  [switch]$NoTunnel,
  [switch]$NoAutoConfig
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Write-Step {
  param(
    [string]$Message,
    [ConsoleColor]$Color = "Cyan"
  )
  Write-Host "[remote-logs] $Message" -ForegroundColor $Color
}

function Resolve-Python {
  $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $venvPython) {
    return $venvPython
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $python) {
    throw "python is required to run the log server."
  }
  return $python.Source
}

function Find-AutoConfigPath {
  if ($NoAutoConfig) {
    return $null
  }
  if ($ClaudeConfigPath -and (Test-Path -LiteralPath $ClaudeConfigPath)) {
    return (Resolve-Path -LiteralPath $ClaudeConfigPath).Path
  }

  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "ccclaude\config.json"),
    (Join-Path $PSScriptRoot "..\..\outputs\claude-remote-stable\config.json")
  )

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  return $null
}

function Load-AutoConfig {
  param([string]$Path)
  if (-not $Path) {
    return $null
  }
  Write-Step "Using external VPS config: $Path" DarkGray
  return Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
}

function Resolve-SshExe {
  param([string]$ConfigPath)

  if ($ConfigPath) {
    $bundled = Join-Path (Split-Path -Parent $ConfigPath) "ssh.exe"
    if (Test-Path -LiteralPath $bundled) {
      return $bundled
    }
  }

  $ssh = Get-Command ssh -ErrorAction SilentlyContinue
  if (-not $ssh) {
    throw "ssh is required to create the reverse tunnel."
  }
  return $ssh.Source
}

function Ensure-SshKey {
  param(
    [object]$Config,
    [string]$KeyPath
  )

  if (-not $KeyPath) {
    $defaultKey = Join-Path $env:USERPROFILE ".ssh\cust6_login"
    if ((Test-Path -LiteralPath $defaultKey) -or ($Config -and $Config.loginKeyB64)) {
      $KeyPath = $defaultKey
    }
  }

  if ($KeyPath -and -not (Test-Path -LiteralPath $KeyPath) -and $Config -and $Config.loginKeyB64) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $KeyPath) | Out-Null
    [IO.File]::WriteAllBytes($KeyPath, [Convert]::FromBase64String($Config.loginKeyB64))
    try {
      icacls $KeyPath /inheritance:r | Out-Null
      icacls $KeyPath /grant:r "$($env:USERNAME):R" | Out-Null
    } catch {
      Write-Step "Could not tighten SSH key permissions automatically." Yellow
    }
  }

  if ($KeyPath -and (Test-Path -LiteralPath $KeyPath)) {
    return (Resolve-Path -LiteralPath $KeyPath).Path
  }

  return $null
}

function Test-LogServerHealth {
  param([int]$Port)

  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
    if ($resp.StatusCode -ne 200) {
      return $false
    }
    $json = $resp.Content | ConvertFrom-Json
    return ($json.service -eq "fre-remote-log-server")
  } catch {
    return $false
  }
}

function Start-LogServer {
  param(
    [string]$PythonExe,
    [int]$Port
  )

  if (Test-LogServerHealth -Port $Port) {
    Write-Step "Log server is already running at http://127.0.0.1:$Port" Yellow
    return $null
  }

  $logDir = Join-Path $PSScriptRoot "web_data\logs"
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  $outLog = Join-Path $logDir "remote-log-server.out.log"
  $errLog = Join-Path $logDir "remote-log-server.err.log"
  $serverScript = Join-Path $PSScriptRoot "tools\remote_log_server.py"
  if (-not (Test-Path -LiteralPath $serverScript)) {
    throw "Missing log server script: $serverScript"
  }

  Write-Step "Starting local read-only log server at http://127.0.0.1:$Port ..."
  $args = @(
    "`"$serverScript`"",
    "--root",
    "`"$PSScriptRoot`"",
    "--host",
    "127.0.0.1",
    "--port",
    "$Port"
  )
  $proc = Start-Process -PassThru -WindowStyle Hidden -FilePath $PythonExe `
    -ArgumentList $args `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog

  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 300
    if (Test-LogServerHealth -Port $Port) {
      Write-Step "Log server is ready. Output: $outLog"
      return $proc
    }
    if ($proc.HasExited) {
      $err = ""
      if (Test-Path -LiteralPath $errLog) {
        $err = (Get-Content -Tail 20 -Encoding UTF8 -LiteralPath $errLog) -join "`n"
      }
      throw "Log server exited before becoming ready.`n$err"
    }
  }

  throw "Log server did not become ready on port $Port."
}

function Build-SshArgs {
  param(
    [string]$User,
    [string]$HostName,
    [int]$Port,
    [string]$KeyPath,
    [int]$Remote,
    [int]$Local
  )

  $args = @()
  if ($KeyPath) {
    $args += @("-i", $KeyPath)
  }
  if ($Port -gt 0) {
    $args += @("-p", "$Port")
  }
  $args += @(
    "-N",
    "-R",
    "$($Remote):127.0.0.1:$($Local)",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ServerAliveInterval=20",
    "-o",
    "ServerAliveCountMax=3",
    "-o",
    "ExitOnForwardFailure=yes",
    "$User@$HostName"
  )
  return $args
}

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, "FundamentalResearchRemoteLogs_$LocalPort", [ref]$createdNew)
if (-not $createdNew) {
  Write-Step "A remote log channel for local port $LocalPort is already running." Yellow
  Write-Step "VPS: curl http://127.0.0.1:$RemotePort/logs"
  Start-Sleep -Seconds 5
  return
}

$logServer = $null
try {
  try { $Host.UI.RawUI.WindowTitle = "FRE Remote Logs" } catch {}

  $configPath = Find-AutoConfigPath
  $config = Load-AutoConfig -Path $configPath
  if (-not $VpsHost -and $config) {
    $VpsHost = if ($config.jumpHost) { $config.jumpHost } else { $config.host }
  }
  if (-not $VpsUser -and $config) {
    $VpsUser = $config.user
  }
  if ($VpsPort -eq 0 -and $config) {
    $VpsPort = if ($config.jumpPort) { [int]$config.jumpPort } else { [int]$config.port }
  }

  $SshKeyPath = Ensure-SshKey -Config $config -KeyPath $SshKeyPath
  $pythonExe = Resolve-Python
  $logServer = Start-LogServer -PythonExe $pythonExe -Port $LocalPort

  Write-Host ""
  Write-Step "Local endpoints:"
  Write-Host "  http://127.0.0.1:$LocalPort/logs"
  Write-Host "  http://127.0.0.1:$LocalPort/tail?file=all&lines=100"
  Write-Host "  http://127.0.0.1:$LocalPort/tail?file=uvicorn-err&lines=200"
  Write-Host ""

  if ($NoTunnel -or -not $VpsHost -or -not $VpsUser) {
    Write-Step "Tunnel is not started because VPS config is missing or -NoTunnel was set." Yellow
    Write-Host "To expose this log server manually, run a command like:"
    Write-Host "  ssh -N -R $RemotePort`:127.0.0.1:$LocalPort <user>@<vps-host>"
    Write-Host ""
    Write-Step "Keep this window open. Press Ctrl+C to stop."
    while ($true) {
      Start-Sleep -Seconds 3600
    }
  }

  $sshExe = Resolve-SshExe -ConfigPath $configPath
  $sshArgs = Build-SshArgs -User $VpsUser -HostName $VpsHost -Port $VpsPort -KeyPath $SshKeyPath -Remote $RemotePort -Local $LocalPort

  Write-Step "Starting reverse tunnel to $VpsUser@$VpsHost ..."
  Write-Host "VPS commands after it connects:"
  Write-Host "  curl http://127.0.0.1:$RemotePort/logs"
  Write-Host "  curl `"http://127.0.0.1:$RemotePort/tail?file=all&lines=100`""
  Write-Host ""
  Write-Step "Keep this window open. If SSH disconnects, it will reconnect automatically."

  $backoff = 5
  while ($true) {
    & $sshExe @sshArgs
    Write-Step "Tunnel disconnected. Reconnecting in $backoff seconds..." Yellow
    Start-Sleep -Seconds $backoff
    if ($backoff -lt 30) {
      $backoff = [Math]::Min($backoff * 2, 30)
    }
  }
}
finally {
  if ($logServer -and -not $logServer.HasExited) {
    Write-Step "Stopping local log server..."
    Stop-Process -Id $logServer.Id -Force -ErrorAction SilentlyContinue
  }
  if ($createdNew) {
    $mutex.ReleaseMutex()
  }
  $mutex.Dispose()
}
