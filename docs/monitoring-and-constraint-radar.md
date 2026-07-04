# 监控层与"约束雷达":预判瓶颈迁移(分析与设计方向)

> 本文档有两个用途:(1) 记录一次关于"是否/如何建立常驻监控"的分析结论;
> (2) 第 0 节是一段**独立、可直接用于与 Codex 讨论的问题陈述**。

---

## 0. 问题陈述(供讨论)

**观察。** 两三年前,CPO(共封装光学)与 HBM(高带宽内存)并未被普遍识别为算力瓶颈。漏判的根因**不是**"没有人研究这些环节",而是**没有预判到一个上游驱动的变化率**——英伟达芯片算力以超预期速度迭代——从而使"绑定约束(binding constraint)"从算力本身**迁移**到了与之相邻的显存带宽(HBM)与光互连(CPO),以及功耗/散热。

**一般化。** 一个只对"已成形的静态题材"做分析的基本面工具,恰恰对最有价值的那类变化是**结构性失明**的:**由某个被低估的上游驱动加速所引发的"绑定约束迁移"**。共识几乎总是在约束真正开始绑定之后才承认它;而到那时,超额收益已经消失。真正的 alpha 在"约束开始迁移、但共识尚未承认"的那段窗口里。

**深层问题(分层)。**
1. **认识论层**:当触发因子通常是"上游驱动的变化率被低估"而非某个离散事件时,如何**系统性地预判绑定约束下一步会迁移到哪里**,且早于共识?
2. **方法论层**:用什么纪律,把它从事后诸葛("HBM 当然会成为瓶颈")变成一个**可重复、可证伪、可校准**的前瞻流程?
3. **产品/运营层**:这是否要求工具从"一次性分析"进化为"持续运行的监视系统"?如果是,以什么**节奏**、盯**什么信号**、用什么**门控**,才能既早于共识捕捉迁移、又不淹没在噪声里?
4. **约束雷达设想**:能否为每个题材维护一张**"当前 + 潜伏候选瓶颈"的实时排名**,持续用新证据、以及被追踪的上游驱动斜率去重新打分——让"某个潜伏约束开始亮起"本身成为早期信号,而不是事后才补记?

**一句话。** 该常驻监控的不是"结论对不对",而是**"绑定约束在哪、正往哪迁移,以及哪个上游驱动的斜率正在超出基准"**。

---

## 1. 洞察的本质:约束会迁移,而我们漏的是"驱动的斜率"

- **约束会迁移(Theory of Constraints, Goldratt)。** 当一个约束被"抬升"(算力以超预期速度提升),约束必然**移动**到下一个环节(带宽 → HBM、互连 → CPO、功耗/散热)。TOC 的五步聚焦里明确:elevate 之后要回到第一步,因为约束已经变了。→ 该监控的是**约束的位置及其迁移**,不是单个环节的好坏。
- **漏的是变化率,不是事实。** 当年不是没看到 HBM/CPO 这些环节,而是**低估了上游驱动(算力迭代速度)的斜率**。→ 监控必须包含**驱动斜率追踪**(如算力/$ 的翻倍周期、模型 scaling 曲线)与"若此斜率延续,下一个先崩的是谁"的反事实扫描。

## 2. 要不要建常驻任务?要,但不是"盲目每日"

**结论:值得建一个监控层,但节奏应是"事件驱动 + 定期结构扫描 + 阈值门控告警",而非每日全量重跑。**

- 结构性瓶颈的**真信号是周/季级别**的(新财报、电话会、产能与路线图公告),日频重跑只会带来噪声、成本与**告警疲劳**——最终没人看。
- 正确的三段节奏:
  - **事件驱动**:出现新 10-K/10-Q/8-K、财报日、重大公告时触发(EDGAR 日期过滤已能做增量发现)。
  - **定期扫描**:每周一次"约束是否迁移"的结构复查。
  - **门控告警**:仅当 diff 出现实质变化、或某个 signpost 被触发、或某个**潜伏瓶颈评分上升**时才告警,且每条告警带 quote-backed 出处。

