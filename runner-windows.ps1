#Requires -Version 5
<#
  runner-windows.ps1 — 运行机(Windows)一键运行:自动跟随 GitHub + FastAPI 热重载

  用途:在「运行机」上把本工程前后端跑起来,并每 N 秒跟随 origin/main。
        编辑机(VPS 上的 Claude/Codex)push 后,这里自动 git reset --hard
        并触发 uvicorn --reload 重启 —— 刷新浏览器即可看到改动。

  首次准备(只做一次):
        git clone git@github.com:Larry-Luo1/fundamental-research-engine.git
        cd fundamental-research-engine
        python -m pip install -e .
        python -m pip install "uvicorn[standard]"     # --reload 依赖 watchfiles
        copy .env.example .env   （按需填好密钥）

  运行:  powershell -ExecutionPolicy Bypass -File runner-windows.ps1
  访问:  http://localhost:8000

  铁律:  本机是「只读消费者」,永远不要在这里改代码。
         同步用 reset --hard(不是 pull/merge),对冲突免疫。
#>
param(
  [int]$Port = 8000,
  [string]$Branch = "main",
  [int]$IntervalSec = 3
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "启动 uvicorn(热重载) http://localhost:$Port ..." -ForegroundColor Cyan
$uvicorn = Start-Process -PassThru -NoNewWindow python `
  -ArgumentList "-m","uvicorn","web.app:app","--host","0.0.0.0","--port","$Port","--reload"

Write-Host "进入同步循环:每 ${IntervalSec}s 检查 origin/$Branch,Ctrl+C 退出。" -ForegroundColor Cyan
try {
  while ($true) {
    git fetch -q origin $Branch
    $local  = (git rev-parse HEAD).Trim()
    $remote = (git rev-parse "origin/$Branch").Trim()
    if ($local -ne $remote) {
      $ts = Get-Date -Format "HH:mm:ss"
      Write-Host "[$ts] 新提交,同步 $($local.Substring(0,7)) -> $($remote.Substring(0,7))" -ForegroundColor Yellow
      $changed = git diff --name-only $local $remote
      git reset --hard "origin/$Branch"
      if ($changed -match "pyproject\.toml") {
        Write-Host "  依赖变化,重装…" -ForegroundColor Yellow
        python -m pip install -e . -q
      }
      Write-Host "  已同步到 $((git rev-parse --short HEAD).Trim()),uvicorn 自动重启中。" -ForegroundColor Green
    }
    Start-Sleep -Seconds $IntervalSec
  }
}
finally {
  if ($uvicorn -and -not $uvicorn.HasExited) {
    Write-Host "停止 uvicorn…" -ForegroundColor Cyan
    Stop-Process -Id $uvicorn.Id -Force -ErrorAction SilentlyContinue
  }
}
