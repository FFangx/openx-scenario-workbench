from __future__ import annotations

import html
import hashlib
import json
from pathlib import Path
from dataclasses import asdict, replace
from typing import Any

import streamlit as st

from openx_workbench.appearance import appearance_css, theme_colors
from openx_workbench.asset_management import label as localized
from openx_workbench.ui_shell import initialize, sidebar, header_controls, source_files, save_preferences, preview_settings
from openx_workbench.catalog import AssetFile, OpenXAsset
from openx_workbench.asset_store import AssetStore, AssetVersion
from openx_workbench.demo import fetch_public_demo
from openx_workbench.esmini_preview import PreviewProcess, start_preview
from openx_workbench.grounding import deterministic_explanation, model_explanation
from openx_workbench.pdf_store import PdfStore, StoredScene
from openx_workbench.project_store import ProjectStore
from openx_workbench.report_html import render_report
from openx_workbench.requirement_editor import edit_structure
from openx_workbench.presentation import display, difference_text, asset_display_title
from openx_workbench.native_locale import native_locale
from openx_workbench.reuse_trace import build_trace, checked_trace
from openx_workbench.batch_matching import match_document, batch_signature
from openx_workbench.retrieval import OpenXIndex, RetrievalResult, build_encoder, catalog_fingerprint
from openx_workbench.scene_package import ScenePackage, scene_package_to_query
from openx_workbench.sim_archive import SimImportReport


st.set_page_config(
    page_title="OpenX 场景工作台",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)


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


@st.cache_data(show_spinner=False)
def _pdf_page(data: bytes, number: int) -> bytes:
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as document:
        page = document[max(0, min(number - 1, len(document) - 1))]
        return page.get_pixmap(matrix=pymupdf.Matrix(1.15, 1.15), alpha=False).tobytes("png")


@st.cache_data(show_spinner=False)
def _demo_files() -> list[AssetFile]:
    demo = fetch_public_demo()
    return [AssetFile(demo.xosc_name, demo.xosc_data), AssetFile(demo.xodr_name, demo.xodr_data)]


@st.cache_resource(show_spinner=False)
def _encoder(name: str):
    return build_encoder(name)


def _index_for(catalog: list[OpenXAsset], encoder_name: str) -> OpenXIndex:
    identity = (encoder_name, catalog_fingerprint(catalog))
    if st.session_state.get("index_identity") == identity:
        return st.session_state["search_index"]
    fingerprint = identity[1][:24]
    path = AssetStore().root / "indexes" / encoder_name / f"{fingerprint}.json"
    encoder = _encoder(encoder_name)
    try:
        index = OpenXIndex.load(path, catalog, encoder)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        index = OpenXIndex(catalog, encoder)
        index.save(path)
    st.session_state.index_identity = identity
    st.session_state.search_index = index
    return index


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