## 3. 可参考的业内方法论

| 目标 | 方法论 | 用处 |
|---|---|---|
| 提前察觉尚未成形的变化 | **Ansoff 弱信号(Weak Signals, 1975)** | 在趋势变强前捕捉;经典学术锚点 |
| 约束会迁移 | **Theory of Constraints(Goldratt)五步聚焦** | "约束雷达"的理论基础 |
| 预定义可观测指标并监控 | **Signpost / Indications & Warning(RAND 假设式规划、情报 I&W)** | 把 scenario 触发条件变成可盯的路标 |
| 系统性环境扫描 | **Horizon Scanning、Emerging Issues Analysis(Molitor)、PEST 扫描(Aguilar)** | 每周结构扫描的框架 |
| 情景 + 路标绑定 | **Shell 情景规划(Wack)、TAIDA** | 情景与监控指标挂钩 |
| 预判驱动斜率 | **能力预测 / scaling laws(Epoch AI、Kaplan/Hoffmann)、Wright's Law** | "算力这样涨,下一个瓶颈是谁" |
| 抢先估现状 | **Nowcasting** | 在官方数据前估计当前态势 |
| 分歧即 alpha | **Variant Perception / 预期投资(Steinhardt、Mauboussin)** | 只在"现实与共识背离"时告警 |
| 校准与增量更新 | **Superforecasting(Tetlock)、Brier** | 已有 calibration,监控喂回它 |

> 对本问题最"对症"的三件套:**Ansoff 弱信号 + TOC 约束迁移 + Signpost 监控**。

## 4. 映射到本引擎:缺的是"监控 loop + 约束雷达"

底座几乎都已具备:
- **已有**:`tracking_signals` / `scenario triggers`(即 signpost)、`diff`(跑次变化)、`calibration`(带日期的可检验预测 + Brier)、EDGAR 日期过滤发现、claim 抽取 + grounding(带出处)、`causal_map`(机制链,已带 quote 验证)。
- **要加的三块**:
  1. **监控 loop**:一个 watchlist(常驻题材)+ 自上次以来的增量收集(新 filing/新闻)+ 重跑 + diff + signpost 触发检测。
  2. **约束雷达 / 瓶颈迁移检测**(差异化核心):为每题材维护"当前 + 相邻/潜伏候选瓶颈"排名,每轮用新证据重新打分,**检测潜伏瓶颈评分上升 / 约束位置变化**。这把"CPO/HBM 迟早浮现"变成可观测的早期信号,而非事后追记。可复用现有 8 维瓶颈打分,并把 `causal_map` 的下游节点当作"相邻潜伏约束"的候选来源。
  3. **告警摘要(digest)**:diff/signpost 门控,只在实质变化时出一份带出处的摘要,并**回写 calibration**(某预测是否兑现)。

## 5. 纪律 / 红线

- **只在"分歧 / 迁移 / 触发"时告警**,不制造日频噪声;每条告警必须带 quote-backed 出处。
- 监控是为了**更新判断与校准**,不是刷存在感;告警口径宁缺毋滥。
- 延续"过程健康 ≠ 论点真值":约束雷达给的是"约束在动"的信号,不是"结论已变对"。
- 重活(抓取 + 抽取 + 模型)按事件触发、放到有资源与 key 的机器;调度器(systemd timer / cron)只做轻量触发,别压小 VPS。

## 6. 建议的最小形态

一个 `fre watch` / 监控 loop:**watchlist + 事件驱动增量收集 + 重跑 diff + 约束雷达(潜伏瓶颈上升检测)+ 门控告警 digest**,复用 EDGAR 发现 / claim 抽取 / grounding / diff / calibration。

## 7. 开放问题(留给与 Codex 的讨论)

