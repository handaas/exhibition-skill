#!/usr/bin/env python3
"""Compose an exhibition big-data report by orchestrating the exhibition MCP.

Calls the upstream exhibition-mcp-server tools and assembles a structured JSON
payload rendered into a professional HTML / Markdown report. Supports
``--dry-run`` which returns a well-formed skeleton from the bundled sample data
WITHOUT contacting the MCP.

Four analysis modes are supported:
  - Enterprise mode (default, requires ``--enterprise``): returns the
    enterprise's exhibition participation, plus optional market context.
  - Market search mode (``--venue-region`` / ``--fair-region`` / ``--fair-industries``
    / ``--search``): returns venues / exhibitors / exhibitions matching the
    given criteria, independent of a specific enterprise.
  - Fair-only search mode (``--search ... --search-target exhibition``): calls
    only the exhibition search product.
  - Fair exhibitors mode (``--fair-exhibitors``): searches for a fair, then
    passes the selected result's real ``_id`` to the fair-exhibitors product.

This file never prints secrets; MCP credentials live in the server's own .env.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import html as _html
import json
import pathlib
import re as _re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from common import REPORT_BANNER, REPORT_TYPE, attach_pagination, call_tool_once, collect_detail_pages, json_dumps, load_json_file, paid_call_scope, print_json
import mcp_client
from render_report import render_html, render_markdown, html_to_pdf

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "report.example.json"

# Exhibition MCP tools.
T_FUZZY = "exhibition_bigdata_fuzzy_search"
T_PARTICIPATION = "exhibition_bigdata_exhibition_participation"
T_VENUE = "exhibition_bigdata_exhibition_venue_search"
T_EXHIBITION = "exhibition_bigdata_exhibition_search"
T_EXHIBITOR = "exhibition_bigdata_exhibitor_search"
T_FAIR_EXHIBITORS = "exhibition_bigdata_exhibition_exhibitors"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _is_api_error(value: Any) -> bool:
    """Return True for failed MCP/tool envelopes, never for a successful empty result."""
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip().lower()
        return any(marker in text for marker in (
            "接口调用失败", "查询失败", "状态码：4", "状态码：5",
            "error executing tool", "validation error", "密钥错误", "鉴权失败",
        ))
    if isinstance(value, list):
        return any(_is_api_error(item) for item in value)
    if isinstance(value, dict):
        if value.get("isError") is True or value.get("is_error") is True or value.get("success") is False:
            return True
        if value.get("_error") not in (None, "", False) or value.get("error") not in (None, "", False):
            return True
        if set(value) <= {"text", "code", "status", "message", "msg"} and value.get("text"):
            text = str(value.get("text")).strip()
            if "查询数据为空" in text:
                return False
            return True
        return any(
            _is_api_error(value.get(key))
            for key in ("text", "message", "msg", "detail", "content")
            if key in value
        )
    return False


def _first_list(value: Any) -> List[Any]:
    """Extract business records without turning envelopes into phantom rows."""
    if _is_api_error(value):
        return []
    if isinstance(value, list):
        cleaned: List[Any] = []
        for item in value:
            if _is_api_error(item) or item in (None, "", {}, []):
                continue
            if isinstance(item, dict):
                business_values = [v for k, v in item.items() if k not in {"total", "count", "code", "message", "msg"}]
                if business_values and all(v in (None, "", "-", [], {}) for v in business_values):
                    continue
            cleaned.append(item)
        return cleaned
    if isinstance(value, dict):
        for key in ("resultList", "storeList", "list", "items", "data", "records"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
        envelope_keys = {
            "text", "message", "msg", "code", "status", "success", "total", "count",
            "pageIndex", "pageSize", "isError", "is_error", "content", "structuredContent",
            "structured_content", "_error", "error",
        }
        if set(value) <= envelope_keys:
            return []
        if value:
            return [value]
    return []


def _first_record(value: Any) -> Dict[str, Any]:
    for record in _first_list(value):
        if isinstance(record, dict) and not _is_api_error(record):
            return record
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
        result = call_tool_once(mcp_client.call_tool, tool, arguments)
        if _is_api_error(result):
            return {"_error": "API错误"}
        return result
    except Exception:
        return {"_error": "调用失败"}


def _safe_total(payload: Any) -> Any:
    if isinstance(payload, dict):
        if _is_api_error(payload):
            return None
        return payload.get("total")
    return None


def _failed_tools(sources: Mapping[str, Any]) -> List[str]:
    """Return only safe tool/dimension labels for failed calls."""
    return [name for name, payload in sources.items() if _is_api_error(payload)]


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
    fuzzy_total = _int(_safe_total(fuzzy))
    if fuzzy_total is not None and fuzzy_total > 1:
        return {"keyword": raw, "enterprise": raw, "resolved": False, "reason": f"模糊查询返回多候选（{fuzzy_total}），未静默选择首条", "fuzzy_total": fuzzy_total}
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
        metrics.append({"label": "展示样本参展展馆数", "value": str(len(pav_dist)), "hint": "仅基于本次展示样本，不是全量"})
        try:
            nums = [int(r.get("参展次数", 0)) for r in pav_dist if r.get("参展次数")]
            total = sum(nums)
            if total > 0:
                top3 = sum(sorted(nums, reverse=True)[:3])
                metrics.append({"label": "展示样本展馆CR3", "value": f"{top3/total*100:.1f}%", "hint": "仅基于本次展示样本，不能代表全量"})
        except (ValueError, TypeError):
            pass
    if isinstance(year_trend, list) and year_trend:
        metrics.append({"label": "展示样本活跃年份数", "value": str(len(year_trend)), "hint": "仅基于本次展示样本"})
        try:
            years = sorted([str(r.get("年份", "")) for r in year_trend if r.get("年份")], reverse=True)
            if years:
                metrics.append({"label": "展示样本最新参展年份", "value": years[0], "hint": "仅基于本次展示样本"})
            peak_rows = [(str(r.get("年份", "")), int(r.get("参展次数", 0))) for r in year_trend if r.get("参展次数")]
            if peak_rows:
                peak_value = max(v for _, v in peak_rows)
                peak_years = [y for y, v in peak_rows if v == peak_value]
                label = "、".join(f"{y}年" for y in peak_years)
                metrics.append({"label": "展示样本参展峰值", "value": f"{label} 各{peak_value}次" if len(peak_years) > 1 else f"{label} {peak_value}次", "hint": "仅基于本次展示样本；并列峰值逐项列出"})
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
    scopes: Dict[str, Any] = {}
    scope_value = subject.get("query_scopes")
    if isinstance(scope_value, dict):
        scopes = dict(scope_value)
    unsupported = any("不支持地区过滤" in str(value) for value in scopes.values())
    dimension_labels = {
        "participation": "展会参与",
        "venue": "展馆查询",
        "exhibition": "展会查询",
        "exhibitor": "展商查询",
        "fair_exhibitors": "指定展会参展企业",
    }
    requested_products = [
        label for key, label in dimension_labels.items()
        if scopes.get(key) and scopes.get(key) != "未请求"
    ]
    limits = ["分页结果仅代表本次采集样本；上游总量不等于本次采集可见记录数。"]
    if scopes.get("exhibition") and scopes.get("exhibition") != "未请求":
        limits.append("关键词命中不保证每条记录都与主题直接相关，应结合报告中的逐条相关性标记复核。")
    if unsupported:
        limits.append("展会关键词查询工具不支持地区过滤，相关展会总量与本次采集均为全国关键词口径，不能外推为指定地区结果。")
    return {
        "match_target": match_target,
        "match_type": match_type,
        "data_scope": "、".join(requested_products) or "未声明查询维度",
        "products": requested_products,
        "limit": "数据来自展会公开信息；少量字段可能存在更新延迟。" + " ".join(limits),
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


def _plain_text(value: Any, limit: int = 0) -> str:
    """Strip HTML tags/entities from an upstream description and collapse space."""
    raw = _text(value)
    if not raw:
        return ""
    raw = _re.sub(r"<[^>]+>", " ", raw)
    raw = _html.unescape(raw)
    raw = " ".join(raw.split())
    if limit and len(raw) > limit:
        return raw[: limit - 1].rstrip() + "…"
    return raw


def _fair_status(item: Mapping[str, Any]) -> str:
    """Render isOpen as an upstream flag without pretending it is an event status."""
    v = item.get("isOpen")
    if v is None:
        return "-"
    try:
        return f"{int(v)}（上游开放标记，未说明含义）"
    except (TypeError, ValueError):
        return f"{_text(v)}（上游开放标记，未说明含义）"


def _participation_rows(payload: Any, search_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    """participation/exhibition share fields: fairName/fairBeginTime/fairEndTime/
    fairPavilion/fairDesc/isOpen. We render date range, venue, upstream flag, and
    a plain-text highlight (fairDesc, truncated)."""
    rows: List[Dict[str, Any]] = []
    for item in _first_list(payload):
        if not isinstance(item, dict):
            continue
        row = {
            "展会ID": _text(item.get("_id")) or "-",
            "展会名称": _text(item.get("fairName")) or "-",
            "展会日期": _fair_date_range(item),
            "展馆": _text(item.get("fairPavilion")) or "-",
            "上游开放标记": _fair_status(item),
            "展会亮点": _plain_text(item.get("fairDesc"), limit=120) or "-",
        }
        if search_keyword:
            keyword = "".join(search_keyword.casefold().split())
            fair_name = "".join(_text(item.get("fairName")).casefold().split())
            visible_desc = "" if row["展会亮点"] == "-" else str(row["展会亮点"])
            fair_desc = "".join(visible_desc.casefold().split())
            if keyword and keyword in fair_name:
                row["关键词相关性"] = "名称命中"
            elif keyword and keyword in fair_desc:
                row["关键词相关性"] = "简介命中"
            else:
                row["关键词相关性"] = "待核：名称和可见简介未命中"
        rows.append(row)
    return rows


def build_core_analysis(
    participation: Any,
    venue: Any,
    exhibition: Any,
    exhibitor: Any,
    fair_exhibitors: Any = None,
    search_keyword: Optional[str] = None,
) -> Dict[str, Any]:
    participation_rows = _participation_rows(participation)
    exhibition_rows = _participation_rows(exhibition, search_keyword)
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
    fair_exhibitor_rows = _table_from(
        fair_exhibitors,
        [
            ("name", "企业名称"),
            ("nameId", "企业ID"),
        ],
    )

    participation_total = _safe_total(participation)
    venue_total = _safe_total(venue)
    exhibition_total = _safe_total(exhibition)
    exhibitor_total = _safe_total(exhibitor)
    fair_exhibitors_total = _safe_total(fair_exhibitors)

    # 派生：展馆分布（按 fairPavilion 聚合参展记录数）。
    pavilion_dist_rows = _aggregate_count(participation_rows, "展馆", name_key="展馆", count_key="参展次数")
    # 派生：参展年度趋势（从 fairBeginTime 提取年份）。
    year_trend_rows = _year_trend_from(participation_rows, "展会日期")

    sections: List[Dict[str, Any]] = []
    if participation_rows or participation_total is not None:
        sections.append({"key": "participation", "title": "展会参与", "kind": "table", "note": (f"上游总量 {participation_total} 条；本次采集展示 {len(participation_rows)} 条" if participation_total is not None else f"本次采集展示 {len(participation_rows)} 条；上游未返回总量"), "columns": [("展会名称", "展会名称"), ("展会日期", "展会日期"), ("展馆", "展馆"), ("上游开放标记", "上游开放标记"), ("展会亮点", "展会亮点")]})
    if pavilion_dist_rows:
        sections.append({"key": "pavilion_dist", "title": "参展展馆分布", "kind": "bar", "note": "仅按本次采集展示样本聚合，不代表上游全量分布", "chart": {"name": "展馆", "value": "参展次数", "orient": "h"}, "columns": [("展馆", "展馆"), ("参展次数", "参展次数")]})
    if year_trend_rows:
        sections.append({"key": "year_trend", "title": "参展年度趋势", "kind": "line", "note": "仅按本次采集展示样本统计，不代表全量年度趋势", "chart": {"x": "年份", "y": "参展次数", "area": True}, "columns": [("年份", "年份"), ("参展次数", "参展次数")]})
    if venue_rows or venue_total is not None:
        sections.append({"key": "venue", "title": "展馆查询", "kind": "table", "note": (f"上游总量 {venue_total} 条；本次采集展示 {len(venue_rows)} 条" if venue_total is not None else f"本次采集展示 {len(venue_rows)} 条；上游未返回总量"), "columns": [("展馆名称", "展馆名称"), ("所在区域", "所在区域"), ("地址", "地址"), ("展馆面积", "展馆面积"), ("展厅数量", "展厅数量")]})
    if exhibition_rows or exhibition_total is not None:
        exhibition_note = (f"上游总量 {exhibition_total} 条；本次采集展示 {len(exhibition_rows)} 条" if exhibition_total is not None else f"本次采集展示 {len(exhibition_rows)} 条；上游未返回总量")
        exhibition_columns = [("展会ID", "展会ID"), ("展会名称", "展会名称"), ("展会日期", "展会日期"), ("展馆", "展馆"), ("上游开放标记", "上游开放标记"), ("展会亮点", "展会亮点")]
        if search_keyword:
            related = sum(1 for row in exhibition_rows if row.get("关键词相关性") in {"名称命中", "简介命中"})
            exhibition_note += f"；可见字段直接命中关键词 {related} 条，其他记录保留并标为待核"
            exhibition_columns.append(("关键词相关性", "关键词相关性"))
        sections.append({"key": "exhibition", "title": "展会查询", "kind": "table", "note": exhibition_note, "columns": exhibition_columns})
    if exhibitor_rows or exhibitor_total is not None:
        sections.append({"key": "exhibitor", "title": "展商查询", "kind": "table", "note": (f"上游总量 {exhibitor_total} 条；本次采集展示 {len(exhibitor_rows)} 条" if exhibitor_total is not None else f"本次采集展示 {len(exhibitor_rows)} 条；上游未返回总量"), "columns": [("展商名称", "展商名称"), ("参展展会", "参展展会"), ("所属行业", "所属行业"), ("展会区域", "展会区域"), ("展位号", "展位号")]})
    if fair_exhibitor_rows or fair_exhibitors_total is not None:
        sections.append({"key": "fair_exhibitors", "title": "指定展会参展企业", "kind": "table", "note": (f"上游总量 {fair_exhibitors_total} 家；本次采集展示 {len(fair_exhibitor_rows)} 家" if fair_exhibitors_total is not None else f"本次采集展示 {len(fair_exhibitor_rows)} 家；上游未返回总量"), "columns": [("企业名称", "企业名称"), ("企业ID", "企业ID")]})

    return {
        "sections": sections,
        "participation": participation_rows,
        "pavilion_dist": pavilion_dist_rows,
        "year_trend": year_trend_rows,
        "venue": venue_rows,
        "exhibition": exhibition_rows,
        "exhibitor": exhibitor_rows,
        "fair_exhibitors": fair_exhibitor_rows,
    }


def _aggregate_count(rows: Sequence[Mapping[str, Any]], key: str, top_n: int = 0, name_key: str = "名称", count_key: str = "数量") -> List[Dict[str, Any]]:
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


def _year_trend_from(rows: Sequence[Mapping[str, Any]], date_key: str) -> List[Dict[str, Any]]:
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
                "上游开放标记": item.get("上游开放标记") or "-",
            })
    if not rows and core.get("fair_exhibitors"):
        for item in core.get("fair_exhibitors") or []:
            rows.append({
                "企业名称": item.get("企业名称") or "-",
                "企业ID": item.get("企业ID") or "-",
            })
    if not rows and core.get("exhibition"):
        for item in core.get("exhibition") or []:
            rows.append({
                "展会名称": item.get("展会名称") or "-",
                "展会日期": item.get("展会日期") or "-",
                "展馆": item.get("展馆") or "-",
                "上游开放标记": item.get("上游开放标记") or "-",
            })
    if not rows and core.get("exhibitor"):
        for item in core.get("exhibitor") or []:
            rows.append({
                "展商名称": item.get("展商名称") or "-",
                "参展展会": item.get("参展展会") or "-",
                "所属行业": item.get("所属行业") or "-",
            })
    return rows[:20]


def _fair_brand_key(name: Any) -> str:
    """Normalise a fair name for textual grouping only (year/届次 removed)."""
    text = _text(name)
    text = _re.sub(r"^(19|20)\d{2}", "", text)
    text = _re.sub(r"^第[0-9一二三四五六七八九十百]+届", "", text)
    text = _re.sub(r"[（(][^）)]*[）)]", "", text)
    text = _re.sub(r"[\s\-—_·,，、:：\"'“”‘’]", "", text)
    return text.casefold()


def _fair_brand_groups(rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    groups: Dict[str, int] = {}
    for row in rows:
        key = _fair_brand_key(row.get("展会名称"))
        if key:
            groups[key] = groups.get(key, 0) + 1
    return groups


def _concentration_rows(rows: Sequence[Mapping[str, Any]], name_key: str, value_key: str, top_n: int = 3) -> Dict[str, Any]:
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


def _year_trend_analysis(rows: List[Mapping[str, Any]], as_of_year: Optional[int] = None) -> Dict[str, Any]:
    """Direction/peak for a year series, with sparse/gap/partial-year guards."""
    series = []
    for r in rows:
        try:
            year = int(str(r.get("年份", "")).strip()[:4])
            value = float(str(r.get("参展次数", 0)).replace(",", ""))
        except (TypeError, ValueError):
            continue
        series.append((year, value))
    if not series:
        return {}
    series.sort(key=lambda x: x[0])
    nums = [v for _, v in series]
    peak = max(nums)
    peak_years = [str(y) for y, v in series if v == peak]
    latest_year = series[-1][0]
    partial_year = latest_year if as_of_year is not None and latest_year == as_of_year else None
    complete = [(y, v) for y, v in series if y != partial_year]
    comparable = False
    reason = ""
    yoy = ""
    direction = "持平"
    if len(complete) >= 2:
        (prev_year, prev), (last_year, last) = complete[-2], complete[-1]
        if last_year - prev_year != 1:
            reason = f"样本年度不连续（{prev_year}→{last_year}），不计算同比"
        elif prev < 2 or last < 2:
            reason = f"相邻两年样本均不足 2 条（{last_year}={last:.0f}，{prev_year}={prev:.0f}），不计算同比"
        elif prev > 0:
            comparable = True
            pct = (last - prev) / prev * 100
            if pct > 5:
                direction = f"上升 {pct:.0f}%"
            elif pct < -5:
                direction = f"下降 {abs(pct):.0f}%"
            yoy = f"{last_year} 年较 {prev_year} 年{direction}（{last:.0f} vs {prev:.0f}）"
    else:
        reason = "剔除不完整年度后可用年度不足 2 个，不计算同比"
    return {
        "peak_period": "、".join(peak_years),
        "peak_value": peak,
        "peak_years": peak_years,
        "direction": direction,
        "yoy": yoy,
        "comparable": comparable,
        "reason": reason,
        "partial_year": partial_year,
        "partial_value": next((v for y, v in series if y == partial_year), None),
        "last": nums[-1],
        "years": len(series),
    }


def build_insights(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]], as_of_year: Optional[int] = None) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    metric_map = {m["label"]: str(m["value"]) for m in metrics}

    if subject.get("search_mode"):
        venue_total = metric_map.get("展馆")
        exhibition_total = metric_map.get("展会")
        exhibitor_total = metric_map.get("展商")
        fair_exhibitors_total = metric_map.get("指定展会参展企业")
        if exhibition_total:
            insights.append({
                "feature": "展会查询返回",
                "evidence": f"上游报告展会查询总量 {exhibition_total} 条。",
                "interpretation": "该数值是上游关键词查询总量；不代表每条记录均与主题直接相关，也不据此推断区域或行业活跃度。",
            })
        exh_rows = core.get("exhibition") or []
        if exh_rows:
            hit_n = sum(1 for r in exh_rows if r.get("关键词相关性") in ("名称命中", "简介命中"))
            pending_n = len(exh_rows) - hit_n
            groups = _fair_brand_groups(exh_rows)
            multi = {k: v for k, v in groups.items() if v > 1}
            evidence = f"本次展示 {len(exh_rows)} 条；可见名称/简介直接含关键词 {hit_n} 条，待核 {pending_n} 条"
            if groups:
                evidence += f"；按名称去除年份与届次后归为 {len(groups)} 组，其中 {len(multi)} 组含多条记录"
                if multi:
                    top_group = max(multi.items(), key=lambda kv: kv[1])
                    evidence += f"（最多一组 {top_group[1]} 条）"
            insights.append({
                "feature": "检索记录与展会品牌",
                "evidence": evidence + "。",
                "interpretation": "同一展会的不同届次会作为多条记录返回；记录数不等于展会品牌数或届次数，归组仅为文本相似，是否同一主办方需核对官方信息。",
            })
        if exhibitor_total:
            insights.append({
                "feature": "展商查询返回",
                "evidence": f"上游报告展商查询总量 {exhibitor_total} 家。",
                "interpretation": "该数值仅说明筛选条件下的上游返回规模，不等同于行业竞争强度、生态规模或完整企业清单。",
            })
        if venue_total:
            insights.append({
                "feature": "展馆查询返回",
                "evidence": f"上游报告展馆查询总量 {venue_total} 家。",
                "interpretation": "该数值仅说明查询返回规模；展馆状态、容量及可用性需逐条核验。",
            })
        if fair_exhibitors_total:
            selected_value = subject.get("selected_fair")
            selected: Mapping[str, Any] = selected_value if isinstance(selected_value, dict) else {}
            fair_name = selected.get("name") or subject.get("match_raw") or "所选展会"
            insights.append({
                "feature": "指定展会参展企业名录",
                "evidence": f"“{fair_name}”检索所得届次命中参展企业 {fair_exhibitors_total} 家。",
                "interpretation": "该名录仅对应报告所列展会ID和届次，可用于参展企业核对；不外推为其他届次或全量行业企业。",
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
                "feature": "参展记录收录",
                "evidence": f"企业展会参与记录 {participation_total} 条。",
                "interpretation": "该数值仅为上游收录记录总量；参展时间、身份及活动成效需逐条核验。",
            })
        # 展馆集中度（基于聚合后的 pavilion_dist）。
        pavilion_dist = core.get("pavilion_dist") or []
        if pavilion_dist:
            conc = _concentration_rows(pavilion_dist, "展馆", "参展次数", 3)
            if conc:
                focus = "聚焦" if conc["top_share"] >= 60 else ("多元" if conc["top_share"] < 40 else "较聚焦")
                insights.append({
                    "feature": "参展展馆集中度",
                    "evidence": f"本次采集样本中，“{conc['top']}”参展占比约 {conc['top_share']:.0f}%，前 3 展馆合计 {conc['cr']:.0f}%（CR3）。",
                    "interpretation": f"本次采集样本的展馆布局{focus}；该比例不代表上游全量分布，不据此外推企业整体展馆策略。",
                })
        # 年度趋势
        year_trend = core.get("year_trend") or []
        if year_trend:
            ta = _year_trend_analysis(year_trend, as_of_year=as_of_year)
            if ta:
                peak_text = f"本次展示样本峰值出现在“{ta['peak_period']}”（{ta['peak_value']:.0f} 次）"
                if len(ta.get("peak_years") or []) > 1:
                    peak_text = f"本次展示样本峰值年度为 {'、'.join(ta['peak_years'])}（各 {ta['peak_value']:.0f} 次）"
                parts = [peak_text]
                if ta.get("yoy"):
                    parts.append(ta["yoy"])
                    if ta.get("partial_year"):
                        parts.append(f"{ta['partial_year']} 年为不完整年度（{ta.get('partial_value') or 0:.0f} 次，截至报告生成日），不纳入同比")
                elif ta.get("partial_year"):
                    parts.append(f"{ta['partial_year']} 年为不完整年度（{ta.get('partial_value') or 0:.0f} 次，截至报告生成日），剔除后可用完整年度不足 2 个，未计算同比")
                elif ta.get("reason"):
                    parts.append(ta["reason"])
                insights.append({
                    "feature": "参展年度趋势",
                    "evidence": "；".join(parts) + "。",
                    "interpretation": "本次展示样本不足以证明企业全量参展趋势；年度不连续或样本过少时，不做同比与预算推断。",
                })
        # 开展状态分布
        if participation:
            status_counts: Dict[str, int] = {}
            for r in participation:
                v = r.get("上游开放标记")
                if v and v != "-":
                    status_counts[v] = status_counts.get(v, 0) + 1
            if status_counts:
                top_status = sorted(status_counts.items(), key=lambda kv: kv[1], reverse=True)[0]
                insights.append({
                    "feature": "上游开放标记",
                    "evidence": f"主要标记为“{top_status[0]}”（{top_status[1]} / {len(participation)}）。",
                    "interpretation": "该字段仅原样呈现上游开放标记，不用于推断当前时间状态；应以实际起止日期另行核验。",
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


def build_metrics(participation: Any, venue: Any, exhibition: Any, exhibitor: Any, fair_exhibitors: Any = None) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []

    def _ttotal(payload: Any, present: bool) -> Optional[str]:
        if not present:
            return None
        if isinstance(payload, dict) and payload.get("total") is not None:
            return _text(payload.get("total"))
        rows = _first_list(payload)
        return str(len(rows)) if rows else None

    has_part = isinstance(participation, dict) and "_error" not in participation
    has_venue = isinstance(venue, dict) and "_error" not in venue
    has_exh = isinstance(exhibition, dict) and "_error" not in exhibition
    has_exhibitor = isinstance(exhibitor, dict) and "_error" not in exhibitor
    has_fair_exhibitors = isinstance(fair_exhibitors, dict) and "_error" not in fair_exhibitors

    metrics.append({"label": "展会参与", "value": _ttotal(participation, has_part), "hint": "企业展会参与条数"})
    metrics.append({"label": "展馆", "value": _ttotal(venue, has_venue), "hint": "展馆查询命中数"})
    metrics.append({"label": "展会", "value": _ttotal(exhibition, has_exh), "hint": "展会查询命中数"})
    metrics.append({"label": "展商", "value": _ttotal(exhibitor, has_exhibitor), "hint": "展商查询命中数"})
    metrics.append({"label": "指定展会参展企业", "value": _ttotal(fair_exhibitors, has_fair_exhibitors), "hint": "按搜索所得展会ID查询的参展企业数"})
    return [m for m in metrics if m.get("value") not in ("", None, "-")]


def build_abstract(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]]) -> str:
    scopes: Dict[str, Any] = {}
    scope_value = subject.get("query_scopes")
    if isinstance(scope_value, dict):
        scopes = dict(scope_value)
    requested = [name for key, name in (("participation", "企业展会参与"), ("venue", "展馆查询"), ("exhibition", "展会查询"), ("exhibitor", "展商查询"), ("fair_exhibitors", "指定展会参展企业")) if scopes.get(key) and scopes.get(key) != "未请求"]
    requested_text = "、".join(requested) or "已请求维度"
    if subject.get("search_mode"):
        name = subject.get("match_raw") or "目标市场"
        parts = [f"本报告以“{name}”为检索关键词，基于展会公开数据呈现{requested_text}；各维度严格采用其工具支持的筛选口径。"]
    else:
        name = subject.get("enterprise") or subject.get("match_raw") or "目标企业"
        parts = [f"本报告以“{name}”为分析对象，基于展会公开数据呈现{requested_text}。"]
    if metrics:
        kv = "、".join(f"{m['label']} {m['value']}" for m in metrics[:5])
        parts.append(f"关键指标包括：{kv}。")
    parts.append("报告呈现已请求维度的查询记录与本次采集结构化汇总，供后续逐条核验。")
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
    return apply_content_review(_assemble(subject, core, metrics, dry_run=True, search_mode=bool(subject.get("search_mode"))))


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def _quality_report(core: Mapping[str, Any]) -> Dict[str, Any]:
    """Section-fill rate from final declared sections and their actual bodies.

    ``0`` is a populated body; None/''/[]/{} is empty. Not an accuracy score.
    """
    ca = core if isinstance(core, dict) else {}
    sections = ca.get("sections")
    if isinstance(sections, list):
        total = len(sections)
        populated = sum(1 for s in sections if isinstance(s, dict) and ca.get(s.get("key")) not in (None, "", [], {}))
    else:
        keys = [k for k in ca if k not in ("sections", "source_status")]
        total = len(keys)
        populated = sum(1 for k in keys if ca.get(k) not in (None, "", [], {}))
    return {
        "total_sections": total,
        "populated_sections": populated,
        "empty_sections": total - populated,
        "coverage_pct": round(populated / max(1, total) * 100),
    }


def _assemble(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]], *, dry_run: bool, search_mode: bool = False, tool_errors: Optional[List[str]] = None) -> Dict[str, Any]:
    abstract = build_abstract(subject, core, metrics)
    records = build_records(core)
    insights = build_insights(subject, core, metrics, as_of_year=dt.datetime.now().year)
    quality_report = _quality_report(core)
    populated = quality_report["populated_sections"]
    if subject.get("blocked_reason"):
        abstract = f"查询受阻：{subject.get('blocked_reason')}。已保留成功取得的检索结果，但未完成受阻维度，不据此生成该维度业务结论。"
    elif populated == 0:
        if tool_errors:
            abstract = "本次查询未获得有效核心数据，且存在上游调用失败维度：" + "、".join(tool_errors) + "。不据此生成业务规模或市场结论。"
        else:
            abstract = "本次查询未返回有效核心数据；报告仅记录查询边界，不生成业务规模或市场结论。"
        import sys
        print("⚠️ 质量门禁警告: 所有核心分析维度均无数据", file=sys.stderr)
    mode_label = {"fair_search": "展会检索", "fair_exhibitors": "指定展会参展企业"}.get(str(subject.get("mode")), "市场检索" if search_mode else "企业参展")
    title = f"{subject.get('enterprise') or subject.get('match_raw') or '目标'} 展会大数据报告（{mode_label}）"
    product_catalog = {
        "participation": {"name": "展会参与", "product_id": "66a26918ff3066996ecc6471"},
        "venue": {"name": "展馆查询", "product_id": "66e2d2ca428a1f4cd69c1083"},
        "exhibition": {"name": "展会查询", "product_id": "66a0f6ca477cbe5f7605973f"},
        "exhibitor": {"name": "展商查询", "product_id": "66d5b7e0537c3f61d646c473"},
        "fair_exhibitors": {"name": "指定展会参展企业", "product_id": "66a2684651cde0f1e3aeff5a"},
    }
    scope_value = subject.get("query_scopes")
    scopes = scope_value if isinstance(scope_value, dict) else {}
    requested_products = [
        product for key, product in product_catalog.items()
        if scopes.get(key) and scopes.get(key) != "未请求"
    ]
    return {
        "report_type": REPORT_TYPE,
        "title": title,
        "banner": REPORT_BANNER,
        "subject": dict(subject),
        "abstract": abstract,
        "summary": abstract,
        "executive_summary": ((["主体解析受阻：" + str(subject.get("blocked_reason")) + "；已停止主体数据调用。"] if subject.get("blocked_reason") else (["数据缺口：" + "、".join(tool_errors or []) + "未成功返回，本报告仅呈现成功维度。"] if tool_errors else [])) + ([item["interpretation"] for item in insights][:5] or [abstract[:120]])),
        "metrics": list(metrics),
        "caliber": build_caliber(subject, search_mode),
        "core_analysis": dict(core),
        "representative_records": records,
        "insights": insights,
        "data_source": {
            "mcp_server": "exhibition-mcp-server",
            "products": requested_products,
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "dry_run": dry_run,
            "tool_errors": list(tool_errors or []),
            "blocked_reason": subject.get("blocked_reason"),
            "quality_report": quality_report,
            "mode": subject.get("mode") or ("market_search" if search_mode else "enterprise"),
        },
    }


_REVIEW_METRIC_LABELS = {
    "当前页参展展馆数": "展示样本参展展馆数",
    "本次采集参展展馆数": "展示样本参展展馆数",
    "当前页展馆CR3": "展示样本展馆CR3",
    "本次采集展馆CR3": "展示样本展馆CR3",
    "当前页活跃年份": "展示样本活跃年份数",
    "本次采集活跃年份": "展示样本活跃年份数",
    "当前页最新参展年份": "展示样本最新参展年份",
    "本次采集最新参展年份": "展示样本最新参展年份",
    "当前页参展峰值": "展示样本参展峰值",
    "本次采集参展峰值": "展示样本参展峰值",
}


def _review_participation_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise old rows: flag is not an event status; strip HTML from snippets."""
    out: List[Dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        if "状态" in row and "上游开放标记" not in row:
            value = _text(row.pop("状态"))
            if value.startswith("上游开放标记="):
                value = value.split("=", 1)[1]
            row["上游开放标记"] = f"{value}（上游开放标记，未说明含义）" if value and value != "-" else "-"
        if row.get("展会亮点") and row.get("展会亮点") != "-":
            row["展会亮点"] = _plain_text(row.get("展会亮点")) or "-"
        out.append(row)
    return out


def _review_core_rows(core: Mapping[str, Any], keyword: str) -> Dict[str, Any]:
    out = dict(core)
    for key in ("participation", "exhibition"):
        if isinstance(out.get(key), list):
            out[key] = _review_participation_rows(out[key])
    token = "".join(str(keyword or "").casefold().split())
    if token and isinstance(out.get("exhibition"), list):
        for row in out["exhibition"]:
            if "关键词相关性" in row:
                continue
            name = "".join(str(row.get("展会名称") or "").casefold().split())
            desc = "".join(str(row.get("展会亮点") or "").casefold().split())
            if token in name:
                row["关键词相关性"] = "名称命中"
            elif token in desc:
                row["关键词相关性"] = "简介命中"
            else:
                row["关键词相关性"] = "待核：名称和可见简介未命中"
    sections = []
    for spec in out.get("sections") or []:
        if isinstance(spec, dict):
            spec = dict(spec)
            columns = []
            for col in spec.get("columns") or []:
                if isinstance(col, (list, tuple)) and len(col) == 2 and col[0] == "状态":
                    columns.append(("上游开放标记", "上游开放标记"))
                else:
                    columns.append(col)
            spec["columns"] = columns
        sections.append(spec)
    out["sections"] = sections
    return out


def _review_metrics(metrics: Sequence[Mapping[str, Any]], core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    peak_rows = [(str(r.get("年份")), int(r.get("参展次数", 0))) for r in (core.get("year_trend") or [])
                 if r.get("年份") and str(r.get("参展次数", "")).isdigit()]
    for raw in metrics:
        if not isinstance(raw, dict):
            continue
        metric = dict(raw)
        label = _REVIEW_METRIC_LABELS.get(str(metric.get("label") or ""), str(metric.get("label") or ""))
        metric["label"] = label
        if label.startswith("展示样本"):
            metric["hint"] = "仅基于本次展示样本，不是全量"
        if label == "展示样本参展峰值" and peak_rows:
            top = max(v for _, v in peak_rows)
            years = [y for y, v in peak_rows if v == top]
            label_text = "、".join(f"{y}年" for y in years)
            metric["value"] = f"{label_text} 各{top}次" if len(years) > 1 else f"{label_text} {top}次"
            metric["hint"] = "仅基于本次展示样本；并列峰值逐项列出"
        if label in seen:
            continue
        seen.add(label)
        out.append(metric)
    return out


def apply_content_review(report: Mapping[str, Any], *, source_sha256: Optional[str] = None,
                         reviewed_at: Optional[str] = None) -> Dict[str, Any]:
    """Rebuild exhibition narrative content offline from an existing payload.

    Uses only fields already present (participation/exhibition rows, year trend,
    metrics, subject, generated_at). No MCP call, no new facts. Fixes:
    * an upstream open flag rendered as event "状态";
    * HTML tags and mid-token truncation in fair highlights;
    * year-over-year claims across non-adjacent/one-record years or including
      the current partial year;
    * peak-year ties silently picking one year;
    * "当前页" sample metrics not naming their scope.
    """
    out = copy.deepcopy(dict(report))
    subject = dict(out.get("subject") or {})
    ds = dict(out.get("data_source") or {})
    if subject.get("blocked_reason") or ds.get("blocked_reason"):
        ds["quality_report"] = _quality_report(out.get("core_analysis") or {})
        ds["content_revision"] = {
            "mode": "offline_source_preserving",
            "source_sha256": source_sha256,
            "original_generated_at": ds.get("generated_at"),
            "reviewed_at": reviewed_at or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "scope": "受阻报告：保留原阻断说明与空结果边界，不重算业务结论",
        }
        out["data_source"] = ds
        return out
    core = _review_core_rows(out.get("core_analysis") or {}, str(subject.get("match_raw") or subject.get("matchKeyword") or ""))
    generated = str(ds.get("generated_at") or "")
    try:
        as_of_year = int(generated[:4]) if generated[:4].isdigit() else dt.datetime.now().year
    except (ValueError, TypeError):
        as_of_year = dt.datetime.now().year
    metrics = _review_metrics(out.get("metrics") or [], core)
    quality = _quality_report(core)
    if quality["populated_sections"] == 0:
        # No business body: keep the assembled empty/failure narrative instead
        # of replacing it with a generic abstract that implies sections exist.
        out["core_analysis"] = core
        out["metrics"] = metrics
        ds["quality_report"] = quality
        ds["content_revision"] = {
            "mode": "offline_source_preserving",
            "source_sha256": source_sha256,
            "original_generated_at": ds.get("generated_at"),
            "reviewed_at": reviewed_at or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "scope": "无有效业务章节：保留原始空结果或调用失败说明，不生成业务结论",
        }
        out["data_source"] = ds
        return out
    insights = build_insights(subject, core, metrics, as_of_year=as_of_year)
    abstract = build_abstract(subject, core, metrics)
    old_abstract = str(out.get("abstract") or "")
    marker = "明细含未完整采集的来源"
    if marker in old_abstract:
        # attach_pagination() appends this disclosure after the review; keep it
        # when an already-attached report is reviewed again offline.
        abstract += old_abstract[old_abstract.index(marker):]
    out["core_analysis"] = core
    out["metrics"] = metrics
    out["insights"] = insights
    out["abstract"] = abstract
    out["summary"] = abstract
    gap_lines = []
    if ds.get("tool_errors"):
        gap_lines = ["数据缺口：" + "、".join(str(item) for item in ds["tool_errors"]) + "未成功返回，本报告仅呈现成功维度。"]
    insight_lines = [i.get("interpretation") for i in insights][:5] or [abstract[:120]]
    out["executive_summary"] = gap_lines + insight_lines
    out["representative_records"] = build_records(core)
    ds["quality_report"] = quality
    ds["content_revision"] = {
        "mode": "offline_source_preserving",
        "source_sha256": source_sha256,
        "original_generated_at": ds.get("generated_at"),
        "reviewed_at": reviewed_at or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "清洗上游标记/HTML摘录；重算趋势可比性；未新增查询、未改写展会日期与名称",
    }
    out["data_source"] = ds
    return out


@paid_call_scope
def build_payload(
    raw: str,
    keyword_type: str,
    venue_region: Optional[str],
    fair_region: Optional[str],
    fair_industries: Optional[str],
    search_keyword: Optional[str],
    page_size: int,
    *,
    search_target: str = "all",
    fair_exhibitors: Optional[str] = None,
    fair_result_index: Optional[int] = None,
    max_pages: int = 1,
) -> Dict[str, Any]:
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages 必须为正整数")
    if fair_exhibitors:
        return _build_fair_exhibitors_payload(fair_exhibitors, page_size, fair_result_index, max_pages)
    if search_target == "exhibition":
        return _build_fair_search_payload(search_keyword or "", page_size, max_pages)

    search_mode = bool(venue_region or fair_region or fair_industries or search_keyword)
    resolved = resolve_enterprise_name(raw) if raw else {"enterprise": "", "resolved": False, "reason": "未指定企业（市场检索模式）"}
    enterprise = resolved.get("enterprise") or raw
    if raw and not resolved.get("resolved") and not search_mode:
        subject = build_subject(raw, resolved, keyword_type, False)
        subject["blocked_reason"] = resolved.get("reason") or "企业主体未唯一解析"
        return apply_content_review(_assemble(subject, build_core_analysis(None, None, None, None), [], dry_run=False))

    participation: Any = None if not raw or not resolved.get("resolved") else collect_detail_pages(
        _safe_call, T_PARTICIPATION,
        {"matchKeyword": enterprise, "keywordType": keyword_type, "pageSize": page_size},
        get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
        max_pages=max_pages,
    )

    venue: Any = None if not venue_region else collect_detail_pages(
        _safe_call, T_VENUE,
        {"pavilionRegion": venue_region, "matchKeyword": search_keyword or None, "pageSize": page_size},
        get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
        max_pages=max_pages,
    )

    exhibition: Any = None if not search_keyword else collect_detail_pages(
        _safe_call, T_EXHIBITION,
        {"matchKeyword": search_keyword, "pageSize": page_size},
        get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
        max_pages=max_pages,
    )

    exhibitor_args: Dict[str, Any] = {"pageSize": page_size}
    if fair_region:
        exhibitor_args["fairRegion"] = fair_region
    if fair_industries:
        exhibitor_args["fairIndustries"] = fair_industries
    if search_keyword:
        exhibitor_args["matchKeyword"] = search_keyword
    exhibitor: Any = None if not (fair_region or fair_industries or search_keyword) else collect_detail_pages(
        _safe_call, T_EXHIBITOR, exhibitor_args,
        get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
        max_pages=max_pages,
    )

    subject = build_subject(raw or (search_keyword or fair_region or venue_region or "市场检索"), resolved, keyword_type, search_mode)
    subject["filters"] = {"venue_region": venue_region, "fair_region": fair_region, "fair_industries": fair_industries, "search_keyword": search_keyword}
    subject["query_scopes"] = {
        "participation": "企业主体口径" if raw else "未请求",
        "venue": "展馆区域筛选口径" if venue_region else "未请求",
        "exhibition": ("全国关键词口径（工具不支持地区过滤）" if search_keyword and fair_region else ("全国关键词口径" if search_keyword else "未请求")),
        "exhibitor": "展商地区/行业筛选口径" if (fair_region or fair_industries) else ("关键词口径" if search_keyword else "未请求"),
    }
    core = build_core_analysis(participation, venue, exhibition, exhibitor, search_keyword=search_keyword)
    metrics = build_metrics(participation, venue, exhibition, exhibitor)
    # --- Enterprise profile enrichment (from fuzzy_search) ---
    _enrich_metrics_with_profile(metrics, resolved.get("record") if isinstance(resolved, dict) else None)
    _derive_core_metrics(metrics, core if isinstance(core, dict) else {})
    report = apply_content_review(
        _assemble(subject, core, metrics, dry_run=False, search_mode=search_mode, tool_errors=_failed_tools({"展会参与": participation, "展馆查询": venue, "展会查询": exhibition, "展商查询": exhibitor}))
    )
    return attach_pagination(report, {"展会参与明细": participation, "展馆查询": venue, "展会查询": exhibition, "展商查询": exhibitor})


def _fair_search_subject(keyword: str, mode: str) -> Dict[str, Any]:
    return {
        "enterprise": "",
        "matchKeyword": keyword,
        "keywordType": "fairName",
        "match_raw": keyword,
        "resolved": False,
        "resolve_reason": "展会关键词无需解析企业主体",
        "search_mode": True,
        "mode": mode,
        "filters": {"search_keyword": keyword},
        "query_scopes": {
            "participation": "未请求",
            "venue": "未请求",
            "exhibition": "全国关键词口径",
            "exhibitor": "未请求",
            "fair_exhibitors": "搜索所得展会ID口径" if mode == "fair_exhibitors" else "未请求",
        },
    }


@paid_call_scope
def _build_fair_search_payload(keyword: str, page_size: int, max_pages: int = 1) -> Dict[str, Any]:
    subject = _fair_search_subject(keyword, "fair_search")
    if not keyword.strip():
        subject["blocked_reason"] = "展会检索关键词为空"
        return apply_content_review(_assemble(subject, build_core_analysis(None, None, None, None), [], dry_run=False, search_mode=True))
    exhibition = collect_detail_pages(
        _safe_call, T_EXHIBITION,
        {"matchKeyword": keyword, "pageSize": page_size},
        get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
        max_pages=max_pages,
    )
    core = build_core_analysis(None, None, exhibition, None, search_keyword=keyword)
    metrics = build_metrics(None, None, exhibition, None)
    report = apply_content_review(
        _assemble(
            subject,
            core,
            metrics,
            dry_run=False,
            search_mode=True,
            tool_errors=_failed_tools({"展会查询": exhibition}),
        )
    )
    return attach_pagination(report, {"展会查询": exhibition})


@paid_call_scope
def _build_fair_exhibitors_payload(keyword: str, page_size: int, fair_result_index: Optional[int], max_pages: int = 1) -> Dict[str, Any]:
    subject = _fair_search_subject(keyword, "fair_exhibitors")
    # 第一跳：展会检索仅用于确定 fairId 候选（选择边界），固定 1 页预算，不因选择而扩大付费调用。
    exhibition = collect_detail_pages(
        _safe_call, T_EXHIBITION,
        {"matchKeyword": keyword, "pageSize": page_size},
        get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
        max_pages=1,
    )
    fair_rows = [row for row in _first_list(exhibition) if isinstance(row, dict)]
    selected: Optional[Dict[str, Any]] = None
    blocked_reason = ""
    if _is_api_error(exhibition):
        blocked_reason = "展会搜索调用失败，未执行参展企业查询"
    elif not fair_rows:
        blocked_reason = "展会搜索未返回可选择的展会，未执行参展企业查询"
    elif fair_result_index is None and len(fair_rows) > 1:
        blocked_reason = f"展会搜索返回 {len(fair_rows)} 条当前页结果；请使用 --fair-result-index 明确选择届次"
    else:
        index = (fair_result_index or 1) - 1
        if index < 0 or index >= len(fair_rows):
            blocked_reason = f"--fair-result-index {fair_result_index} 超出当前页 {len(fair_rows)} 条结果范围"
        else:
            selected = fair_rows[index]

    fair_id = _text(selected.get("_id")) if selected else ""
    if selected and not fair_id:
        blocked_reason = "所选展会未返回可用展会ID，未执行参展企业查询"
        selected = None

    fair_exhibitor_payload: Any = None
    if selected:
        subject["selected_fair"] = {
            "id": fair_id,
            "name": _text(selected.get("fairName")) or "-",
            "date": _fair_date_range(selected),
            "pavilion": _text(selected.get("fairPavilion")) or "-",
            "result_index": (fair_result_index or 1),
        }
        fair_exhibitor_payload = collect_detail_pages(
            _safe_call, T_FAIR_EXHIBITORS,
            {"matchKeyword": fair_id, "pageSize": page_size},
            get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
            max_pages=max_pages,
        )
    else:
        subject["blocked_reason"] = blocked_reason

    core = build_core_analysis(None, None, exhibition, None, fair_exhibitor_payload, search_keyword=keyword)
    metrics = build_metrics(None, None, exhibition, None, fair_exhibitor_payload)
    tool_errors = _failed_tools({"展会查询": exhibition, "指定展会参展企业": fair_exhibitor_payload})
    report = apply_content_review(
        _assemble(
            subject,
            core,
            metrics,
            dry_run=False,
            search_mode=True,
            tool_errors=tool_errors,
        )
    )
    return attach_pagination(report, {"展会筛选候选": exhibition, "参展企业": fair_exhibitor_payload})


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
    parser.add_argument("--search-target", choices=["all", "exhibition"], default="all", help="检索目标；exhibition 仅查询展会，不连带查询展商")
    parser.add_argument("--fair-exhibitors", help="指定展会参展企业模式：输入展会名称/关键词，内部先检索展会再以真实展会ID查询参展企业")
    parser.add_argument("--fair-result-index", type=int, help="指定展会参展企业模式：选择当前页第几条展会检索结果（从1开始；多条结果时必填）")
    parser.add_argument("--page-size", type=int, default=10, help="分页大小（最多 50）")
    parser.add_argument("--max-pages", type=int, default=1, help="规划的明细付费调用页数上限，默认1；先按 total 估算，只有必要且已授权时提高")
    parser.add_argument("--dry-run", action="store_true", help="不调用真实 MCP，使用样例数据组装报告骨架")
    parser.add_argument("--output", help="输出 JSON 路径；省略则打印到 stdout")
    parser.add_argument("--report-output", help="同时输出 HTML 报告（.html）与 Markdown 报告（.md）")
    parser.add_argument("--pdf-output", help="额外输出 PDF 报告（.pdf）；需要 Playwright + Chromium")
    args = parser.parse_args()

    if not 1 <= args.page_size <= 50:
        parser.error("--page-size 必须在 1 到 50 之间。")
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages 必须为正整数。")
    if not args.enterprise and not args.dry_run and not (args.venue_region or args.fair_region or args.fair_industries or args.search_keyword or args.fair_exhibitors):
        parser.error("至少需要 --enterprise（企业参展模式）、--venue-region / --fair-region / --fair-industries / --search 之一（市场检索模式）或 --fair-exhibitors；或使用 --dry-run。")
    if args.search_target == "exhibition":
        if not args.search_keyword:
            parser.error("--search-target exhibition 必须与 --search 一起使用。")
        if args.enterprise or args.venue_region or args.fair_region or args.fair_industries or args.fair_exhibitors:
            parser.error("展会单项检索不可与企业、展馆、展商过滤或 --fair-exhibitors 混用。")
    if args.fair_exhibitors:
        if args.enterprise or args.venue_region or args.fair_region or args.fair_industries or args.search_keyword:
            parser.error("--fair-exhibitors 是独立两跳模式，不可与企业、展馆、展商过滤或 --search 混用。")
    elif args.fair_result_index is not None:
        parser.error("--fair-result-index 只能与 --fair-exhibitors 一起使用。")

    if args.dry_run:
        payload = build_dry_run_payload(args.enterprise or "示例科技有限公司", args.keyword_type)
    else:
        payload = build_payload(
            args.enterprise or "",
            args.keyword_type,
            args.venue_region,
            args.fair_region,
            args.fair_industries,
            args.search_keyword,
            args.page_size,
            search_target=args.search_target,
            fair_exhibitors=args.fair_exhibitors,
            fair_result_index=args.fair_result_index,
            max_pages=args.max_pages,
        )

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
