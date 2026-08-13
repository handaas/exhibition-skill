#!/usr/bin/env python3
"""Compose an exhibition big-data report by orchestrating the exhibition MCP.

Calls the upstream exhibition-mcp-server tools and assembles a structured JSON
payload rendered into a professional HTML / Markdown report. Supports
``--dry-run`` which returns a well-formed skeleton from the bundled sample data
WITHOUT contacting the MCP.

Two analysis modes are supported:
  - Enterprise mode (default, requires ``--enterprise``): returns the
    enterprise's exhibition participation, plus optional market context.
  - Market search mode (``--venue-region`` / ``--fair-region`` / ``--fair-industries``
    / ``--search``): returns venues / exhibitors / exhibitions matching the
    given criteria, independent of a specific enterprise.

This file never prints secrets; MCP credentials live in the server's own .env.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Mapping, Optional

from common import REPORT_BANNER, REPORT_TYPE, json_dumps, load_json_file, print_json
import mcp_client
from render_report import render_html, render_markdown, html_to_pdf

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "report.example.json"

# Exhibition MCP tools.
T_FUZZY = "exhibition_bigdata_fuzzy_search"
T_PARTICIPATION = "exhibition_bigdata_exhibition_participation"
T_VENUE = "exhibition_bigdata_exhibition_venue_search"
T_EXHIBITION = "exhibition_bigdata_exhibition_search"
T_EXHIBITOR = "exhibition_bigdata_exhibitor_search"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _is_api_error(value: Any) -> bool:
    """Detect MCP API error responses (not empty data, but actual failures like 405)."""
    if value is None:
        return False
    if isinstance(value, str):
        return any(s in value for s in ("接口调用失败", "查询失败", "状态码：4", "状态码：5"))
    if isinstance(value, dict):
        for v in value.values():
            if isinstance(v, str) and any(s in v for s in ("接口调用失败", "查询失败", "状态码：4", "状态码：5")):
                return True
    return False

def _first_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if _is_api_error(value):
            return []
        # Treat upstream empty responses ({"text": "查询数据为空"}) and internal
        # skip markers ({"_error": "未指定..."}) as empty so tables don't render
        # a phantom all-"-" row.
        if set(value.keys()) <= {"text", "error", "code", "_error"} and not any(
            isinstance(value.get(k), list) for k in ("resultList", "list", "items", "data")
        ):
            return []
        for key in ("resultList", "list", "items", "data"):
            if isinstance(value.get(key), list):
                return value[key]
    if value in (None, "", {}):
        return []
    return [value]


def _first_record(value: Any) -> Dict[str, Any]:
    for record in _first_list(value):
        if isinstance(record, dict):
            return record
    if isinstance(value, dict):
        return value
    return {}


def _text(value: Any, limit: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        t = json.dumps(value, ensure_ascii=False)
    else:
        t = str(value)
    t = " ".join(t.split())
    if limit and len(t) > limit:
        return t[: limit - 1].rstrip() + "…"
    return t


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_call(tool: str, arguments: Dict[str, Any]) -> Any:
    try:
        result = mcp_client.call_tool(tool, arguments)
        if _is_api_error(result):
            return {"_error": "API错误"}
        return result
    except Exception as exc:
        return {"_error": str(exc)}


def _safe_total(payload: Any) -> Any:
    if isinstance(payload, dict):
        if _is_api_error(payload):
            return None
        return payload.get("total")
    return None


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #

def resolve_enterprise_name(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {"keyword": "", "enterprise": "", "resolved": False, "reason": "关键词为空"}
    if any(suffix in raw for suffix in ("公司", "集团", "有限", "院", "厂", "中心", "事务所", "合作社", "合伙")):
        return {"keyword": raw, "enterprise": raw, "resolved": True, "reason": "视为企业全称"}
    fuzzy = _safe_call(T_FUZZY, {"matchKeyword": raw, "pageIndex": 1})
    record = _first_record(fuzzy)
    name = str(record.get("name") or "").strip()
    if name:
        return {"keyword": raw, "enterprise": name, "resolved": True, "reason": "由关键词模糊查询补全", "fuzzy_total": _int(_safe_total(fuzzy)), "record": record}
    return {"keyword": raw, "enterprise": raw, "resolved": False, "reason": "模糊查询未命中企业全称，按关键词直查"}


# --------------------------------------------------------------------------- #
# Enterprise profile helpers (from fuzzy_search record)
# --------------------------------------------------------------------------- #

def _extract_profile(record: Dict[str, Any]) -> Dict[str, Any]:
    """Extract enterprise profile fields from a fuzzy_search record."""
    return {
        "name": _text(record.get("name")),
        "reg_capital": record.get("regCapitalValue"),
        "reg_capital_coin": _text(record.get("regCapitalCoinType")),
        "annual_turnover": _text(record.get("annualTurnover")),
        "oper_status": _text(record.get("operStatus")),
        "enterprise_type": _text(record.get("enterpriseType")),
        "found_time": _text(record.get("foundTime")),
        "legal_rep": _text(record.get("legalRepresentative")),
        "address": _text(record.get("address")),
        "homepage": _text(record.get("homepage")),
    }


def _format_capital(val: Any, coin: str = "") -> str:
    """Format capital value: 10995210218.0 -> '109.95 亿'."""
    try:
        v = float(val)
        if v >= 1e8:
            s = f"{v / 1e8:.2f} 亿"
        elif v >= 1e4:
            s = f"{v / 1e4:.2f} 万"
        else:
            s = f"{v:.0f}"
        if coin:
            s += f" {coin}"
        return s
    except (TypeError, ValueError):
        return _text(val) if val else "-"


def _enrich_metrics_with_profile(metrics: List[Dict[str, Any]], record: Any) -> List[Dict[str, Any]]:
    """Append enterprise profile metrics from a fuzzy_search record."""
    if not isinstance(record, dict):
        return metrics
    _prof = _extract_profile(record)
    if _prof.get("reg_capital") and _prof["reg_capital"] not in ("-", "", None):
        metrics.append({"label": "注册资本", "value": _format_capital(_prof["reg_capital"], _prof.get("reg_capital_coin", "")), "hint": "工商登记注册资本"})
    if _prof.get("found_time") and _prof["found_time"] != "-":
        metrics.append({"label": "成立时间", "value": _prof["found_time"], "hint": "工商登记成立日期"})
    if _prof.get("oper_status") and _prof["oper_status"] != "-":
        metrics.append({"label": "经营状态", "value": _prof["oper_status"], "hint": "工商登记经营状态"})
    if _prof.get("enterprise_type") and _prof["enterprise_type"] != "-":
        metrics.append({"label": "企业类型", "value": _prof["enterprise_type"], "hint": "工商登记企业类型"})
    if _prof.get("legal_rep") and _prof["legal_rep"] != "-":
        metrics.append({"label": "法定代表人", "value": _prof["legal_rep"], "hint": "工商登记法定代表人"})
    return metrics

def _derive_core_metrics(metrics: List[Dict[str, Any]], core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Derive additional metrics from core analysis sections."""
    pav_dist = core.get("pavilion_dist", []) if isinstance(core, dict) else []
    year_trend = core.get("year_trend", []) if isinstance(core, dict) else []
    if isinstance(pav_dist, list) and pav_dist:
        metrics.append({"label": "参展展馆数", "value": str(len(pav_dist)), "hint": "不同展馆数量"})
        try:
            nums = [int(r.get("参展次数", 0)) for r in pav_dist if r.get("参展次数")]
            total = sum(nums)
            if total > 0:
                top3 = sum(sorted(nums, reverse=True)[:3])
                metrics.append({"label": "展馆CR3", "value": f"{top3/total*100:.1f}%", "hint": "前3大展馆参展集中度"})
        except (ValueError, TypeError):
            pass
    if isinstance(year_trend, list) and year_trend:
        metrics.append({"label": "活跃年份", "value": str(len(year_trend)), "hint": "有参展记录的年度数"})
        try:
            years = sorted([str(r.get("年份", "")) for r in year_trend if r.get("年份")], reverse=True)
            if years:
                metrics.append({"label": "最新参展年份", "value": years[0], "hint": "最近一次参展年份"})
            nums = [(str(r.get("年份", "")), int(r.get("参展次数", 0))) for r in year_trend if r.get("参展次数")]
            if nums:
                peak = max(nums, key=lambda x: x[1])
                metrics.append({"label": "参展峰值", "value": f"{peak[0]}年 {peak[1]}次", "hint": "参展最多的年份及次数"})
        except (ValueError, TypeError):
            pass
    return metrics


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #

