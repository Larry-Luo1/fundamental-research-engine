# 编辑机 / 运行机分离：git 驱动的 reload debug 循环

用于快速反复 debug：代码在 **VPS（Claude + Codex）** 上改，前后端在 **Windows 运行机** 上跑，GitHub 做中转。

这不是公网隧道、反向代理或 VPN；它是一条“代码同步通道”：
VPS 改代码并 push 到 GitHub，Windows 运行机自动跟随 `origin/main`，本地 `uvicorn --reload` 负责热重启。浏览器仍然访问 Windows 本机的 `http://localhost:8000`。

```
编辑机 = 美国 VPS(Claude+Codex)      GitHub(中转)         运行机 = Windows 本机
   改代码  ── git push ──────────────→  origin/main  ──────────→ 自动 reset --hard + uvicorn --reload
                                                                  ↑ 浏览器 http://localhost:8000
```

## 角色与铁律
- **编辑机(VPS)**:唯一改代码的地方。Claude/Codex 改完 `git push origin main`。
- **运行机(Windows)**:**只读消费者**,永不在此改代码。用 `git reset --hard origin/main` 跟随,冲突免疫。
- **工程形态**:FastAPI + uvicorn,前端是 `web/static/index.html` 静态页,前后端一体,一条 uvicorn 全起。

## 运行机（Windows）用法
日常只需要一条命令：
```powershell
powershell -ExecutionPolicy Bypass -File runner-windows.ps1
```

脚本会自动做这些事：
- 优先使用本仓库 `.venv\Scripts\python.exe`；没有 `.venv` 时自动创建。
- 自动安装 Web 依赖：`.[web]` 和 `uvicorn[standard]`。
- 自动读取 `.env`；没有 `.env` 时从 `.env.example` 创建。
- 默认只监听 `127.0.0.1:8000`，避免把服务暴露到公网网卡。
- 如果 8000 端口已经被旧 Python 服务占用，默认会先停止旧监听，避免“一闪而退”。
- 每 3 秒 `git fetch origin main`，发现新提交就 `git reset --hard origin/main`。
- 如果本地有尚未推送的提交领先远端，脚本会暂停自动 reset 并提示先推送，避免把本地修复擦掉。
- 如果 `pyproject.toml` 变了，会自动重装依赖。

启动成功后访问：
```text
http://localhost:8000
```

如果要临时换端口：
```powershell
powershell -ExecutionPolicy Bypass -File runner-windows.ps1 -Port 8001
```

如果希望脚本只检查环境、不自动安装依赖：
```powershell
powershell -ExecutionPolicy Bypass -File runner-windows.ps1 -NoInstall
```

## Linux 运行机等价(备用)
```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload &
while true; do
  git fetch -q origin main
  [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ] && git reset --hard origin/main
  sleep 3
done
```
运行机用只读 deploy key 即可（不需要 push 权限）。

## 进阶(可选)
3 秒轮询已够 debug。要更实时可上 GitHub webhook / Actions 触发即时 pull,但需运行机有可达端点,先不必。