def _theme() -> None:
    st.markdown(
        theme_colors("""
<style>
/* finesse · register=product · A=cool-slate+cobalt · B=system-sans · C=evidence-triptych
 * D=feedback-only · E=safety-case-workstation · SOUL=5 SPECTACLE=2 DENSITY=9 */
:root{--page:#edf1f5;--bg:#fbfcfe;--panel-2:#f3f6f9;--border:rgba(18,42,66,.12);--ink-1:#10243a;--ink-2:#3e5267;--ink-3:#68798b;--accent:#0876d9;--accent-2:#0a9fc0;--accent-soft:rgba(8,118,217,.10);--on-accent:#f8fbff;--up:#128044;--up-soft:#e9f8ee;--down:#bd3e35;--warn:#a36d00;--navy:#143149;--shadow:0 1px 3px rgba(20,49,73,.05)}
html,body{overflow-x:clip;color-scheme:light}body,.stApp,[data-testid="stAppViewContainer"]{background:var(--page);color:var(--ink-1);font-size:13px}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],#MainMenu,footer{display:none!important}
[data-testid="stAppViewContainer"]>.main{padding-top:0}[data-testid="stMainBlockContainer"],.block-container{max-width:none;padding:0 8px 8px!important}[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:0!important}
.stApp *{box-sizing:border-box;font-family:"Segoe UI Variable Text","Segoe UI","Noto Sans SC",sans-serif}.stApp [data-testid="stIconMaterial"]{font-family:"Material Symbols Rounded","Material Symbols Outlined"!important}::selection{background:#c8e5ff;color:#0b2638}
*:focus-visible{outline:3px solid rgba(8,118,217,.28)!important;outline-offset:2px}*{scrollbar-color:#9dafbb #edf2f5;scrollbar-width:thin}.ow-icon{display:block;flex:none}
.ow-steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) 300px;background:var(--bg);border:1px solid var(--border);border-top:0;margin:0 -8px 6px;height:43px}.ow-step{height:42px;display:flex;align-items:center;gap:9px;padding:0 18px;color:#68798b;font-size:10.5px;border-right:1px solid var(--border);position:relative}.ow-step:not(:nth-child(4)):after{content:"";position:absolute;right:-5px;width:8px;height:8px;border-top:1px solid #b5c0cb;border-right:1px solid #b5c0cb;transform:rotate(45deg);background:var(--bg);z-index:2}.ow-step.active{color:#0668c5;font-weight:700}.ow-step.done{color:#29495f}.ow-node{width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:#a2adb9;color:var(--on-accent);font-size:10px;font-weight:750}.ow-step.active .ow-node{background:var(--accent)}.ow-step.done .ow-node{background:#2d718f}.ow-step-tools{height:42px;display:flex;align-items:center;justify-content:center;gap:22px;color:#34485d;font-size:10px}.ow-step-tools span{display:flex;align-items:center;gap:6px;white-space:nowrap}
[data-testid="stHorizontalBlock"]{gap:6px!important}[data-testid="stVerticalBlockBorderWrapper"]{background:var(--bg);border:1px solid var(--border)!important;border-radius:6px!important;box-shadow:var(--shadow);min-height:calc(100vh - 94px)}[data-testid="stVerticalBlockBorderWrapper"]>div{padding:8px 8px 7px}.st-key-evidence_panel,.st-key-asset_panel,.st-key-decision_panel{min-height:calc(100vh - 94px);background:var(--bg);border-radius:6px}
.ow-title{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:14px;font-weight:730;color:var(--ink-1);margin:0 0 7px;height:34px;text-wrap:balance}.ow-index{width:22px;height:22px;border-radius:50%;background:var(--accent);color:var(--on-accent);display:inline-flex;align-items:center;justify-content:center;font-size:10px;margin-right:7px}.ow-section-rule{height:1px;background:var(--border);margin:7px -8px}.ow-tabs{display:flex;align-items:center;gap:24px;height:34px;border-bottom:1px solid var(--border);margin:0 -8px 8px;padding:0 14px}.ow-tab{height:34px;display:flex;align-items:center;font-size:10.5px;color:var(--ink-3);white-space:nowrap}.ow-tab.active{color:#0668c5;border-bottom:2px solid var(--accent);font-weight:680}.ow-library-meta{display:flex;justify-content:flex-end;gap:14px;color:var(--ink-3);font-size:9.5px;margin:-28px 4px 8px 0}.ow-online{color:var(--up);font-weight:680}.ow-online:before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--up);margin-right:5px}
.ow-label{font-size:10.5px;font-weight:680;color:#294655;margin:7px 0 4px}.ow-empty{border:1px dashed rgba(18,42,66,.22);background:#f8fafc;min-height:92px;display:flex;flex-direction:column;justify-content:center;padding:13px;border-radius:5px}.ow-empty strong{color:#294655;font-size:11.5px}.ow-empty span{color:var(--ink-3);font-size:11px;margin-top:4px;line-height:1.45}.ow-section{border:1px solid var(--border);border-radius:5px;padding:8px;margin-top:8px;background:#fdfefe}.ow-section-title{display:flex;justify-content:space-between;align-items:center;font-size:10.5px;font-weight:700;margin-bottom:5px;color:#24384a}.ow-section-title span{font-weight:500;color:var(--ink-3)}.ow-evidence{border:1px solid var(--border);background:#f8fafc;padding:8px;border-radius:5px}.ow-evidence p{font-size:11px;line-height:1.48;margin:4px 0 0;max-height:145px;overflow:auto;text-wrap:pretty}.ow-chips{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0}.ow-chip{border:1px solid rgba(8,118,217,.16);background:var(--accent-soft);color:#275a7a;border-radius:4px;padding:3px 6px;font-size:9.5px}
.ow-library-line{display:flex;gap:10px;align-items:center;color:var(--ink-3);font-size:9px;margin:2px 0 5px}.ow-library-line span+span:before{content:"·";margin-right:10px;color:#a3afba}
.ow-status{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border-radius:999px;font-size:9.5px;font-weight:680;color:#0868bd;background:#e9f4ff}.ow-status::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}.ow-status.good{color:var(--up);background:var(--up-soft)}.ow-file{display:grid;grid-template-columns:34px minmax(0,1fr) auto;gap:9px;align-items:center;border:1px solid var(--border);border-radius:5px;padding:9px;background:#fdfefe;margin-bottom:7px}.ow-file-icon{width:30px;height:34px;background:#d92534;color:var(--on-accent);display:grid;place-items:center;font-size:8px;font-weight:800;border-radius:3px}.ow-file strong{display:block;font-size:11.5px}.ow-file small{font-size:9.5px;color:var(--ink-3)}
.st-key-evidence_panel:has(.ow-file) [data-testid="stFileUploader"],.st-key-evidence_panel:has(.ow-file) [data-testid="stTextInput"]{display:none!important}[class*="st-key-scene_row_"]{border:1px solid var(--border);border-radius:5px;padding:7px;margin:0 0 7px;background:#fdfefe;min-height:86px}[class*="st-key-scene_row_selected_"]{border-color:#1687e8;background:#eaf6ff;box-shadow:inset 2px 0 0 #1687e8}[class*="st-key-scene_row_"] [data-testid="stHorizontalBlock"]{align-items:stretch!important;gap:8px!important}[class*="st-key-scene_row_"] [data-testid="stImage"]{height:70px;overflow:hidden;border-radius:2px;background:#e7edf1}[class*="st-key-scene_row_"] [data-testid="stImage"] img{height:70px!important;width:100%!important;object-fit:cover!important;object-position:top center!important}[class*="st-key-scene_row_"] .stButton,[class*="st-key-scene_row_"] .stButton>div{height:100%}[class*="st-key-scene_row_"] .stButton button{height:70px!important;min-height:70px!important;text-align:left!important;justify-content:flex-start!important;padding:8px 10px!important;background:transparent!important;border:0!important;color:var(--ink-1)!important;white-space:pre-line!important;line-height:1.32!important;font-weight:560!important}[class*="st-key-scene_row_selected_"] .stButton button{color:#075fae!important;font-weight:700!important}
.ow-filter-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:1px 0 8px}.ow-filter{display:inline-flex;gap:7px;align-items:center;background:#edf4fb;border:1px solid #d8e4ee;border-radius:4px;padding:6px 9px;font-size:9.5px;color:#41566c}.ow-filter b{color:#075fae;font-weight:700}.ow-filter i{font-style:normal;color:#1687e8;font-size:13px}.ow-candidate-head{display:flex;justify-content:space-between;align-items:center;margin:8px 0 6px}.ow-candidate-head strong{font-size:11.5px}.ow-candidate-head span{font-size:9.5px;color:var(--ink-3)}
.ow-table-wrap{height:386px;border:1px solid var(--border);border-radius:4px;overflow:auto;background:#fdfefe}.ow-candidate-table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:10px;color:#31475b}.ow-candidate-table th{height:43px;padding:6px 7px;text-align:left;background:#f1f4f7;border-right:1px solid var(--border);border-bottom:1px solid var(--border);font-size:9px;color:#34465a;line-height:1.2;position:sticky;top:0;z-index:1}.ow-candidate-table td{height:45px;padding:6px 7px;border-right:1px solid rgba(18,42,66,.08);border-bottom:1px solid rgba(18,42,66,.08);vertical-align:middle;overflow:hidden;text-overflow:ellipsis}.ow-candidate-table th:last-child,.ow-candidate-table td:last-child{border-right:0}.ow-candidate-table tr.selected td{background:#dff1ff;border-bottom-color:#9fcef5}.ow-candidate-table .num{width:28px;text-align:center}.ow-candidate-table .pair{width:28%}.ow-candidate-table .desc{width:18%}.ow-candidate-table .score{font-variant-numeric:tabular-nums;text-align:right}.ow-pair{color:#075fae;font-weight:650;line-height:1.35}.ow-pair small{display:block;color:#52687b;font-weight:500}.ow-match{display:inline-flex;white-space:nowrap;border-radius:3px;padding:3px 5px;font-weight:680;font-size:8.5px}.ow-match.direct{color:#146b32;background:#c9f0bf}.ow-match.modify{color:#79560f;background:#ffe3a1}.ow-match.new_build{color:#5b6570;background:#e5e9ee}.ow-match.review{color:#075fae;background:#e1f0fd}.ow-checkbox{width:12px;height:12px;border:1px solid #7b8da0;border-radius:2px;display:inline-grid;place-items:center;margin:auto}.selected .ow-checkbox{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}.selected .ow-checkbox:after{content:"✓";font-size:8px;font-weight:900}
.ow-asset-shell{border:1px solid var(--border);border-radius:5px;background:#fdfefe}.ow-asset-name{padding:8px 10px;border-bottom:1px solid var(--border);color:#075fae;font-weight:680;font-size:10.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ow-asset-grid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1.3fr) minmax(0,.9fr);min-height:166px}.ow-asset-cell{padding:9px;border-right:1px solid var(--border);min-width:0}.ow-asset-cell:last-child{border-right:0}.ow-mini-title{font-size:9.5px;font-weight:700;color:#334b5d;margin-bottom:7px}.ow-fact{display:grid;grid-template-columns:68px minmax(0,1fr);gap:6px;padding:4px 0;font-size:9.5px}.ow-fact span:first-child{color:var(--ink-3)}.ow-fact span:last-child{overflow:hidden;text-overflow:ellipsis}.ow-schematic{height:112px;border:1px solid rgba(18,42,66,.15);border-radius:3px;overflow:hidden;background:#4f625e}.ow-schematic svg{width:100%;height:100%;display:block}.ow-preview-state{height:112px;border:1px dashed rgba(18,42,66,.22);background:#eef2f5;display:grid;place-items:center;text-align:center;color:#496272;padding:10px;font-size:9.5px;border-radius:3px}
.ow-decision{padding:12px;border-radius:5px;border:1px solid #8dd1a5;background:#eaf8ef}.ow-decision.modify{border-color:#e5c567;background:#fff8df}.ow-decision.new_build{border-color:#e5aaa6;background:#fff1f0}.ow-decision.review{border-color:#9bc3df;background:#eef7fd}.ow-decision-line{display:flex;justify-content:space-between;align-items:baseline;gap:10px}.ow-decision h3{margin:2px 0 4px;font-size:20px;color:var(--up)!important;letter-spacing:-.02em}.ow-decision.modify h3{color:var(--warn)!important}.ow-decision.new_build h3{color:var(--down)!important}.ow-decision.review h3{color:var(--accent)!important}.ow-score{font-size:11px;font-weight:720;font-variant-numeric:tabular-nums}.ow-verdict-kicker{display:flex;align-items:center;gap:7px;font-size:10.5px;font-weight:700}.ow-check{width:20px;height:20px;border-radius:50%;display:inline-grid;place-items:center;background:currentColor}.ow-check:after{content:"✓";color:var(--on-accent);font-weight:900}.ow-decision p{font-size:10.5px;color:#4e6270;margin:5px 0 0;line-height:1.4}.ow-decision .ow-verdict-kicker{color:var(--up)}.ow-decision.modify .ow-verdict-kicker{color:var(--warn)}.ow-decision.new_build .ow-verdict-kicker{color:var(--down)}.ow-decision.review .ow-verdict-kicker{color:var(--accent)}
.ow-list{margin:4px 0 8px;padding-left:18px;color:#405765;font-size:10.5px}.ow-list li{margin:5px 0}.ow-trace{display:grid;grid-template-columns:72px minmax(0,1fr);gap:8px;padding:7px 0;border-bottom:1px solid rgba(18,42,66,.08);font-size:10px}.ow-trace:last-child{border-bottom:0}.ow-trace span:first-child{color:var(--ink-3)}.ow-trace span:last-child{color:#075fae;overflow-wrap:anywhere}.ow-action-row{display:grid;grid-template-columns:1.35fr .85fr;gap:8px;margin-top:8px}.ow-interface-button{min-height:35px;border:1px solid #aebdca;border-radius:4px;display:flex;align-items:center;justify-content:center;gap:7px;color:#075fae;background:#fdfefe;font-size:10px;font-weight:680}.ow-interface-button.primary{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.stButton button,.stDownloadButton button{border-radius:4px!important;min-height:34px;font-size:10.5px;font-weight:650;box-shadow:none!important;white-space:nowrap}.stTextInput input,.stSelectbox [data-baseweb="select"]>div,.stFileUploader section{border-radius:4px!important;font-size:10.5px}.stTextInput input{min-height:34px}.stFileUploader section{padding:8px!important}.stCaptionContainer p{font-size:9.5px!important}.stAlert{padding:8px 10px!important;border-radius:4px!important;font-size:10.5px!important}.st-key-candidate_picker{margin-top:-4px}.st-key-candidate_picker [data-baseweb="select"]>div{min-height:31px!important;height:31px!important}
@media(max-width:1120px){.ow-steps{grid-template-columns:repeat(2,minmax(0,1fr));height:auto}[data-testid="stHorizontalBlock"]:has(.st-key-evidence_panel):has(.st-key-asset_panel):has(.st-key-decision_panel){display:grid!important;grid-template-columns:minmax(0,1fr)!important}[data-testid="stHorizontalBlock"]:has(.st-key-evidence_panel):has(.st-key-asset_panel):has(.st-key-decision_panel)>[data-testid="stColumn"]{width:100%!important;min-width:0!important;max-width:none!important;flex:none!important}.ow-asset-grid{grid-template-columns:minmax(0,1fr)}.ow-asset-cell{border-right:0;border-bottom:1px solid var(--border)}.ow-asset-cell:last-child{border-bottom:0}.ow-table-wrap{height:330px}[data-testid="stVerticalBlockBorderWrapper"]{min-height:0}}
@media(max-width:640px){.ow-step{padding:0 9px}.ow-step:nth-child(n+3){display:none}.ow-action-row{grid-template-columns:minmax(0,1fr)}.ow-table-wrap{overflow-x:auto}.ow-candidate-table{min-width:680px}.stButton button,.stDownloadButton button{min-height:44px}.stTextInput input,.stSelectbox [data-baseweb="select"]>div{min-height:44px;font-size:16px}.ow-title{overflow-wrap:anywhere;min-width:0}}
@media(prefers-reduced-motion:reduce){*{animation-duration:.01ms!important;transition-duration:.01ms!important}}
.st-key-evidence_panel .stButton button{white-space:normal!important;overflow-wrap:anywhere;text-align:left}
.st-key-decision_panel .stButton button,.st-key-decision_panel .stDownloadButton button{white-space:normal!important;overflow-wrap:anywhere}
</style>
        """),
        unsafe_allow_html=True,
    )


def _chips(values: list[str] | dict[str, float]) -> str:
    entries = values.items() if isinstance(values, dict) else values
    parts = []
    for value in entries:
        label = f"{value[0]} {value[1]:g}" if isinstance(value, tuple) else str(value)
        parts.append(f'<span class="ow-chip">{safe(label)}</span>')
    return f'<div class="ow-chips">{"".join(parts)}</div>' if parts else ""


def _empty(title: str, detail: str) -> None:
    st.markdown(f'<div class="ow-empty"><strong>{safe(title)}</strong><span>{safe(detail)}</span></div>', unsafe_allow_html=True)


def _panel(number: int, title: str, status: str = "") -> None:
    badge = f'<span class="ow-status">{safe(status)}</span>' if status else ""
    st.markdown(f'<div class="ow-title"><span><span class="ow-index">{number}</span>{safe(title)}</span>{badge}</div>', unsafe_allow_html=True)


def _header(*, show_steps: bool = True) -> str:
    language = "zh" if st.session_state.language == "中文" else "en"
    header_controls(language)
    if not show_steps:
        return language
    active = 3 if st.session_state.get("retrieval_results") else 2 if st.session_state.get("selected_stored_scene") else 1
    stages = []
    for index, label in enumerate(tx(language, "steps"), 1):
        state = "active" if index == active else "done" if index < active else ""
        stages.append(f'<div class="ow-step {state}"><span class="ow-node">{index}</span><span>{safe(label)}</span></div>')
    st.markdown(
        f'<div class="ow-steps">{"".join(stages)}</div>',
        unsafe_allow_html=True,
    )
    return language