1. **节奏**:纯事件驱动、周频结构扫描、还是两者结合?各自的触发条件如何定义?
2. **潜伏瓶颈来源**:相邻候选约束是人工枚举、模型生成、还是从 `causal_map` 下游节点/价值链自动派生?
3. **告警口径**:什么算"实质变化"?diff 的哪些字段、signpost 命中、评分上升多少个阈值才告警?如何治理告警疲劳?
4. **驱动斜率量化**:如何追踪"上游驱动变化率"(如算力/$ 翻倍周期)?数据源与更新方式?
5. **约束雷达评分**:如何在现有 8 维瓶颈打分之上,表达"约束正在迁移"而不仅是"某环节评分高"?
6. **校准闭环**:告警 → 生成/更新预测 → 事后兑现打分,如何自动串起来?
7. **归属与架构**:监控是引擎内的 `fre watch`(CLI + 调度),还是独立的常驻服务?与 Web 层如何衔接?

## 8. Codex 讨论后的暂定判断(2026-07-04)

### 8.1 节奏:事件发现 + 周频雷达 + 季频深度重估

不建议第一版做成"常驻大而全服务",也不建议每日全量重跑。更合适的节奏是三层:

1. **轻量日频 / 事件监听**:只做 source discovery,不重跑完整分析。触发源包括
   filing、财报、重大产品/产能公告、标准路线图、重要客户 capex 变化。
2. **周频结构扫描**:重算约束雷达,比较本周 vs 上周的 bottleneck score、
   causal edge、signpost、tracking signal。
3. **季频深度重估**:财报季后重做完整主题分析、adversarial QC 和
   calibration review。

事件驱动负责早发现,周频扫描负责结构化复核,季频重估负责校准与方法论清账。
第一版产品形态应先做可审计批处理,再升级为服务。

### 8.2 潜伏瓶颈来源:三源合成,并分层管理

相邻候选约束不应只靠模型生成,也不应只靠人工枚举。建议三源合成:

1. **人工种子**:由 domain pack / ontology 定义候选约束,例如 HBM、CoWoS、
   CPO、power、cooling、switching、substrate、EDA/IP、qualification、
   grid interconnect。
2. **自动派生**:从 `causal_map` 的 source/target、value chain 的
   upstream/enabler、profit pool 的前置条件里抽取相邻约束。
3. **模型扩展**:让模型基于机制链提出二阶候选,但必须进入 `candidate`
   状态,不能直接进入正式雷达排名。

约束池建议分三圈:

- `current_binding`:当前已绑定或市场已经承认的约束。
- `adjacent_latent`:如果当前约束被抬升,下一步最可能绑定的相邻环节。
- `second_order_external`:电网、政策、地缘、客户预算、制造交付等外生约束。

这能避免"模型想到什么就监控什么",也能避免只盯已有热门题材。

### 8.3 告警口径:只报迁移、斜率、路标、退化

告警不应是一个泛化总分,而应分为四类:

1. `constraint_migration_alert`:潜伏约束分数跨过阈值,且周环比明显上升。
2. `driver_slope_alert`:上游驱动斜率超出基准,例如算力/$、rack power、
   capex、HBM attach、lead time。
3. `signpost_alert`:已有 scenario trigger 被 quote-backed evidence 命中。
4. `thesis_degradation_alert`:新证据削弱原 thesis,或原 causal edge 失效。

每条告警至少需要:

- quote-backed 来源。
- 旧分数、新分数、变化原因。
- 影响路径:哪个 driver -> 哪个 constraint -> 哪个 segment/company。
- 反证条件:后续看到什么会撤销该告警。
- 冷却期:同一主题同一原因不要反复报。

告警级别建议三档:

- `watch`:弱信号,进入周报,不打断。
- `investigate`:多源确认或评分跨阈值,需要人工看。
- `action`:高可靠来源 + 机制链闭合 + 约束迁移影响明确。

### 8.4 第一版实现顺序

建议按以下顺序落地,避免一开始就陷入调度、Web、消息系统:

