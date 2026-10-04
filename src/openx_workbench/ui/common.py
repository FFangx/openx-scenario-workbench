"""Shared vocabulary, small HTML helpers and retrieval controls for the Streamlit pages."""

from __future__ import annotations

import html

import streamlit as st

from openx_workbench import matching
from openx_workbench.asset_management import label as localized
from openx_workbench.catalog import OpenXAsset
from openx_workbench.retrieval import OpenXIndex
from openx_workbench.ui_shell import save_preferences


TEXT = {
    "zh": {
        "subtitle": "从法规证据到可复用 OpenX 场景资产",
        "steps": ("提取场景需求", "检索资产库", "评估复用", "导出评估报告"),
        "requirements": "法规与提取场景",
        "pdf_help": "上传 ADAS 法规或测试规程 PDF。场景、页码和原文证据会保留在同一条追踪链中。",
        "standard": "标准名称",
        "standard_hint": "例如 Euro NCAP 2025 LSS",
        "scenes": "提取场景",
        "no_pdf": "尚未上传 PDF",
        "no_pdf_detail": "上传后显示真实提取的场景、页码和原文证据。",
        "evidence": "选中来源证据",
        "entities": "参与者", "actions": "动作", "triggers": "触发条件",
        "roads": "道路", "parameters": "参数", "pages": "页码",
        "assets": "资产库检索与候选场景",
        "source": "资产来源", "demo": "esmini 公共样例", "upload": "上传资产",
        "load_demo": "载入 esmini 样例", "build": "构建资产库",
        "files": "SIM / XOSC / XODR 文件", "pairs": "配对资产",
        "sim_cases": "SIM 可配对 case", "missing_roads": "缺少道路",
        "library_empty": "先载入公共样例或上传配套的 XOSC/XODR 文件。",
        "encoder": "检索方式", "hashing": "基础文本检索（离线）", "bge": "多语言语义检索（BGE-M3）",
        "query": "补充检索条件", "query_hint": "可选：道路、天气、速度或测试目标",
        "search": "检索可复用资产", "candidates": "候选场景",
        "no_results": "构建资产库并检索后显示真实候选结果。",
        "candidate": "查看候选", "selected": "选中资产摘要",
        "preview_off": "已解析 · 预览工具未找到", "preview_on": "已解析 · 预览工具就绪",
        "run_preview": "播放仿真", "stop_preview": "停止",
        "home": "总览", "text_search": "文本检索", "pdf_workflow": "PDF 工作流",
        "asset_management": "资产管理", "no_assets": "还没有导入资产。请到资产管理页上传文件。",
        "reuse": "复用决策与追踪链", "no_decision": "尚无复用决策",
        "no_decision_detail": "检索后解释匹配依据、阻塞差异和所需修改。",
        "direct": "直接复用", "modify": "修改后复用", "new_build": "新建场景", "review": "候选待评估",
        "structured_needed": "当前只有文本召回结果。上传并选择 PDF 场景后，才能基于结构差异给出复用决策。",
        "score": "综合", "vector": "语义", "scenario": "场景", "road": "道路",
        "cost": "修改成本", "decision": "决策", "blocking": "阻塞差异",
        "matched": "匹配依据", "edits": "所需修改", "none": "无",
        "trace": "证据溯源", "download": "下载评估数据", "details": "技术详情",
        "selected_item": "选中资产", "scenario_file": "场景文件", "road_file": "道路文件",
        "source_label": "需求来源", "change_cost": "预计修改量", "evidence_label": "原文证据", "match_score": "匹配分",
    },
    "en": {
        "subtitle": "From regulatory evidence to reusable OpenX scenario assets",
        "steps": ("Extract requirements", "Search asset library", "Assess reuse", "Export assessment report"),
        "requirements": "Requirements and extracted scenes",
        "pdf_help": "Upload an ADAS regulation or test protocol. Scenes, page ranges and source evidence stay connected.",
        "standard": "Standard name", "standard_hint": "For example, Euro NCAP 2025 LSS",
        "scenes": "Extracted scenes", "no_pdf": "No PDF uploaded",
        "no_pdf_detail": "Real extracted scenes, pages and source evidence will appear here.",
        "evidence": "Selected source evidence", "entities": "Participants", "actions": "Actions",
        "triggers": "Triggers", "roads": "Road context", "parameters": "Parameters", "pages": "Pages",
        "assets": "Asset library search and candidate scenarios",
        "source": "Asset source", "demo": "esmini public sample", "upload": "Upload assets",
        "load_demo": "Load esmini sample", "build": "Build asset library", "files": "SIM / XOSC / XODR files",
        "sim_cases": "Pairable SIM cases", "missing_roads": "Missing roads",
        "pairs": "Paired assets", "library_empty": "Load the public sample or upload paired XOSC/XODR files.",
        "encoder": "Search method", "hashing": "Basic text search (offline)", "bge": "Multilingual semantic search (BGE-M3)",
        "query": "Additional retrieval criteria", "query_hint": "Optional: road, weather, speed or test objective",
        "search": "Search reusable assets", "candidates": "Candidate scenarios",
        "no_results": "Build the library and run retrieval to see grounded candidates.",
        "candidate": "Inspect candidate", "selected": "Selected asset summary",
        "preview_off": "Parsed · preview tool not found", "preview_on": "Parsed · preview tool ready",
        "run_preview": "Play simulation", "stop_preview": "Stop",
        "home": "Overview", "text_search": "Text search", "pdf_workflow": "PDF workflow",
        "asset_management": "Asset management", "no_assets": "No assets imported yet. Upload files in Asset management.",
        "reuse": "Reuse decision and traceability", "no_decision": "No reuse decision yet",
        "no_decision_detail": "Retrieval explains matches, blockers and required edits here.",
        "direct": "Direct reuse", "modify": "Modify and reuse", "new_build": "Build new scenario", "review": "Candidate: assess next",
        "structured_needed": "This is text recall only. Upload and select a PDF scene to make a reuse decision from explicit structural differences.",
        "score": "Combined", "vector": "Semantic", "scenario": "Scenario", "road": "Road",
        "cost": "Change cost", "decision": "Decision", "blocking": "Blocking differences",
        "matched": "Matched evidence", "edits": "Required edits", "none": "None",
        "trace": "Evidence provenance", "download": "Download assessment data", "details": "Technical details",
        "selected_item": "Selected asset", "scenario_file": "Scenario file", "road_file": "Road file",
        "source_label": "Requirement source", "change_cost": "Estimated changes", "evidence_label": "Source evidence", "match_score": "Match score",
    },
}


