#Requires -Version 5
<#
  Windows runner for the local display/debug machine.

  What it does:
    1. Starts the FastAPI app with uvicorn --reload.
    2. Polls origin/<branch> every few seconds.
    3. When a new commit appears, resets this checkout to origin/<branch>.

  Important:
    This machine is treated as a read-only consumer. Do not edit code here while
    the runner is active, because updates intentionally use git reset --hard.

  Daily use:
    powershell -ExecutionPolicy Bypass -File runner-windows.ps1

  Open:
    http://localhost:8000
#>
param(
  [int]$Port = 8000,
  [string]$HostAddress = "127.0.0.1",
  [string]$Branch = "main",
  [int]$IntervalSec = 3,
  [bool]$StopExistingPythonOnPort = $true,
  [switch]$NoInstall
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Write-Step {
  param(
    [string]$Message,
    [ConsoleColor]$Color = "Cyan"
  )
  Write-Host "[runner] $Message" -ForegroundColor $Color
}

function Assert-Command {
  param([string]$Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $Name"
  }
}

function Format-ProxyUrl {
  param([string]$Proxy)

  if (-not $Proxy) {
    return $null
  }

  $candidate = $Proxy.Trim()
  if ($candidate -match ";") {
    if ($candidate -match "(^|;)https=([^;]+)") {
      $candidate = $Matches[2]
    } elseif ($candidate -match "(^|;)http=([^;]+)") {
      $candidate = $Matches[2]
    } else {
      return $null
    }
  }

  if ($candidate -notmatch "^[a-zA-Z][a-zA-Z0-9+.-]*://") {
    $candidate = "http://$candidate"
  }

  return $candidate
}

function Resolve-GitProxy {
  foreach ($name in @("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY")) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    $proxy = Format-ProxyUrl -Proxy $value
    if ($proxy) {
      return $proxy
    }
  }

  try {
    $settings = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction Stop
    if ($settings.ProxyEnable -eq 1) {
      return (Format-ProxyUrl -Proxy ([string]$settings.ProxyServer))
    }
  } catch {
    return $null
  }

  return $null
}

function Initialize-GitNetwork {
  $script:GitNetworkArgs = @()
  $proxy = Resolve-GitProxy
  if ($proxy) {
    $script:GitNetworkArgs = @("-c", "http.proxy=$proxy", "-c", "https.proxy=$proxy")
    Write-Step "Using proxy for git network calls: $proxy" Yellow
  }
}

function Invoke-GitNetwork {
  param([string[]]$Arguments)

  $allArgs = @()
  $allArgs += $script:GitNetworkArgs
  $allArgs += $Arguments
  & git @allArgs
}

function Invoke-Checked {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$FailureMessage
  )
  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$FailureMessage (exit code $LASTEXITCODE)"
  }
}

function Import-DotEnv {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) {
    if (Test-Path -LiteralPath ".env.example") {
      Copy-Item -LiteralPath ".env.example" -Destination $Path
      Write-Step "Created .env from .env.example. Fill API keys if model calls are needed." Yellow
    } else {
      Write-Step ".env not found. The app may fail if required env vars are missing." Yellow
      return
    }
  }

  foreach ($rawLine in Get-Content -LiteralPath $Path) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith("#")) {
      continue
    }

    $parts = $line -split "=", 2
    if ($parts.Count -ne 2) {
      continue
    }

    $key = $parts[0].Trim().TrimStart([char]0xFEFF)
    $value = $parts[1].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    [Environment]::SetEnvironmentVariable($key, $value, "Process")
  }
}

function Resolve-Python {
  $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $venvPython) {
    return $venvPython
  }

  Assert-Command "python"
  if ($NoInstall) {
    return "python"
  }

  Write-Step "Creating local virtual environment: .venv"
  Invoke-Checked -FilePath "python" -Arguments @("-m", "venv", ".venv") -FailureMessage "Failed to create .venv"

  if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment was created, but python.exe was not found at $venvPython"
  }

  return $venvPython
}

function Test-WebDependencies {
  param([string]$PythonExe)
  & $PythonExe -c "import fastapi, uvicorn" *> $null
  return ($LASTEXITCODE -eq 0)
}

function Ensure-WebDependencies {
  param(
    [string]$PythonExe,
    [switch]$Force
  )

  if (-not $Force -and (Test-WebDependencies -PythonExe $PythonExe)) {
    return
  }

  if ($NoInstall) {
    throw "Web dependencies are missing. Re-run without -NoInstall or install: python -m pip install -e `".[web]`" `"uvicorn[standard]`""
  }

  Write-Step "Installing web dependencies into the local environment..."
  Invoke-Checked -FilePath $PythonExe -Arguments @("-m", "pip", "install", "-e", ".[web]") -FailureMessage "Failed to install project web extra"
  Invoke-Checked -FilePath $PythonExe -Arguments @("-m", "pip", "install", "uvicorn[standard]") -FailureMessage "Failed to install uvicorn standard extra"
}

