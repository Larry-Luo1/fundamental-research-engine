# 质量门(Quality Gate)实现设计

> 目标:把"分析质量"从一次性输出变成流水线内建的**质量闭环**——提高单次质量、并随时间保持。
> 本设计覆盖第 1 步:**接地检查 + 多镜头对抗式 critique + 质量记分卡**。

## 0. 原则(不可动摇)

1. **质量信号 ≠ 论点真值**。所有分数只衡量研究流程健康度,不替代判断。记分卡显式标注。
2. **默认非阻断**。延续现有 `critique` 从不阻断的立场——质量门产出结论,由人决定是否采纳。`--strict` 才阻断。
3. **确定性优先**。接地检查与记分卡聚合**无需 LLM、可离线、进 CI**;只有对抗式 QC 需要模型,单独触发。
4. **复用引擎,不重写**。接现有 `evidence.py`/`critique.py`/adapters/流水线。

## 1. 现状可复用组件

| 组件 | 现状 | 在质量门中的角色 |
|---|---|---|
| `evidence.build_evidence_audit` | owner 级 coverage、claim 链接、`_RELIABILITY_WEIGHTS`、summary | 接地检查的数据源 |
| `models.Evidence` | 带 `reliability`、`claims` | 接地/三角验证的基础 |
| `models.Bottleneck/CompanyPosition` | 带 `evidence_ids` | owner→证据链接 |
| `critique.py` + `prompts/critique.md` | 单阶段、模型驱动、结构化 concerns | 对抗式 QC 的模板 |
| `cli._complete_json_with_retry` / `_parse_model_json` | JSON 提取 + 校验重试 | 对抗式 QC 复用 |
| `adapters.get_adapter` | Claude/OpenAI/manual | 对抗式 QC 的模型调用 |
| `pipeline.build_analysis` / `run_pipeline` | 组装 analysis.json + memo | 记分卡嵌入点 |
| `diff.py` + `tracking_signals` + `as_of` | 跑次比对 | 对接后续校准闭环(Step C) |

## 2. 三部分设计

### A. 接地检查(确定性,新增 `src/fundamental_research_engine/quality.py`)

对整份 analysis 计算每个"论断所有者"(owner: bottleneck / company;可选扩展到 thesis/scenario)的接地质量:

- **grounded**:owner 至少链接 1 条证据。
- **corroborated(三角验证)**:owner 被 **≥2 个独立来源**支撑(按 `source_type` 或来源 URL/标题去重)。
- **reliability**:owner 所链证据的最高/加权可靠度(复用 `_RELIABILITY_WEIGHTS`)。
- **thin**:仅单一来源支撑。
- **ungrounded**:零证据。

聚合出接地摘要:
```json
"grounding": {
  "owners": [
    {"id":"bn-hbm4-...","kind":"bottleneck","name":"...",
     "evidence_count":4,"distinct_sources":3,"distinct_source_types":2,
     "reliability_max":"high","grounded":true,"corroborated":true}
  ],
  "ungrounded": ["co-foo"],
  "thin": ["co-bar"],
  "reliability_weighted_coverage": 0.78,
  "summary": {"owners":7,"grounded":6,"corroborated":4,"ungrounded":1,"thin":1}
}
```

**可选 schema 扩展(建议但非必需)**:给 `theme.thesis` 与每个 `scenario` 加可选 `evidence_ids`,让核心论断与情景也能被接地检查覆盖。向后兼容(缺省=当前行为),在 `validation.py` 与 `models.py` 增加可选字段。

### B. 对抗式 QC(LLM,`quality.py` + `prompts/quality_review.md`)

对**整份组装后的 analysis**(跨阶段)跑多镜头审查,每个镜头产出结构化结论:

| 镜头 | 方法论 | 检什么 |
|---|---|---|
| `premortem` | Klein pre-mortem | 假设一年后论点错了,最可能的失败原因 |
| `steelman_bear` | Munger inversion / variant perception | counter_theses 是否是稻草人?给出最强空头版本与关键证伪点 |
| `consistency` | 逻辑闭合 | 机制链是否真支撑瓶颈?情景是否覆盖 counter-theses?打分是否有证据基础? |
| `unsupported_claims` | Popper 可证伪 / Mosaic | 列出无证据支撑的核心论断(与 A 的确定性结果交叉印证) |

输出契约(新增 `validate_quality_review_shape`,风格对齐 `validate_critique_shape`):
```json
{
  "lenses": {
    "premortem": {"findings":[{"target":"<owner id 或 'thesis'>","failure_mode":"...","severity":"high|medium|low","suggested_fix":"..."}]},
    "steelman_bear": {"counter_thesis_strength":"weak|moderate|strong","strongest_disconfirmers":["..."],"assessment":"..."},
    "consistency": {"issues":[{"between":["mechanism","bottleneck"],"issue":"...","severity":"..."}]},
    "unsupported_claims": {"items":[{"location":"<owner id/字段>","claim":"...","severity":"..."}]}
  },
  "open_concerns": [{"severity":"...","target":"...","issue":"...","suggested_fix":"..."}],
  "recommendation": "accept|revise"
}
```

实现:单次 LLM 调用、一个模板返回上述多段结构(接线简单);后续可拆成每镜头独立调用 + **对抗式验证**(每个 finding 由独立"怀疑者"复核,多数否决则剔除,降低误报)。复用 `_complete_json_with_retry`。

### C. 质量记分卡(确定性聚合,嵌入 analysis.json + memo)

