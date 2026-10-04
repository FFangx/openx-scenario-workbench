"""PDF scene library, source evidence and requirement fact editing."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import streamlit as st

from openx_workbench.asset_management import label as localized
from openx_workbench.batch_matching import batch_signature, match_document
from openx_workbench.pdf_store import PdfStore, StoredScene
from openx_workbench.presentation import display
from openx_workbench.project_store import ProjectStore
from openx_workbench.report_html import render_report
from openx_workbench.requirement_editor import edit_structure
from openx_workbench.scene_package import ScenePackage
from openx_workbench.ui.common import batch_summary, empty, encoder_control, index_for, panel, safe, tx


@st.cache_data(show_spinner=False)
def _pdf_page(data: bytes, number: int) -> bytes:
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as document:
        page = document[max(0, min(number - 1, len(document) - 1))]
        return page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes("png")


@st.dialog("PDF 原文 / Source document", width="large")
def _source_reader(selected: StoredScene, page_number: int, language: str) -> None:
    """Read the same immutable source page at a larger, legible width."""
    st.caption(f"{selected.document.filename} · {tx(language, 'pages')} {page_number}")
    with st.container(height=650, key="source_reader_page"):
        st.image(_pdf_page(PdfStore().pdf_bytes(selected.document), page_number), width="stretch")


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
                    trace = match_document(document, scenes, index_for(catalog, encoder), versions)
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
        batch_summary(trace, language)
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


def pdf_scene_library(language: str) -> StoredScene | None:
    project_id = st.session_state.get("active_project_id")
    panel(1, localized(language, "场景需求与原文", "Requirements and evidence"))
    if not project_id:
        with st.expander(tx(language, "encoder")):
            encoder_control(language)
        st.info("请先在顶栏创建或选择项目。" if language == "zh" else "Create or select a project in the top navigation first.")
        st.session_state.selected_stored_scene = None
        return None
    store = PdfStore()
    documents = store.documents(project_id)
    _import_pdfs(store, project_id, documents, language)
    if not documents:
        empty(tx(language, "no_pdf"), tx(language, "no_pdf_detail"))
        st.session_state.selected_stored_scene = None
        return None
    mode, document, all_visible_scenes = _document_scope(store, project_id, documents, language)
    quick_jump, scenes = _filtered_scenes(all_visible_scenes, language)
    selected_key = st.session_state.get("selected_scene_key")
    by_key = _scene_picker(project_id, scenes, selected_key, quick_jump, language)
    _requirement_queue(store, project_id, by_key, selected_key, language)
    if mode == "by_pdf":
        _document_records(store, project_id, document, scenes, language)
    if not scenes:
        st.info("没有符合筛选条件的场景。清空关键词或选择全部功能。" if language == "zh" else
                "No scenes match. Clear your search or choose all functions.")
    return _selected_scene(project_id, all_visible_scenes)


def _import_pdfs(store: PdfStore, project_id: str, documents: list, language: str) -> None:
    with st.container(key="pdf_import"):
        with st.expander("导入 PDF 与设置" if language == "zh" else "Import PDFs and settings", expanded=not documents):
            encoder_control(language)
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


def _document_scope(store: PdfStore, project_id: str, documents: list, language: str) -> tuple[str, Any, list[StoredScene]]:
    """The scope radio and PDF picker; `document` is None when showing all scenes."""
    document = None
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
    else:
        scenes = store.all_scenes(project_id)
    return mode, document, scenes


def _filtered_scenes(scenes: list[StoredScene], language: str):
    """Search and function filters; returns the quick-jump expander and the matching scenes."""
    all_visible_scenes = scenes
    functions = sorted({scene.package.classification.get("function", "未知") for scene in scenes})
    filters = [st.container(), st.expander(localized(language, "筛选与快速跳转", "Filters and quick jump"))]
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
    return filters[1], scenes


def _scene_picker(project_id: str, scenes: list[StoredScene], selected_key, quick_jump, language: str) -> dict:
    keys = [(project_id, item.document.document_id, item.scene_id) for item in scenes]
    st.session_state.pdf_queue_keys = keys
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
    elif selected_key is None and keys:
        # Open a real requirement on entry; an empty document/filter stays empty.
        st.session_state[picker_key] = keys[0]
    with quick_jump:
        choice = st.selectbox("选择场景需求" if language == "zh" else "Select a requirement", keys,
                              index=keys.index(selected_key) if selected_key in keys else None,
                              format_func=scene_label, key=picker_key,
                              placeholder="选择一个场景…" if language == "zh" else "Choose a scene…")
    if choice is not None and choice != selected_key:
        st.session_state.selected_scene_key = choice
        st.session_state.pdf_stage = "review"
        st.session_state.retrieval_results = []
        st.rerun()
    return by_key


def _requirement_queue(store: PdfStore, project_id: str, by_key: dict, selected_key, language: str) -> None:
    published = {(item["document_id"], item["scene_id"], item["revision"]) for item in store.library() if item["project_id"] == project_id}
    evaluated = {(source.get("document_id"), source.get("scene_id"), source.get("revision"))
                 for report in ProjectStore().reports(project_id) for source in [report.get("trace", {}).get("source", {})]}
    with st.container(height=350, border=False, key="requirement_queue"):
        for queue_key, item in by_key.items():
            evidence = item.package.evidence[0] if item.package.evidence else None
            page = f"P{evidence.page_start}" if evidence else localized(language, "无页码", "No page")
            confirmed = (item.document.document_id, item.scene_id, item.revision) in published
            state = localized(language, "已确认" if confirmed else "待核对", "Confirmed" if confirmed else "To review")
            if (item.document.document_id, item.scene_id, item.revision) in evaluated:
                state = localized(language, "已保存评估", "Assessment saved")
            label = f"**{item.package.title}**\n\n{page} · v{item.revision} · {state}"
            if st.button(label, key="queue_" + hashlib.sha256(repr(queue_key).encode()).hexdigest()[:16],
                         type="primary" if queue_key == selected_key else "secondary", width="stretch"):
                st.session_state.scene_picker_target = queue_key
                st.rerun()


def _document_records(store: PdfStore, project_id: str, document, scenes: list[StoredScene], language: str) -> None:
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


def _selected_scene(project_id: str, scenes: list[StoredScene]) -> StoredScene | None:
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


def _requirement_fact_sheet(package: ScenePackage, language: str) -> None:
    """Show saved values without inference, preserving zero and missing states."""
    zh = language == "zh"
    unknown = localized(language, "未明确", "Not specified")

    def value(item):
        if item is None or item == "" or item == [] or item == {} or item in ("未知", "unknown", "未知方位", "未知朝向"):
            return f'<span class="ox-fact-unknown">{unknown}</span>'
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            return safe(format(item, ".15g"))
        if isinstance(item, (list, tuple)):
            return " · ".join(safe(display(part, language)) for part in item)
        if isinstance(item, dict):
            return safe(json.dumps(item, ensure_ascii=False))
        return safe(display(item, language))

    if package.structure:
        structure = package.structure
        rows = [(localized(language, "道路类型", "Road type"), structure.get("road_class")),
                (localized(language, "被测功能", "Tested function"), structure.get("tested_function")),
                (localized(language, "试验目的", "Test intent"), structure.get("test_intent")),
                (localized(language, "主车动作", "Ego actions"), structure.get("ego_actions")),
                (localized(language, "触发条件", "Trigger types"), structure.get("semantic_triggers"))]
        params = structure.get("params") or {}
    else:
        rows = [(localized(language, "道路类型", "Road types"), package.road_types),
                (localized(language, "参与者", "Participants"), package.entities),
                (localized(language, "动作", "Actions"), package.actions),
                (localized(language, "触发条件", "Triggers"), package.triggers)]
        params = dict(package.parameters)
        if "ttc_value" not in params and "ttc_s" in params:
            params["ttc_value"] = params.pop("ttc_s")
    labels = {"ego_speed_kph": localized(language, "主车速度（km/h）", "Ego speed (km/h)"),
              "ttc_value": "TTC (s)", "lane_count": localized(language, "车道数", "Lane count"),
              "curve_radius_m": localized(language, "弯道半径（m）", "Curve radius (m)"),
              "fog_visibility_m": localized(language, "能见度（m）", "Visibility (m)"),
              "target_speeds_kph": localized(language, "目标速度（km/h）", "Target speeds (km/h)"),
              "lateral_direction": localized(language, "横向方向", "Lateral direction"),
              "lane_direction": localized(language, "车道方向", "Lane direction"),
              "weather": localized(language, "天气", "Weather"),
              "time_of_day": localized(language, "时段", "Time of day"),
              "end_condition": localized(language, "结束条件", "End condition")}
    primary_params = ("ego_speed_kph", "target_speeds_kph", "ttc_value", "lane_count", "weather", "time_of_day") if package.structure else ("ego_speed_kph", "ttc_value", "lane_count")
    for key in primary_params:
        rows.append((labels[key], params.get(key)))
    for key, item in params.items():
        if key not in primary_params and item is not None:
            rows.append((labels.get(key, display(key, language)), item))
    if not package.structure:
        rows.extend([(labels["weather"], package.weather), (labels["time_of_day"], package.time_of_day)])
    table = "".join(f'<tr><th scope="row">{safe(label)}</th><td>{value(item)}</td></tr>' for label, item in rows)
    description = f'<p class="ox-saved-description">{safe(package.preferred_text)}</p>' if package.preferred_text else ""
    st.markdown(f'<section class="ox-fact-sheet"><div class="ox-sheet-heading">{safe(localized(language, "已保存的需求事实", "Saved requirement facts"))}</div>'
                f'{description}<table><tbody>{table}</tbody></table></section>', unsafe_allow_html=True)
    participants = package.structure.get("participants", [])
    if participants:
        headings = ("参与者类型", "方位", "朝向", "动作") if zh else ("Participant", "Bearing", "Facing", "Actions")
        actor_rows = "".join('<tr>' + "".join(f'<td>{value(actor.get(key))}</td>' for key in ("kind", "bearing", "facing", "actions")) + '</tr>' for actor in participants)
        st.markdown('<section class="ox-fact-sheet"><div class="ox-sheet-heading">' + localized(language, "其他参与者", "Other participants") +
                    '</div><div class="ox-actor-scroll"><table><thead><tr>' + "".join(f'<th scope="col">{heading}</th>' for heading in headings) +
                    f'</tr></thead><tbody>{actor_rows}</tbody></table></div></section>', unsafe_allow_html=True)


def requirement_details(selected: StoredScene, language: str) -> None:
    store = PdfStore()
    project_id = selected.document.project_id
    package = selected.package
    source_column, facts_column = st.columns([1.12, 1], gap="large")
    with source_column:
        with st.container(key="source_evidence"):
            st.markdown("**" + localized(language, "PDF 原文", "PDF evidence") + "**")
            evidence = package.evidence[0] if package.evidence else None
            if len(package.evidence) > 1:
                evidence_index = st.selectbox("原文条款" if language == "zh" else "Source clause", range(len(package.evidence)),
                                              format_func=lambda index: f"{package.evidence[index].section_id} · {package.evidence[index].page_start}–{package.evidence[index].page_end}",
                                              key=f"evidence_{selected.document.document_id}_{selected.scene_id}")
                evidence = package.evidence[evidence_index]
            if evidence:
                page_number = evidence.page_start
                if evidence.page_end > evidence.page_start:
                    page_number = st.selectbox(localized(language, "证据页码", "Evidence page"),
                                               range(evidence.page_start, evidence.page_end + 1),
                                               key=f"source_page_{selected.document.document_id}_{selected.scene_id}")
                page_image = None
                try:
                    page_image = _pdf_page(store.pdf_bytes(selected.document), page_number)
                except Exception:
                    st.warning(localized(language, "原页暂时无法显示，可下载原始 PDF 核对。", "Source page unavailable. Download the original PDF to review it."))
                if page_image:
                    with st.container(height=510, border=False, key="source_page_view"):
                        st.image(page_image, width="stretch")
                source_actions, source_status = st.columns([1, 1.5])
                with source_actions:
                    if st.button(localized(language, "放大阅读", "Enlarge page"), key="enlarge_source_page",
                                 icon=":material/open_in_full:", disabled=page_image is None):
                        _source_reader(selected, page_number, language)
                with source_status:
                    st.caption(localized(language, f"原始 PDF · 第 {page_number} 页 · 只读", f"Original PDF · Page {page_number} · Read-only"))
                if evidence.source_text.strip():
                    with st.expander(localized(language, "查看证据文本", "Evidence text")):
                        st.markdown(f'<div class="ow-evidence"><strong>{safe(evidence.section_id)}</strong>'
                                    f'<p>{safe(evidence.source_text)}</p></div>', unsafe_allow_html=True)
            else:
                st.info(localized(language, "此需求尚未关联原文证据。", "No source evidence is linked to this requirement."))
    with facts_column:
        with st.container(height=620, border=False, key="requirement_facts"):
            _requirement_fact_sheet(package, language)
            with st.expander("编辑事实" if language == "zh" else "Edit facts", expanded=st.session_state.pop("requirement_edit_open", False)):
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
                        fact_columns = st.columns(2)
                        for field_index, (key, label) in enumerate((("entities", localized(language, "参与者", "Participants")), ("actions", localized(language, "动作", "Actions")),
                                           ("triggers", localized(language, "触发条件", "Triggers")), ("road_types", localized(language, "道路", "Road types")),
                                           ("weather", localized(language, "天气", "Weather")), ("time_of_day", localized(language, "时段", "Time of day")))):
                            with fact_columns[field_index % 2]:
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
            _publication_details(selected, language)


def _publication_details(selected: StoredScene, language: str) -> None:
    store = PdfStore()
    project_id = selected.document.project_id
    package = selected.package
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
