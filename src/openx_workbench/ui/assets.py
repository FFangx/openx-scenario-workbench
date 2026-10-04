"""Candidate comparison and esmini simulation preview."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

import streamlit as st

from openx_workbench import matching
from openx_workbench.asset_management import label as localized
from openx_workbench.asset_store import AssetStore, AssetVersion
from openx_workbench.candidate_table import candidate_table
from openx_workbench.catalog import OpenXAsset
from openx_workbench.esmini_preview import PreviewProcess, start_preview
from openx_workbench.presentation import asset_display_title, display
from openx_workbench.preview_frames import read_frame
from openx_workbench.retrieval import RetrievalResult
from openx_workbench.scene_package import ScenePackage
from openx_workbench.sim_archive import SimImportReport
from openx_workbench.ui_shell import preview_settings
from openx_workbench.ui.common import index_for, safe, tx, verdict_label
from openx_workbench.ui.imports import library_controls


def _rows(results: list[RetrievalResult], language: str) -> list[dict[str, Any]]:
    rows = [{"#": i, tx(language,"scenario"): asset_display_title(r.asset, language), tx(language,"score"): round(r.score, 2),
             tx(language,"decision"): verdict_label(language, r.confirmation_level, r.confirmation_review_kind),
             tx(language,"cost"): r.estimated_change_cost} for i, r in enumerate(results, 1)]
    for row, result in zip(rows, results):
        version = st.session_state.get("asset_versions", {}).get(result.asset.asset_id)
        cached = read_frame(AssetStore(), version) if version else None
        row[localized(language, "真实帧", "Frame")] = "data:image/jpeg;base64," + base64.b64encode(cached[0]).decode("ascii") if cached else ""
    return rows


def asset_summary(asset: OpenXAsset, language: str) -> None:
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
    if status.get("snapshot_error"):
        st.warning(localized(language, "仿真画面已生成，但缩略图未能保存。请检查本机数据目录的写入权限。", "Simulation rendered, but its still frame could not be saved. Check data-folder write access."))
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
            if status["state"] == "running":
                st.markdown(
                    f'<img src="{safe(preview.url)}/stream?token={safe(preview.token)}" '
                    f'alt="{safe(localized(language, "实时仿真画面", "Live esmini simulation"))}" style="width:100%;height:auto;aspect-ratio:16/9;object-fit:contain;display:block;background:#17242e">',
                unsafe_allow_html=True,
            )
        st.caption(localized(language, "预览已结束，可以重新播放。", "Preview finished. You can play it again.")
                   if status["state"] == "finished" else localized(language,
                   f"正在播放 · 已生成 {status['frames']} 帧真实画面", f"Playing · {status['frames']} rendered frames"))


def preview_controls(version: AssetVersion, language: str, *, show_identity: bool = True) -> None:
    version = next((item for item in AssetStore().versions()
                    if item.asset_id == version.asset_id and item.version_id == version.version_id), version)
    if show_identity:
        st.caption(localized(language, f"资产 {version.asset_id[:10]} · 版本 {version.version_number} · {display(version.compatibility, language)}", f"Asset {version.asset_id[:10]} · version {version.version_number} · {version.compatibility}"))
    if version.compatibility_detail:
        st.caption(version.compatibility_detail)
    playback = st.container()
    with st.expander(localized(language, "仿真工具设置", "Simulation tool settings")):
        executable = preview_settings(language)
    with playback:
        if executable is None:
            st.caption(localized(language, "请展开下方仿真工具设置，选择 esmini 安装位置。", "Open Simulation tool settings below to locate esmini."))
        _preview_playback(version, language, executable)


@st.fragment(run_every="1s")
def _preview_playback(version: AssetVersion, language: str, executable: Path | None) -> None:
    preview = st.session_state.get("preview_process")
    selected_preview = preview is not None and (preview.asset_id, preview.version_id) == (version.asset_id, version.version_id)
    status = preview.status() if selected_preview else None
    active = selected_preview and preview.process.poll() is None and status["state"] in {"starting", "running"}
    run_col, stop_col, frame_col = st.columns([1.2, .8, 1])
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
    with frame_col:
        if st.button(localized(language, "生成缩略图", "Capture frame"), key="capture_esmini_frame",
                     width="stretch", disabled=executable is None or active, icon=":material/photo_camera:"):
            previous = st.session_state.pop("preview_process", None)
            if previous:
                previous.stop()
            try:
                with st.spinner(localized(language, "正在渲染真实画面…", "Rendering a real frame…")):
                    st.session_state.preview_process = start_preview(AssetStore(), version, executable, duration=2)
            except Exception as exc:
                st.error(localized(language, "缩略图生成失败：", "Frame capture failed: ") + str(exc))
    preview = st.session_state.get("preview_process")
    matching = preview and (preview.asset_id, preview.version_id) == (version.asset_id, version.version_id)
    status = preview.status() if matching else None
    if matching:
        _preview_live(preview, version, language, status)
        if status["state"] in {"finished", "failed"} and st.session_state.get("preview_terminal_token") != preview.token:
            st.session_state.preview_terminal_token = preview.token
            # Refresh version status and candidate thumbnails outside this fragment.
            st.rerun()
    if not matching or status["state"] not in {"starting", "running"}:
        cached = read_frame(AssetStore(), version)
        if cached:
            jpeg, metadata = cached
            st.image(jpeg, use_container_width=True)
            st.caption(localized(language,
                f"esmini 真实帧 · {metadata['simulation_seconds']:g} s · 资产版本 {version.version_number} · 静态预览",
                f"esmini frame · {metadata['simulation_seconds']:g} s · asset version {version.version_number} · Still preview"))
        else:
            st.info(localized(language, "还没有这个版本的画面。生成缩略图，或直接播放仿真。", "No frame for this version yet. Capture a frame or play the simulation."))

def asset_panel(language: str, package: ScenePackage | None) -> None:
    catalog: list[OpenXAsset] = st.session_state.get("catalog", [])
    st.subheader(localized(language, "比较候选资产", "Compare candidates"))
    query_text, search_clicked = _search_row(package, catalog, language)
    encoder_name = st.session_state.get("retrieval_encoder", "bge")
    st.caption(localized(language, f"在 {len(catalog)} 个资产中匹配 · ", f"Search {len(catalog)} assets · ") + tx(language, encoder_name))
    if not catalog:
        library_controls(language, expanded=True)
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
        _search(package, query_text, catalog, encoder_name, language)
    results: list[RetrievalResult] = st.session_state.get("retrieval_results", [])
    st.markdown(
        f'<div class="ow-candidate-head"><strong>{safe(tx(language,"candidates"))}</strong><span>{safe(localized(language, f"{len(results)} 个结果 · 按结构重新排序", f"{len(results)} results · structural ranking"))}</span></div>',
        unsafe_allow_html=True,
    )
    if not results:
        st.info(localized(language, "选好需求后点击检索，候选、预览和评估会显示在这里。", "Select a requirement and search to see candidates, previews and assessment."))
        if catalog:
            library_controls(language, expanded=False, show_progress=False)
        return
    st.caption(localized(language, "相似度越高越相似；修改成本是相对分值，不代表工时。复用结论请查看“复用评估”。", "Higher similarity means closer matches. Change cost is a relative score, not working hours. See Reuse assessment for the conclusion."))
    if "result_index" not in st.session_state:
        st.session_state.result_index = min(st.session_state.get("selected_candidate_index", 0), len(results) - 1)
    choices, preview = st.container(), st.container()
    with choices:
        index = _candidate_choices(results, language)
    with preview:
        image_column, difference_column = st.columns([1, 1.1], gap="large")
        with image_column:
            asset_summary(results[index].asset, language)
            version = st.session_state.get("asset_versions", {}).get(results[index].asset.asset_id)
            if version:
                preview_controls(version, language)
        with difference_column:
            _candidate_differences(results[index], language)
    library_controls(language, expanded=False, show_progress=False)


def _search_row(package: ScenePackage | None, catalog: list[OpenXAsset], language: str) -> tuple[str, bool]:
    with st.container(key="candidate_search"):
        search_row = st.columns([3.5, 1.7, 1.1])
        with search_row[0]:
            query_text = st.text_input(tx(language, "query"), placeholder=tx(language, "query_hint"), label_visibility="collapsed")
        with search_row[1]:
            search_clicked = st.button(tx(language, "search"), type="primary", use_container_width=True,
                                       key="pdf_search_button", icon=":material/search:", disabled=not catalog or (package is None and not query_text.strip()))
        with search_row[2]:
            if st.button(localized(language, "清空结果", "Clear results"), use_container_width=True):
                st.session_state.retrieval_results = []
                st.rerun()
    return query_text, search_clicked


def _search(package: ScenePackage | None, query_text: str, catalog: list[OpenXAsset], encoder_name: str, language: str) -> None:
    try:
        query = matching.scene_query(package, query_text)
        with st.spinner(localized(language, "正在检索并核对候选结构…", "Retrieving and checking candidate structures…")):
            results = matching.search(index_for(catalog, encoder_name), query, query_text, top_k=min(8, len(catalog)))
        st.session_state.update(retrieval_results=results, result_index=0, selected_candidate_index=0)
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))


def _candidate_choices(results: list[RetrievalResult], language: str) -> int:
    """Candidate table plus by-name picker; returns the selected candidate index."""
    index = min(st.session_state.get("result_index", 0), len(results) - 1)
    signature = hashlib.sha256(repr([(r.asset.asset_id, r.score, r.confirmation_level) for r in results]).encode()).hexdigest()[:12]
    table_key = f"candidate_rows_{signature}_{index}"
    rows = _rows(results, language)
    selected_row = candidate_table(rows, index, language, key=table_key)
    if selected_row != index:
        st.session_state.result_index = selected_row
        st.session_state.selected_candidate_index = selected_row
        st.rerun()
    selector_tools, export_tools = st.columns(2)
    with selector_tools, st.expander(localized(language, "按名称选择候选", "Select candidate by name")):
        index = st.selectbox(tx(language, "candidate"), range(len(results)),
                            format_func=lambda i: f"{i+1}. {asset_display_title(results[i].asset, language)}",
                            key="result_index")
    with export_tools, st.expander(localized(language, "表格工具与导出", "Table tools and export")):
        st.dataframe(rows, hide_index=True, width="stretch", height=260,
                     column_config={localized(language, "真实帧", "Frame"): st.column_config.ImageColumn(width=86)})
    st.markdown('<div class="ow-section-rule"></div>', unsafe_allow_html=True)
    st.session_state.selected_candidate_index = index
    return index


def _candidate_differences(result: RetrievalResult, language: str) -> None:
    st.markdown("**" + localized(language, "需求与候选的差异", "Requirement / candidate differences") + "**")
    differences = result.differences
    st.caption(verdict_label(language, result.confirmation_level, result.confirmation_review_kind))
    if differences:
        difference_rows = []
        for difference in differences:
            state = localized(language, "待核实" if not difference.verified else "阻断复用" if difference.blocking else "需调整",
                              "Unverified" if not difference.verified else "Blocking" if difference.blocking else "Change needed")
            difference_rows.append(f'<tr><th scope="row">{safe(display(difference.category, language))}</th>'
                                   f'<td>{safe(display(difference.requested, language))}</td>'
                                   f'<td>{safe(display(difference.candidate, language))}</td><td>{safe(state)}</td></tr>')
        headings = ("字段", "需求", "候选", "状态") if language == "zh" else ("Field", "Required", "Candidate", "Status")
        st.markdown('<div class="ox-comparison-scroll"><table class="ox-comparison-table"><thead><tr>' +
                    ''.join(f'<th scope="col">{label}</th>' for label in headings) + '</tr></thead><tbody>' +
                    ''.join(difference_rows) + '</tbody></table></div>', unsafe_allow_html=True)
    else:
        st.caption(localized(language, "已检查字段没有发现差异；完整结论和证据请在复用评估中核对。", "No differences in checked fields. Review the complete conclusion and evidence in Reuse assessment."))