function Get-ListenerProcessIds {
  param([int]$ListenPort)
  if (-not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
    return @()
  }

  return @(Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Stop-CompatibleListeners {
  param([int]$ListenPort)

  $processIds = Get-ListenerProcessIds -ListenPort $ListenPort
  foreach ($processId in $processIds) {
    if (-not $processId -or $processId -eq $PID) {
      continue
    }

    if ($StopExistingPythonOnPort -and (Test-PythonProcessGroup -RootProcessId $processId)) {
      Write-Step "Stopping existing Python listener on port $ListenPort (PID $processId)." Yellow
      Stop-PythonProcessGroup -RootProcessId $processId
      Start-Sleep -Milliseconds 500
      continue
    }

    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) {
      throw "Port $ListenPort is already in use by PID $processId, but the process is not visible."
    }

    throw "Port $ListenPort is already in use by PID $processId ($($process.ProcessName)). Stop it or run with -Port <other>."
  }
}

function Test-PythonProcessGroup {
  param([int]$RootProcessId)

  $process = Get-Process -Id $RootProcessId -ErrorAction SilentlyContinue
  if ($process -and $process.ProcessName -match "^python") {
    return $true
  }

  $children = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ParentProcessId -eq $RootProcessId })
  foreach ($child in $children) {
    if ($child.Name -match "^python" -or (Test-PythonProcessGroup -RootProcessId $child.ProcessId)) {
      return $true
    }
  }

  return $false
}

function Stop-PythonProcessGroup {
  param([int]$RootProcessId)

  $children = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ParentProcessId -eq $RootProcessId })
  foreach ($child in $children) {
    Stop-PythonProcessGroup -RootProcessId $child.ProcessId
  }

  $process = Get-Process -Id $RootProcessId -ErrorAction SilentlyContinue
  if ($process -and $process.ProcessName -match "^python") {
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
  }
}

function Stop-PythonListenersOnPort {
  param([int]$ListenPort)

  $processIds = Get-ListenerProcessIds -ListenPort $ListenPort
  foreach ($processId in $processIds) {
    if ($processId -and (Test-PythonProcessGroup -RootProcessId $processId)) {
      Stop-PythonProcessGroup -RootProcessId $processId
    }
  }
}

function Stop-ProcessTree {
  param([int]$RootProcessId)

  $children = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ParentProcessId -eq $RootProcessId })
  foreach ($child in $children) {
    Stop-ProcessTree -RootProcessId $child.ProcessId
  }

  Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

Assert-Command "git"
Initialize-GitNetwork
$pythonExe = Resolve-Python
Import-DotEnv ".env"
Ensure-WebDependencies -PythonExe $pythonExe
Stop-CompatibleListeners -ListenPort $Port

Write-Step "Starting uvicorn at http://localhost:$Port ..."
$uvicorn = Start-Process -PassThru -NoNewWindow -FilePath $pythonExe `
  -ArgumentList @("-m", "uvicorn", "web.app:app", "--host", $HostAddress, "--port", "$Port", "--reload")

Start-Sleep -Seconds 2
if ($uvicorn.HasExited) {
  throw "uvicorn exited immediately. Check the error output above."
}

Write-Step "Watching origin/$Branch every ${IntervalSec}s. Press Ctrl+C to stop."
try {
  while ($true) {
    Invoke-GitNetwork -Arguments @("fetch", "-q", "origin", $Branch)
    if ($LASTEXITCODE -ne 0) {
      Write-Step "git fetch failed; will retry." Yellow
      Start-Sleep -Seconds $IntervalSec
      continue
    }

    $local = (& git rev-parse HEAD).Trim()
    $remote = (& git rev-parse "origin/$Branch").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $remote) {
      Write-Step "Could not resolve origin/$Branch; will retry." Yellow
      Start-Sleep -Seconds $IntervalSec
      continue
    }

    if ($local -ne $remote) {
      $mergeBase = (& git merge-base HEAD "origin/$Branch").Trim()
      if ($LASTEXITCODE -eq 0 -and $mergeBase -eq $remote) {
        Write-Step "Local HEAD is ahead of origin/$Branch. Push local commits before enabling auto-reset." Yellow
        Start-Sleep -Seconds $IntervalSec
        continue
      }

      $ts = Get-Date -Format "HH:mm:ss"
      Write-Step "[$ts] New commit found: $($local.Substring(0, 7)) -> $($remote.Substring(0, 7))" Yellow
      $changed = @(& git diff --name-only $local $remote)

      & git reset --hard "origin/$Branch"
      if ($LASTEXITCODE -ne 0) {
        Write-Step "git reset failed; will retry." Red
        Start-Sleep -Seconds $IntervalSec
        continue
      }

      if ($changed -match "pyproject\.toml") {
        Ensure-WebDependencies -PythonExe $pythonExe -Force
      }

      Write-Step "Synced to $((git rev-parse --short HEAD).Trim()). uvicorn reload will pick up changes." Green
    }

    Start-Sleep -Seconds $IntervalSec
  }
}
finally {
  if ($uvicorn -and -not $uvicorn.HasExited) {
    Write-Step "Stopping uvicorn..."
    Stop-ProcessTree -RootProcessId $uvicorn.Id
  }
  Stop-PythonListenersOnPort -ListenPort $Port
}
