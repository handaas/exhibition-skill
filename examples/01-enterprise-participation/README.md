# 科技企业参展画像

- 用户需求：请分析华为技术有限公司的参展记录和展会布局。
- 决策用途：品牌活动与行业覆盖研究
- 本轮结果：**本轮检查通过**
- 实际工具调用：1；失败 0
- 章节覆盖率：100%（不代表证据质量）

## 预期业务检查（不自动宣称通过）

- 企业参展模式且不触发无关市场查询
- 展会名称、时间、地区等记录可读
- 参展次数与当前页样本区分
- 不把参展等同赞助或获奖

## 本轮自动检查发现


## 使用局限

- 公开参展记录可能不完整
- 历史参展不代表未来计划

## 证据与复现

- [审计结果](result.json)
- [工具调用、结果形态与响应摘要哈希](calls.json)
- [JSON](report.json) / [HTML](report.html) / [Markdown](report.md)

```bash
python3 exhibition-skill/scripts/compose_report.py --enterprise '华为技术有限公司' --page-size 10 --output exhibition-skill/output/01-enterprise-participation/report.json --report-output exhibition-skill/output/01-enterprise-participation/report.html
```

## 逐场景业务复核

当前真实产物逐项复核通过；结论限于本次上游公开样本与报告声明口径。

- **pass** 企业参展模式且不触发无关市场查询：已证明“企业参展模式且不触发无关市场查询”。 当前事实={"technical_status":"passed","successful_data_calls":1,"calls":[{"tool":"exhibition_bigdata_exhibition_participation","status":"data","row_count":10,"reported_total":255,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name","pageIndex":1,"pageSize":10}}],"quality":{"total_sections":3,"populated_sections":3,"empty_sections":0,"coverage_pct":100},"sections":[{"title":"展会参与","note":"上游总量 255 条；当前页展示 10 条"},{"title":"参展展馆分布","note":"仅按当前页展示样本聚合，不代表上游全量分布"},{"title":"参展年度趋势","note":"仅按当前页展示样本统计，不代表全量年度趋势"}],"rows":[{"展会ID":"-","展会名称":"2026第20届中国（深圳）国际金融博览会","展会日期":"2026-05-27 至 2026-05-29","展馆":"深圳会展中心","状态":"上游开放标记=1","展会亮点":"-"},{"展会ID":"-","展会名称":"2026第21届中国（武汉）光谷·国际光电子博览会","展会日期":"2026-05-18 至 2026-05-20",…
- **pass** 展会名称、时间、地区等记录可读：已证明“展会名称、时间、地区等记录可读”。 实际调用=[{"tool":"exhibition_bigdata_exhibition_participation","status":"data","row_count":10,"reported_total":255,"arguments":{"matchKeyword":"华为技术有限公司","keywordType":"name","pageIndex":1,"pageSize":10}}] subject={"enterprise":"华为技术有限公司","matchKeyword":"华为技术有限公司","keywordType":"name","match_raw":"华为技术有限公司","resolved":true,"resolve_reason":"视为企业全称","search_mode":false,"filters":{"venue_region":null,"fair_region":null,"fair_industries":null,"search_keyword":null},"query_scopes":{"participation":"企业主体口径","venue":"未请求","exhibition":"未请求","exhibitor":"未请求"}} 口径={"match_target":"华为技术有限公司","match_type":"展会参与按企业主体匹配（keywordType=name）；支持企业名称/注册号/统一社会信用代码/企业 id","data_scope":"展会参与","products":["展会参与"],"limit":"数据来自展会公开信息；少量字段可能存在更新延迟。分页结果仅代表当前页样本；上游总量不等于当前页可见记录数。"} 实际记录样本={"participation":[{"展会ID":"-","展会名称":"2026第20届中国（深圳）国际金融博览会","展会日期":"2026-05-27 至 2026-05-29","展馆":"深圳会展中心","状态":"上游开放标记=1","展会亮点":"-"},{"展会ID":"-","展会名称":"2026第21届中国（武汉）光谷·国际光电子博览会","展会日期":"2026-05-18 至 2026-05-20","展馆":"中国光谷科技会展中心","状态":"上游开放标记=1","展会亮点":"-"}],"pavilion_dist":[{"展馆":"深圳会展中心","参展次数":"1"},{"展馆":"中国光谷科技会展中心","参展次数":"1"}],"year_trend":[{"年份":"2025","参展次数":"3"},{"年份":"2026","参展次数":"7"}]} 可见章节=[{"title":"展会参与","note":"上游总量 255 条；当前页展示 10 条"},{"title":"参展展馆分布","note":"仅按当前页展示样本聚合，不代表上游全量分布"},{"title":"参展年度趋势","note":"仅按当前页展示样本统计，不代表全量年度趋势"}]
- **pass** 参展次数与当前页样本区分：已证明“参展次数与当前页样本区分”。 摘要/局限={"summary":"本报告以“华为技术有限公司”为分析对象，基于展会公开数据呈现企业展会参与。关键指标包括：展会参与 255、当前页参展展馆数 8、当前页展馆CR3 37.5%、当前页活跃年份 2、当前页最新参展年份 2026。报告呈现已请求维度的查询记录与当前页结构化汇总，供后续逐条核验。","limit":"数据来自展会公开信息；少量字段可能存在更新延迟。分页结果仅代表当前页样本；上游总量不等于当前页可见记录数。","insights":[{"feature":"参展记录收录","evidence":"企业展会参与记录 255 条。","interpretation":"该数值仅为上游收录记录总量；参展时间、身份及活动成效需逐条核验。"},{"feature":"参展展馆集中度","evidence":"当前页样本中，“深圳会展中心”参展占比约 12%，前 3 展馆合计 38%（CR3）。","interpretation":"当前页样本的展馆布局多元；该比例不代表上游全量分布，不据此外推企业整体展馆策略。"}]}
- **pass** 不把参展等同赞助或获奖：已证明“不把参展等同赞助或获奖”。 摘要/局限={"summary":"本报告以“华为技术有限公司”为分析对象，基于展会公开数据呈现企业展会参与。关键指标包括：展会参与 255、当前页参展展馆数 8、当前页展馆CR3 37.5%、当前页活跃年份 2、当前页最新参展年份 2026。报告呈现已请求维度的查询记录与当前页结构化汇总，供后续逐条核验。","limit":"数据来自展会公开信息；少量字段可能存在更新延迟。分页结果仅代表当前页样本；上游总量不等于当前页可见记录数。","insights":[{"feature":"参展记录收录","evidence":"企业展会参与记录 255 条。","interpretation":"该数值仅为上游收录记录总量；参展时间、身份及活动成效需逐条核验。"},{"feature":"参展展馆集中度","evidence":"当前页样本中，“深圳会展中心”参展占比约 12%，前 3 展馆合计 38%（CR3）。","interpretation":"当前页样本的展馆布局多元；该比例不代表上游全量分布，不据此外推企业整体展馆策略。"}]}

## 离线浏览器检查

[Ego Lite 离线图表、页面溢出和脚本检查](browser-check.json)
[页面截图](browser.png)