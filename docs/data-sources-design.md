# 真实数据源实现设计:EDGAR 源发现 + 自动 claim 抽取

> 目标:补上当前证据体系最大的两个缺口——**没有源发现**(源要么手写 URL,要么模型建议 URL 有幻觉)和**没有自动"文本→claim"抽取**(抓来的原文只存不解析)。
> 两步都接现有 `evidence.py` / 证据库 / 审计 / grounding,产出与手工著录的 `evidence[]` **同形**,直接进流水线。

## 0. 原则(延续现有取向)

1. **可审计优先**:每条源可追溯(EDGAR accession/URL),每条 claim 必须绑定源文里的**逐字引文**。
2. **反幻觉是确定性守卫**:claim 的引文必须在抓取文本中**逐字命中**,命不中即丢弃/标记——不靠模型自证。
3. **人审后入库**:发现和抽取默认**只产出候选**,不自动写进主题(与 `critique`/`qc` 一致)。`--apply` 才落库。
4. **合法与合规**:仅 http/https,遵守 robots;EDGAR 用 SEC 要求的 User-Agent(含联系方式)+ ≤10 req/s。
5. **零新增依赖**:stdlib `urllib` + 现有 adapter;HTTP 与模型全可注入,测试 hermetic。

## 1. 现状衔接点

| 现有组件 | 复用方式 |
|---|---|
| `models.Evidence` `{id,title,source_type,date,url,reliability,claims[]}` | 发现/抽取的输出目标形状 |
| `evidence.default_fetch` (robots-aware, stdlib, HTML→text, 失败回退) | 抓取 EDGAR 文档正文 |
| `evidence.write_evidence_store` / `fre evidence-sync` | 候选源与 claim 落 `data/` 存储 |
| `evidence.build_evidence_audit` | 新证据自动进审计盘点 |
| `quality.build_grounding`(接地/三角验证/可靠度) | claim 一填,grounding 分自然上升 |
| `llm_json.complete_json_with_retry` | claim 抽取的 JSON 提取+校验重试 |
| `primer.py` suggested_sources | 用 EDGAR 真实命中**替换**模型幻觉 URL |
| `knowledge/ontology.json` | (可选)新增 `source_types` 受控词表 |

---

## 2. 设计一:EDGAR 源发现(免密、一手财报)

新增 `src/fundamental_research_engine/edgar.py`。SEC 的 EDGAR 提供**免密 JSON API**,是"无搜索发现"缺口最实的补法。

### 用到的 SEC 端点(均免密)
- 全文检索:`https://efts.sec.gov/LATEST/search-index?q=<query>&forms=<10-K,...>&startdt=<YYYY-MM-DD>&enddt=<YYYY-MM-DD>`
  返回 `hits.hits[]`,每条 `_id = "<accession-with-dashes>:<primary-doc>"`,`_source` 含 `display_names`(公司)、`cik`、`file_date`、表单类型。覆盖 2001 年至今。
- 文档正文:`https://www.sec.gov/Archives/edgar/data/<cik>/<accession-no-dashes>/<primary-doc>`
- (可选)公司过滤:`https://data.sec.gov/submissions/CIK<10位补零>.json`;`ticker→CIK`:`https://www.sec.gov/files/company_tickers.json`

### 硬性合规
- **User-Agent 必填**(SEC 政策):`FRE_SEC_USER_AGENT` 环境变量,默认 `"fundamental-research-engine <contact-email>"`,缺失联系方式则打警告。
- **限速** ≤10 req/s:一个简单的单调时钟节流器(CLI/service 上下文用 `time.monotonic`+`sleep`,可注入 no-op 供测试)。

### 接口
```python
def search_filings(query, *, forms=None, date_from=None, date_to=None, limit=10,
                   http_get=default_edgar_get) -> list[dict]:
    """返回归一化命中:{adsh, cik, form, filed, company, title, url}。url 指向主文档。"""

def filing_to_evidence(hit, *, evidence_id, reliability="high") -> dict:
    """把命中转成 evidence 同形记录:
       {id, title, source_type:"regulatory_filing", date:filed, url, reliability, claims:[]}。"""

def fetch_filing_text(hit, fetch=default_fetch) -> str:
    """抓取主文档正文(复用 default_fetch 的 HTML→text)。供 claim 抽取用。"""
```
`default_edgar_get(url)`:urllib GET + SEC User-Agent + 节流 + JSON 解析;可注入。

### CLI
```bash
# 只发现,产出 evidence 候选(不入库):
fre sources search "high bandwidth memory qualification" --forms 10-K,10-Q \
  --from 2025-01-01 --limit 8 [--out sources.json]
```
输出一组 evidence 同形记录 + 命中摘要;分析师挑选后可手工并入某主题的 `scenario_analysis.evidence`,或交给设计二直接抽 claim。

### 与现有的衔接
- **Primer**:`primer.build_primer` 的 `suggested_sources` 从"模型给 URL"升级为"EDGAR 真实命中",消除幻觉 URL。
- **evidence-sync**:新增 `fre evidence-sync <theme> --discover-edgar "<query>"`,把命中并入候选源再抓取。

### 测试(hermetic + 一次真实冒烟)
- 注入 `http_get` 返回**固定的 EFTS JSON** → 断言 `search_filings` 归一化、`filing_to_evidence` 形状、URL 拼接正确。
- 节流器用注入的假时钟测(不真 sleep)。
- **一次性真实冒烟**(本机网络通、EDGAR 免密):对 efts.sec.gov 跑一次真实查询,证明端点可用;CI 不依赖网络。

---

## 3. 设计二:自动 claim 抽取(文本 → 结构化 claim)

