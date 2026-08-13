# MCP 工具参考 — exhibition-mcp-server

本 skill 连接的 MCP server：`handaas-mcp-server/exhibition-mcp-server`（“展会大数据”）。

> **重要**：`exhibition_bigdata_exhibition_participation` 入参为 `matchKeyword`（**企业全称** / 注册号 / 统一社会信用代码 / 企业 id）+ `keywordType`；当用户只给企业关键词时，必须先调关键词模糊查询补全全称。展馆 / 展会 / 展商查询属于市场检索类工具，与特定企业主体无关。

## 通用约定

- `keywordType` 枚举：`name`（企业名称）/ `nameId`（企业 id）/ `regNumber`（注册号）/ `socialCreditCode`（统一社会信用代码）。
- 分页：`pageIndex` 从 1 开始；`pageSize` 单页最多 50。

---

## 工具清单

### 1. `exhibition_bigdata_exhibition_participation` — 展会参与

用途：按企业主体返回其展会参与记录。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业名称 / 注册号 / 统一社会信用代码 / 企业 id |
| `pageIndex` | int | 否 | 从 1 开始（默认 1） |
| `pageSize` | int | 否 | 单页最多 50（默认 10） |
| `keywordType` | string | 否 | 主体类型：name / nameId / regNumber / socialCreditCode |

返回（list + `total`）：`fairName`（展会名称）、`fairIndustry`（展会行业）、`fairRegion`（展会区域）、`fairDate`（展会日期）、`venueName`（展馆）、`role`（参展身份）、`boothNo`（展位号）等。

product_id：`66a26918ff3066996ecc6471`。

---

### 2. `exhibition_bigdata_fuzzy_search` — 关键词模糊查询企业

用途：根据企业名称 / 人名 / 品牌 / 产品 / 岗位等关键词模糊查询企业列表，用于补全企业全称。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 匹配关键词 |
| `pageIndex` | int | 否 | 分页开始位置（默认 1） |

返回：`total` + 企业列表（`name`、`nameId`、`regCapitalValue`、`foundTime`、`operStatus`、`address`、`legalRepresentative`、`enterpriseType`、`catchReason` 命中原因等）。

product_id：`675cea1f0e009a9ea37edaa1`。

---

### 3. `exhibition_bigdata_exhibition_venue_search` — 展馆查询

用途：按展馆所在区域查询展馆信息（市场检索模式）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `pavilionRegion` | string | 是 | 展馆所在区域 |
| `matchKeyword` | string | 否 | 展馆名称关键词（可选） |
| `pageIndex` | int | 否 | 从 1 开始（默认 1） |

返回（list + `total`）：`venueName`（展馆名称）、`venueRegion`（所在区域）、`venueAddress`（地址）、`venueArea`（展馆面积）、`hallCount`（展厅数量）等。

product_id：`66e2d2ca428a1f4cd69c1083`。

---

### 4. `exhibition_bigdata_exhibition_search` — 展会查询

用途：按关键词查询展会列表（市场检索模式）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 否 | 展会名称 / 行业关键词 |
| `pageIndex` | int | 否 | 从 1 开始（默认 1） |

返回（list + `total`）：`fairName`（展会名称）、`fairIndustry`（展会行业）、`fairRegion`（展会区域）、`fairDate`（展会日期）、`venueName`（展馆）、`organizer`（主办单位）等。

product_id：`66a0f6ca477cbe5f7605973f`。

---

### 5. `exhibition_bigdata_exhibitor_search` — 展商查询

用途：按展会区域 / 行业 / 关键词查询展商列表（市场检索模式）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `fairRegion` | string | 否 | 展会区域 |
| `matchKeyword` | string | 否 | 展商 / 展会关键词 |
| `fairIndustries` | string | 否 | 展会行业 |
| `pageIndex` | int | 否 | 从 1 开始（默认 1） |
| `pageSize` | int | 否 | 单页最多 50（默认 10） |

返回（list + `total`）：`exhibitorName`（展商名称）、`fairName`（参展展会）、`fairIndustry`（所属行业）、`fairRegion`（展会区域）、`boothNo`（展位号）等。

product_id：`66d5b7e0537c3f61d646c473`。

---

## 推荐调用顺序（报告编排）

- **企业参展模式**：
  1. （若仅有关键词）`exhibition_bigdata_fuzzy_search` → 取 `name` 作为全称。
  2. `exhibition_bigdata_exhibition_participation` → 企业展会参与记录。
- **市场检索模式**：
  1. `exhibition_bigdata_exhibition_venue_search`（按 `pavilionRegion`）→ 展馆。
  2. `exhibition_bigdata_exhibition_search`（按 `matchKeyword`）→ 展会。
  3. `exhibition_bigdata_exhibitor_search`（按 `fairRegion` / `fairIndustries` / `matchKeyword`）→ 展商。

> 两种模式可组合：同一份报告同时呈现企业参展与市场检索结果。
