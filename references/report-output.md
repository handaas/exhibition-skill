# 报告输出 — 展会大数据报告

本文件规定 `exhibition-report` skill 产出的报告结构、质量底线与渲染工作流。所有产物遵循 `AGENTS.md` 的统一 JSON 骨架与本 skill 的领域裁剪。

## 默认展示模式

- HTML：可分享 / 可交付的可视化报告；独立本地文件，内嵌 CSS，无调试 / 内部段落。
- Markdown：知识库 / wiki / PRD / 后续手工编辑。
- JSON：系统集成或二次处理。

`compose_report.py` 通过 `--report-output <path>` 同时产出 HTML + Markdown；`--output <path>` 产出 JSON。`render_report.py` 可基于已有 JSON 重渲染。

## 报告结构（7 章）

1. **报告摘要**：分析对象 / 检索范围、数据覆盖范围、核心发现、关键指标卡。
2. **查询对象与口径**：企业全称（企业参展模式）或检索条件（市场检索模式）、匹配方式、数据范围、产品、局限。
3. **数据总览**：展会参与、展馆、展会、展商、指定展会参展企业命中条数等指标卡。
4. **核心分析**（展会专属子章节，由 `core_analysis.sections` 驱动渲染，按命中维度呈现，空维度自动跳过）：
   - 展会参与（表：展会名称 / 行业 / 区域 / 日期 / 展馆 / 参展身份 / 展位号）。
   - 展馆查询（表：展馆名称 / 区域 / 地址 / 面积 / 展厅数）。
   - 展会查询（表：展会名称 / 行业 / 区域 / 日期 / 展馆 / 主办单位）。
   - 展商查询（表：展商名称 / 参展展会 / 行业 / 区域 / 展位号）。
   - 指定展会参展企业（表：企业名称 / 企业 ID；仅对应报告中所选展会 ID 与届次）。
5. **代表性记录**：关键展会 / 展商记录 Top N。
6. **特征与洞察**：结构化事实摘要（上游收录数、当前页分布、开放标记及核验边界），每条含 `feature` / `evidence` / `interpretation`。记录数不得用于推断营销投入、品牌建设、区域/行业活跃度或当前开展状态。
7. **数据口径与来源**：MCP server、数据产品、生成时间、是否 dry-run、模式（enterprise / market_search）。

分页结果必须同时披露“上游总量”和“当前页展示数”；当前页派生的展馆集中度或年度分布不得冒充全量统计。展会关键词查询不支持地区过滤时，必须标为全国关键词口径，不能承接指定城市结论。未请求的维度不是调用失败，不进入 `tool_errors`。

展会关键词检索必须保留上游当前页全部记录，并逐条标记“名称命中 / 简介命中 / 待核”；上游关键词返回不等于每条记录都与主题直接相关，不得静默丢弃疑似误匹配记录。`isOpen` 只呈现为“上游开放标记=值”，当前状态须结合实际起止日期另行核验。

## 质量底线

- 报告脱离 Skill 上下文也可独立阅读；正文只见展会事实与结构化数据。
- 绝不出现工具名、入参（如 `matchKeyword=...`）、product_id、内部字段名、空表、调试信息。
- HTML 采用研究报告视觉风格：A4 风、灰色顶部条纹、蓝色报告横幅、左侧目录 / 范围侧栏、深蓝章节标题、深蓝表头、浅蓝斑马行、打印友好分页。
- 数据为空时明确说明数据范围 / 口径，不渲染空表、不臆造事实。
- 绝不打印 `secret_id` / `secret_key` / 签名 / token / 原始签名请求。
- 自动补全企业全称时，在报告口径中说明“由关键词模糊查询补全”。
- 市场检索模式下，口径章节明确说明“市场检索模式：与特定企业主体无关”。

### 数据格式约束（铁律）

以下约束适用于 compose_report.py 组装数据与 render_report.py 渲染输出的全过程：

1. **嵌套 JSON 字符串必须解析**：MCP 返回的某些字段（如 `regCapital`、`addressValue`、`subscriptionDetail`）可能是 JSON 字符串（例：`{"coinType":"人民币","value":430000000.0}`）。compose 层必须调用 `_unwrap_json_str()` / `_parse_reg_capital()` / `_flatten_addr()` 解析为可读文本（如"4.30 亿 人民币"、"浙江省杭州市滨江区..."）。绝不在报告正文、表格单元格或指标值中输出原始 JSON 字符串。

2. **section 标题必须用中文**：`core_analysis.sections` 数组中每个 section 的 `title` 字段必须使用中文（如"企业基本信息"、"对外投资"、"股东信息"）。`key` 字段用英文 snake_case 供程序索引，但 `title` 绝不可显示英文 key。即使缺少 sections 数组，渲染器回退逻辑也内置了 `_TITLE_MAP` 映射。

3. **指标值可读化**：所有 `metrics` 的 `value` 字段必须格式化为人类可读形式：
   - 金额：`10995210218.0` → `109.95 亿 人民币`（≥1 亿用亿，≥1 万用万）
   - 地址：嵌套 dict → 省+市+区拼接 或取 `value` 字段
   - 比率：`0.8858` → `88.58%`
   - 日期：保持 `yyyy-MM-dd` 格式
   - "-" 表示字段缺失（MCP 未返回）；`0` 表示真实为零

4. **企业画像指标提取**：有 fuzzy_search 的 skill 必须从返回的 record 中提取 `regCapitalValue` / `foundTime` / `operStatus` / `enterpriseType` / `legalRepresentative`，通过 `_enrich_metrics_with_profile()` 追加为指标卡。

5. **分布派生指标**：`_derive_core_metrics()` 从 core_analysis 各 section 计算分布指标（CR3 集中度、覆盖城市/平台/类目数、价格区间、正面占比等），确保指标总数 M ≥ 6。

## 工作流

```bash
# 1. 干跑（不调真实 API，用样例数据组装报告骨架）
python scripts/compose_report.py \
  --enterprise "示例科技有限公司" \
  --dry-run \
  --output output/exhibition.json \
  --report-output output/exhibition.html

# 2. 企业参展模式（真实查询）
python scripts/compose_report.py \
  --enterprise "示例科技有限公司" \
  --output output/exhibition.json \
  --report-output output/exhibition.html

# 3. 市场检索模式
python scripts/compose_report.py \
  --venue-region "上海" \
  --fair-industries "电子信息" \
  --search "半导体" \
  --output output/exhibition_market.json \
  --report-output output/exhibition_market.html

# 4. 重渲染已有 JSON
python scripts/render_report.py --input output/exhibition.json --output output/exhibition.html
python scripts/render_report.py --input output/exhibition.json --output output/exhibition.md

# 5. 只查展会（不会调用展商查询）
python scripts/compose_report.py \
  --search "半导体" --search-target exhibition --page-size 10 \
  --output output/fair_search.json --report-output output/fair_search.html

# 6. 展会搜索 -> 真实展会 ID -> 参展企业
python scripts/compose_report.py \
  --fair-exhibitors "中国国际线缆及线材展览会" --fair-result-index 1 --page-size 10 \
  --output output/fair_exhibitors.json --report-output output/fair_exhibitors.html
```

返回：JSON 路径、HTML 路径、Markdown 路径，以及企业全称映射 / 检索条件与数据口径摘要（含模式标注）。