新增 `src/fundamental_research_engine/claims.py` + `prompts/claim_extraction.md`。这是把"抓来的原文"变成 `evidence[].claims` 的关键一步,也是当前最大的人工瓶颈。

### 流程
1. 取源文本(EDGAR 主文档 / 已抓取的 raw_source / 任意 URL)。
2. **LLM 抽取**(复用 `complete_json_with_retry`):给定源文本 + 主题/owner 上下文,抽出原子、可核验的 claim。**硬规则:只能用文本内的信息,每条 claim 必须附一段源文里的逐字引文。**
3. **反幻觉引文核验(确定性)**:对每条 claim,把其 `quote` 归一化空白后在源文本里做**逐字子串匹配**;命不中的 claim **丢弃并计数**(而非保留)。这是核心质量守卫。
4. 输出:核验通过的 claim。

### 输出契约(`validate_claims_shape`,风格对齐 `validate_critique_shape`)
```json
{
  "claims": [
    {"text": "atomic checkable claim",
     "quote": "verbatim snippet copied from the source",
     "confidence": "high|medium|low",
     "bears_on": ["<bottleneck/company/thesis id 或 'thesis'>"]}
  ]
}
```

### 接口
```python
def extract_claims(source_text, adapter, *, context, prompts_dir, max_attempts=2) -> dict:
    """返回 {claims:[...], dropped_unverified:int}。dropped 是引文未命中被丢弃的数量。"""

def verify_quotes(claims, source_text) -> tuple[list, int]:
    """确定性:保留 quote 在 source_text 中逐字命中的 claim;返回 (kept, dropped_count)。"""
```

### 数据落点(不破坏现有 schema)
- 主题的 `evidence[].claims` **保持 `list[str]`**(仅 claim 文本)——审计的 `E1.C1` 链接与现有测试不变。
- `fre extract-claims --out` 仍产出候选报告;`--apply` 只把核验后的 claim 文本写回 `evidence[].claims`。
- `fre extract-claims --store` 会把富信息(quote/confidence/bears_on/verified/source_sha256/extracted_at/model)同步进 `data/evidence/<theme>/claims.json` 扩展字段,作为 provenance 侧车。
- 已写回主题的 claim 保持 `E1.C1` 这类稳定 id;尚未写回主题但已核验的候选 claim 以 `E1.Q1` 这类 `status:"candidate"` 记录进入 sidecar。
- 这样 grounding/audit 契约不动,同时逐步补上"每条 claim 背后的逐字出处"。

### CLI
```bash
# 抽取并核验,默认只产出候选(人审):
fre extract-claims <theme> --source <evidence_id|url> --model claude --model-name claude-opus-4-8
# 审核后写回 scenario_analysis.evidence[].claims:
fre extract-claims <theme> --source <evidence_id> --apply
# 同步写入 quote provenance sidecar:
fre extract-claims <theme> --source <evidence_id> --claims <report.json> --apply --store
```
默认**不自动写主题**(与项目立场一致);`--apply` 才落库。也可挂在 `evidence-sync --fetch-sources --extract-claims` 上做批量。

### 闭环价值
- claim 一填,`build_evidence_audit` 的覆盖率与 `build_grounding` 的接地分**如实上升**——而且是**逐字引文支撑的上升**,不是灌水。
- 引文核验 = 确定性反幻觉守卫,与质量门"过程健康、非真值"的哲学一致:抽取可审计、可复算。

### 测试(hermetic)
- 假 adapter 返回固定 claims JSON;`verify_quotes` 用"引文在/不在源文"两种 claim → 断言保留/丢弃与 `dropped` 计数。
- `validate_claims_shape` 单测;`--apply` 写回后 `validate_theme_dict` 仍通过。

---

## 4. 可选小步:`source_types` 受控词表

给 `ontology.json` 加 `source_types`(如 `company_disclosure / regulatory_filing / industry_research / official_report / reference / news`),在 `validation.py`/`stages.py` 用 `_check_enum` 校验 `evidence[].source_type`。让手工著录、EDGAR 发现、claim 抽取三方用一致标签。向后兼容:枚举为空则不校验(与现有 enum 处理一致)。

## 5. 构建顺序

1. ✅ `edgar.py` + `default_edgar_get` + 节流器;`search_filings`/`filing_to_evidence`/`fetch_filing_text`;`fre sources search`;注入式单测 + 一次真实冒烟。**已完成**:真实 EDGAR 全文检索 → evidence 同形记录 → 构造的 Archives URL 经 `fetch_filing_text` 验证可解析(拉到真实 10-K 正文,查询词命中)。
2. ✅ `claims.py` + `prompts/claim_extraction.md` + `validate_claims_shape` + `verify_quotes`(确定性反幻觉);`fre extract-claims`(默认候选,`--apply` 落库);fake-adapter/CLI 单测。**已完成**:支持本地 source text、URL/evidence id 抓取、manual prompt、模型直接抽取、预生成 JSON/report 复用和逐字 quote 二次核验。
3. 衔接:primer `suggested_sources` 用 EDGAR 命中;`evidence-sync --discover-edgar` / `--extract-claims`;批量生成候选报告后人审入库。
4. (可选)`source_types` 受控词表。

## 6. 红线

- 每条 claim 必须有**逐字引文且核验命中**,否则丢弃——抽取绝不臆造。
- 发现/抽取**默认只出候选**,人审后才入库。
- EDGAR 遵守 SEC User-Agent + 限速;仅合法源。
- 网络/模型路径用注入式 fake 测试;真实模型抽取需带 key 的环境;EDGAR 免密但真实联调需网络。