def _encoder_changed():
    save_preferences(encoder=st.session_state.retrieval_encoder)
    for key in ("retrieval_results", "text_results"):
        st.session_state[key] = []
    st.session_state.pop("batch_assessment", None)


def _encoder_control(language: str) -> str:
    return st.selectbox(tx(language, "encoder"), ["bge", "hashing"],
                        format_func=lambda value: tx(language, value), key="retrieval_encoder",
                        on_change=_encoder_changed)


def _verdict_label(language: str, level: str, scope: str = "") -> str:
    names = {"standards": ("文件标准待复核", "File standards need review"),
             "partial": ("部分已验证 · 待复核", "Partially verified · review"),
             "undecidable": ("关键结构不足 · 无法判断", "Insufficient structure · undecidable"),
             "recall": ("文本召回 · 待结构验证", "Text recall · verify structure"),
             "no_candidates": ("没有候选资产", "No candidate assets")}
    key = scope if level == "review" and scope else level
    if key in names:
        return names[key][0 if language == "zh" else 1]
    return tx(language, level)


def _review_detail(language: str, scope: str) -> str:
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


def _batch_summary(trace: dict, language: str):
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
                     tx(language, "decision"): _verdict_label(language, assessment["level"], assessment.get("review_kind", "")),
                     tx(language, "cost"): assessment.get("estimated_change_cost")})
    st.dataframe(rows, hide_index=True, width="stretch",
                 column_order=[tx(language, "decision"), tx(language, "scenario"), tx(language, "pages"),
                               tx(language, "candidates"), localized(language, "修订", "Revision"), tx(language, "cost")],
                 column_config={tx(language, "decision"): st.column_config.TextColumn(width="medium")})
    st.caption(" · ".join(f"{_verdict_label(language, 'review' if key in {'partial', 'undecidable', 'recall', 'standards'} else key, key)}: {count}"
                          for key, count in trace["counts"].items()))


def _document_matching(document, scenes, language: str):
    with st.expander("整份 PDF 匹配与汇总" if language == "zh" else "Match entire PDF and summarize"):
        catalog = st.session_state.get("catalog", [])
        versions = st.session_state.get("asset_versions", {})
        encoder = st.session_state.get("retrieval_encoder", "bge")
        signature = batch_signature(document, scenes, catalog, versions, encoder)
        st.caption(localized(language, f"匹配本文档全部 {len(scenes)} 个场景，使用当前编码器和资产库。",
                         f"Match all {len(scenes)} document scenes using the current encoder and asset library."))
        if st.button("批量匹配" if language == "zh" else "Match all scenes", key="match_document",
                     disabled=not catalog or not scenes, icon=":material/search:"):
            try:
                with st.spinner("正在匹配整份 PDF…" if language == "zh" else "Matching PDF scenes…"):
                    trace = match_document(document, scenes, _index_for(catalog, encoder), versions)
                st.session_state.batch_assessment = (signature, trace)
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
        saved = st.session_state.get("batch_assessment")
        if not saved or saved[0] != signature:
            if saved:
                st.info("场景、资产或编码器已改变，请重新匹配。" if language == "zh" else
                        "Scenes, assets or encoder changed. Run matching again.")
            return
        trace = saved[1]
        _batch_summary(trace, language)
        left, right = st.columns(2)
        with left:
            st.download_button("下载汇总 JSON" if language == "zh" else "Download summary JSON",
                               json.dumps(trace, ensure_ascii=False, indent=2), "openx-document.json", "application/json")
        with right:
            st.download_button("下载汇总 HTML" if language == "zh" else "Download summary HTML",
                               render_report(trace, language=language), "openx-document.html", "text/html")
        if st.button("保存汇总报告" if language == "zh" else "Save summary report", key="save_batch_report"):
            try:
                ProjectStore().save_batch(document.project_id, trace)
                st.success("汇总已保存，候选资产版本已固定。" if language == "zh" else
                           "Summary saved with pinned candidate asset versions.")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))


def _pdf_scene_library(language: str) -> StoredScene | None:
    project_id = st.session_state.get("active_project_id")
    st.subheader(localized(language, "场景需求", "Requirements"))
    if not project_id:
        with st.expander(tx(language, "encoder")):
            _encoder_control(language)
        st.info("请先在左侧创建或选择项目。" if language == "zh" else "Create or select a project in the sidebar first.")
        st.session_state.selected_stored_scene = None
        return None
    store = PdfStore()
    documents = store.documents(project_id)
    with st.expander("导入 PDF 与设置" if language == "zh" else "Import PDFs and settings", expanded=not documents):
        _encoder_control(language)
        uploads = st.file_uploader("选择 PDF 文件" if language == "zh" else "Choose PDF files", type=["pdf"], accept_multiple_files=True,
                                   key=f"project_pdfs_{project_id}")
        standard = st.text_input(tx(language, "standard"), placeholder=tx(language, "standard_hint"),
                                 key="pdf_standard")
        st.caption("识别场景需求、核对原文证据，再由你复核入库。导入时会向已配置的模型发送 PDF 文字。" if language == "zh" else
                   "Extract requirements, check source evidence, then review and publish. Import sends PDF text to your configured model.")
        if not uploads:
            st.caption("请先点击文件选择按钮添加 PDF，然后导入。" if language == "zh" else
                       "Choose a PDF using the file selection button, then import it.")
        if st.button("导入 PDF" if language == "zh" else "Import PDFs",
                     disabled=not uploads, key="import_project_pdfs", type="primary", icon=":material/description:"):
            try:
                imported = []
                with st.status("正在提取 PDF 场景…" if language == "zh" else "Extracting PDF scenes…", expanded=True) as status:
                    for item in uploads:
                        st.write(item.name)
                        imported.append(store.import_pdf(project_id, item.name, item.getvalue(), standard.strip(), progress=st.write))
                    status.update(label=localized(language, "提取完成", "Extraction complete"), state="complete")
                st.session_state.current_document_id = imported[-1].document_id
                st.session_state.selected_scene_key = None
                st.session_state.selected_stored_scene = None
                st.session_state.retrieval_results = []
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"PDF: {exc}")
    if not documents:
        _empty(tx(language, "no_pdf"), tx(language, "no_pdf_detail"))
        st.session_state.selected_stored_scene = None
        return None
    document_by_id = {item.document_id: item for item in documents}
    if len(documents) > 1:
        mode = st.radio("场景范围" if language == "zh" else "Scene scope", ["by_pdf", "all"],
                        format_func=lambda item: ("按 PDF 分组" if item == "by_pdf" else "全部场景")
                        if language == "zh" else ("By PDF" if item == "by_pdf" else "All scenes"),
                        horizontal=True, key="pdf_view_mode")
    else:
        mode = "by_pdf"
    if mode == "by_pdf":
        ids = list(document_by_id)
        if st.session_state.get("current_document_id") not in ids:
            st.session_state.current_document_id = ids[0]
        selected_doc = st.selectbox("PDF", ids, key="current_document_id",
                                    format_func=lambda item: f"{document_by_id[item].filename} · {document_by_id[item].scene_count} " + localized(language, "个场景", "scenes"))
        scenes = store.scenes(project_id, selected_doc)
        document = document_by_id[selected_doc]
        with st.expander("文档批量评估与解析记录" if language == "zh" else "Document assessment and extraction record"):
            _document_matching(document, scenes, language)
            from openx_workbench.pdf_extraction import ENGINE_VERSION
            if document.extraction_engine != ENGINE_VERSION:
                if st.button("重新识别场景" if language == "zh" else "Extract scenes again", key="reextract_pdf", icon=":material/refresh:"):
                    try:
                        with st.status(localized(language, "正在重新提取", "Re-extracting"), expanded=True):
                            updated = store.import_pdf(project_id, document.filename, store.pdf_bytes(document), document.source_standard, progress=st.write)
                        st.session_state.document_to_select = updated.document_id
                        st.session_state.selected_scene_key = None
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            audit = store.extraction_audit(document)
            if audit:
                with st.expander("解析与校验记录" if language == "zh" else "Extraction and validation"):
                    st.caption(("使用模型：" if language == "zh" else "Model: ") + audit["run"]["model"])
                    issues = audit["structure_quality"]["issues"] + (audit["run"].get("validation") or {}).get("issues", [])
                    for issue in issues:
                        st.warning(issue.get("detail") or issue.get("message") or issue["code"])
                    for flag in audit.get("structure_flags", []):
                        st.warning(f"P{flag['page_number']}: {flag['detail']}")
                    if audit.get("preprocessing"):
                        st.caption("扫描页已在本机识别；请对照原文复核文字与表格。" if language == "zh" else
                                   "Scanned pages were recognized locally. Review text and tables against the source.")
                    st.download_button("下载解析记录" if language == "zh" else "Download extraction record",
                                       json.dumps(audit, ensure_ascii=False, indent=2), "extraction.json", "application/json")
                if not scenes:
                    st.info("模型已完成提取，此文档没有识别到场景。可下载解析记录核查。" if language == "zh" else
                            "Extraction completed with no scenes. Download the record to inspect the result.")
    else:
        scenes = store.all_scenes(project_id)
    all_visible_scenes = scenes
    functions = sorted({scene.package.classification.get("function", "未知") for scene in scenes})
    filters = [st.container(), st.container()]
    with filters[0]:
        phrase = st.text_input("查找场景" if language == "zh" else "Find a scene", key="pdf_scene_search",
                               placeholder="标题、条款或页码" if language == "zh" else "Title, clause or page")
    with filters[1]:
        function_filter = st.selectbox("功能分类" if language == "zh" else "Function category", ["全部 / All", *functions],
                                        key="pdf_function_filter", format_func=lambda v: localized(language, "全部", "All") if v == "全部 / All" else v)
    if function_filter != "全部 / All":
        scenes = [item for item in scenes if item.package.classification.get("function", "未知") == function_filter]
    if phrase.strip():
        scenes = [item for item in scenes if phrase.strip().casefold() in
                  (item.package.title + " " + " ".join(f"{e.section_id} {e.page_start} {e.page_end}" for e in item.package.evidence)).casefold()]
    st.caption(f"筛选结果 {len(scenes)} / {len(all_visible_scenes)} 个场景 · 选择后在右侧核对" if language == "zh" else
               f"{len(scenes)} / {len(all_visible_scenes)} scenes · Select one to review")
    selected_key = st.session_state.get("selected_scene_key")
    keys = [(project_id, item.document.document_id, item.scene_id) for item in scenes]
    by_key = dict(zip(keys, scenes))
    def scene_label(key):
        item = by_key[key]
        evidence = item.package.evidence[0] if item.package.evidence else None
        pages = f"{evidence.page_start}–{evidence.page_end}" if evidence else "—"
        return f"{item.package.title} · {tx(language, 'pages')} {pages} · v{item.revision}"
    # A searchable native control bounds the list regardless of document size.
    signature = hashlib.sha256(repr([(key, by_key[key].revision) for key in keys]).encode()).hexdigest()[:12]
    picker_key = "scene_picker_" + signature
    external = st.session_state.pop("scene_picker_target", None)
    if external in keys:
        st.session_state[picker_key] = external
    choice = st.selectbox("选择场景需求" if language == "zh" else "Select a requirement", keys,
                          index=keys.index(selected_key) if selected_key in keys else None,
                          format_func=scene_label, key=picker_key,
                          placeholder="选择一个场景…" if language == "zh" else "Choose a scene…")
    if choice is not None and choice != selected_key:
        st.session_state.selected_scene_key = choice
        st.session_state.pdf_stage = "review"
        st.session_state.retrieval_results = []
        st.rerun()
    if not scenes:
        st.info("没有符合筛选条件的场景。清空关键词或选择全部功能。" if language == "zh" else
                "No scenes match. Clear your search or choose all functions.")
    scenes = all_visible_scenes
    selected_key = st.session_state.get("selected_scene_key")
    selected: StoredScene | None = next((item for item in scenes if selected_key ==
                                         (project_id, item.document.document_id, item.scene_id)), None)
    if selected is None and selected_key and selected_key[0] == project_id:
        st.session_state.selected_scene_key = None
        st.session_state.retrieval_results = []
        st.rerun()
    if selected is None:
        st.session_state.selected_stored_scene = None
        return None
    st.session_state.selected_stored_scene = selected
    return selected


