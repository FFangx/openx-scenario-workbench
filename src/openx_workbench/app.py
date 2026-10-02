from __future__ import annotations

import html
import hashlib
import json
import os
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
from openx_workbench.esmini_preview import PreviewProcess, find_esmini, start_preview
from openx_workbench.grounding import deterministic_explanation, model_explanation
from openx_workbench.pdf_store import PdfStore, StoredScene
from openx_workbench.project_store import ProjectStore
from openx_workbench.report_html import render_report
from openx_workbench.reuse_trace import build_trace, checked_trace
from openx_workbench.batch_matching import match_document, batch_signature
from openx_workbench.retrieval import OpenXIndex, RetrievalResult, build_encoder, catalog_fingerprint
from openx_workbench.scene_package import ScenePackage, scene_package_to_query
from openx_workbench.sim_archive import SimImportReport


st.set_page_config(
    page_title="OpenX Scenario Workbench",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)


TEXT = {
    "zh": {
        "subtitle": "从法规证据到可复用 OpenX 场景资产",
        "steps": ("从 PDF 提取", "检索资产库", "评估复用", "导出追踪包"),
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
        "encoder": "语义编码器", "hashing": "本地哈希（快速基线）", "bge": "BGE-M3 语义向量",
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
        "trace": "追踪关系", "download": "下载追踪包", "details": "技术详情",
    },
    "en": {
        "subtitle": "From regulatory evidence to reusable OpenX scenario assets",
        "steps": ("Extract from PDF", "Search asset library", "Assess reuse", "Export trace package"),
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
        "encoder": "Semantic encoder", "hashing": "Local hashing (fast baseline)", "bge": "BGE-M3 semantic vectors",
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
        "trace": "Traceability", "download": "Download trace package", "details": "Technical details",
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
                     "Revision": source["revision"], tx(language, "candidates"): candidates[0]["candidate"]["xosc"] if candidates else "—",
                     tx(language, "decision"): _verdict_label(language, assessment["level"], assessment.get("review_kind", "")),
                     tx(language, "cost"): assessment.get("estimated_change_cost")})
    st.dataframe(rows, hide_index=True, width="stretch",
                 column_order=[tx(language, "decision"), tx(language, "scenario"), tx(language, "pages"),
                               tx(language, "candidates"), "Revision", tx(language, "cost")],
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
                               render_report(trace), "openx-document.html", "text/html")
        if st.button("保存汇总报告" if language == "zh" else "Save summary report", key="save_batch_report"):
            try:
                ProjectStore().save_batch(document.project_id, trace)
                st.success("汇总已保存，候选资产版本已固定。" if language == "zh" else
                           "Summary saved with pinned candidate asset versions.")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))