1. **`fre radar`**:读取主题,生成当前约束 + 潜伏约束排名,不接调度。
2. **`fre watch --weekly`**:watchlist + 上次 run + diff + radar delta。
3. **digest / 内控告警**:把 `watch` / `investigate` / `action` 输出成
   quote-backed 摘要,再考虑 Web 层和消息推送。

### 8.5 口径调整建议

`publishable memo` 这个 tier 名称后续建议改成 `review-ready` 或
`decision-review-ready`。监控层只应表达"约束在动、证据足够审查",
不应表达"结论可发布 / 可交易"。这与内控口径一致:系统给过程信号,
最终判断由人完成。

### 8.6 给下一位实现者的接口建议

第一轮可以新增独立模块,不要侵入既有 pipeline:

- `radar.py`:约束池、候选来源、评分、迁移 delta。
- `watch.py`:watchlist、上次运行状态、周频扫描、digest 生成。
- `configs/watchlists/*.json`:声明要监控的主题、扫描节奏、候选约束种子。
- `reports/watch/<date>/digest.md|json`:生成物,默认不提交。

与现有能力的连接点:

- 从 `theme.bottlenecks` 和 `theme.causal_map` 初始化当前约束。
- 从 `segments` / `profit_pools` / `causal_map.target` 派生潜伏约束。
- 复用 `quality_scorecard.causal_quality` 判断机制链是否足够可靠。
- 复用 `calibration` 把重要告警转成可回测预测。

## 9. Claude 的进一步意见 + v1 实现(2026-07-04)

Codex 的 Section 8 把**运营骨架**做扎实了(三段节奏、三圈候选、四类告警、落地顺序),认同。
但最难的"早于共识预判迁移"还偏薄——雷达"重打分看分数上升"是**滞后**确认。补四个齿轮:

- **A 余量比侵蚀(leading)**:下一个绑定的约束 = 相邻环节里 `capacity_growth / demand_growth`
  最小、下降最快的那个。余量比在评分/价格反映"已绑定"之前就开始下降。
- **B 斜率惊奇**:盯"实现斜率 − 论点假设斜率"这个 gap 与加速度,而非绝对水平。配版本化基准斜率库。
- **C 共识代理**:候选约束在已抓取语料里的**提及频率趋势**;"余量比侵蚀 + 提及仍低而平"= 前共识窗口 = alpha。
- **D 雷达自校准**:每条迁移判断 = 带日期的预测,事后 Brier 打分;否则雷达退化成"总能找到一个在迁移的约束"的讲故事机。
- 方法按圈分:物理约束用余量比法;`second_order_external`(电网/政策/地缘)走 signpost。
- 雷达需自己的持久化时间序列 `radar_state`(算 delta/斜率/校准的底座)。

**v1 已实现**(`src/fundamental_research_engine/radar.py` + `fre radar`,确定性、离线、不侵入 pipeline):
齿轮 **A + B + F**。`fre radar <theme> <radar_spec.json>`:三圈候选(exogenous 走 signpost)、
余量比排名、门控告警(watch/investigate/action,带 old/new ratio + driver_path + 反证条件)、
`uncovered_candidates` 提示未覆盖的 theme 派生候选、`radar_state/<theme>.json` 时序持久化。
demo(`configs/radar/hbm4.json`):HBM=0.79 为承认约束,**rack power/cooling=0.65 更紧 → action 迁移告警
"now tighter than any acknowledged constraint"**;二次运行显示 0.65→0.575 侵蚀 −0.075。

**下一增量**:C 共识代理(复用抓取语料的提及频率)→ 只在"迁移且未被定价"时升级告警;
D 雷达自校准(迁移判断 → calibration 预测 → Brier);`fre watch --weekly`(watchlist + 上次 run + diff + radar delta)+ digest;
把候选从 `causal_map.target`/`segments` 自动派生(目前仅 `uncovered_candidates` 提示)。
