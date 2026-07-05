# CLAUDE.md — fundamental-research-engine 协作约定

工程背景见 `PROJECT_CONTEXT.md`(权威、详尽)与 `README.md`。本文件只讲**你(Claude)与 Codex 同机协作**的规矩。

## 双 AI 圆桌协议
- 你和 Codex 运行在**同一台 VPS、同一个工程目录**,共享文件系统。
- 公共黑板是本目录的 `DISCUSSION.md`。协作流程:
  1. 用户把问题写进 `DISCUSSION.md` 的「🎯 当前问题」。
  2. 用户让你在「💬 讨论区」**追加**方案发言,署名 `@Claude`,标注轮次。
  3. 用户切到 Codex,让它读黑板并追加 `@Codex` 的评审/反方案。
  4. 用户再转达给你,来回 1–2 轮,直到「✅ 结论」区达成一致。
  5. 按结论分工改代码,另一方 `git diff` review,结果回填「🔬 验证记录」。
- **只追加,不改删 Codex 或用户的发言。** 发言格式见 `DISCUSSION.md` 内注释。

## 机器约束(重要)
- 这台 VPS 仅 1G 内存,同时跑 Claude + Codex 时可用内存很紧。
- **讨论/小改在 VPS;大编译、全量测试、数据回填等重活下发用户 Windows 本机跑**,结果回填黑板。别在 VPS 上跑吃内存的批处理。

## 工程速览
- Python 项目(`pyproject.toml`),CLI 名 `fre`,`run.sh` / `run.bat` 入口。
- 源码 `src/fundamental_research_engine/`,配置 `configs/`,产出 `reports/` `runs/`。
- 有 `fre watch` 周报闭环、EDGAR 采集、四路雷达等模块(详见 PROJECT_CONTEXT.md)。
