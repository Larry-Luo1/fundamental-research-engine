# 编辑机 / 运行机分离 —— git 驱动的 reload debug 循环

用于快速反复 debug:代码在 **VPS(Claude + Codex)** 上改,前后端在 **Windows 运行机**上跑,
GitHub 做中转。改 → push → 运行机自动拉取 + 热重启 → 刷浏览器看效果。

```
编辑机 = 美国 VPS(Claude+Codex)      GitHub(中转)         运行机 = Windows 本机
   改代码  ── git push ──────────────→  origin/main  ──────────→ 自动 reset --hard + uvicorn --reload
                                                                  ↑ 浏览器 http://localhost:8000
```

## 角色与铁律
- **编辑机(VPS)**:唯一改代码的地方。Claude/Codex 改完 `git push origin main`。
- **运行机(Windows)**:**只读消费者**,永不在此改代码。用 `git reset --hard origin/main` 跟随,冲突免疫。
- **工程形态**:FastAPI + uvicorn,前端是 `web/static/index.html` 静态页,前后端一体,一条 uvicorn 全起。

## 运行机(Windows)用法
首次准备见 `runner-windows.ps1` 顶部注释(clone、`pip install -e .`、`uvicorn[standard]`、`.env`)。
日常一条命令:
```powershell
powershell -ExecutionPolicy Bypass -File runner-windows.ps1
```
它会:① 起 `uvicorn web.app:app --reload`;② 每 3 秒 `git fetch`,发现新提交就 `reset --hard` +(依赖变了才)重装。
后端改动 uvicorn 自动重启;前端静态页刷新浏览器即可。

## Linux 运行机等价(备用)
```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload &
while true; do
  git fetch -q origin main
  [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ] && git reset --hard origin/main
  sleep 3
done
```
运行机用只读 deploy key 即可(不需要 push 权限)。

## 进阶(可选)
3 秒轮询已够 debug。要更实时可上 GitHub webhook / Actions 触发即时 pull,但需运行机有可达端点,先不必。