def build_subject(raw: str, resolved: Mapping[str, Any], keyword_type: str, search_mode: bool) -> Dict[str, Any]:
    return {
        "enterprise": resolved.get("enterprise") or raw,
        "matchKeyword": resolved.get("enterprise") or raw,
        "keywordType": keyword_type,
        "match_raw": raw,
        "resolved": bool(resolved.get("resolved")) and not search_mode,
        "resolve_reason": resolved.get("reason", ""),
        "search_mode": search_mode,
    }


def build_caliber(subject: Mapping[str, Any], search_mode: bool) -> Dict[str, Any]:
    if search_mode:
        match_target = subject.get("match_raw") or "市场检索（无指定企业）"
        match_type = "市场检索模式：按展馆区域 / 展会区域 / 展会行业 / 展会关键词检索，与特定企业主体无关"
    else:
        match_target = subject.get("enterprise") or subject.get("match_raw")
        match_type = f"展会参与按企业主体匹配（keywordType={subject.get('keywordType', 'name')}）；支持企业名称/注册号/统一社会信用代码/企业 id"
    return {
        "match_target": match_target,
        "match_type": match_type,
        "data_scope": "展会参与、展馆查询、展会查询、展商查询",
        "products": ["展会参与", "展馆查询", "展会查询", "展商查询"],
        "limit": "数据来自展会公开信息；少量字段可能存在更新延迟。",
    }


