---
name: exhibition-report
description: Use for generating a professional exhibition big-data report (展会大数据报告) from the HandaaS exhibition MCP — covering 展会参与、展馆查询、展会查询、展商查询、指定展会参展企业. Trigger when users ask for “展会大数据报告”, “展会分析报告”, “查一家公司的参展记录”, “展会参与”, “展馆查询”, “展会查询”, “展商查询”, “某届展会有哪些参展企业”, or “企业参展画像”. Infer the canonical enterprise name (auto-fuzzy-completing a keyword), pick the right MCP tools, and produce HTML + Markdown + JSON reports automatically. Also supports fair-only search and a search-derived fair ID to exhibitors workflow. MCP 服务名称触发词：展会行业情报。
---

# 展会大数据报告

## 用户契约

把“展会大数据报告”作为面向用户的调用短语。`exhibition-report` 仅为内部包名。

当本 skill 处于激活状态：

1. 不要向用户索要 product_id、MCP 工具名、API 字段、内部参数或凭证信息；只接受企业名称、统一社会信用代码、注册号或企业 ID，或市场检索条件（区域 / 行业 / 关键词）。
2. 接受自然目标，例如“查一下某某公司的参展记录”“分析这家企业的展会布局”“给我一份某某地区的展会市场报告”“看看某个行业有哪些展商”。
3. 当用户只给企业关键词时，自动调用关键词模糊查询补全企业全称，再查展会参与。
4. 优先使用 MCP 连接（`EXHIBITION_MCP_URL` Remote MCP 或本地 `handaas-mcp-server/exhibition-mcp-server`）；不要让用户处理签名或凭证。
5. 同时产出 HTML（可分享交付）、Markdown（知识库 / wiki）、JSON（系统集成）三类产物。
6. 报告正文必须是专业研究报告风格：只见展会事实与结构化数据，绝不出现工具名、入参、product_id、内部字段或空表。
7. 绝不打印 `secret_id`、`secret_key`、签名、token 或原始签名请求。
8. 默认 dry-run；真实付费 / 凭证调用需用户明确要求且 MCP 连接配置完整。
9. 数据为空时明确说明数据范围 / 口径，不渲染空表、不臆造事实。


- MCP 返回的嵌套 JSON 字符串（如金额 `{"coinType":"人民币","value":430000000.0}`、地址 `{"city":"杭州市",...}`）必须解析为可读文本（如"4.30 亿 人民币"、"浙江省杭州市"），绝不在报告正文、表格或指标中输出原始 JSON 字符串。
- 报告所有章节标题、指标卡标签必须用中文；`core_analysis.sections` 的 `title` 字段必须中文，不可显示英文 key（如 `holders`、`investments`）。
- 指标值必须可读化：金额格式为"X 亿/万 + 币种"，地址拼接省市区，比率显示百分号。详见 `references/report-output.md` 的「数据格式约束」。

## 付费调用纪律（先规划后查询）

每次真实调用均按接口/页计费，必须先规划再查询，不得默认全量拉取：

1. 每一次业务/工具调用、每一页都可能收费。想算 total / 页数不是无限制取全量的授权。
2. 调用前先推导：需要哪些结论、需要哪些数据维度、工具与参数计划、必要页数与最大调用预算。total 未知时，第一个必要的明细页同时完成 total 发现并直接作为报告数据，绝不为此多付一次（首屏响应必须复用，不重复拉取）。
3. 明细接口仅取结论、图表、代表性记录或用户明确的全量/计数需求所需的行数。只有用户明确要全面报告时才跑全面管线，绝不因为工具存在就全部调用。
4. 在 schema 允许范围内用合理的大 pageSize（≤50），取得所需证据 / 样本即停，且不超出显式预算。更多调用必须有“缺失结论”的正当理由，不能只为填满章节。不得用样本分布冒充全量结论。
5. 复用当前任务 / 报告内的相同请求（含首屏规划数据）；不要为渲染重跑 compose/MCP，用已保存 JSON 本地重渲染。不自动重试、不重复拉取同一明细。任何补充查询必须先列缺口并复用已返回记录。
6. `total_pages` / `remaining_pages` 是按请求 pageSize 的估算；短而非空页面仍有剩余记录时在预算内继续。只有稳定有效的 total 等于实际扫描条数才算完整采集；错误、提前空页、重复页、total 变化/缺失、数量溢出均视为不完整。显式预算 / 样本停止即部分采集，绝不宣称全量。
7. 预算不足以支撑用户要求的关键结论时：先说明证据缺口与预计需要追加的调用数，再请求扩大授权（提高 `--max-pages`）；不静默降级结论，也不擅自扩大计费范围。