def _requirement_details(selected: StoredScene, language: str) -> None:
    store = PdfStore()
    project_id = selected.document.project_id
    package = selected.package
    st.write(package.preferred_text)
    st.caption(localized(language, "先核对需求事实，再检索资产。需要修改时展开编辑区；原文证据保持只读。", "Review the requirement before searching assets. Expand the editor to make changes; source evidence remains read-only."))
    with st.expander("核对并编辑事实" if language == "zh" else "Review and edit facts", expanded=st.session_state.pop("requirement_edit_open", False)):
        st.caption(localized(language, "编辑后先保存事实修订，再切换场景或页面。匹配会使用已保存的事实。", "Save fact edits before changing scenes or pages. Matching uses saved facts."))
        with st.form(key=f"edit_scene_{selected.document.document_id}_{selected.scene_id}_{selected.revision}"):
            title = st.text_input("场景标题" if language == "zh" else "Scene title", value=package.title)
            preferred_text = st.text_area("场景说明" if language == "zh" else "Extracted facts / interpretation",
                                          value=package.preferred_text, height=115)
            fields = {}
            if package.structure:
                structured_draft = edit_structure(package.structure, language)
                with st.expander("高级结构编辑" if language == "zh" else "Advanced structure editor"):
                    st.caption("复杂参与者、关系和目标速度会保留。勾选后以 JSON 替换完整结构。" if language == "zh" else
                               "Participants, relations and target speeds are preserved. Enable JSON to replace the entire structure.")
                    use_json = st.checkbox("使用 JSON 编辑结果" if language == "zh" else "Use JSON edits")
                    structured_json = st.text_area("结构 JSON" if language == "zh" else "Structure JSON", value=json.dumps(package.structure, ensure_ascii=False, indent=2), height=180)
            else:
                for key, label in (("entities", localized(language, "参与者", "Participants")), ("actions", localized(language, "动作", "Actions")),
                                   ("triggers", localized(language, "触发条件", "Triggers")), ("road_types", localized(language, "道路", "Road types")),
                                   ("weather", localized(language, "天气", "Weather")), ("time_of_day", localized(language, "时段", "Time of day"))):
                    fields[key] = st.text_input(label, value=", ".join(getattr(package, key)))
                parameters = st.text_input(localized(language, "高级参数（JSON）", "Advanced parameters (JSON)"),
                                           value=json.dumps(package.parameters, ensure_ascii=False))
            save = st.form_submit_button("保存事实修订" if language == "zh" else "Save fact revision")
    if save:
        try:
            edits = {"title": title, "preferred_text": preferred_text}
            if package.structure:
                edits.update(structure=json.loads(structured_json) if use_json else structured_draft)
            else:
                edits.update({key: [part.strip() for part in value.split(",") if part.strip()]
                              for key, value in fields.items()})
                edits["parameters"] = json.loads(parameters)
            store.revise_scene(project_id, selected.document.document_id, selected.scene_id, edits)
            st.session_state.retrieval_results = []
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(localized(language, "修订未保存。请检查数值和结构格式；你的输入仍保留在表单中。", "Revision was not saved. Check values and structure; your inputs remain in the form."))
            with st.expander(localized(language, "查看错误详情", "Error details")):
                st.code(str(exc), language=None)
    with st.expander("结构与分类" if language == "zh" else "Structure and classification"):
        st.json({"structure": package.structure, "classification": package.classification})
        for issue in package.extraction.get("validation", {}).get("issues", []):
            st.warning(issue.get("detail", issue.get("code", "")))
        for flag in package.extraction.get("structure_flags", []):
            st.warning(flag["detail"])
        if any(block.get("source") == "ocr" for block in package.extraction.get("source_blocks", [])):
            st.caption("包含本机 OCR 识别的证据，请对照原文复核。" if language == "zh" else
                       "Includes locally recognized OCR evidence; review against the source.")
    with st.expander("对照 PDF 原文" if language == "zh" else "Check PDF evidence"):
        evidence = package.evidence[0] if package.evidence else None
        if len(package.evidence) > 1:
            evidence_index = st.selectbox("原文条款" if language == "zh" else "Source clause", range(len(package.evidence)),
                                          format_func=lambda index: f"{package.evidence[index].section_id} · {package.evidence[index].page_start}–{package.evidence[index].page_end}",
                                          key=f"evidence_{selected.document.document_id}_{selected.scene_id}")
            evidence = package.evidence[evidence_index]
        if evidence:
            st.markdown(f'<div class="ow-label">{safe(tx(language,"evidence"))} · {safe(localized(language, "原文只读", "Read-only source"))}</div>', unsafe_allow_html=True)
            image_col, text_col = st.columns([1, 2])
            with image_col:
                try:
                    st.image(_pdf_page(store.pdf_bytes(selected.document), evidence.page_start),
                             caption=f"{selected.document.filename} · {tx(language, 'pages')} {evidence.page_start}",
                             use_container_width=True)
                except Exception:
                    st.caption(f"{selected.document.filename} · {tx(language, 'pages')} {evidence.page_start}–{evidence.page_end}")
            with text_col:
                st.markdown(f'<div class="ow-evidence"><strong>{safe(evidence.section_id)} · {safe(selected.document.filename)}</strong>'
                            f'<p>{safe(evidence.source_text)}</p></div>', unsafe_allow_html=True)
    with st.expander(localized(language, "入库与修订记录", "Publication and revisions")):
        confirmed = any(item["project_id"] == project_id and item["document_id"] == selected.document.document_id and item["scene_id"] == selected.scene_id and item["revision"] == selected.revision for item in store.library())
        st.caption(localized(language, "当前修订已确认入库" if confirmed else "当前修订尚未确认入库；保存事实和确认入库是两个步骤。", "Current revision published" if confirmed else "Current revision is not published. Save facts before confirming publication."))
        if package.classification:
            st.caption(" · ".join(str(package.classification.get(key, "")) for key in ("function", "road_type", "intent")))
        if st.button("确认已保存修订并入库" if language == "zh" else "Confirm and publish revision", key="publish_pdf_scene", icon=":material/library_add:", disabled=confirmed):
            store.publish_scene(selected)
            st.success("已保存到全局需求场景库，可在资产管理中查看。" if language == "zh" else
                       "Saved to the shared requirement library in Asset management.")
        if selected.revision > 1:
            with st.expander("修订历史" if language == "zh" else "Revision history"):
                st.dataframe([{localized(language, "修订", "Revision"): item.revision, localized(language, "标题", "Title"): item.package.title,
                               localized(language, "参数", "Parameters"): json.dumps(item.package.parameters, ensure_ascii=False)}
                              for item in store.revisions(project_id, selected.document.document_id,
                                                          selected.scene_id)],
                             use_container_width=True, hide_index=True)


def _rows(results: list[RetrievalResult], language: str) -> list[dict[str, Any]]:
    return [{"#": i, tx(language,"scenario"): asset_display_title(r.asset, language), tx(language,"score"): round(r.score, 2),
             tx(language,"decision"): _verdict_label(language, r.confirmation_level, r.confirmation_review_kind),
             tx(language,"cost"): r.estimated_change_cost} for i, r in enumerate(results, 1)]


def _road_schematic(asset: OpenXAsset, *, scenario: bool) -> str:
    lanes = max(2, min(6, asset.bundle.road.lane_count or 2))
    lane_lines = "".join(
        f'<line x1="{20 + i * 160 / lanes:.1f}" y1="0" x2="{20 + i * 160 / lanes:.1f}" y2="112" stroke="#dce4e5" stroke-width="1" stroke-dasharray="8 7"/>'
        for i in range(1, lanes)
    )
    vehicles = ""
    if scenario:
        vehicles = (
            '<rect x="72" y="72" width="21" height="34" rx="5" fill="#0876d9" stroke="#d9f1ff"/>'
            '<rect x="118" y="38" width="21" height="34" rx="5" fill="#eef2f4" stroke="#334b5d"/>'
            '<path d="M128 78 C117 88 105 89 96 89" fill="none" stroke="#f8fbff" stroke-width="2" stroke-dasharray="4 3"/>'
        )
    return (
        '<div class="ow-schematic"><svg viewBox="0 0 200 112" role="img" aria-label="Parsed OpenX schematic">'
        '<rect width="200" height="112" fill="#536864"/><path d="M0 0h18v112H0zM182 0h18v112h-18z" fill="#728e6e"/>'
        '<line x1="20" y1="0" x2="20" y2="112" stroke="#f1f5f5" stroke-width="2"/>'
        '<line x1="180" y1="0" x2="180" y2="112" stroke="#f1f5f5" stroke-width="2"/>'
        f'{lane_lines}{vehicles}</svg></div>'
    )