def _table_from(payload: Any, fields: List[tuple]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in _first_list(payload):
        if not isinstance(item, dict):
            continue
        row: Dict[str, Any] = {}
        for key, label in fields:
            row[label] = _text(item.get(key)) or "-"
        rows.append(row)
    return rows


def _fair_date_range(item: Mapping[str, Any]) -> str:
    """Format fairBeginTime + fairEndTime into "开始 至 结束"."""
    begin = _text(item.get("fairBeginTime"))
    end = _text(item.get("fairEndTime"))
    if begin and end:
        return f"{begin} 至 {end}"
    return begin or end or "-"


def _fair_status(item: Mapping[str, Any]) -> str:
    """isOpen: 1=开放/即将开展, 0=已结束或未开放."""
    v = item.get("isOpen")
    if v is None:
        return "-"
    try:
        return "开放/即将开展" if int(v) == 1 else "已结束/未开放"
    except (TypeError, ValueError):
        return _text(v)


def _participation_rows(payload: Any) -> List[Dict[str, Any]]:
    """participation/exhibition share fields: fairName/fairBeginTime/fairEndTime/
    fairPavilion/fairDesc/isOpen. We render date range, venue, status, and a
    highlight (fairDesc, truncated)."""
    rows: List[Dict[str, Any]] = []
    for item in _first_list(payload):
        if not isinstance(item, dict):
            continue
        rows.append({
            "展会名称": _text(item.get("fairName")) or "-",
            "展会日期": _fair_date_range(item),
            "展馆": _text(item.get("fairPavilion")) or "-",
            "状态": _fair_status(item),
            "展会亮点": _text(item.get("fairDesc"), limit=80) or "-",
        })
    return rows


def build_core_analysis(
    participation: Any,
    venue: Any,
    exhibition: Any,
    exhibitor: Any,
) -> Dict[str, Any]:
    participation_rows = _participation_rows(participation)
    exhibition_rows = _participation_rows(exhibition)
    venue_rows = _table_from(
        venue,
        [
            ("venueName", "展馆名称"),
            ("venueRegion", "所在区域"),
            ("venueAddress", "地址"),
            ("venueArea", "展馆面积"),
            ("hallCount", "展厅数量"),
        ],
    )
    exhibitor_rows = _table_from(
        exhibitor,
        [
            ("exhibitorName", "展商名称"),
            ("fairName", "参展展会"),
            ("fairIndustry", "所属行业"),
            ("fairRegion", "展会区域"),
            ("boothNo", "展位号"),
        ],
    )

    participation_total = _safe_total(participation)
    venue_total = _safe_total(venue)
    exhibition_total = _safe_total(exhibition)
    exhibitor_total = _safe_total(exhibitor)

    # 派生：展馆分布（按 fairPavilion 聚合参展记录数）。
    pavilion_dist_rows = _aggregate_count(participation_rows, "展馆", name_key="展馆", count_key="参展次数")
    # 派生：参展年度趋势（从 fairBeginTime 提取年份）。
    year_trend_rows = _year_trend_from(participation_rows, "展会日期")

    sections: List[Dict[str, Any]] = []
    if participation_rows or participation_total is not None:
        sections.append({"key": "participation", "title": "展会参与", "kind": "table", "note": f"企业展会参与记录 {participation_total if participation_total is not None else '若干'} 条", "columns": [("展会名称", "展会名称"), ("展会日期", "展会日期"), ("展馆", "展馆"), ("状态", "状态"), ("展会亮点", "展会亮点")]})
    if pavilion_dist_rows:
        sections.append({"key": "pavilion_dist", "title": "参展展馆分布", "kind": "bar", "note": "按展馆聚合参展记录数", "chart": {"name": "展馆", "value": "参展次数", "orient": "h"}, "columns": [("展馆", "展馆"), ("参展次数", "参展次数")]})
    if year_trend_rows:
        sections.append({"key": "year_trend", "title": "参展年度趋势", "kind": "line", "note": "按年度统计参展次数", "chart": {"x": "年份", "y": "参展次数", "area": True}, "columns": [("年份", "年份"), ("参展次数", "参展次数")]})
    if venue_rows or venue_total is not None:
        sections.append({"key": "venue", "title": "展馆查询", "kind": "table", "note": f"展馆记录 {venue_total if venue_total is not None else '若干'} 条", "columns": [("展馆名称", "展馆名称"), ("所在区域", "所在区域"), ("地址", "地址"), ("展馆面积", "展馆面积"), ("展厅数量", "展厅数量")]})
    if exhibition_rows or exhibition_total is not None:
        sections.append({"key": "exhibition", "title": "展会查询", "kind": "table", "note": f"展会记录 {exhibition_total if exhibition_total is not None else '若干'} 条", "columns": [("展会名称", "展会名称"), ("展会日期", "展会日期"), ("展馆", "展馆"), ("状态", "状态"), ("展会亮点", "展会亮点")]})
    if exhibitor_rows or exhibitor_total is not None:
        sections.append({"key": "exhibitor", "title": "展商查询", "kind": "table", "note": f"展商记录 {exhibitor_total if exhibitor_total is not None else '若干'} 条", "columns": [("展商名称", "展商名称"), ("参展展会", "参展展会"), ("所属行业", "所属行业"), ("展会区域", "展会区域"), ("展位号", "展位号")]})

    return {
        "sections": sections,
        "participation": participation_rows,
        "pavilion_dist": pavilion_dist_rows,
        "year_trend": year_trend_rows,
        "venue": venue_rows,
        "exhibition": exhibition_rows,
        "exhibitor": exhibitor_rows,
    }


def _aggregate_count(rows: List[Mapping[str, Any]], key: str, top_n: int = 0, name_key: str = "名称", count_key: str = "数量") -> List[Dict[str, Any]]:
    """Aggregate rows by a field, returning [{name_key: value, count_key: n}] sorted desc."""
    counts: Dict[str, int] = {}
    for r in rows:
        v = r.get(key)
        if not v or v == "-":
            continue
        counts[v] = counts.get(v, 0) + 1
    items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    if top_n:
        items = items[:top_n]
    return [{name_key: k, count_key: str(n)} for k, n in items]


def _year_trend_from(rows: List[Mapping[str, Any]], date_key: str) -> List[Dict[str, Any]]:
    """Extract 4-digit year from a date string and aggregate counts by year, sorted."""
    import re as _re
    counts: Dict[str, int] = {}
    for r in rows:
        raw = str(r.get(date_key) or "")
        m = _re.search(r"(20\d{2})", raw)
        if not m:
            continue
        y = m.group(1)
        counts[y] = counts.get(y, 0) + 1
    return [{"年份": y, "参展次数": str(n)} for y, n in sorted(counts.items())]


def build_records(core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if core.get("participation"):
        for item in core.get("participation") or []:
            rows.append({
                "展会名称": item.get("展会名称") or "-",
                "展会日期": item.get("展会日期") or "-",
                "展馆": item.get("展馆") or "-",
                "状态": item.get("状态") or "-",
            })
    if not rows and core.get("exhibition"):
        for item in core.get("exhibition") or []:
            rows.append({
                "展会名称": item.get("展会名称") or "-",
                "展会日期": item.get("展会日期") or "-",
                "展馆": item.get("展馆") or "-",
                "状态": item.get("状态") or "-",
            })
    if not rows and core.get("exhibitor"):
        for item in core.get("exhibitor") or []:
            rows.append({
                "展商名称": item.get("展商名称") or "-",
                "参展展会": item.get("参展展会") or "-",
                "所属行业": item.get("所属行业") or "-",
            })
    return rows[:20]


def _concentration_rows(rows: List[Mapping[str, Any]], name_key: str, value_key: str, top_n: int = 3) -> Dict[str, Any]:
    """CRn concentration from aggregated rows."""
    items = []
    for r in rows:
        try:
            items.append((r.get(name_key, "-"), float(str(r.get(value_key, 0)).replace(",", ""))))
        except (TypeError, ValueError):
            items.append((r.get(name_key, "-"), 0.0))
    total = sum(v for _, v in items)
    if not total:
        return {}
    items.sort(key=lambda x: x[1], reverse=True)
    cr = sum(v for _, v in items[:top_n]) / total * 100
    return {"top": items[0][0], "top_share": items[0][1] / total * 100, "cr": cr, "total": total, "count": len(items)}


def _year_trend_analysis(rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Direction/peak/YoY for参展次数 year series."""
    nums = []
    for r in rows:
        try:
            nums.append(float(str(r.get("参展次数", 0)).replace(",", "")))
        except (TypeError, ValueError):
            nums.append(0.0)
    if not nums:
        return {}
    peak_idx = max(range(len(nums)), key=lambda i: nums[i])
    direction = "持平"
    yoy = ""
    if len(nums) >= 2:
        last, prev = nums[-1], nums[-2]
        if prev > 0:
            pct = (last - prev) / prev * 100
            if pct > 5:
                direction = f"上升 {pct:.0f}%"
            elif pct < -5:
                direction = f"下降 {abs(pct):.0f}%"
            yoy = f"同比 {pct:+.0f}%"
    return {"peak_period": rows[peak_idx].get("年份", "-"), "peak_value": nums[peak_idx], "direction": direction, "yoy": yoy, "last": nums[-1]}


def build_insights(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    metric_map = {m["label"]: str(m["value"]) for m in metrics}

    if subject.get("search_mode"):
        venue_total = metric_map.get("展馆")
        exhibition_total = metric_map.get("展会")
        exhibitor_total = metric_map.get("展商")
        if exhibition_total:
            insights.append({
                "feature": "市场展会规模",
                "evidence": f"检索命中展会 {exhibition_total} 场。",
                "interpretation": "展会数量反映目标区域/行业的市场活跃度，是评估线下营销机会的重要参考。",
            })
        if exhibitor_total:
            insights.append({
                "feature": "展商密度",
                "evidence": f"检索命中展商 {exhibitor_total} 家。",
                "interpretation": "展商数量反映行业竞争与生态规模；可结合行业分布定位潜在合作伙伴或竞品。",
            })
        if venue_total:
            insights.append({
                "feature": "展馆资源",
                "evidence": f"检索命中展馆 {venue_total} 家。",
                "interpretation": "展馆资源反映目标区域的办展基础设施承载力。",
            })
        # 行业分布集中度（基于 exhibition/exhibitor 聚合）
        exh_rows = core.get("exhibition") or []
        if exh_rows:
            conc = _concentration_rows(_agg_local(exh_rows, "展会行业"), "名称", "数量", 3)
            if conc:
                insights.append({
                    "feature": "展会行业集中度",
                    "evidence": f"“{conc['top']}”类展会占比约 {conc['top_share']:.0f}%，前 3 行业合计 {conc['cr']:.0f}%（CR3）。",
                    "interpretation": "行业集中度反映目标市场的主导产业；集中度高便于聚焦垂直领域营销。",
                })
    else:
        participation_total = metric_map.get("展会参与")
        participation = core.get("participation") or []
        if participation_total:
            insights.append({
                "feature": "参展活跃度",
                "evidence": f"企业展会参与记录 {participation_total} 条。",
                "interpretation": "参展频度反映企业线下营销投入与行业曝光度；持续参展通常意味着稳定的渠道与品牌建设。",
            })
        # 展馆集中度（基于聚合后的 pavilion_dist）。
        pavilion_dist = core.get("pavilion_dist") or []
        if pavilion_dist:
            conc = _concentration_rows(pavilion_dist, "展馆", "参展次数", 3)
            if conc:
                focus = "聚焦" if conc["top_share"] >= 60 else ("多元" if conc["top_share"] < 40 else "较聚焦")
                insights.append({
                    "feature": "参展展馆集中度",
                    "evidence": f"“{conc['top']}”参展占比约 {conc['top_share']:.0f}%，前 3 展馆合计 {conc['cr']:.0f}%（CR3）。",
                    "interpretation": f"展馆布局{focus}；高集中度反映核心展会阵地清晰，多元分布说明跨场馆/跨城市拓展。",
                })
        # 年度趋势
        year_trend = core.get("year_trend") or []
        if year_trend:
            ta = _year_trend_analysis(year_trend)
            if ta:
                insights.append({
                    "feature": "参展年度趋势",
                    "evidence": f"峰值出现在“{ta['peak_period']}”（{ta['peak_value']:.0f} 次），近年{ta['direction']}，{ta.get('yoy', '')}。",
                    "interpretation": "参展频次上升反映线下营销加码或新业务推广；下降可能是预算收缩或转向线上。",
                })
        # 开展状态分布
        if participation:
            status_counts: Dict[str, int] = {}
            for r in participation:
                v = r.get("状态")
                if v and v != "-":
                    status_counts[v] = status_counts.get(v, 0) + 1
            if status_counts:
                top_status = sorted(status_counts.items(), key=lambda kv: kv[1], reverse=True)[0]
                insights.append({
                    "feature": "开展状态",
                    "evidence": f"主要状态为“{top_status[0]}”（{top_status[1]} / {len(participation)}）。",
                    "interpretation": "开放/即将开展的展会占比高说明企业近期线下营销活跃；已结束为主则反映历史参展记录较多。",
                })
    if not insights:
        insights.append({
            "feature": "数据完整性",
            "evidence": "部分维度未返回有效数据。",
            "interpretation": "建议核对检索条件或企业全称，或检查 MCP 连接与上游数据产品覆盖范围。",
        })
    return insights


def _agg_local(rows: List[Mapping[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Local aggregation helper returning [{名称, 数量}]."""
    counts: Dict[str, int] = {}
    for r in rows:
        v = r.get(key)
        if not v or v == "-":
            continue
        counts[v] = counts.get(v, 0) + 1
    return [{"名称": k, "数量": str(n)} for k, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]


def build_metrics(participation: Any, venue: Any, exhibition: Any, exhibitor: Any) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []

    def _ttotal(payload: Any, present: bool) -> str:
        if not present:
            return "-"
        if isinstance(payload, dict) and payload.get("total") is not None:
            return _text(payload.get("total"))
        return "若干"

    has_part = isinstance(participation, dict) and "_error" not in participation
    has_venue = isinstance(venue, dict) and "_error" not in venue
    has_exh = isinstance(exhibition, dict) and "_error" not in exhibition
    has_exhibitor = isinstance(exhibitor, dict) and "_error" not in exhibitor

    metrics.append({"label": "展会参与", "value": _ttotal(participation, has_part), "hint": "企业展会参与条数"})
    metrics.append({"label": "展馆", "value": _ttotal(venue, has_venue), "hint": "展馆查询命中数"})
    metrics.append({"label": "展会", "value": _ttotal(exhibition, has_exh), "hint": "展会查询命中数"})
    metrics.append({"label": "展商", "value": _ttotal(exhibitor, has_exhibitor), "hint": "展商查询命中数"})
    return [m for m in metrics if m.get("value") not in ("", None, "-")]


def build_abstract(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]]) -> str:
    if subject.get("search_mode"):
        name = subject.get("match_raw") or "目标市场"
        parts = [f"本报告以“{name}”为检索范围，基于展会公开数据，系统呈现展馆、展会、展商的市场检索结果。"]
    else:
        name = subject.get("enterprise") or subject.get("match_raw") or "目标企业"
        parts = [f"本报告以“{name}”为分析对象，基于展会公开数据，系统呈现企业展会参与记录及目标市场展馆、展会、展商检索结果。"]
    if metrics:
        kv = "、".join(f"{m['label']} {m['value']}" for m in metrics[:5])
        parts.append(f"关键指标包括：{kv}。")
    parts.append("报告围绕展会参与度与市场检索规模给出结构化解读，便于线下营销、行业研究与展会选型决策参考。")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Dry-run sample
# --------------------------------------------------------------------------- #

def build_dry_run_payload(raw: str, keyword_type: str) -> Dict[str, Any]:
    try:
        sample = load_json_file(SAMPLE_PATH)
    except Exception:
        sample = {}
    sample = sample if isinstance(sample, dict) else {}
    subject = sample.get("subject") or {"enterprise": raw, "matchKeyword": raw, "keywordType": keyword_type, "match_raw": raw}
    subject = {**subject, "match_raw": raw, "keywordType": keyword_type}
    core = sample.get("core_analysis") or {}
    metrics = sample.get("metrics") or []
    return _assemble(subject, core, metrics, dry_run=True, search_mode=bool(subject.get("search_mode")))


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def _assemble(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]], *, dry_run: bool, search_mode: bool = False) -> Dict[str, Any]:
    abstract = build_abstract(subject, core, metrics)
    records = build_records(core)
    insights = build_insights(subject, core, metrics)
    # Quality gate: count populated core-analysis sections.
    ca = core if isinstance(core, dict) else {}
    secs = ca.get("sections", [])
    if secs:
        total_secs = len(secs)
        populated = sum(1 for s in secs if isinstance(s, dict) and ca.get(s.get("key")) not in (None, "", [], {}))
    else:
        total_secs = max(1, len([k for k in ca if k != "sections"]))
        populated = sum(1 for k in ca if k != "sections" and ca.get(k) not in (None, "", [], {}))
    quality_report = {
        "total_sections": total_secs,
        "populated_sections": populated,
        "empty_sections": total_secs - populated,
        "coverage_pct": round(populated / max(1, total_secs) * 100),
    }
    if populated == 0:
        import sys
        print("⚠️ 质量门禁警告: 所有核心分析维度均无数据", file=sys.stderr)
    mode_label = "市场检索" if search_mode else "企业参展"
    title = f"{subject.get('enterprise') or subject.get('match_raw') or '目标'} 展会大数据报告（{mode_label}）"
    return {
        "report_type": REPORT_TYPE,
        "title": title,
        "banner": REPORT_BANNER,
        "subject": dict(subject),
        "abstract": abstract,
        "summary": abstract,
        "executive_summary": [item["interpretation"] for item in insights][:5] or [abstract[:120]],
        "metrics": list(metrics),
        "caliber": build_caliber(subject, search_mode),
        "core_analysis": dict(core),
        "representative_records": records,
        "insights": insights,
        "data_source": {
            "mcp_server": "exhibition-mcp-server",
            "products": [
                {"name": "展会参与", "product_id": "66a26918ff3066996ecc6471"},
                {"name": "展馆查询", "product_id": "66e2d2ca428a1f4cd69c1083"},
                {"name": "展会查询", "product_id": "66a0f6ca477cbe5f7605973f"},
                {"name": "展商查询", "product_id": "66d5b7e0537c3f61d646c473"},
            ],
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "dry_run": dry_run,
            "quality_report": quality_report,
            "mode": "market_search" if search_mode else "enterprise",
        },
    }