def _project_pdf_panel(language: str) -> ScenePackage | None:
    project_id = st.session_state.get("active_project_id")
    _panel(1, tx(language, "requirements"))
    with st.expander(tx(language, "encoder"), expanded=False):
        _encoder_control(language)
    if not project_id:
        st.info("请先在左侧创建或选择项目。" if language == "zh" else "Create or select a project in the sidebar first.")
        st.session_state.selected_stored_scene = None
        return None
    store = PdfStore()
    uploads = st.file_uploader("PDF", type=["pdf"], accept_multiple_files=True,
                               key=f"project_pdfs_{project_id}")
    standard = st.text_input(tx(language, "standard"), placeholder=tx(language, "standard_hint"),
                             key="pdf_standard")
    st.caption("V2 · 模型识别与分类 → 引用校验 → 复核入库。点击导入会向设置中的模型发送 PDF 文字。" if language == "zh" else
               "V2 · Model extraction and classification → evidence checks → review and publish. Import sends PDF text to your configured model.")
    if st.button("导入 PDF" if language == "zh" else "Import PDFs",
                 disabled=not uploads, key="import_project_pdfs"):
        try:
            imported = []
            with st.status("正在提取 PDF 场景…" if language == "zh" else "Extracting PDF scenes…", expanded=True) as status:
                for item in uploads:
                    st.write(item.name)
                    imported.append(store.import_pdf(project_id, item.name, item.getvalue(), standard.strip(), progress=st.write))
                status.update(label="提取完成 / Extraction complete", state="complete")
            st.session_state.current_document_id = imported[-1].document_id
            st.session_state.selected_scene_key = None
            st.session_state.selected_stored_scene = None
            st.session_state.retrieval_results = []
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"PDF: {exc}")
    documents = store.documents(project_id)
    if not documents:
        _empty(tx(language, "no_pdf"), tx(language, "no_pdf_detail"))
        st.session_state.selected_stored_scene = None
        return None
    document_by_id = {item.document_id: item for item in documents}
    mode = st.radio("Scenes / 场景", ["by_pdf", "all"],
                    format_func=lambda item: ("按 PDF 分组" if item == "by_pdf" else "全部场景")
                    if language == "zh" else ("By PDF" if item == "by_pdf" else "All scenes"),
                    horizontal=True, key="pdf_view_mode")
    if mode == "by_pdf":
        ids = list(document_by_id)
        if st.session_state.get("current_document_id") not in ids:
            st.session_state.current_document_id = ids[0]
        selected_doc = st.selectbox("PDF", ids, key="current_document_id",
                                    format_func=lambda item: f"{document_by_id[item].filename} · {item[:8]} · {document_by_id[item].scene_count} scenes")
        scenes = store.scenes(project_id, selected_doc)
        document = document_by_id[selected_doc]
        _document_matching(document, scenes, language)
        st.caption(document.extraction_engine)
        from openx_workbench.pdf_extraction import ENGINE_VERSION
        if document.extraction_engine != ENGINE_VERSION:
            if st.button("用 V2 重新提取" if language == "zh" else "Re-extract with V2", key="reextract_pdf", icon=":material/refresh:"):
                try:
                    with st.status("正在重新提取 / Re-extracting", expanded=True):
                        updated = store.import_pdf(project_id, document.filename, store.pdf_bytes(document), document.source_standard, progress=st.write)
                    st.session_state.document_to_select = updated.document_id
                    st.session_state.selected_scene_key = None
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        audit = store.extraction_audit(document)
        if audit:
            with st.expander("解析与校验记录" if language == "zh" else "Extraction and validation"):
                st.write({"model": audit["run"]["model"], "prompt": audit["run"]["prompt_version"],
                          "status": audit["run"]["status"], "usage": audit["run"]["usage"]})
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
    st.caption(f"{len(documents)} PDF · {len(scenes)} visible scenes")
    functions = sorted({scene.package.classification.get("function", "未知") for scene in scenes})
    if functions:
        function_filter = st.selectbox("功能分类" if language == "zh" else "Function category", ["全部 / All", *functions], key="pdf_function_filter")
        if function_filter != "全部 / All":
            scenes = [scene for scene in scenes if scene.package.classification.get("function", "未知") == function_filter]
    for scene in scenes:
        evidence = scene.package.evidence[0] if scene.package.evidence else None
        pages = f"{evidence.page_start}–{evidence.page_end}" if evidence else "—"
        label = (f"{scene.package.title}\n{scene.document.filename} ({scene.document.document_id[:8]}) · {tx(language, 'pages')} {pages} · "
                 f"v{scene.revision}")
        if st.button(label, key=f"scene_{scene.document.document_id}_{scene.scene_id}",
                     use_container_width=True):
            st.session_state.selected_scene_key = (project_id, scene.document.document_id, scene.scene_id)
            st.session_state.retrieval_results = []
            st.rerun()
    selected_key = st.session_state.get("selected_scene_key")
    selected: StoredScene | None = next((item for item in scenes if selected_key ==
                                         (project_id, item.document.document_id, item.scene_id)), None)
    if selected is None and selected_key and selected_key[0] == project_id:
        st.session_state.selected_scene_key = None
        st.session_state.retrieval_results = []
        st.rerun()
    if selected is None:
        st.session_state.selected_stored_scene = None
        st.info("选择一个提取场景以进入工作区。" if language == "zh" else "Select an extracted scene to open the workbench.")
        return None
    st.session_state.selected_stored_scene = selected
    package = selected.package
    st.markdown(f"**{safe(package.title)}** · revision {selected.revision}")
    if package.classification:
        st.caption(" · ".join(str(package.classification.get(key, "")) for key in ("function", "road_type", "intent")))
    with st.expander("结构与分类" if language == "zh" else "Structure and classification"):
        st.json({"structure": package.structure, "classification": package.classification})
        for issue in package.extraction.get("validation", {}).get("issues", []):
            st.warning(issue.get("detail", issue.get("code", "")))
        for flag in package.extraction.get("structure_flags", []):
            st.warning(flag["detail"])
        if any(block.get("source") == "ocr" for block in package.extraction.get("source_blocks", [])):
            st.caption("包含本机 OCR 识别的证据，请对照原文复核。" if language == "zh" else
                       "Includes locally recognized OCR evidence; review against the source.")
    if st.button("确认当前修订并入库" if language == "zh" else "Confirm and publish revision", key="publish_pdf_scene", icon=":material/library_add:"):
        store.publish_scene(selected)
        st.success("已保存到全局需求场景库，可在资产管理中查看。" if language == "zh" else
                   "Saved to the shared requirement library in Asset management.")
    if selected.revision > 1:
        with st.expander("修订历史" if language == "zh" else "Revision history"):
            st.dataframe([{"Revision": item.revision, "Title": item.package.title,
                           "Parameters": json.dumps(item.package.parameters, ensure_ascii=False)}
                          for item in store.revisions(project_id, selected.document.document_id,
                                                      selected.scene_id)],
                         use_container_width=True, hide_index=True)
    with st.form(key=f"edit_scene_{selected.document.document_id}_{selected.scene_id}_{selected.revision}"):
        title = st.text_input("场景标题" if language == "zh" else "Scene title", value=package.title)
        preferred_text = st.text_area("提取事实 / 解释" if language == "zh" else "Extracted facts / interpretation",
                                      value=package.preferred_text, height=115)
        fields = {}
        if package.structure:
            structured_json = st.text_area("结构 JSON / Structure JSON", value=json.dumps(package.structure, ensure_ascii=False, indent=2), height=180)
        else:
            for key, label in (("entities", "参与者 / Entities"), ("actions", "动作 / Actions"),
                               ("triggers", "触发条件 / Triggers"), ("road_types", "道路 / Road types"),
                               ("weather", "天气 / Weather"), ("time_of_day", "时间 / Time of day")):
                fields[key] = st.text_input(label, value=", ".join(getattr(package, key)))
            parameters = st.text_input("参数 JSON / Parameters JSON",
                                       value=json.dumps(package.parameters, ensure_ascii=False))
        save = st.form_submit_button("保存事实修订" if language == "zh" else "Save fact revision")
    if save:
        try:
            edits = {"title": title, "preferred_text": preferred_text}
            if package.structure:
                edits.update(structure=json.loads(structured_json))
            else:
                edits.update({key: [part.strip() for part in value.split(",") if part.strip()]
                              for key, value in fields.items()})
                edits["parameters"] = json.loads(parameters)
            store.revise_scene(project_id, selected.document.document_id, selected.scene_id, edits)
            st.session_state.retrieval_results = []
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
    evidence = package.evidence[0] if package.evidence else None
    if len(package.evidence) > 1:
        evidence_index = st.selectbox("原文条款" if language == "zh" else "Source clause", range(len(package.evidence)),
                                      format_func=lambda index: f"{package.evidence[index].section_id} · {package.evidence[index].page_start}–{package.evidence[index].page_end}",
                                      key=f"evidence_{selected.document.document_id}_{selected.scene_id}")
        evidence = package.evidence[evidence_index]
    if evidence:
        st.markdown(f'<div class="ow-label">{safe(tx(language,"evidence"))} · immutable</div>', unsafe_allow_html=True)
        image_col, text_col = st.columns([1, 1.6])
        with image_col:
            try:
                st.image(_pdf_page(store.pdf_bytes(selected.document), evidence.page_start),
                         caption=f"{selected.document.filename} · {tx(language, 'pages')} {evidence.page_start}",
                         use_container_width=True)
            except Exception:
                st.caption(f"{selected.document.filename} · {tx(language, 'pages')} {evidence.page_start}–{evidence.page_end}")
        with text_col:
            st.markdown(f'<div class="ow-evidence"><strong>{safe(evidence.section_id)} · {safe(selected.document.filename)}</strong>'
                        f'<p>{safe(evidence.source_text[:1200])}</p></div>', unsafe_allow_html=True)
    return package