def _asset_summary(asset: OpenXAsset, language: str) -> None:
    road = asset.bundle.road
    st.markdown(f"**{safe(asset_display_title(asset, language))}**")
    st.caption(localized(language,
               f"参与者 {len(asset.bundle.scenario.entities)} 个 · 道路总长 {road.total_length:g} m · 车道记录 {road.lane_count} 条",
               f"{len(asset.bundle.scenario.entities)} entities · Road length {road.total_length:g} m · {road.lane_count} lane records"))
    with st.expander(localized(language, "场景与道路文件", "Scenario and road files")):
        st.write(localized(language, "原始名称：", "Original title: ") + asset.title)
        st.write(f"OpenSCENARIO: {asset.xosc_name}")
        st.write(f"OpenDRIVE: {asset.xodr_name}")
        geometry_labels = {"line": "直线", "arc": "圆弧", "spiral": "缓和曲线", "poly3": "三次曲线", "paramPoly3": "参数曲线"}
        geometry = " · ".join(f"{geometry_labels.get(k, k) if language == 'zh' else k} {v}" for k, v in road.geometry_types.items()) or "—"
        st.caption(localized(language, "道路几何：", "Road geometry: ") + geometry)


def _preview_live(preview: PreviewProcess, version: AssetVersion, language: str, status: dict) -> None:
    store = AssetStore()
    current = next((item for item in store.versions()
                    if item.asset_id == version.asset_id and item.version_id == version.version_id), version)
    if status["state"] == "failed":
        if current.compatibility != "failed" or current.compatibility_detail != status["error"]:
            store.set_compatibility(version, "failed", status["error"])
        st.error(localized(language, "这个场景暂时无法播放，请查看下方详情。", "This scenario could not play. See the details below."))
        with st.expander(localized(language, "预览失败详情", "Preview failure details")):
            st.code(status["error"], language=None)
            try:
                st.code((preview.workdir / "worker.log").read_text(errors="replace")[-4000:], language=None)
            except OSError:
                pass  # A finished worker may already have removed its staging files.
    elif status["state"] == "stopped":
        st.warning(localized(language, "预览已停止，可以重新播放。", "Preview stopped. You can play it again."))
    elif status["state"] == "finished" and not status["frames"]:
        if current.compatibility != "failed":
            store.set_compatibility(version, "failed", "esmini finished without rendered frames.")
        st.error(localized(language, "预览结束，但没有生成画面。", "Preview ended without producing a frame."))
    else:
        if status["frames"]:
            if current.compatibility != "playable":
                store.set_compatibility(version, "playable")
            st.markdown(
                f'<img src="{safe(preview.url)}/stream?token={safe(preview.token)}" '
                f'alt="{safe(localized(language, "实时仿真画面", "Live esmini simulation"))}" style="width:100%;height:auto;aspect-ratio:16/9;object-fit:contain;display:block;background:#17242e">',
                unsafe_allow_html=True,
            )
        st.caption(localized(language, "预览已结束，可以重新播放。", "Preview finished. You can play it again.")
                   if status["state"] == "finished" else localized(language,
                   f"正在播放 · 已生成 {status['frames']} 帧真实画面", f"Playing · {status['frames']} rendered frames"))


def _preview_controls(version: AssetVersion, language: str, *, show_identity: bool = True) -> None:
    version = next((item for item in AssetStore().versions()
                    if item.asset_id == version.asset_id and item.version_id == version.version_id), version)
    if show_identity:
        st.caption(localized(language, f"资产 {version.asset_id[:10]} · 版本 {version.version_number} · {display(version.compatibility, language)}", f"Asset {version.asset_id[:10]} · version {version.version_number} · {version.compatibility}"))
    if version.compatibility_detail:
        st.caption(version.compatibility_detail)
    _preview_playback(version, language, preview_settings(language))


@st.fragment(run_every="1s")
def _preview_playback(version: AssetVersion, language: str, executable: Path | None) -> None:
    preview = st.session_state.get("preview_process")
    selected_preview = preview is not None and (preview.asset_id, preview.version_id) == (version.asset_id, version.version_id)
    status = preview.status() if selected_preview else None
    active = selected_preview and preview.process.poll() is None and status["state"] != "finished"
    run_col, stop_col = st.columns(2)
    with run_col:
        if st.button(tx(language, "run_preview"), width="stretch", key="run_esmini_preview", icon=":material/play_arrow:",
                     type="primary", disabled=executable is None):
            previous = st.session_state.pop("preview_process", None)
            if previous:
                previous.stop()
            try:
                with st.spinner(localized(language, "正在启动仿真…", "Starting simulation…")):
                    st.session_state.preview_process = start_preview(AssetStore(), version, executable)
                status = st.session_state.preview_process.status()
            except Exception as exc:  # noqa: BLE001
                AssetStore().set_compatibility(version, "failed", str(exc))
                st.error(localized(language, "预览未能启动。请检查工具设置或场景依赖。", "Preview could not start. Check tool settings or scenario dependencies."))
                with st.expander(localized(language, "预览失败详情", "Preview failure details")):
                    st.code(str(exc), language=None)
    with stop_col:
        if st.button(tx(language, "stop_preview"), width="stretch", key="stop_esmini_preview", icon=":material/stop:", disabled=not active):
            previous = st.session_state.pop("preview_process", None)
            if previous:
                previous.stop()
    preview = st.session_state.get("preview_process")
    if preview and (preview.asset_id, preview.version_id) == (version.asset_id, version.version_id):
        _preview_live(preview, version, language, status)


@st.fragment(run_every="1s")
def _import_progress(language: str) -> None:
    import time
    from openx_workbench.import_jobs import current_job, status, start_import
    from openx_workbench.classification import read_classification
    from openx_workbench.asset_management import label
    store = AssetStore()
    state = status(store)
    versions = store.versions()
    pending = [v for v in versions if read_classification(store, v).get("status") not in {"classified", "manual_confirmed"}]
    if not state and not pending:
        return
    active = bool(state and state["status"] == "running")
    retry_available = bool(state and st.session_state.get("asset_import_retry_files") and
                           st.session_state.get("asset_import_retry_job") == state["id"])
    if state:
        signature = (state["id"], state["saved"], state["status"])
        if st.session_state.get("import_snapshot") != signature:
            st.session_state.import_snapshot = signature
            catalog, mapping = store.catalog()
            st.session_state.update(catalog=catalog, asset_versions=mapping,
                                    retrieval_results=[], text_results=[], result_index=0)
            st.rerun()
    with st.container(key="asset_job_strip"):
        summary, actions = st.columns([4, 1.4], vertical_alignment="top")
        with summary:
            if state:
                names = {"queued": label(language, "准备导入", "Preparing import"),
                         "expanding": label(language, "展开场景文件", "Expanding archive"),
                         "parsing": label(language, "解析场景与道路", "Parsing scenarios and roads"),
                         "saving": label(language, "保存资产", "Saving assets"),
                         "classifying": label(language, "复核分类", "Reviewing classification")}
                stage = names.get(state["stage"], state["stage"])
                states = {"completed": label(language, "导入完成", "Import completed"),
                          "stopped": label(language, "任务已停止", "Import stopped"),
                          "interrupted": label(language, "任务已中断", "Import interrupted"),
                          "failed": label(language, "任务失败", "Import failed")}
                title = stage if active else states.get(state["status"], state["status"])
                reports = state.get("reports", [])
                total_cases = sum(report["case_count"] for report in reports)
                paired_cases = sum(report["imported_count"] for report in reports)
                skipped = max(0, total_cases - paired_cases)
                missing = sum(len(report["missing_road_references"]) for report in reports)
                warning_count = int(state.get("failed", 0)) + skipped
                summary_text = label(language, f"已保存 / 复用 {state['saved']} 个场景", f"{state['saved']} scenarios saved / reused")
                if total_cases:
                    summary_text += label(language, f" · 来源 {total_cases} 个场景 · 跳过 {skipped}", f" · {total_cases} source cases · {skipped} skipped")
                if state["stage"] == "classifying" and state["total"]:
                    summary_text += label(language, f" · 分类 {state['done']}/{state['total']}", f" · Classification {state['done']}/{state['total']}")
                if warning_count or state.get("error"):
                    summary_text += label(language, f" · {warning_count or 1} 项警告", f" · {warning_count or 1} warning(s)")
                if active:
                    elapsed = max(0, int(time.time() - state["started"]))
                    summary_text += label(language, f" · 已运行 {elapsed} 秒", f" · {elapsed}s elapsed")
                st.markdown(f"**{title}**")
                st.caption(summary_text)
                if active and state["current"]:
                    st.caption(state["current"])
                if not active and state["status"] == "completed" and not (skipped or missing or state.get("failed") or state.get("error")):
                    st.caption(label(language, "可配对资产已入库，可立即使用。", "Pairable assets are saved and ready to use."))
            elif pending:
                st.caption(label(language, f"{len(pending)} 个版本待模型复核", f"{len(pending)} versions await model review"))
        with actions:
            job = current_job(store)
            if active and job:
                if job.cancel.is_set():
                    st.caption(label(language, "正在停止，已保存资产会保留。", "Stopping; saved assets retained."))
                elif st.button(label(language, "停止任务", "Stop task"), icon=":material/stop:", key="stop_asset_import"):
                    job.cancel.set()
                    st.rerun(scope="fragment")
            elif state and state["status"] in {"failed", "stopped", "interrupted"} and retry_available:
                if st.button(label(language, "重试导入", "Retry import"), icon=":material/refresh:", key="retry_asset_import"):
                    retry_job = start_import(store, st.session_state.asset_import_retry_files,
                                             classify=st.session_state.get("asset_import_retry_classify", False))
                    st.session_state.asset_import_retry_job = retry_job.snapshot()["id"]
                    st.rerun()
            if pending:
                if st.button(label(language, "继续模型分类", "Resume model classification"),
                             disabled=active, icon=":material/category:", key="resume_asset_classification",
                             help=label(language, "发送待复核资产的结构与描述到设置中的模型。", "Send pending asset structure and descriptions to the model in Settings.")):
                    start_import(store, [], classify=True, versions=pending)
                    st.rerun()
        if state:
            detail_label = label(language, "任务详情", "Job details")
            if warning_count or state.get("error"):
                detail_label += label(language, f" · {warning_count or 1} 项需处理", f" · {warning_count or 1} issue(s)")
            with st.expander(detail_label, expanded=False):
                if skipped or missing:
                    st.warning(label(language, f"部分场景未入库：跳过 {skipped} 个场景，{missing} 条道路引用缺失。",
                                     f"Partial import: {skipped} cases skipped; {missing} missing road references."))
                elif state.get("failed") or state.get("error"):
                    st.warning(label(language, "任务包含错误，已保存的资产仍可使用。", "The job has errors; saved assets remain available."))
                elapsed = max(0, int(state.get("finished", time.time()) - state["started"]))
                st.caption(label(language, f"耗时 {elapsed} 秒 · 分类失败 {state['failed']}", f"{elapsed}s elapsed · {state['failed']} classification failures"))
                if state["total"]:
                    st.progress(min(state["done"] / state["total"], 1.0), text=f"{stage}: {state['done']} / {state['total']}")
                if active:
                    st.text(state["current"] or stage)
                for report in state.get("reports", []):
                    st.caption(label(language, f"{report['source_name']}: {report['imported_count']}/{report['case_count']} 个场景可配对",
                                     f"{report['source_name']}: {report['imported_count']}/{report['case_count']} pairable cases"))
                    if report["missing_road_references"]:
                        st.warning(label(language, "补充以下 XODR 文件后重新导入。", "Add these XODR files and reimport."))
                        st.text("\n".join(report["missing_road_references"]))
                if state["error"]:
                    st.error(state["error"])
                if state["status"] in {"interrupted", "stopped", "failed"} and not retry_available:
                    st.caption(label(language, "重新打开导入资产并选择原文件可重试；重复内容不会产生新版本。", "Open Import assets and reselect the original files to retry; identical content does not create a new version."))
            if active and int(time.time() - state["updated"]) >= 20:
                waiting = int(time.time() - state["updated"])
                st.warning(label(language, f"当前步骤已等待 {waiting} 秒。模型请求连接/读取超时上限为 90 秒；停止将在当前步骤结束后生效。",
                                 f"Current step waiting {waiting}s. Model connection/read timeout: 90s. Stop takes effect after the current step."))


