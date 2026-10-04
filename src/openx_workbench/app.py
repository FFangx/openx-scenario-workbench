"""Classic Streamlit workbench entry point: page setup, theme and routing.

`launcher.py` runs this file with `streamlit run`; the pages live in `openx_workbench.ui`.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from openx_workbench.appearance import appearance_css, theme_colors
from openx_workbench.asset_store import AssetStore
from openx_workbench.native_locale import native_locale
from openx_workbench.project_store import ProjectStore
from openx_workbench.ui.common import tx
from openx_workbench.ui.management import management_page
from openx_workbench.ui.overview import home_page
from openx_workbench.ui.pdf_workflow import pdf_workflow_page
from openx_workbench.ui.text_search import text_search_page
from openx_workbench.ui_shell import initialize, workspace_navigation


st.set_page_config(
    page_title="OpenX 场景工作台",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _theme() -> None:
    st.markdown(
        theme_colors("""
<style>
/* Engineering workspace base styles. The approved reference and workflow.css
 * define the current visual treatment. */
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


def main() -> None:
    initialize()
    if "catalog" not in st.session_state:
        catalog, versions = AssetStore().catalog()
        st.session_state.update(catalog=catalog, asset_versions=versions, asset_files=[], sim_reports=[])
    _theme()
    st.markdown("<style>" + theme_colors(Path(__file__).with_name("shell.css").read_text(encoding="utf-8")) + appearance_css(st.session_state.appearance) + Path(__file__).with_name("workflow.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
    projects = ProjectStore()
    if "active_project_id" not in st.session_state:
        last = projects.last()
        st.session_state.active_project_id = last.project_id if last else None
    pending_project = st.session_state.pop("project_to_select", None)
    if pending_project:
        st.session_state.active_project_id = pending_project
    page = workspace_navigation(tx)
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
    language = "zh" if st.session_state.language == "中文" else "en"
    native_locale(language)
    if page == "home":
        home_page(language)
    elif page == "text_search":
        text_search_page(language)
    elif page == "asset_management":
        management_page(language)
    else:
        pdf_workflow_page(language)


main()
