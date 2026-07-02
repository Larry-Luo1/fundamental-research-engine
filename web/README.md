# Web UI — 部署与使用

一个可选的网页前端：在**一台服务器**上运行工程本体，所有人用**浏览器**访问，通过「引导式对话」构建结构化基本面分析并查看研究备忘录。

核心引擎保持零依赖；只有这一层需要 `fastapi`/`uvicorn`（通过 `web` 可选依赖安装）。

---

## 一键部署

前置条件：目标机器装有 **Python 3.10+**。Ubuntu 上还需 venv 支持（`sudo apt install python3-venv`）；Windows 用 python.org 官方安装包自带。

### Ubuntu / Linux / macOS
```bash
git clone <repo-url>
cd fundamental-research-engine
./deploy.sh          # 建 venv、装依赖、生成 .env
nano .env            # 填 FRE_WEB_PASSWORD 和 ANTHROPIC_API_KEY
./run.sh             # 启动，默认 http://0.0.0.0:8000
```

### Windows
```bat
git clone <repo-url>
cd fundamental-research-engine
deploy.bat
notepad .env         REM 填 FRE_WEB_PASSWORD 和 ANTHROPIC_API_KEY
run.bat
```

浏览器打开 `http://<服务器IP>:8000`，输入共享口令即可。

---

## 配置（.env）

| 变量 | 必填 | 说明 |
|---|---|---|
| `FRE_WEB_PASSWORD` | ✅ | 所有人登录用的共享口令 |
| `ANTHROPIC_API_KEY` | ✅（用 LLM 时） | 服务器统一一个 key，所有用户共享。只看报告/跑现成主题不需要 |
| `FRE_MODEL_NAME` | | 模型 id，默认 `claude-opus-4-8` |
| `FRE_MAX_CONCURRENCY` | | 同时进行的起草任务数，小机器保持 1-2 |
| `FRE_MAX_TOKENS` | | 单次输出 token 上限，默认 16000 |
| `PORT` / `FRE_HOST` | | 监听端口/地址 |
| `FRE_WEB_DATA_DIR` | | 会话与产物存放目录，默认 `./web_data` |
| `FRE_MODEL` + `OPENAI_API_KEY` | | 设 `FRE_MODEL=openai` 可改用 OpenAI |

---

## 使用流程（引导式主题构建）

1. **新建分析**：输入一句话主题描述（如「HBM4 在 2026-2027 是否仍是 AI 基础设施核心瓶颈」）。
2. 后台自动分 **6 个阶段**（theme_definition → mechanism → bottleneck → value_chain → company → scenario）用模型起草，网页**实时显示进度**（SSE 流式）。
3. 校验通过后**运行流水线**，生成 `memo.md` + `analysis.json`。
4. **查看结果**：论点、瓶颈评分表、公司卡位、证据审计、完整备忘录。
5. **迭代**：对任一阶段点「审阅(critique)」做对抗式评审，或「优化(refine)」给出修改说明→重新起草该阶段并重跑，产出新 run（含与上次的 diff）。

每个用户/会话的产物隔离在 `web_data/sessions/<id>/`，互不覆盖。

---

## 并发（小团队 2-3 人同时问答）

- 不同人各做各的分析：会话在磁盘上隔离，异步服务器 + 线程池让 LLM 调用互不阻塞。
- **同一个分析的所有写操作（起草/critique/refine）串行化**（每 session 一把锁），两人或双击同一分析不会损坏 `meta.json`/阶段文件。
- 全局并发闸 `FRE_MAX_CONCURRENCY`（默认 4）限制同时进行的起草/优化数量；排队时网页显示"等待空闲槽位"。真正的天花板通常是 Anthropic 账号速率限制，而非本机。
- 团队共享一个会话池（互相可见），符合小团队协作；如需按人隔离再另加身份层。
- 依赖单 worker 保证进程内锁/闸有效——扩多进程/多机前需改用外部锁。

## 架构与注意事项

- Web 层（`web/`）直接 `import` 引擎的 `pipeline`/`diff`/`evidence`/`adapters`，复用其起草与流水线逻辑，不重写研究逻辑。
- 单 worker 运行以保证进程内会话/任务状态一致；LLM 调用通过线程池执行、并发受 `FRE_MAX_CONCURRENCY` 限制，适合小服务器。
- **打分/覆盖率是流程健康信号，不是论点真值**——网页上也如此标注。
- 生产环境建议放在反向代理（nginx/Caddy）后加 HTTPS；共享口令仅作轻量门禁，不是强鉴权。

---

## 关于这台构建机

本仓库当前所在的 1G VPS 缺少 `pip`/`venv`，无法在此做完整的 HTTP 联调；已在此完成语法编译 + 引擎集成层（auth/config/service/流水线→产物）的离线冒烟测试。目标机器只要满足「Python 3.10+ 且有 venv」即可一键部署。