def build_payload(
    raw: str,
    keyword_type: str,
    venue_region: Optional[str],
    fair_region: Optional[str],
    fair_industries: Optional[str],
    search_keyword: Optional[str],
    page_size: int,
) -> Dict[str, Any]:
    search_mode = bool(venue_region or fair_region or fair_industries or search_keyword)
    resolved = resolve_enterprise_name(raw) if raw else {"enterprise": "", "resolved": False, "reason": "未指定企业（市场检索模式）"}
    enterprise = resolved.get("enterprise") or raw

    participation: Any = {"_error": "未指定企业，跳过展会参与查询"} if not raw else _safe_call(
        T_PARTICIPATION,
        {"matchKeyword": enterprise, "keywordType": keyword_type, "pageIndex": 1, "pageSize": page_size},
    )

    venue: Any = {"_error": "未指定展馆区域，跳过展馆查询"} if not venue_region else _safe_call(T_VENUE, {"pavilionRegion": venue_region, "matchKeyword": search_keyword or None, "pageIndex": 1})

    exhibition: Any = {"_error": "未指定检索条件，跳过展会查询"} if not search_keyword else _safe_call(T_EXHIBITION, {"matchKeyword": search_keyword, "pageIndex": 1})

    exhibitor_args: Dict[str, Any] = {"pageIndex": 1, "pageSize": page_size}
    if fair_region:
        exhibitor_args["fairRegion"] = fair_region
    if fair_industries:
        exhibitor_args["fairIndustries"] = fair_industries
    if search_keyword:
        exhibitor_args["matchKeyword"] = search_keyword
    exhibitor: Any = {"_error": "未指定展商检索条件，跳过展商查询"} if not (fair_region or fair_industries or search_keyword) else _safe_call(T_EXHIBITOR, exhibitor_args)

    subject = build_subject(raw or (search_keyword or fair_region or venue_region or "市场检索"), resolved, keyword_type, search_mode)
    core = build_core_analysis(participation, venue, exhibition, exhibitor)
    metrics = build_metrics(participation, venue, exhibition, exhibitor)
    # --- Enterprise profile enrichment (from fuzzy_search) ---
    _enrich_metrics_with_profile(metrics, resolved.get("record") if isinstance(resolved, dict) else None)
    _derive_core_metrics(metrics, core if isinstance(core, dict) else {})
    return _assemble(subject, core, metrics, dry_run=False, search_mode=search_mode)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Compose an exhibition big-data report via the exhibition MCP.")
    parser.add_argument("--enterprise", help="企业全称或关键词（企业参展模式，关键词将自动模糊补全）")
    parser.add_argument("--keyword-type", default="name", help="主体类型：name/nameId/regNumber/socialCreditCode")
    parser.add_argument("--venue-region", help="展馆所在区域（市场检索模式：展馆查询，必填项之一）")
    parser.add_argument("--fair-region", help="展会区域（市场检索模式：展商查询过滤）")
    parser.add_argument("--fair-industries", help="展会行业（市场检索模式：展商查询过滤）")
    parser.add_argument("--search", dest="search_keyword", help="展会 / 展商 / 展馆关键词（市场检索模式）")
    parser.add_argument("--page-size", type=int, default=10, help="分页大小（最多 50）")
    parser.add_argument("--dry-run", action="store_true", help="不调用真实 MCP，使用样例数据组装报告骨架")
    parser.add_argument("--output", help="输出 JSON 路径；省略则打印到 stdout")
    parser.add_argument("--report-output", help="同时输出 HTML 报告（.html）与 Markdown 报告（.md）")
    parser.add_argument("--pdf-output", help="额外输出 PDF 报告（.pdf）；需要 Playwright + Chromium")
    args = parser.parse_args()

    if not args.enterprise and not args.dry_run and not (args.venue_region or args.fair_region or args.fair_industries or args.search_keyword):
        parser.error("至少需要 --enterprise（企业参展模式）或 --venue-region / --fair-region / --fair-industries / --search 之一（市场检索模式）；或使用 --dry-run。")

    if args.dry_run:
        payload = build_dry_run_payload(args.enterprise or "示例科技有限公司", args.keyword_type)
    else:
        payload = build_payload(args.enterprise or "", args.keyword_type, args.venue_region, args.fair_region, args.fair_industries, args.search_keyword, args.page_size)

    if args.output:
        out = pathlib.Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_dumps(payload, pretty=True), encoding="utf-8")
        print_json({"ok": True, "json": str(out), "dry_run": args.dry_run})
    else:
        print_json(payload)

    if args.report_output:
        base_out = pathlib.Path(args.report_output).expanduser()
        base_out.parent.mkdir(parents=True, exist_ok=True)
        html_path = base_out.with_suffix(".html") if base_out.suffix.lower() not in (".html", ".htm") else base_out
        md_path = html_path.with_suffix(".md")
        html_path.write_text(render_html(payload), encoding="utf-8")
        md_path.write_text(render_markdown(payload), encoding="utf-8")
        if args.pdf_output:
            pdf_path = pathlib.Path(args.pdf_output).expanduser()
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            html_to_pdf(render_html(payload), str(pdf_path))
        print_json({"ok": True, "html": str(html_path), "markdown": str(md_path), "pdf": str(pdf_path) if args.pdf_output else None, "dry_run": args.dry_run})


if __name__ == "__main__":
    main()