分页收集默认一次明细调用预算 `--max-pages 1`（每明细接口）；明细接口的 total、实际取数、完整性披露写入报告 `data_source.pagination`，报告级去重统计写入 `data_source.call_usage`。

本 skill 的分页口径：
- 可分页并受预算控制：`exhibition_bigdata_exhibition_participation`、`exhibition_bigdata_exhibitor_search`、`exhibition_bigdata_exhibition_exhibitors`（均支持 pageIndex+pageSize，pageSize≤50）；`exhibition_bigdata_exhibition_search` 参考表仅列 pageIndex，但线上调用证据显示同样接受 pageSize，故按 pageSize 分页。
- 展馆查询 `exhibition_bigdata_exhibition_venue_search` 的上游服务同样支持 `pageIndex` 与 `pageSize`（默认 10、最多 50）；按 `total` 估页，在 `--max-pages` 预算内采集并披露数量，不能因旧参考表漏列参数而绕过分页与预算。
- 身份解析绝不翻页：`exhibition_bigdata_fuzzy_search` 仅用于企业全称补全，固定单页。
- 两跳模式第一跳（展会检索取 fairId 候选）固定 1 页预算：`--fair-result-index` 只从第一页候选选择，不因选择扩大付费调用；仅第二跳（参展企业明细）受 `--max-pages` 控制。

## MCP 服务入口

- MCP 服务当前名称：展会行业情报（连接仍使用原服务目录标识）。

- 上游 MCP 项目：`handaas-mcp-server/exhibition-mcp-server`（位于 `HANDAAS_MCP_SERVER_ROOT` 或本仓库同级目录）。
- Remote MCP：设置环境变量 `EXHIBITION_MCP_URL`（streamable-http），可选 `EXHIBITION_MCP_TOKEN`。
- 本地 MCP：设置 `HANDAAS_MCP_SERVER_ROOT` 指向 `handaas-mcp-server` 仓库根目录；该 server 自己的 `.env` 提供 `INTEGRATOR_ID` / `SECRET_ID` / `SECRET_KEY`。
- 首次真实查询前，运行 `scripts/mcp_client.py ping` 与 `scripts/mcp_client.py list-tools` 验证连通。

## 按需加载 references

- 不清楚该 MCP 有哪些工具、参数、返回字段、何时调用：`references/mcp-tools-reference.md`。
- 报告结构、章节、质量底线、渲染工作流：`references/report-output.md`。

## 意图路由

| 用户意图 | 内部工作流 |
| --- | --- |
| 查一家公司的展会参与报告 | 企业参展模式；`compose_report.py --enterprise ...` |
| 查某地区展馆 / 办展资源 | 市场检索模式；`compose_report.py --venue-region ...` |
| 查某区域 / 行业的展会列表 | 市场检索模式；`compose_report.py --search ...` |
| 只查展会、不连带查展商 | 展会单项检索；`compose_report.py --search ... --search-target exhibition` |
| 查指定届次的参展企业 | 两跳模式；`compose_report.py --fair-exhibitors ... --fair-result-index N` |
| 查某区域 / 行业的展商 | 市场检索模式；`compose_report.py --fair-region ... / --fair-industries ...` |
| 组合检索（既看企业参展又看市场） | `compose_report.py --enterprise ... --venue-region ...` |
| 只给企业关键词（不是全称） | 先 `exhibition_bigdata_fuzzy_search` 补全全称，再查展会参与 |
| 只要 JSON / 只要 HTML / 只要 Markdown | 用 `--output`（JSON）或 `--report-output`（HTML+MD），或 `render_report.py` 重渲染 |
| 连接 / 工具不存在 / 传参错误 | `mcp_client.py ping` / `list-tools` 排查；报脱敏后的缺失项 |

## Golden path for 展会大数据报告