def _library_controls(language: str, *, expanded: bool, show_progress: bool = True) -> None:
    from openx_workbench.import_jobs import start_import, status
    from openx_workbench.asset_management import label
    store = AssetStore()
    state = status(store)
    busy = bool(state and state["status"] == "running")
    with st.expander(label(language, "导入资产", "Import assets"), expanded=expanded):
        source = st.radio(tx(language, "source"), ["upload", "demo"], format_func=lambda value: tx(language, value),
                          horizontal=True, key="asset_source", disabled=busy)
        if source == "demo":
            st.caption(label(language, "点击后会下载公开的 esmini 示例。", "Downloads a public esmini example when selected."))
            if st.button(tx(language, "load_demo"), disabled=busy, icon=":material/download:"):
                try:
                    files = _demo_files()
                    st.session_state.asset_import_retry_files = files
                    st.session_state.asset_import_retry_classify = False
                    job = start_import(store, files)
                    st.session_state.asset_import_retry_job = job.snapshot()["id"]
                    st.session_state.asset_import_open = False
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        else:
            uploads = st.file_uploader(tx(language, "files"), type=["sim", "xosc", "xodr", "zip"],
                                       accept_multiple_files=True, key="assets", disabled=busy,
                                       help=label(language, "ZIP 可包含 XOSC、XODR、目录、模型及纹理，并保留相对路径。", "ZIP packages may include XOSC, XODR, catalogs, models and textures with relative paths."))
            classify = st.checkbox(label(language, "入库时用模型复核分类", "Review classification with model on import"),
                                   value=False, key="classify_import", disabled=busy,
                                   help=label(language, "启用后会将场景结构与描述发送给已配置的模型；分类失败仍保留资产。", "Sends scenario structure and descriptions to the configured model; assets are retained if classification fails."))
            if st.button(label(language, "开始导入", "Start import"), type="primary", icon=":material/upload:",
                         key="start_asset_import", disabled=busy or not uploads):
                try:
                    files = [AssetFile(item.name, item.getvalue()) for item in uploads]
                    st.session_state.asset_import_retry_files = files
                    st.session_state.asset_import_retry_classify = classify
                    job = start_import(store, files, classify=classify)
                    st.session_state.asset_import_retry_job = job.snapshot()["id"]
                    st.session_state.asset_import_open = False
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        if busy:
            st.caption(label(language, "导入任务正在后台运行，结束后可再次导入。", "An import is running in the background. You can import again when it finishes."))
    if show_progress:
        _import_progress(language)


def _asset_panel(language: str, package: ScenePackage | None) -> None:
    catalog: list[OpenXAsset] = st.session_state.get("catalog", [])
    st.subheader(localized(language, "比较候选资产", "Compare candidates"))
    search_row = st.columns([4.5, 1.15, .9])
    with search_row[0]:
        query_text = st.text_input(tx(language, "query"), placeholder=tx(language, "query_hint"), label_visibility="collapsed")
    with search_row[1]:
        search_clicked = st.button(tx(language, "search"), type="primary", use_container_width=True,
                                   key="pdf_search_button", icon=":material/search:", disabled=not catalog or (package is None and not query_text.strip()))
    with search_row[2]:
        if st.button(localized(language, "清空结果", "Clear results"), use_container_width=True):
            st.session_state.retrieval_results = []
            st.rerun()
    encoder_name = st.session_state.get("retrieval_encoder", "bge")
    st.caption(localized(language, f"在 {len(catalog)} 个资产中匹配 · ", f"Search {len(catalog)} assets · ") + tx(language, encoder_name))
    if not catalog:
        _library_controls(language, expanded=True)
    sim_reports: list[SimImportReport] = st.session_state.get("sim_reports", [])
    catalog = st.session_state.get("catalog", [])
    if not catalog:
        st.caption(f'{tx(language, "library_empty")} · XOSC → LogicFile → XODR')
    for report in sim_reports:
        missing = ", ".join(report.missing_road_references) or tx(language, "none")
        st.caption(
            f'{report.source_name} · {tx(language, "sim_cases")} '
            f'{report.imported_count}/{report.case_count} · '
            f'{tx(language, "missing_roads")}: {missing}'
        )
    auto_search = st.session_state.pop("pdf_auto_search", False)
    if search_clicked or auto_search:
        try:
            query = scene_package_to_query(package) if package else None
            if query and query_text.strip():
                query = replace(query, text=f"{query.text} {query_text.strip()}")
            with st.spinner(localized(language, "正在检索并核对候选结构…", "Retrieving and checking candidate structures…")):
                results = _index_for(catalog, encoder_name).search(query.text if query else query_text.strip(), query=query, top_k=min(8, len(catalog)))
            st.session_state.update(retrieval_results=results, result_index=0, selected_candidate_index=0)
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
    results: list[RetrievalResult] = st.session_state.get("retrieval_results", [])
    st.markdown(
        f'<div class="ow-candidate-head"><strong>{safe(tx(language,"candidates"))}</strong><span>{safe(localized(language, f"{len(results)} 个结果 · 按结构重新排序", f"{len(results)} results · structural ranking"))}</span></div>',
        unsafe_allow_html=True,
    )
    if not results:
        st.info(localized(language, "选好需求后点击检索，候选、预览和评估会显示在这里。", "Select a requirement and search to see candidates, previews and assessment."))
        if catalog:
            _library_controls(language, expanded=False, show_progress=False)
        return
    st.caption(localized(language, "相似度越高越相似；修改成本是相对分值，不代表工时。复用结论请查看“复用评估”。", "Higher similarity means closer matches. Change cost is a relative score, not working hours. See Reuse assessment for the conclusion."))
    if "result_index" not in st.session_state:
        st.session_state.result_index = min(st.session_state.get("selected_candidate_index", 0), len(results) - 1)
    choices, preview = st.columns([1.2, 1], gap="large")
    with choices:
        index = min(st.session_state.get("result_index", 0), len(results) - 1)
        signature = hashlib.sha256(repr([(r.asset.asset_id, r.score, r.confirmation_level) for r in results]).encode()).hexdigest()[:12]
        table_key = f"candidate_rows_{signature}_{index}"
        selection = st.dataframe(_rows(results, language), hide_index=True, height=300, width="stretch",
                                 key=table_key, on_select="rerun", selection_mode="single-row",
                                 selection_default={"selection": {"rows": [index]}},
                                 column_config={"#": st.column_config.NumberColumn(width=35),
                                                tx(language, "scenario"): st.column_config.TextColumn(width=185),
                                                tx(language, "decision"): st.column_config.TextColumn(width=130),
                                                tx(language, "score"): st.column_config.NumberColumn(width=65),
                                                tx(language, "cost"): st.column_config.NumberColumn(width=65)})
        selected_rows = selection.selection.rows
        if selected_rows and selected_rows[0] != index:
            st.session_state.result_index = selected_rows[0]
            st.session_state.selected_candidate_index = selected_rows[0]
            st.rerun()
        index = st.selectbox(tx(language, "candidate"), range(len(results)),
                             format_func=lambda i: f"{i+1}. {asset_display_title(results[i].asset, language)}",
                             key="result_index")
        st.markdown('<div class="ow-section-rule"></div>', unsafe_allow_html=True)
        st.session_state.selected_candidate_index = index
    with preview:
        _asset_summary(results[index].asset, language)
        version = st.session_state.get("asset_versions", {}).get(results[index].asset.asset_id)
        if version:
            _preview_controls(version, language)
    _library_controls(language, expanded=False, show_progress=False)


def _trace(result: RetrievalResult, package: ScenePackage | None) -> dict[str, Any]:
    version = st.session_state.get("asset_versions", {}).get(result.asset.asset_id)
    stored_scene: StoredScene | None = st.session_state.get("selected_stored_scene")
    identity = {}
    if package and stored_scene and stored_scene.package is package:
        identity = {"document_id": stored_scene.document.document_id,
                    "pdf_sha256": stored_scene.document.sha256,
                    "scene_id": stored_scene.scene_id, "revision": stored_scene.revision}
    return build_trace(result, package, version, identity)