把 A(确定性)与 B(若已跑)聚合成一张记分卡:
```json
"quality_scorecard": {
  "grounding_score": 0.78,
  "disconfirmation": {"premortem_done":true,"steelman_done":true,"open_critical":0,"open_major":2},
  "calibration": {"track_record_runs":0,"brier":null},
  "flags": ["thesis 无链接证据","co-foo 零证据支撑"],
  "note": "过程健康信号,非论点真值"
}
```
- `grounding_score` 来自 A 的 `reliability_weighted_coverage` 与三角验证比例。
- `disconfirmation` 来自 B(若未跑对抗式,标 `*_done:false`)。
- `calibration` 现在留**占位**,读取(若存在)该主题的 `track_record.json`——**这是给后续 Step C(校准闭环)预留的接口**,现在写 null。
- `flags` 由 A 的 ungrounded/thin + B 的 open critical 汇总。

## 3. 一个小重构(先做,降耦合)

把 `cli._parse_model_json` / `_complete_json_with_retry` / `CompletionAttempt` 抽到新模块 `src/fundamental_research_engine/llm_json.py`,`cli.py` 与 `quality.py` 共同导入。避免 `quality.py` 依赖 `cli` 私有函数。纯搬迁,行为不变,现有测试覆盖不动。

## 4. CLI 与门禁策略

新增命令:
```bash
# 完整质量门(接地 + 对抗式 + 记分卡),写 qc.json;需要模型
fre qc configs/themes/hbm4.json --model claude --model-name claude-opus-4-8 [--out qc.json]

# 仅确定性接地 + 记分卡(无 LLM,可离线/进 CI)
fre qc configs/themes/hbm4.json --grounding-only
```
- `fre run` 默认**内嵌确定性接地记分卡**(无 LLM,不改变离线/CI 行为);对抗式部分仅在 `fre qc` 跑。
- 门禁:默认非阻断。`fre qc --strict` 在"接地分 < 阈值"或"存在 open critical"时返回非零退出码(供 CI/发布卡口按需启用)。

## 5. 与现有流程衔接

- `pipeline.build_analysis`:追加确定性 `quality_scorecard`(仅接地部分)。
- `render.py`:memo 增加 "Quality Scorecard" 段(接地率、未接地/单源清单、免责声明)。
- `diff.py`:把 `quality_scorecard.grounding_score` 纳入跑次比对,长期观察质量是否退化(呼应"保持")。
- `qc.json` 与其余生成物一样在 `runs/` 下、被 git 忽略。

## 6. 测试策略

- **确定性部分(A + 记分卡)**:纯单测,构造带/不带证据的主题,断言 grounded/corroborated/ungrounded/thin 与分数;进 CI。
- **对抗式部分(B)**:注入 fake adapter(返回定制 JSON),测 `validate_quality_review_shape`、JSON 提取重试、记分卡聚合;**不触网**,CI 保持 hermetic(与现有 evidence fetch 测试同策略)。
- 更新 golden memo 快照(memo 新增记分卡段)。

## 7. 构建顺序(全部已完成)

1. ✅ 小重构:抽 `llm_json.py`(纯搬迁 + 现有测试跑绿)。
2. ✅ `quality.py` 接地检查 + 确定性记分卡;`build_analysis`/`render` 内嵌;单测 + golden 更新。
3. ✅ `prompts/quality_review.md` + `validate_quality_review_shape` + 对抗式 QC;fake-adapter 单测。
4. ✅ `fre qc` CLI(完整 / `--grounding-only` / `--review` / `--strict`)。
5. ✅ schema 扩展:`thesis_evidence_ids` + scenario `evidence_ids`(可选、向后兼容,`OPTIONAL_STAGE_FIELDS`)。
6. ✅ 校准闭环:`calibration.py` + `fre calibrate`(register/resolve/show)+ `fre qc --track-record`,记分卡 `calibration` 由占位变为真实 track record(counts + resolution rate + Brier)。

> 对抗式 QC 的模型路径目前仅 fake-adapter 单测覆盖;真实模型联调需带 `ANTHROPIC_API_KEY` 的环境。

## 8. 守住的红线

- 记分卡永远标注"过程健康,非真值"。
- 对抗式 QC 默认不改写、不阻断 `run`/`fill`/`draft` 输出——人决定是否采纳(与现有 `critique` 一致)。
- 确定性部分零新增依赖、可离线、进 CI;LLM 部分单独触发、测试用 fake adapter。

## 9. Causal Map 质量扩展(2026-07-04)

`causal_map` 已接入确定性质量门。目标是让"产业链机制洞察"不只停留在
叙述层,而是逐条边检查证据强度。

新增检查项:

- 每条 causal edge 的 `claim_ids` 是否能解析到主题内 `E*.C*` 声明,或
  解析到 `data/evidence/<theme>/claims.json` 里的候选 `E*.Q*` provenance。
- 每条边是否有 quote-verified provenance。没有 sidecar 时不阻断运行,但会
  在 `quality_scorecard.flags` 中明确暴露。
- 每条边是否只由单一来源支撑。
- 每条边是否低置信度;低置信边会被标记为不应支撑高确信 thesis。
- causal map 级别汇总:总边数、supported、fully_quote_verified、thin、
  low_confidence、missing_claims、weak_evidence。

接入点:

- `quality.build_causal_quality(...)`:纯确定性检查。
- `pipeline.load_claim_provenance(...)`:可选读取
  `data/evidence/<theme>/claims.json` sidecar。
- `pipeline.build_analysis(...)` 和 `fre qc`:都把 causal quality 合并进
  `quality_scorecard`。
- `render.py`:memo 的 Quality Scorecard 增加 causal edge 汇总,详细问题仍
  汇总在 Quality Flags。