1. **确定模式**：若用户提供企业主体走“企业参展模式”；若提供区域 / 行业 / 关键词走“市场检索模式”；两者也可组合。
2. **解析企业全称**（企业参展模式）：若输入含“公司/集团/有限/院/厂/中心/事务所/合作社/合伙”等后缀视为全称；否则调 `exhibition_bigdata_fuzzy_search` 取首个命中。
3. **调用展会工具**：`exhibition_bigdata_exhibition_participation`（企业参展）、`exhibition_bigdata_exhibition_venue_search`（展馆）、`exhibition_bigdata_exhibition_search`（展会）、`exhibition_bigdata_exhibitor_search`（市场展商）；查询指定届次参展企业时，必须先从展会查询实际结果取得 `_id`，再调用 `exhibition_bigdata_exhibition_exhibitors`，不得手写 ID。分页：默认 1 页预算，按 total 驱动、在 `--max-pages` 预算内翻页，超出预算披露未纳入条数而非宣称全量；`exhibition_bigdata_exhibition_venue_search` 无 pageSize 且无文档化固定页大小，保持单页调用并注明当前页口径。
4. **组装统一报告**：核心分析含展会参与（表）、展馆查询（表）、展会查询（表）、展商查询（表）（按检索命中的维度呈现，空维度自动跳过）。
5. **渲染三件套**：`compose_report.py --enterprise ... --output ... --report-output ...` 直接产出 JSON + HTML + Markdown；或 `render_report.py --input ... --output ...` 重渲染。
6. **返回路径**：返回 JSON、HTML、Markdown 文件路径，以及企业全称映射与数据口径（含模式标注）。

## 脚本速查

```bash
# 校验连接配置（脱敏）
python scripts/validate_config.py --allow-placeholders

# 连通性自测
python scripts/mcp_client.py ping
python scripts/mcp_client.py list-tools

# 干跑（不调真实 API，用样例数据组装报告骨架）
python scripts/compose_report.py \
  --enterprise "示例科技有限公司" \
  --dry-run \
  --output output/exhibition.json \
  --report-output output/exhibition.html

# 企业参展模式（真实查询）
python scripts/compose_report.py \
  --enterprise "示例科技有限公司" \
  --output output/exhibition.json \
  --report-output output/exhibition.html

# 市场检索模式：按展馆区域 / 行业 / 关键词
python scripts/compose_report.py \
  --venue-region "上海" \
  --fair-industries "电子信息" \
  --search "半导体" \
  --output output/exhibition_market.json \
  --report-output output/exhibition_market.html

# 展会单项检索：不连带调用展商端点
python scripts/compose_report.py \
  --search "中国国际线缆及线材展览会" \
  --search-target exhibition \
  --page-size 10 \
  --max-pages 1 \
  --output output/fair_search.json \
  --report-output output/fair_search.html

# 指定展会参展企业：先搜索（第一跳固定第 1 页预算）再选择第 1 条真实结果并以其 _id 查询
# --fair-result-index 候选仅来自第一页，不为此扩大付费调用；第二跳参展企业受 --max-pages 控制
python scripts/compose_report.py \
  --fair-exhibitors "中国国际线缆及线材展览会" \
  --fair-result-index 1 \
  --page-size 10 \
  --max-pages 1 \
  --output output/fair_exhibitors.json \
  --report-output output/fair_exhibitors.html

# 手动调单个工具
python scripts/mcp_client.py call-tool \
  --tool exhibition_bigdata_exhibition_participation \
  --arguments-json '{"matchKeyword": "示例科技有限公司", "keywordType": "name", "pageIndex": 1, "pageSize": 10}'

# 重渲染已有 JSON
python scripts/render_report.py --input output/exhibition.json --output output/exhibition.html
python scripts/render_report.py --input output/exhibition.json --output output/exhibition.md
```

## 输出字段

- `subject`：企业全称、匹配关键词、主体类型、是否自动补全、是否市场检索模式。
- `abstract` / `summary`：封面摘要与详细摘要。
- `metrics`：展会参与、展馆、展会、展商的命中条数等指标卡。
- `caliber`：匹配对象、匹配方式（含模式标注）、数据范围、产品、局限。
- `core_analysis`：展会参与（表）、展馆查询（表）、展会查询（表）、展商查询（表）。
- `representative_records`：代表性展会 / 展商记录。
- `insights`：结构化事实摘要（上游收录数、当前页分布、开放标记及其核验边界）；不由记录数推断营销投入、品牌建设、行业活跃度或当前开展状态。
- `data_source`：MCP server、数据产品、生成时间、是否 dry-run、模式（enterprise / market_search）；真实调用时还含 `pagination`（每个分页接口的 total、实际请求页数、未纳入条数与完整性披露）与 `call_usage`（报告内请求执行 / 复用计数）。

若 API 调用失败，明确报出缺失的配置 / 缺失的工具 / MCP 错误 / 参数校验错误 / 上游网络错误，给出 dry-run 命令或配置步骤，绝不暴露密钥。