def tx(language: str, key: str):
    return TEXT[language][key]


def safe(value: object) -> str:
    return html.escape(str(value), quote=True)


def icon(name: str, size: int = 16) -> str:
    paths = {
        "folder": '<path d="M3 6.5h6l1.8 2H21v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 8.5V6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v.5"/>',
        "history": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5M12 7v5l3 2"/>',
        "help": '<circle cx="12" cy="12" r="9"/><path d="M9.8 9a2.3 2.3 0 1 1 3.7 1.8c-1 .7-1.5 1.2-1.5 2.2M12 17h.01"/>',
        "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1z"/>',
        "shield": '<path d="M12 3l7 3v5c0 4.5-2.7 7.8-7 10-4.3-2.2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
        "link": '<path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1"/>',
        "download": '<path d="M12 3v12m0 0 4-4m-4 4-4-4M4 19h16"/>',
        "external": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"/>',
        "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    }
    body = paths.get(name, paths["search"])
    return f'<svg class="ow-icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>'


def chips(values: list[str] | dict[str, float]) -> str:
    entries = values.items() if isinstance(values, dict) else values
    parts = []
    for value in entries:
        label = f"{value[0]} {value[1]:g}" if isinstance(value, tuple) else str(value)
        parts.append(f'<span class="ow-chip">{safe(label)}</span>')
    return f'<div class="ow-chips">{"".join(parts)}</div>' if parts else ""


def empty(title: str, detail: str) -> None:
    st.markdown(f'<div class="ow-empty"><strong>{safe(title)}</strong><span>{safe(detail)}</span></div>', unsafe_allow_html=True)


def panel(number: int, title: str, status: str = "") -> None:
    badge = f'<span class="ow-status">{safe(status)}</span>' if status else ""
    st.markdown(f'<div class="ow-title"><span><span class="ow-index">{number}</span>{safe(title)}</span>{badge}</div>', unsafe_allow_html=True)


def index_for(catalog: list[OpenXAsset], encoder_name: str) -> OpenXIndex:
    identity = matching.index_identity(catalog, encoder_name)
    if st.session_state.get("index_identity") != identity:
        st.session_state.search_index = matching.open_index(catalog, identity)
        st.session_state.index_identity = identity
    return st.session_state["search_index"]


def _encoder_changed():
    save_preferences(encoder=st.session_state.retrieval_encoder)
    for key in ("retrieval_results", "text_results"):
        st.session_state[key] = []
    st.session_state.pop("batch_assessment", None)


def encoder_control(language: str) -> str:
    return st.selectbox(tx(language, "encoder"), ["bge", "hashing"],
                        format_func=lambda value: tx(language, value), key="retrieval_encoder",
                        on_change=_encoder_changed)


def verdict_label(language: str, level: str, scope: str = "") -> str:
    names = {"standards": ("文件标准待复核", "File standards need review"),
             "partial": ("部分已验证 · 待复核", "Partially verified · review"),
             "undecidable": ("关键结构不足 · 无法判断", "Insufficient structure · undecidable"),
             "recall": ("文本召回 · 待结构验证", "Text recall · verify structure"),
             "no_candidates": ("没有候选资产", "No candidate assets")}
    key = scope if level == "review" and scope else level
    if key in names:
        return names[key][0 if language == "zh" else 1]
    return tx(language, level)


def review_detail(language: str, scope: str) -> str:
    descriptions = {
        "standards": ("结构相似，但场景或道路的标准检查未通过或未完成。修复并重新检查后才能确认直接复用。",
                      "Structure matches, but scenario or road standard checks have not passed. Repair and recheck before confirming direct reuse."),
        "partial": ("已完成部分结构比较；以下未验证项确认前，不能认定可直接复用。",
                    "Some structure was compared. Resolve the unverified items before confirming direct reuse."),
        "undecidable": ("参与者交互或主车动作缺少关键结构，现有证据无法支持复用判断。",
                        "Key participant interaction or ego action evidence is missing; reuse cannot be assessed."),
        "recall": ("这是文本检索结果。选择有结构和原文证据的 PDF 场景后才能评估复用。",
                   "This is a text retrieval result. Select a structured PDF scene with source evidence to assess reuse."),
    }
    return descriptions.get(scope, descriptions["undecidable"])[0 if language == "zh" else 1]


def batch_summary(trace: dict, language: str):
    st.caption(trace["source"]["title"])
    encoder_label = (tx(language, "bge") if trace["encoder"] == "sentence-transformers:BAAI/bge-m3"
                     else tx(language, "hashing") if trace["encoder"].startswith("hashing-") else trace["encoder"])
    st.caption(localized(language, f"共 {trace['scene_count']} 个场景 · {encoder_label}",
                     f"{trace['scene_count']} scenes · {encoder_label}"))
    rows = []
    for entry in trace["entries"]:
        source, assessment = entry["source"], entry["assessment"]
        candidates = entry["candidates"]
        evidence = source.get("evidence") or []
        pages = ", ".join(f"{item['page_start']}–{item['page_end']}" for item in evidence)
        rows.append({tx(language, "scenario"): source["title"], tx(language, "pages"): pages,
                     localized(language, "修订", "Revision"): source["revision"], tx(language, "candidates"): candidates[0]["candidate"]["title"] if candidates else "—",
                     tx(language, "decision"): verdict_label(language, assessment["level"], assessment.get("review_kind", "")),
                     tx(language, "cost"): assessment.get("estimated_change_cost")})
    st.dataframe(rows, hide_index=True, width="stretch",
                 column_order=[tx(language, "decision"), tx(language, "scenario"), tx(language, "pages"),
                               tx(language, "candidates"), localized(language, "修订", "Revision"), tx(language, "cost")],
                 column_config={tx(language, "decision"): st.column_config.TextColumn(width="medium")})
    st.caption(" · ".join(f"{verdict_label(language, 'review' if key in {'partial', 'undecidable', 'recall', 'standards'} else key, key)}: {count}"
                          for key, count in trace["counts"].items()))
