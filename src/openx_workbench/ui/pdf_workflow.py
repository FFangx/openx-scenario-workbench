"""PDF workflow page: requirement queue on the left, review → compare → assess on the right."""

from __future__ import annotations

import streamlit as st

from openx_workbench.asset_management import label as localized
from openx_workbench.pdf_store import StoredScene
from openx_workbench.presentation import asset_display_title
from openx_workbench.scene_package import ScenePackage
from openx_workbench.ui.assessment import decision_panel
from openx_workbench.ui.assets import asset_panel
from openx_workbench.ui.common import tx
from openx_workbench.ui.requirements import pdf_scene_library, requirement_details


def pdf_workflow_page(language: str) -> None:
    with st.container(key="pdf_workspace"):
        library, work = st.columns([.9, 2.4], gap="large")
        with library:
            with st.container(key="pdf_library"):
                selected = pdf_scene_library(language)
        with work:
            with st.container(key="pdf_current"):
                if selected is None:
                    st.subheader(localized(language, "从一条需求开始", "Start with a requirement"))
                    st.write(localized(language, "在左侧选择 PDF 和场景，再核对事实、比较资产并保存评估。", "Choose a PDF and scene on the left, then review facts, compare assets and save the assessment."))
                    return
                _current_requirement(selected, language)


def _current_requirement(selected: StoredScene, language: str) -> None:
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
        _review_stage(selected, language)
    elif stage == "compare":
        _compare_stage(package, language)
    else:
        _assess_stage(package, language)


def _review_stage(selected: StoredScene, language: str) -> None:
    with st.container(key="evidence_panel"):
        requirement_details(selected, language)
    with st.container(key="task_actions"):
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


def _compare_stage(package: ScenePackage, language: str) -> None:
    with st.container(key="asset_panel"):
        asset_panel(language, package)
    if st.session_state.get("retrieval_results") and st.button(localized(language, "查看复用评估", "View reuse assessment"), key="open_pdf_assessment", type="primary"):
        st.session_state.pdf_next_stage = "assess"
        st.rerun()


def _assess_stage(package: ScenePackage, language: str) -> None:
    results = st.session_state.get("retrieval_results", [])
    if results:
        if "result_index" not in st.session_state:
            st.session_state.result_index = min(st.session_state.get("selected_candidate_index", 0), len(results)-1)
        st.selectbox(tx(language, "candidate"), range(len(results)), key="result_index",
                     format_func=lambda i: f"{i+1}. {asset_display_title(results[i].asset, language)}")
        st.session_state.selected_candidate_index = st.session_state.result_index
    with st.container(key="decision_panel"):
        decision_panel(language, package)
