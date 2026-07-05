# 远程查看 Windows 运行日志

这个工程现在支持把 Windows 运行机上的前后端日志，通过一条窄口径、只读的反向隧道给 VPS 查看。VPS 可以用 `curl` 读日志，但不会获得 Windows shell。

## 记录哪些日志

- `web_data/logs/runner.log`：`runner-windows.ps1` 生命周期和 git 同步状态。
- `web_data/logs/uvicorn.out.log`：FastAPI/uvicorn stdout 和 access log。
- `web_data/logs/uvicorn.err.log`：FastAPI/uvicorn stderr 和 traceback。
- `web_data/audit/events.jsonl`：结构化维测事件。
- 前端 JavaScript 报错会在登录后上报到 `/api/client-log`，并以 `client_log` 写入审计日志。

审计日志面向维测，只记录状态、耗时、hash、ID 和短错误摘要，不应记录 API Key、prompt 或模型原文。

## Windows 侧启动

先启动正常运行机：

```powershell
powershell -ExecutionPolicy Bypass -File runner-windows.ps1
```

再另开一个窗口启动日志通道：

```powershell
powershell -ExecutionPolicy Bypass -File start-remote-log-channel.ps1
```

脚本会在 Windows 本机启动只读日志服务 `127.0.0.1:19024`。如果能找到已有 Claude/VPS 隧道配置，会同时建立：

```text
VPS 127.0.0.1:19024 -> Windows 127.0.0.1:19024
```

如果没有自动配置，可以显式传入 VPS：

```powershell
powershell -ExecutionPolicy Bypass -File start-remote-log-channel.ps1 -VpsUser claude -VpsHost <vps-host> -VpsPort 8443
```

只在本机测试，不连 VPS：

```powershell
powershell -ExecutionPolicy Bypass -File start-remote-log-channel.ps1 -NoTunnel
```

## VPS 侧查看

日志通道连上后，在 VPS 上执行：

```bash
curl http://127.0.0.1:19024/logs
curl "http://127.0.0.1:19024/tail?file=all&lines=100"
curl "http://127.0.0.1:19024/tail?file=runner&lines=200"
curl "http://127.0.0.1:19024/tail?file=uvicorn-out&lines=200"
curl "http://127.0.0.1:19024/tail?file=uvicorn-err&lines=200"
curl "http://127.0.0.1:19024/tail?file=audit&lines=200"
```

可用的 `file` 值：

- `runner`
- `uvicorn-out`
- `uvicorn-err`
- `remote-log-server-out`
- `remote-log-server-err`
- `audit`
- `all`

## 注意

- 保持日志通道窗口打开；关闭窗口会停止本地日志服务和反向隧道。
- 反向隧道使用 `ssh -R`，所以 VPS 访问的是 `http://127.0.0.1:19024/...`。
- Windows 上的日志服务只绑定 `127.0.0.1`，不会直接暴露到局域网或公网。