def _rows(results: list[RetrievalResult], language: str) -> list[dict[str, Any]]:
    return [{"#": i, tx(language,"scenario"): r.asset.xosc_name, tx(language,"road"): r.asset.xodr_name, tx(language,"score"): f"{r.score:.2f}", tx(language,"vector"): f"{r.vector_score:.2f}", "Struct.": f"{r.scenario_score:.2f}", "Road": f"{r.road_score:.2f}", tx(language,"cost"): "—" if r.estimated_change_cost is None else f"{r.estimated_change_cost:g}", tx(language,"decision"): _verdict_label(language, r.confirmation_level, r.confirmation_review_kind)} for i, r in enumerate(results, 1)]


def _candidate_table(results: list[RetrievalResult], selected: int, language: str) -> str:
    if not results:
        body = '<tr><td colspan="9" style="height:260px;text-align:center;color:#68798b">No candidates yet · build the library and run retrieval</td></tr>'
    else:
        rows = []
        for idx, result in enumerate(results):
            cost = "—" if result.estimated_change_cost is None else f"{result.estimated_change_cost:g}"
            rows.append(
                f'<tr class="{"selected" if idx == selected else ""}">'
                f'<td class="num">{idx + 1}</td><td class="num"><span class="ow-checkbox" aria-hidden="true"></span></td>'
                f'<td class="pair"><span class="ow-pair">{safe(result.asset.xosc_name)}<small>+ {safe(result.asset.xodr_name)}</small></span></td>'
                f'<td class="desc">{safe(result.asset.title or "Parsed OpenX scenario")}</td>'
                f'<td class="score">{result.vector_score:.2f}</td><td class="score">{result.scenario_score:.2f}</td>'
                f'<td class="score">{result.road_score:.2f}</td><td class="score">{safe(cost)}</td>'
                f'<td><span class="ow-match {safe(result.confirmation_level)}">{safe(_verdict_label(language, result.confirmation_level, result.confirmation_review_kind))}</span></td></tr>'
            )
        body = "".join(rows)
    return (
        '<div class="ow-table-wrap"><table class="ow-candidate-table"><thead><tr>'
        '<th class="num">#</th><th class="num"><span class="ow-checkbox"></span></th>'
        '<th class="pair">Scenario pair<br>(XOSC / XODR)</th><th class="desc">Description</th>'
        '<th>Semantic<br>similarity</th><th>Scenario<br>similarity</th><th>Road<br>similarity</th>'
        '<th>Change<br>cost</th><th>Match</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div>'
    )


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
    bundle = asset.bundle
    road = bundle.road
    esmini = find_esmini(st.session_state.get("esmini_path", "")) is not None
    geometry = ", ".join(f"{k} {v}" for k, v in road.geometry_types.items()) or "—"
    preview_state = tx(language, "preview_on" if esmini else "preview_off")
    facts = (
        f'<div class="ow-fact"><span>File</span><span>{safe(asset.xosc_name)}</span></div>'
        f'<div class="ow-fact"><span>Entities</span><span>{len(bundle.scenario.entities)}</span></div>'
        f'<div class="ow-fact"><span>Description</span><span>{safe(asset.title or "Parsed OpenX scenario")}</span></div>'
        f'<div class="ow-fact"><span>Road</span><span>{safe(asset.xodr_name)}</span></div>'
        f'<div class="ow-fact"><span>Geometry</span><span>{safe(geometry)}</span></div>'
    )
    st.markdown(
        f'<div class="ow-label">{safe(tx(language,"selected"))}</div>'
        f'<div class="ow-asset-shell"><div class="ow-asset-name">{safe(asset.xosc_name)} &nbsp;+&nbsp; {safe(asset.xodr_name)}</div>'
        '<div class="ow-asset-grid">'
        f'<div class="ow-asset-cell"><div class="ow-mini-title">Scenario (XOSC)</div>{facts}</div>'
        f'<div class="ow-asset-cell"><div class="ow-mini-title">Parsed scenario schematic</div>{_road_schematic(asset, scenario=True)}<div class="ow-fact"><span>Status</span><span>{safe(preview_state)}</span></div></div>'
        f'<div class="ow-asset-cell"><div class="ow-mini-title">Associated road</div>{_road_schematic(asset, scenario=False)}<div class="ow-fact"><span>Length</span><span>{road.total_length:g} m</span></div><div class="ow-fact"><span>Lane entries</span><span>{road.lane_count}</span></div></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


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
                'alt="Live esmini simulation" style="width:100%;height:auto;aspect-ratio:16/9;object-fit:contain;display:block;background:#17242e">',
                unsafe_allow_html=True,
            )
        st.caption(localized(language, "预览已结束，可以重新播放。", "Preview finished. You can play it again.")
                   if status["state"] == "finished" else localized(language,
                   f"正在播放 · 已生成 {status['frames']} 帧真实画面", f"Playing · {status['frames']} rendered frames"))


