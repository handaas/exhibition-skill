---
name: exhibition-report
description: Use for generating a professional exhibition big-data report (展会大数据报告) from the HandaaS exhibition MCP — covering 展会参与、展馆查询、展会查询、展商查询. Trigger when users ask for “展会大数据报告”, “展会分析报告”, “查一家公司的参展记录”, “展会参与”, “展馆查询”, “展会查询”, “展商查询”, or “企业参展画像”. Infer the canonical enterprise name (auto-fuzzy-completing a keyword), pick the right MCP tools, and produce HTML + Markdown + JSON reports automatically. Also supports market search mode (by venue region / fair region / fair industries / exhibition keyword) independent of a specific enterprise.
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

## MCP 服务入口

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
| 查某区域 / 行业的展商 | 市场检索模式；`compose_report.py --fair-region ... / --fair-industries ...` |
| 组合检索（既看企业参展又看市场） | `compose_report.py --enterprise ... --venue-region ...` |
| 只给企业关键词（不是全称） | 先 `exhibition_bigdata_fuzzy_search` 补全全称，再查展会参与 |
| 只要 JSON / 只要 HTML / 只要 Markdown | 用 `--output`（JSON）或 `--report-output`（HTML+MD），或 `render_report.py` 重渲染 |
| 连接 / 工具不存在 / 传参错误 | `mcp_client.py ping` / `list-tools` 排查；报脱敏后的缺失项 |

## Golden path for 展会大数据报告

1. **确定模式**：若用户提供企业主体走“企业参展模式”；若提供区域 / 行业 / 关键词走“市场检索模式”；两者也可组合。
2. **解析企业全称**（企业参展模式）：若输入含“公司/集团/有限/院/厂/中心/事务所/合作社/合伙”等后缀视为全称；否则调 `exhibition_bigdata_fuzzy_search` 取首个命中。
3. **调用展会工具**：`exhibition_bigdata_exhibition_participation`（企业参展，入参 `matchKeyword`（企业全称）+ `keywordType`，分页）、`exhibition_bigdata_exhibition_venue_search`（展馆，入参 `pavilionRegion` 必填）、`exhibition_bigdata_exhibition_search`（展会，入参 `matchKeyword`）、`exhibition_bigdata_exhibitor_search`（展商，入参 `fairRegion` / `fairIndustries` / `matchKeyword`）。
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
- `insights`：结构化解读（参展活跃度 / 参展行业集中度 / 市场展会规模 / 展商密度 / 展馆资源）。
- `data_source`：MCP server、数据产品、生成时间、是否 dry-run、模式（enterprise / market_search）。

若 API 调用失败，明确报出缺失的配置 / 缺失的工具 / MCP 错误 / 参数校验错误 / 上游网络错误，给出 dry-run 命令或配置步骤，绝不暴露密钥。
