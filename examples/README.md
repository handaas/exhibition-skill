# exhibition-skill：已验收示例

本目录只展示 **5 个完全通过的真实正向场景**（最低要求4例）。

每例均为真实、非空、非缓存调用；技术检查、独立业务检查和离线浏览器检查全部通过。不把空数据、报错处理或仅生成页面计作通过。历史验收记录保留在本地 test-records/；本目录的 HTML/Markdown 由原 JSON 重渲染，不代表重新查询或重新验收。

| 场景 | 真实使用需求 | 报告 |
|---|---|---|
| [科技企业参展画像](01-enterprise-participation/README.md) | 请分析华为技术有限公司的参展记录和展会布局。 | [HTML](01-enterprise-participation/report.html) / [MD](01-enterprise-participation/report.md) / [JSON](01-enterprise-participation/report.json) |
| [车企参展布局](02-ev-participation/README.md) | 请查看比亚迪股份有限公司的展会参与情况。 | [HTML](02-ev-participation/report.html) / [MD](02-ev-participation/report.md) / [JSON](02-ev-participation/report.json) |
| [芯片企业参展时间线与会场触点](09-template-enterprise-participation/README.md) | 请查询珠海市杰理科技股份有限公司的公开参展记录，按实际举办时间整理参展活动时间线，并列出对应展会名称和展馆或地区触点，用于安排同业活动跟踪。 | [HTML](09-template-enterprise-participation/report.html) / [MD](09-template-enterprise-participation/report.md) / [JSON](09-template-enterprise-participation/report.json) |
| [国际线缆线材展精确检索](10-exact-cable-fair-discovery/README.md) | 请精确检索“中国国际线缆及线材展览会”，确认实际返回的展会名称与该目标全称对齐，并按实际可用字段列出届次、举办时间、展馆或简介，用于锁定后续调研对象。 | [HTML](10-exact-cable-fair-discovery/report.html) / [MD](10-exact-cable-fair-discovery/report.md) / [JSON](10-exact-cable-fair-discovery/report.json) |
| [半导体行业展会机会池](11-semiconductor-fair-landscape/README.md) | 请检索多个不同的半导体相关展会，要求相关性能够从实际返回的展会名称或简介中看出；列出展会名称，并按实际可用字段补充举办时间或展馆，形成招商团队可比较的行业机会池；本次不查询展商。 | [HTML](11-semiconductor-fair-landscape/report.html) / [MD](11-semiconductor-fair-landscape/report.md) / [JSON](11-semiconductor-fair-landscape/report.json) |

- [逐例验收结果](results.json) · [业务复核](review.json) · [证据摘要](evidence-index.json)
- 完整测试记录仅存于本地 test-records/live-replaced-20261027/（仅本地审计用，不随本目录发布），不属于可展示示例。
- 当前数据与结论限于原查询时点及公开样本；覆盖率不代表准确率或低风险。