def _decision_panel(language: str, package: ScenePackage | None) -> None:
    results: list[RetrievalResult] = st.session_state.get("retrieval_results", [])
    st.subheader(localized(language, "复用评估", "Reuse assessment"))
    if not results:
        st.caption(localized(language, "检索候选后，这里会显示复用结论、差异和保存操作。", "Search for candidates to see the reuse assessment, differences and save actions."))
        return
    result = results[min(st.session_state.get("result_index", 0), len(results)-1)]
    blocking = [item for item in result.differences if item.blocking]
    edits = [item for item in result.differences if not item.blocking]
    st.markdown(
        f'<div class="ow-decision {result.confirmation_level}"><div class="ow-verdict-kicker">{safe(tx(language,"decision"))}</div><div class="ow-decision-line"><h3>{safe(_verdict_label(language, result.confirmation_level, result.confirmation_review_kind))}</h3><span class="ow-score">{safe(tx(language,"match_score"))} {result.score:.2f}</span></div><p>{safe(asset_display_title(result.asset, language))}</p></div>',
        unsafe_allow_html=True,
    )
    with st.expander(localized(language, "文件与追溯记录", "Files and provenance")):
        source_title = package.title if package else ("文本检索" if language == "zh" else "Text search")
        st.markdown(
            f'<div class="ow-section"><div class="ow-section-title"><span style="display:flex;align-items:center;gap:6px;color:#24384a">{icon("shield",14)} {safe(tx(language,"selected_item"))}</span><span>{safe(result.asset.asset_id)}</span></div><div class="ow-trace"><span>{safe(tx(language,"scenario_file"))}</span><span>{safe(result.asset.xosc_name)}</span></div><div class="ow-trace"><span>{safe(tx(language,"road_file"))}</span><span>{safe(result.asset.xodr_name)}</span></div><div class="ow-trace"><span>{safe(tx(language,"source_label"))}</span><span>{safe(source_title)}</span></div><div class="ow-trace"><span>{safe(tx(language,"change_cost"))}</span><span>{"—" if result.estimated_change_cost is None else f"{result.estimated_change_cost:g}"}</span></div></div>',
            unsafe_allow_html=True,
        )
        version = st.session_state.get("asset_versions", {}).get(result.asset.asset_id)
        if version and st.button("查看源文件" if language == "zh" else "View source files", key="view_source_files", icon=":material/code:"):
            source_files(version, language)
        from openx_workbench.validation_ui import validation_details
        validation_details(result.asset.bundle, language)
    if result.confirmation_level == "review":
        st.warning(_review_detail(language, result.confirmation_review_kind))
        if package and result.confirmation_review_kind != "standards":
            if st.button(localized(language, "返回核对需求事实", "Review requirement facts"), key="review_requirement"):
                st.session_state.requirement_edit_open = True
                st.session_state.pdf_next_stage = "review"
                st.rerun()
        for difference in result.differences:
            if not difference.verified:
                st.warning(difference_text(difference, language))
    else:
        blocking_body = (
            f'<ul class="ow-list">{"".join(f"<li>{safe(difference_text(d, language))}</li>" for d in blocking)}</ul>'
            if blocking else f'<span class="ow-status good">{safe(tx(language,"none"))}</span>'
        )
        st.markdown(f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"blocking"))} <span>{len(blocking)}</span></div>{blocking_body}</div>', unsafe_allow_html=True)
    with st.expander(localized(language, "查看匹配依据", "Matching evidence")):
        st.markdown(f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"matched"))}<span>{len(result.reasons)}</span></div>{_chips([display(reason, language) for reason in result.reasons])}</div>', unsafe_allow_html=True)
    if result.confirmation_level != "review":
        edits_body = (
            f'<ul class="ow-list">{"".join(f"<li>{safe(difference_text(d, language))}</li>" for d in edits)}</ul>'
            if edits else f'<span class="ow-status good">{safe(tx(language,"none"))}</span>'
        )
        st.markdown(f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"edits"))}<span>{len(edits)}</span></div>{edits_body}</div>', unsafe_allow_html=True)
    payload = _trace(result, package)
    if package:
        version = st.session_state.get("asset_versions", {}).get(result.asset.asset_id)
        explanation_key = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                                     sort_keys=True).encode("utf-8")).hexdigest()
        with st.expander(localized(language, "证据解释", "Evidence explanation"), expanded=False):
            baseline = deterministic_explanation(package, result, version)
            for item in baseline.evidence:
                st.caption(f"[{item.evidence_id}] {item.location}")
            with st.expander("查看发送内容" if language == "zh" else "Review evidence payload"):
                st.json([asdict(item) for item in baseline.evidence])
            if baseline.insufficient_evidence:
                for reason in baseline.insufficient_evidence:
                    st.warning(reason)
            structural_col, model_col = st.columns(2)
            with structural_col:
                if st.button("结构依据" if language == "zh" else "Explain from structure",
                             key="explain_structural", disabled=bool(baseline.insufficient_evidence)):
                    st.session_state.grounded_explanation = (explanation_key, baseline)
            with model_col:
                from openx_workbench.llm_service import load_config
                configured = bool(load_config().api_key)
                if st.button("发送证据并生成解释" if language == "zh" else "Send evidence to model",
                             key="explain_model", disabled=not configured or bool(baseline.insufficient_evidence),
                             help=localized(language, "将引用的 PDF 原文和资产事实发送到已配置的模型服务。", "Sends the cited PDF excerpt and asset facts to the configured model service.")):
                    try:
                        st.session_state.grounded_explanation = (
                            explanation_key, model_explanation(package, result, version, language=language))
                    except Exception as exc:  # noqa: BLE001
                        st.error(str(exc))
            saved = st.session_state.get("grounded_explanation")
            if saved and saved[0] == explanation_key:
                explanation = saved[1]
                st.caption(("结构评估结论：" if language == "zh" else "Structural assessment: ") + _verdict_label(language, explanation.verdict))
                for observation in explanation.observations:
                    st.write(f"{observation.text}  [{', '.join(observation.citations)}]")
                payload["explanation"] = asdict(explanation)
    action_left, action_middle = st.columns(2)
    with action_left:
        st.download_button("Assessment data (JSON)" if language == "en" else "评估数据（JSON）",
                           json.dumps(payload, ensure_ascii=False, indent=2),
                           "openx-trace-package.json", "application/json", use_container_width=True)
    with action_middle:
        st.download_button("Assessment report (HTML)" if language == "en" else "评估报告（HTML）",
                           render_report(payload, language=language), "openx-reuse-report.html", "text/html",
                           use_container_width=True)
    with st.container():
        project_id = st.session_state.get("active_project_id")
        version = st.session_state.get("asset_versions", {}).get(result.asset.asset_id)
        if st.button("Save decision" if language == "en" else "保存复用决策",
                     use_container_width=True, key="save_reuse_decision", icon=":material/bookmark_add:",
                     disabled=not project_id or version is None or package is None or result.confirmation_level == "review",
                     help=(localized(language, "请先创建或选择项目。", "Create or select a project first.") if not project_id else
                           localized(language, "需完成事实与文件标准复核后才能保存为复用决策；当前可下载评估快照。", "Complete fact and file-standard review before saving a reuse decision. You can download the current assessment snapshot."))) :
            try:
                ProjectStore().save_decision(project_id, version, payload)
                st.success("Decision saved to this project and pinned to the selected asset version."
                           if language == "en" else "决策已保存到项目，并绑定当前资产版本。")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    with st.expander(tx(language, "details")):
        st.json(payload)


def _continue_review(source, language, key):
    project = st.session_state.get("active_project_id")
    document = source.get("document_id")
    scene = source.get("scene_id")
    exists = document and scene and any(item.scene_id == scene for item in PdfStore().scenes(project, document))
    if st.button(localized(language, "打开需求继续复核", "Continue reviewing requirement"), key=key, disabled=not exists):
        st.session_state.update(active_page="pdf_workflow", document_to_select=document,
                                scene_to_select=(project, document, scene), retrieval_results=[],
                                pdf_scene_search="", requirement_edit_open=True, pdf_stage="review")
        st.rerun()
    if exists:
        st.caption(localized(language, "将打开最新事实修订；本报告仍保留保存时的快照。", "Opens the latest fact revision. This report retains its saved snapshot."))


def _saved_decisions(language: str) -> None:
    project_id = st.session_state.get("active_project_id")
    if not project_id:
        return
    reports = ProjectStore().reports(project_id)
    heading = "项目决策记录" if language == "zh" else "Saved project decisions"
    with st.expander(f"{heading} · {len(reports)}", expanded=bool(reports)):
        if not reports:
            st.caption("在 PDF 工作区保存复用决策后，可在这里重新查看和下载。" if language == "zh"
                       else "Save a reuse decision in the PDF workspace to reopen and download it here.")
            return
        by_id = {item["report_id"]: item for item in reports}
        selected = st.selectbox(
            "已保存决策" if language == "zh" else "Saved decision", list(by_id),
            format_func=lambda value: (
                f"{by_id[value]['saved_at'][:19].replace('T', ' ')} UTC · "
                f"{(by_id[value]['trace'].get('source') or {}).get('title', value[:8])}"
            ), key=f"saved_report_{project_id}",
        )
        report = by_id[selected]
        trace = checked_trace(report["trace"])
        if trace.get("kind") == "batch_match":
            _batch_summary(trace, language)
            entries = trace.get("entries", [])
            if entries:
                target = st.selectbox(localized(language, "选择需要继续复核的场景", "Choose a scene to review"), range(len(entries)),
                                      format_func=lambda i: entries[i]["source"].get("title", str(i)), key="batch_review_scene")
                _continue_review(entries[target]["source"], language, "continue_batch_review")
            st.caption("保存时的快照，含待复核和无法判断项。" if language == "zh" else
                       "Saved assessment snapshot, including review and undecidable cases.")
            st.download_button("下载已保存 JSON" if language == "zh" else "Download saved JSON",
                               json.dumps(trace, ensure_ascii=False, indent=2), f"openx-batch-{selected}.json", "application/json")
            st.download_button("下载已保存 HTML" if language == "zh" else "Download saved HTML",
                               render_report(trace, language=language), f"openx-batch-{selected}.html", "text/html")
            return
        source = trace.get("source") or {}
        candidate = trace.get("candidate") or {}
        st.write(_verdict_label(language, trace["reuse"]["level"], trace["reuse"].get("review_kind", "")))
        st.caption(("保存时的快照；后续事实修订和资产更新不会改变这份报告。" if language == "zh"
                    else "Saved snapshot. Later fact revisions and asset updates do not change this report."))
        st.write(f"{source.get('title', '')} · " + localized(language, "修订", "Revision") + f" {source.get('revision', '—')}")
        _continue_review(source, language, "continue_saved_review")
        st.caption(f"{candidate.get('xosc', '')} + {candidate.get('xodr', '')} · "
                   f"v{candidate.get('version_number', '—')} · {report['version_id']}")
        for evidence in source.get("evidence", []):
            st.caption(f"{evidence.get('source_pdf', '')} · {evidence.get('section_id', '')} · "
                       f"{tx(language, 'pages')} {evidence.get('page_start', '—')}–{evidence.get('page_end', '—')}")
        json_col, html_col = st.columns(2)
        with json_col:
            st.download_button("下载已保存 JSON" if language == "zh" else "Download saved JSON",
                               json.dumps(trace, ensure_ascii=False, indent=2),
                               f"openx-decision-{selected}.json", "application/json",
                               key="saved_decision_json", use_container_width=True)
        with html_col:
            st.download_button("下载已保存 HTML" if language == "zh" else "Download saved HTML",
                               render_report(trace, language=language), f"openx-decision-{selected}.html", "text/html",
                               key="saved_decision_html", use_container_width=True)
        with st.expander("查看完整记录" if language == "zh" else "View full saved record"):
            st.json(report)


