"""Reuse assessment for the selected candidate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

import streamlit as st

from openx_workbench import matching
from openx_workbench.asset_management import label as localized
from openx_workbench.grounding import deterministic_explanation, model_explanation
from openx_workbench.presentation import asset_display_title, difference_text, display
from openx_workbench.project_store import ProjectStore
from openx_workbench.report_html import render_report
from openx_workbench.retrieval import RetrievalResult
from openx_workbench.scene_package import ScenePackage
from openx_workbench.ui_shell import source_files
from openx_workbench.ui.common import chips, icon, review_detail, safe, tx, verdict_label


def _trace(result: RetrievalResult, package: ScenePackage | None) -> dict[str, Any]:
    return matching.assessment_trace(result, package, st.session_state.get("asset_versions", {}).get(result.asset.asset_id),
                                     st.session_state.get("selected_stored_scene"))


def decision_panel(language: str, package: ScenePackage | None) -> None:
    results: list[RetrievalResult] = st.session_state.get("retrieval_results", [])
    st.subheader(localized(language, "复用评估", "Reuse assessment"))
    if not results:
        st.caption(localized(language, "检索候选后，这里会显示复用结论、差异和保存操作。", "Search for candidates to see the reuse assessment, differences and save actions."))
        return
    result = results[min(st.session_state.get("result_index", 0), len(results)-1)]
    st.markdown(
        f'<div class="ow-decision {result.confirmation_level}"><div class="ow-verdict-kicker">{safe(tx(language,"decision"))}</div><div class="ow-decision-line"><h3>{safe(verdict_label(language, result.confirmation_level, result.confirmation_review_kind))}</h3><span class="ow-score">{safe(tx(language,"match_score"))} {result.score:.2f}</span></div><p>{safe(asset_display_title(result.asset, language))}</p></div>',
        unsafe_allow_html=True,
    )
    _provenance(result, package, language)
    _findings(result, package, language)
    with st.expander(localized(language, "查看匹配依据", "Matching evidence")):
        st.markdown(f'<div class="ow-section"><div class="ow-section-title">{safe(tx(language,"matched"))}<span>{len(result.reasons)}</span></div>{chips([display(reason, language) for reason in result.reasons])}</div>', unsafe_allow_html=True)
    payload = _trace(result, package)
    if package:
        _evidence_explanation(package, result, payload, language)
    _downloads(payload, language)
    _save_decision(result, package, payload, language)
    with st.expander(tx(language, "details")):
        st.json(payload)


def _provenance(result: RetrievalResult, package: ScenePackage | None, language: str) -> None:
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


def _findings(result: RetrievalResult, package: ScenePackage | None, language: str) -> None:
    """Open review items, or the blocking differences and required edits."""
    blocking = [item for item in result.differences if item.blocking]
    edits = [item for item in result.differences if not item.blocking]
    if result.confirmation_level == "review":
        st.warning(review_detail(language, result.confirmation_review_kind))
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
        edits_body = (
            f'<ul class="ow-list">{"".join(f"<li>{safe(difference_text(d, language))}</li>" for d in edits)}</ul>'
            if edits else f'<span class="ow-status good">{safe(tx(language,"none"))}</span>'
        )
        st.markdown(f'<div class="ox-assessment-grid"><section class="ow-section"><div class="ow-section-title">{safe(tx(language,"blocking"))} <span>{len(blocking)}</span></div>{blocking_body}</section>'
                    f'<section class="ow-section"><div class="ow-section-title">{safe(tx(language,"edits"))}<span>{len(edits)}</span></div>{edits_body}</section></div>', unsafe_allow_html=True)


def _evidence_explanation(package: ScenePackage, result: RetrievalResult, payload: dict[str, Any], language: str) -> None:
    """Cited evidence and optional explanations; a shown explanation is added to `payload`."""
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
            st.caption(("结构评估结论：" if language == "zh" else "Structural assessment: ") + verdict_label(language, explanation.verdict))
            for observation in explanation.observations:
                st.write(f"{observation.text}  [{', '.join(observation.citations)}]")
            payload["explanation"] = asdict(explanation)


def _downloads(payload: dict[str, Any], language: str) -> None:
    action_left, action_middle = st.columns(2)
    with action_left:
        st.download_button("Assessment data (JSON)" if language == "en" else "评估数据（JSON）",
                           json.dumps(payload, ensure_ascii=False, indent=2),
                           "openx-trace-package.json", "application/json", use_container_width=True)
    with action_middle:
        st.download_button("Assessment report (HTML)" if language == "en" else "评估报告（HTML）",
                           render_report(payload, language=language), "openx-reuse-report.html", "text/html",
                           use_container_width=True)


def _save_decision(result: RetrievalResult, package: ScenePackage | None, payload: dict[str, Any], language: str) -> None:
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
                st.session_state.last_saved_requirement = (project_id, payload["source"].get("document_id"),
                                                           payload["source"].get("scene_id"), payload["source"].get("revision"))
                st.success("Decision saved to this project and pinned to the selected asset version."
                           if language == "en" else "决策已保存到项目，并绑定当前资产版本。")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
        current = st.session_state.get("selected_stored_scene")
        current_key = st.session_state.get("selected_scene_key")
        queue = st.session_state.get("pdf_queue_keys", [])
        if current and current_key and st.session_state.get("last_saved_requirement") == (*current_key, current.revision):
            position = queue.index(current_key) if current_key in queue else len(queue)
            if position + 1 < len(queue) and st.button(localized(language, "继续下一条需求", "Review next requirement"), key="next_requirement", icon=":material/arrow_forward:"):
                st.session_state.scene_picker_target = queue[position + 1]
                st.rerun()
