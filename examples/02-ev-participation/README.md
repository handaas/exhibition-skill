# 车企参展布局

- 用户需求：请查看比亚迪股份有限公司的展会参与情况。
- 决策用途：市场推广与区域活动分析
- 本轮结果：**本轮检查通过**
- 实际工具调用：1；失败 0
- 章节覆盖率：100%（不代表证据质量）

## 预期业务检查（不自动宣称通过）

- 主体全称直查
- 参展记录按返回事实排列
- 地区/行业洞察有记录支撑
- 缺失角色字段不自行推断

## 本轮自动检查发现


## 使用局限

- 参展商名称可能由关联主体登记
- 不能从记录推断展位规模

## 证据与复现

- [审计结果](result.json)
- [工具调用、结果形态与响应摘要哈希](calls.json)
- [JSON](report.json) / [HTML](report.html) / [Markdown](report.md)

```bash
python3 exhibition-skill/scripts/compose_report.py --enterprise '比亚迪股份有限公司' --page-size 8 --output exhibition-skill/output/02-ev-participation/report.json --report-output exhibition-skill/output/02-ev-participation/report.html
```

## 逐场景业务复核

当前真实产物逐项复核通过；结论限于本次上游公开样本与报告声明口径。

- **pass** 主体全称直查：已证明“主体全称直查”。 实际调用=[{"tool":"exhibition_bigdata_exhibition_participation","status":"data","row_count":8,"reported_total":34,"arguments":{"matchKeyword":"比亚迪股份有限公司","keywordType":"name","pageIndex":1,"pageSize":8}}] subject={"enterprise":"比亚迪股份有限公司","matchKeyword":"比亚迪股份有限公司","keywordType":"name","match_raw":"比亚迪股份有限公司","resolved":true,"resolve_reason":"视为企业全称","search_mode":false,"filters":{"venue_region":null,"fair_region":null,"fair_industries":null,"search_keyword":null},"query_scopes":{"participation":"企业主体口径","venue":"未请求","exhibition":"未请求","exhibitor":"未请求"}} 口径={"match_target":"比亚迪股份有限公司","match_type":"展会参与按企业主体匹配（keywordType=name）；支持企业名称/注册号/统一社会信用代码/企业 id","data_scope":"展会参与","products":["展会参与"],"limit":"数据来自展会公开信息；少量字段可能存在更新延迟。分页结果仅代表当前页样本；上游总量不等于当前页可见记录数。"}
- **pass** 参展记录按返回事实排列：已证明“参展记录按返回事实排列”。 实际记录样本={"participation":[{"展会ID":"-","展会名称":"2025第二十届济南国际太阳能利用大会暨新能源与储能应用博览会","展会日期":"2025-03-05 至 2025-03-07","展馆":"-","状态":"上游开放标记=1","展会亮点":"-"},{"展会ID":"-","展会名称":"2024第十七届国际太阳能光伏与智慧能源(上海)大会暨展览会","展会日期":"2024-06-13 至 2024-06-15","展馆":"-","状态":"上游开放标记=1","展会亮点":"-"}],"pavilion_dist":[{"展馆":"中国国际展览中心-新馆","参展次数":"2"},{"展馆":"北京国家会议中心","参展次数":"1"}],"year_trend":[{"年份":"2023","参展次数":"2"},{"年份":"2024","参展次数":"5"}]} 可见章节=[{"title":"展会参与","note":"上游总量 34 条；当前页展示 8 条"},{"title":"参展展馆分布","note":"仅按当前页展示样本聚合，不代表上游全量分布"},{"title":"参展年度趋势","note":"仅按当前页展示样本统计，不代表全量年度趋势"}]
- **pass** 地区/行业洞察有记录支撑：已证明“地区/行业洞察有记录支撑”。 实际调用=[{"tool":"exhibition_bigdata_exhibition_participation","status":"data","row_count":8,"reported_total":34,"arguments":{"matchKeyword":"比亚迪股份有限公司","keywordType":"name","pageIndex":1,"pageSize":8}}] subject={"enterprise":"比亚迪股份有限公司","matchKeyword":"比亚迪股份有限公司","keywordType":"name","match_raw":"比亚迪股份有限公司","resolved":true,"resolve_reason":"视为企业全称","search_mode":false,"filters":{"venue_region":null,"fair_region":null,"fair_industries":null,"search_keyword":null},"query_scopes":{"participation":"企业主体口径","venue":"未请求","exhibition":"未请求","exhibitor":"未请求"}} 口径={"match_target":"比亚迪股份有限公司","match_type":"展会参与按企业主体匹配（keywordType=name）；支持企业名称/注册号/统一社会信用代码/企业 id","data_scope":"展会参与","products":["展会参与"],"limit":"数据来自展会公开信息；少量字段可能存在更新延迟。分页结果仅代表当前页样本；上游总量不等于当前页可见记录数。"} 实际记录样本={"participation":[{"展会ID":"-","展会名称":"2025第二十届济南国际太阳能利用大会暨新能源与储能应用博览会","展会日期":"2025-03-05 至 2025-03-07","展馆":"-","状态":"上游开放标记=1","展会亮点":"-"},{"展会ID":"-","展会名称":"2024第十七届国际太阳能光伏与智慧能源(上海)大会暨展览会","展会日期":"2024-06-13 至 2024-06-15","展馆":"-","状态":"上游开放标记=1","展会亮点":"-"}],"pavilion_dist":[{"展馆":"中国国际展览中心-新馆","参展次数":"2"},{"展馆":"北京国家会议中心","参展次数":"1"}],"year_trend":[{"年份":"2023","参展次数":"2"},{"年份":"2024","参展次数":"5"}]} 可见章节=[{"title":"展会参与","note":"上游总量 34 条；当前页展示 8 条"},{"title":"参展展馆分布","note":"仅按当前页展示样本聚合，不代表上游全量分布"},{"title":"参展年度趋势","note":"仅按当前页展示样本统计，不代表全量年度趋势"}]
- **pass** 缺失角色字段不自行推断：已证明“缺失角色字段不自行推断”。 实际记录样本={"participation":[{"展会ID":"-","展会名称":"2025第二十届济南国际太阳能利用大会暨新能源与储能应用博览会","展会日期":"2025-03-05 至 2025-03-07","展馆":"-","状态":"上游开放标记=1","展会亮点":"-"},{"展会ID":"-","展会名称":"2024第十七届国际太阳能光伏与智慧能源(上海)大会暨展览会","展会日期":"2024-06-13 至 2024-06-15","展馆":"-","状态":"上游开放标记=1","展会亮点":"-"}],"pavilion_dist":[{"展馆":"中国国际展览中心-新馆","参展次数":"2"},{"展馆":"北京国家会议中心","参展次数":"1"}],"year_trend":[{"年份":"2023","参展次数":"2"},{"年份":"2024","参展次数":"5"}]} 可见章节=[{"title":"展会参与","note":"上游总量 34 条；当前页展示 8 条"},{"title":"参展展馆分布","note":"仅按当前页展示样本聚合，不代表上游全量分布"},{"title":"参展年度趋势","note":"仅按当前页展示样本统计，不代表全量年度趋势"}] 三件套=True，空tbody=False，quality={"total_sections":3,"populated_sections":3,"empty_sections":0,"coverage_pct":100}

## 离线浏览器检查

[Ego Lite 离线图表、页面溢出和脚本检查](browser-check.json)