def _home_page(language: str) -> None:
    store = AssetStore()
    versions = store.versions()
    latest = store.latest()
    st.subheader(tx(language, "home"))
    _saved_decisions(language)
    counts = {
        "playable": sum(item.compatibility == "playable" for item in latest),
        "unavailable": sum(item.compatibility in {"unsupported", "failed", "timeout"} for item in latest),
        "untested": sum(item.compatibility == "not_tested" for item in latest),
    }
    cols = st.columns(4)
    for col, label, value in zip(cols, (("资产", "版本", "可播放", "未检测") if language == "zh" else ("Assets", "Versions", "Playable", "Not tested")),
                                 (len(latest), len(versions), counts["playable"], counts["untested"])):
        col.metric(label, value)
    if not latest:
        st.info(tx(language, "no_assets"))
        st.caption("Recent imports: none" if language == "en" else "最近导入：暂无")
        return
    tested = len(latest) - counts["untested"]
    st.caption("Preview test coverage" if language == "en" else "预览检测覆盖率")
    st.progress(tested / len(latest), text=f"已检测 {tested}/{len(latest)} 个资产" if language == "zh" else f"{tested}/{len(latest)} assets tested")
    if tested:
        st.caption("Playable among tested assets" if language == "en" else "已检测资产的可播放比例")
        st.progress(counts["playable"] / tested, text=f"{counts['playable']}/{tested} 可播放" if language == "zh" else f"{counts['playable']}/{tested} playable")
    st.caption(f"预览失败 {counts['unavailable']} 个 · 状态仅代表已检测的版本。" if language == "zh" else f"Preview failures: {counts['unavailable']} · Status reflects tested versions only.")
    st.subheader("Recent imports" if language == "en" else "最近导入")
    recent = sorted(versions, key=lambda item: item.created_at, reverse=True)[:8]
    from openx_workbench.asset_management import value_label
    headings = ("资产", "来源", "版本", "预览状态", "导入时间") if language == "zh" else (
        "Asset", "Source", "Version", "Preview", "Imported")
    st.dataframe([dict(zip(headings, (item.title, item.source_name, item.version_number,
                                     value_label(item.compatibility, language), item.created_at[:19]))) for item in recent],
                 use_container_width=True, hide_index=True)


def _text_search_page(language: str) -> None:
    st.subheader(tx(language, "text_search"))
    catalog: list[OpenXAsset] = st.session_state.get("catalog", [])
    if not catalog:
        st.info(tx(language, "no_assets"))
        return
    query = st.text_input("Search scenario assets" if language == "en" else "描述要查找的场景",
                          key="text_search_query")
    encoder = _encoder_control(language)
    if st.button(tx(language, "search"), type="primary", disabled=not query.strip(), key="text_search_button", icon=":material/search:"):
        try:
            st.session_state.text_results = _index_for(catalog, encoder).search(
                query.strip(), top_k=min(12, len(catalog)))
            st.session_state.text_search_signature = (query.strip(), encoder)
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
    results: list[RetrievalResult] = (st.session_state.get("text_results", [])
                                      if st.session_state.get("text_search_signature") == (query.strip(), encoder)
                                      else [])
    if not results:
        st.caption(tx(language, "no_results"))
        return
    st.caption("Similar assets only · no reuse decision" if language == "en" else "仅展示相似资产；不作复用结论")
    labels = [f"{i + 1}. {item.asset.title} · {item.score:.2f} · {item.asset.xosc_name}"
              for i, item in enumerate(results)]
    selected = st.selectbox(tx(language, "candidate"), range(len(results)),
                            format_func=lambda i: labels[i], key="text_result_index")
    asset = results[selected].asset
    _asset_summary(asset, language)
    version = st.session_state.get("asset_versions", {}).get(asset.asset_id)
    if version:
        _preview_controls(version, language)


def _management_page(language: str) -> None:
    from openx_workbench.asset_management import render
    render(language, import_controls=_library_controls, import_progress=_import_progress,
           preview_controls=_preview_controls, road_schematic=_road_schematic, source_files=source_files)


def main() -> None:
    initialize()
    if "catalog" not in st.session_state:
        catalog, versions = AssetStore().catalog()
        st.session_state.update(catalog=catalog, asset_versions=versions, asset_files=[], sim_reports=[])
    _theme()
    st.markdown("<style>" + theme_colors(Path(__file__).with_name("shell.css").read_text(encoding="utf-8")) + appearance_css(st.session_state.appearance) + "</style>", unsafe_allow_html=True)
    projects = ProjectStore()
    if "active_project_id" not in st.session_state:
        last = projects.last()
        st.session_state.active_project_id = last.project_id if last else None
    pending_project = st.session_state.pop("project_to_select", None)
    if pending_project:
        st.session_state.active_project_id = pending_project
    page = sidebar(tx)
    if st.session_state.get("pdf_active_project") != st.session_state.get("active_project_id"):
        st.session_state.pdf_active_project = st.session_state.get("active_project_id")
        st.session_state.selected_scene_key = None
        st.session_state.selected_stored_scene = None
        st.session_state.retrieval_results = []
    pending_document = st.session_state.pop("document_to_select", None)
    if pending_document:
        st.session_state.current_document_id = pending_document
        st.session_state.pdf_view_mode = "by_pdf"
        st.session_state.pdf_function_filter = "全部 / All"
    pending_scene = st.session_state.pop("scene_to_select", None)
    if pending_scene:
        st.session_state.selected_scene_key = pending_scene
        st.session_state.scene_picker_target = pending_scene
        st.session_state.pdf_stage = "review"
    next_stage = st.session_state.pop("pdf_next_stage", None)
    if next_stage:
        st.session_state.pdf_stage = next_stage
    language = _header(show_steps=False)
    native_locale(language)
    if page == "home":
        _home_page(language)
    elif page == "text_search":
        _text_search_page(language)
    elif page == "asset_management":
        _management_page(language)
    else:
        with st.container(key="pdf_workspace"):
            library, work = st.columns([.9, 2.4], gap="large")
            with library:
                with st.container(key="pdf_library"):
                    selected = _pdf_scene_library(language)
            with work:
                with st.container(key="pdf_current"):
                    if selected is None:
                        st.subheader(localized(language, "从一条需求开始", "Start with a requirement"))
                        st.write(localized(language, "在左侧选择 PDF 和场景，再核对事实、比较资产并保存评估。", "Choose a PDF and scene on the left, then review facts, compare assets and save the assessment."))
                        return
                    package = selected.package
                    evidence = package.evidence[0] if package.evidence else None
                    st.subheader(package.title)
                    pages = f" · {tx(language, 'pages')} {evidence.page_start}–{evidence.page_end}" if evidence else ""
                    st.caption(f"{selected.document.filename}{pages} · " + localized(language, f"修订 {selected.revision}", f"Revision {selected.revision}"))
                    if "pdf_stage" not in st.session_state:
                        st.session_state.pdf_next_stage = "review"
                    stages = {"review": localized(language, "核对需求", "Review requirement"),
                              "compare": localized(language, "候选与预览", "Candidates and preview"),
                              "assess": localized(language, "复用评估", "Reuse assessment")}
                    stage = st.radio(localized(language, "当前任务", "Current task"), list(stages),
                                     format_func=stages.get, key="pdf_stage", horizontal=True,
                                     label_visibility="collapsed")
                    if stage == "review":
                        with st.container(key="evidence_panel"):
                            _requirement_details(selected, language)
                        actions, context = st.columns([1, 2])
                        with actions:
                            if st.button(localized(language, "检索并比较资产", "Search and compare assets"),
                                         key="pdf_search_button", type="primary", icon=":material/search:",
                                         disabled=not st.session_state.get("catalog")):
                                st.session_state.pdf_next_stage = "compare"
                                st.session_state.pdf_auto_search = True
                                st.rerun()
                        with context:
                            st.caption(localized(language, f"资产库已就绪 · {len(st.session_state.get('catalog', []))} 个资产", f"Library ready · {len(st.session_state.get('catalog', []))} assets"))
                    elif stage == "compare":
                        with st.container(key="asset_panel"):
                            _asset_panel(language, package)
                        if st.session_state.get("retrieval_results") and st.button(localized(language, "查看复用评估", "View reuse assessment"), key="open_pdf_assessment", type="primary"):
                            st.session_state.pdf_next_stage = "assess"
                            st.rerun()
                    else:
                        results = st.session_state.get("retrieval_results", [])
                        if results:
                            if "result_index" not in st.session_state:
                                st.session_state.result_index = min(st.session_state.get("selected_candidate_index", 0), len(results)-1)
                            st.selectbox(tx(language, "candidate"), range(len(results)), key="result_index",
                                         format_func=lambda i: f"{i+1}. {asset_display_title(results[i].asset, language)}")
                            st.session_state.selected_candidate_index = st.session_state.result_index
                        with st.container(key="decision_panel"):
                            _decision_panel(language, package)



main()