def _preview_controls(version: AssetVersion, language: str, *, show_identity: bool = True) -> None:
    version = next((item for item in AssetStore().versions()
                    if item.asset_id == version.asset_id and item.version_id == version.version_id), version)
    if show_identity:
        st.caption(f"Asset {version.asset_id[:10]} · version {version.version_number} ({version.version_id[:10]}) · {version.compatibility}")
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
    _panel(2, tx(language, "assets"))
    st.markdown(
        f'<div class="ow-label">{len(catalog)} {safe(tx(language,"pairs"))}</div>',
        unsafe_allow_html=True,
    )
    search_row = st.columns([4.5, 1.15, .9])
    with search_row[0]:
        query_text = st.text_input(tx(language, "query"), placeholder=tx(language, "query_hint"), label_visibility="collapsed")
    with search_row[1]:
        search_clicked = st.button(tx(language, "search"), type="primary", use_container_width=True,
                                   key="pdf_search_button", icon=":material/search:", disabled=not catalog or (package is None and not query_text.strip()))
    with search_row[2]:
        if st.button("Reset", use_container_width=True):
            st.session_state.retrieval_results = []
            st.rerun()
    encoder_name = st.session_state.get("retrieval_encoder", "bge")
    source_title = package.title if package else ("Ad-hoc text recall" if query_text.strip() else "No requirement selected")
    st.markdown(
        '<div class="ow-filter-row">'
        f'<span class="ow-filter">Scenario type <b>{safe(package.road_types[0] if package and package.road_types else "Any")}</b><i>×</i></span>'
        f'<span class="ow-filter">Requirement <b>{safe(source_title)}</b><i>×</i></span>'
        f'<span class="ow-filter">Encoder <b>{safe(encoder_name.upper())}</b><i>×</i></span>'
        '</div>',
        unsafe_allow_html=True,
    )
    if not catalog:
        _library_controls(language, expanded=True)
    sim_reports: list[SimImportReport] = st.session_state.get("sim_reports", [])
    catalog = st.session_state.get("catalog", [])
    if catalog:
        xosc = len(catalog)
        xodr = len({item.xodr_name for item in catalog})
        st.markdown(
            f'<div class="ow-library-line"><span>{len(catalog)} {safe(tx(language,"pairs"))}</span><span>{xosc} XOSC</span><span>{xodr} XODR</span><span>Recall → structural rerank</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption(f'{tx(language, "library_empty")} · XOSC → LogicFile → XODR')
    for report in sim_reports:
        missing = ", ".join(report.missing_road_references) or tx(language, "none")
        st.caption(
            f'{report.source_name} · {tx(language, "sim_cases")} '
            f'{report.imported_count}/{report.case_count} · '
            f'{tx(language, "missing_roads")}: {missing}'
        )
    if search_clicked:
        try:
            query = scene_package_to_query(package) if package else None
            if query and query_text.strip():
                query = replace(query, text=f"{query.text} {query_text.strip()}")
            results = _index_for(catalog, encoder_name).search(query.text if query else query_text.strip(), query=query, top_k=min(8, len(catalog)))
            st.session_state.update(retrieval_results=results, result_index=0)
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
    results: list[RetrievalResult] = st.session_state.get("retrieval_results", [])
    st.markdown(
        f'<div class="ow-candidate-head"><strong>{safe(tx(language,"candidates"))}</strong><span>{len(results)} results · structured reranking</span></div>',
        unsafe_allow_html=True,
    )
    if not results:
        st.markdown(_candidate_table([], 0, language), unsafe_allow_html=True)
        st.markdown('<div class="ow-section-rule"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="ow-label">{safe(tx(language,"selected"))}</div><div class="ow-asset-shell"><div class="ow-asset-name">No candidate selected</div><div class="ow-asset-grid"><div class="ow-asset-cell"><div class="ow-preview-state">{safe(tx(language,"no_results"))}</div></div><div class="ow-asset-cell"><div class="ow-preview-state">Scenario preview interface</div></div><div class="ow-asset-cell"><div class="ow-preview-state">Road preview interface</div></div></div></div>',
            unsafe_allow_html=True,
        )
        if catalog:
            _library_controls(language, expanded=False)
        return
    index = min(st.session_state.get("result_index", 0), len(results) - 1)
    st.markdown(_candidate_table(results, index, language), unsafe_allow_html=True)
    index = st.selectbox(
        tx(language, "candidate"),
        range(len(results)),
        format_func=lambda i: f'{i+1}. {results[i].asset.xosc_name} + {results[i].asset.xodr_name}',
        key="result_index",
        label_visibility="collapsed",
    )
    st.markdown('<div class="ow-section-rule"></div>', unsafe_allow_html=True)
    _asset_summary(results[index].asset, language)
    version = st.session_state.get("asset_versions", {}).get(results[index].asset.asset_id)
    if version:
        _preview_controls(version, language)
    _library_controls(language, expanded=False)


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
    _panel(3, tx(language, "reuse"))
    if not results:
        st.markdown(
            f'<div class="ow-decision review"><div class="ow-verdict-kicker"><span class="ow-check"></span>{safe(tx(language,"review"))}</div><div class="ow-decision-line"><h3>{safe(tx(language,"no_decision"))}</h3><span class="ow-score">Confidence —</span></div><p>{safe(tx(language,"no_decision_detail"))}</p></div>'
            f'<div class="ow-section"><div class="ow-section-title"><span style="display:flex;align-items:center;gap:6px;color:#24384a">{icon("shield",14)} Selected item</span><span>—</span></div><div class="ow-trace"><span>Scenario</span><span>—</span></div><div class="ow-trace"><span>Road</span><span>—</span></div><div class="ow-trace"><span>Source</span><span>—</span></div></div>'
            f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"blocking"))}<span>—</span></div><span class="ow-status">{safe(tx(language,"no_decision"))}</span></div>'
            f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"matched"))}<span>—</span></div><span class="ow-status">{safe(tx(language,"no_decision"))}</span></div>'
            f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"edits"))}<span>—</span></div><span class="ow-status">{safe(tx(language,"no_decision"))}</span></div>'
            f'<div class="ow-section"><div class="ow-section-title"><span style="display:flex;align-items:center;gap:6px;color:#24384a">{icon("link",14)} {safe(tx(language,"trace"))}</span><span>0 links</span></div><div class="ow-trace"><span>Evidence</span><span>—</span></div><div class="ow-trace"><span>XOSC</span><span>—</span></div><div class="ow-trace"><span>XODR</span><span>—</span></div></div>',
            unsafe_allow_html=True,
        )
        st.button(tx(language, "download"), disabled=True, use_container_width=True, key="disabled_trace_download")
        return
    result = results[min(st.session_state.get("result_index", 0), len(results)-1)]
    blocking = [item for item in result.differences if item.blocking]
    edits = [item for item in result.differences if not item.blocking]
    st.markdown(
        f'<div class="ow-decision {result.confirmation_level}"><div class="ow-verdict-kicker"><span class="ow-check"></span>{safe(tx(language,"decision"))}</div><div class="ow-decision-line"><h3>{safe(_verdict_label(language, result.confirmation_level, result.confirmation_review_kind))}</h3><span class="ow-score">Confidence {result.score:.2f}</span></div><p>{safe(result.asset.xosc_name)} + {safe(result.asset.xodr_name)}</p></div>',
        unsafe_allow_html=True,
    )
    source_title = package.title if package else "Ad-hoc text query"
    st.markdown(
        f'<div class="ow-section"><div class="ow-section-title"><span style="display:flex;align-items:center;gap:6px;color:#24384a">{icon("shield",14)} Selected item</span><span>{safe(result.asset.asset_id)}</span></div><div class="ow-trace"><span>Scenario</span><span>{safe(result.asset.xosc_name)}</span></div><div class="ow-trace"><span>Road</span><span>{safe(result.asset.xodr_name)}</span></div><div class="ow-trace"><span>Source</span><span>{safe(source_title)}</span></div><div class="ow-trace"><span>Change cost</span><span>{"—" if result.estimated_change_cost is None else f"{result.estimated_change_cost:g}"}</span></div></div>',
        unsafe_allow_html=True,
    )
    version = st.session_state.get("asset_versions", {}).get(result.asset.asset_id)
    if version and st.button("查看源文件" if language == "zh" else "View source files", key="view_source_files", icon=":material/code:"):
        source_files(version, language)
    from openx_workbench.validation_ui import validation_details
    validation_details(result.asset.bundle, language)
    if result.confirmation_level == "review":
        st.info(_review_detail(language, result.confirmation_review_kind))
        for difference in result.differences:
            if not difference.verified:
                st.warning(f"{difference.category}: {difference.requested} → {difference.action}")
    else:
        blocking_body = (
            f'<ul class="ow-list">{"".join(f"<li><strong>{safe(d.category)}</strong>: {safe(d.requested)} → {safe(d.action)}</li>" for d in blocking)}</ul>'
            if blocking else f'<span class="ow-status good">{safe(tx(language,"none"))}</span>'
        )
        st.markdown(f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"blocking"))} <span>{len(blocking)}</span></div>{blocking_body}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"matched"))}<span>{len(result.reasons)}</span></div>{_chips([reason.replace("_"," ") for reason in result.reasons])}</div>', unsafe_allow_html=True)
    if result.confirmation_level != "review":
        edits_body = (
            f'<ul class="ow-list">{"".join(f"<li><strong>{safe(d.category)}</strong>: {safe(d.requested)} → {safe(d.action)}</li>" for d in edits)}</ul>'
            if edits else f'<span class="ow-status good">{safe(tx(language,"none"))}</span>'
        )
        st.markdown(f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"edits"))}<span>{len(edits)}</span></div>{edits_body}</div>', unsafe_allow_html=True)
    evidence = package.evidence[0] if package and package.evidence else None
    source = f'{evidence.source_pdf} · {evidence.section_id} · {evidence.page_start}–{evidence.page_end}' if evidence else "Ad-hoc query"
    st.markdown(f'<div class="ow-section"><div class="ow-section-title"><span style="display:flex;align-items:center;gap:6px;color:#24384a">{icon("link",14)} {safe(tx(language,"trace"))}</span><span>3 links</span></div><div class="ow-trace"><span>Evidence</span><span>{safe(source)}</span></div><div class="ow-trace"><span>XOSC</span><span>{safe(result.asset.xosc_name)}</span></div><div class="ow-trace"><span>XODR</span><span>{safe(result.asset.xodr_name)}</span></div></div>', unsafe_allow_html=True)
    payload = _trace(result, package)
    if package:
        version = st.session_state.get("asset_versions", {}).get(result.asset.asset_id)
        explanation_key = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                                     sort_keys=True).encode("utf-8")).hexdigest()
        with st.expander("证据解释 / Evidence explanation", expanded=False):
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
                configured = bool(os.environ.get("OPENX_LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"))
                if st.button("发送证据并生成解释" if language == "zh" else "Send evidence to model",
                             key="explain_model", disabled=not configured or bool(baseline.insufficient_evidence),
                             help="Sends the cited PDF excerpt and parsed asset facts to the configured model service."):
                    try:
                        st.session_state.grounded_explanation = (
                            explanation_key, model_explanation(package, result, version, language=language))
                    except Exception as exc:  # noqa: BLE001
                        st.error(str(exc))
            saved = st.session_state.get("grounded_explanation")
            if saved and saved[0] == explanation_key:
                explanation = saved[1]
                st.caption(f"Fixed structural verdict: {explanation.verdict} · {explanation.method}")
                for observation in explanation.observations:
                    st.write(f"{observation.text}  [{', '.join(observation.citations)}]")
                payload["explanation"] = asdict(explanation)
    action_left, action_middle = st.columns(2)
    with action_left:
        st.download_button("Download JSON" if language == "en" else "下载 JSON",
                           json.dumps(payload, ensure_ascii=False, indent=2),
                           "openx-trace-package.json", "application/json", use_container_width=True)
    with action_middle:
        st.download_button("Download HTML" if language == "en" else "下载 HTML",
                           render_report(payload), "openx-reuse-report.html", "text/html",
                           use_container_width=True)
    with st.container():
        project_id = st.session_state.get("active_project_id")
        version = st.session_state.get("asset_versions", {}).get(result.asset.asset_id)
        if st.button("Save decision" if language == "en" else "保存复用决策",
                     use_container_width=True, key="save_reuse_decision", icon=":material/bookmark_add:",
                     disabled=not project_id or version is None or package is None or result.confirmation_level == "review",
                     help="Create or select a project in the sidebar first."):
            try:
                ProjectStore().save_decision(project_id, version, payload)
                st.success("Decision saved to this project and pinned to the selected asset version."
                           if language == "en" else "决策已保存到项目，并绑定当前资产版本。")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    with st.expander(tx(language, "details")):
        st.json(payload)


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
            st.caption("保存时的快照，含待复核和无法判断项。" if language == "zh" else
                       "Saved assessment snapshot, including review and undecidable cases.")
            st.download_button("下载已保存 JSON" if language == "zh" else "Download saved JSON",
                               json.dumps(trace, ensure_ascii=False, indent=2), f"openx-batch-{selected}.json", "application/json")
            st.download_button("下载已保存 HTML" if language == "zh" else "Download saved HTML",
                               render_report(trace), f"openx-batch-{selected}.html", "text/html")
            return
        source = trace.get("source") or {}
        candidate = trace.get("candidate") or {}
        st.write(_verdict_label(language, trace["reuse"]["level"], trace["reuse"].get("review_kind", "")))
        st.caption(("保存时的快照；后续事实修订和资产更新不会改变这份报告。" if language == "zh"
                    else "Saved snapshot. Later fact revisions and asset updates do not change this report."))
        st.write(f"{source.get('title', '')} · revision {source.get('revision', '—')}")
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
                               render_report(trace), f"openx-decision-{selected}.html", "text/html",
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
    for col, label, value in zip(cols, ("Assets", "Versions", "Preview playable", "Untested"),
                                 (len(latest), len(versions), counts["playable"], counts["untested"])):
        col.metric(label, value)
    if not latest:
        st.info(tx(language, "no_assets"))
        st.caption("Recent imports: none" if language == "en" else "最近导入：暂无")
        return
    tested = len(latest) - counts["untested"]
    st.caption("Preview test coverage" if language == "en" else "预览检测覆盖率")
    st.progress(tested / len(latest), text=f"{tested}/{len(latest)} assets tested")
    if tested:
        st.caption("Playable among tested assets" if language == "en" else "已检测资产的可播放比例")
        st.progress(counts["playable"] / tested, text=f"{counts['playable']}/{tested} playable")
    st.caption(f"Preview failures: {counts['unavailable']} · Status reflects tested versions only.")
    st.subheader("Recent imports" if language == "en" else "最近导入")
    recent = sorted(versions, key=lambda item: item.created_at, reverse=True)[:8]
    st.dataframe([{"Asset": item.title, "Source": item.source_name,
                   "Version": item.version_number, "Preview": item.compatibility,
                   "Imported": item.created_at[:19]} for item in recent],
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
    language = _header(show_steps=page == "pdf_workflow")
    if page == "home":
        _home_page(language)
    elif page == "text_search":
        _text_search_page(language)
    elif page == "asset_management":
        _management_page(language)
    elif not (st.session_state.get("selected_scene_key") and
              st.session_state["selected_scene_key"][0] == st.session_state.get("active_project_id")):
        left, center, right = st.columns([1, 2, 1])
        with center:
            with st.container(border=True, key="evidence_panel"):
                _project_pdf_panel(language)
    else:
        left, center, right = st.columns([1.08, 1.78, 1.08], gap="small")
        with left:
            with st.container(border=True, key="evidence_panel"):
                package = _project_pdf_panel(language)
        with center:
            with st.container(border=True, key="asset_panel"):
                _asset_panel(language, package)
        with right:
            with st.container(border=True, key="decision_panel"):
                _decision_panel(language, package)


main()
