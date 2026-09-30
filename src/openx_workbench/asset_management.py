"""List-first asset library and explicit, version-scoped inspection."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

import streamlit as st

from .asset_store import AssetStore
from .classification import FUNCTIONS, ROADS, TARGETS, read_classification, classify_asset, confirm_classification
from .import_jobs import status
from .pdf_store import PdfStore


def label(language, zh, en):
    return zh if language == "zh" else en


_VALUES = {
    "未知": "Unknown", "直道": "Straight", "弯道": "Curve", "交叉口": "Intersection",
    "停车场": "Parking", "环岛": "Roundabout", "匝道": "Ramp", "乘用车": "Passenger car",
    "商用车": "Commercial vehicle", "两轮车": "Two-wheeler", "行人": "Pedestrian",
    "骑行者": "Cyclist", "障碍物": "Obstacle", "动物": "Animal",
    "rule_only": "Rule classified", "classified": "Model reviewed", "manual_confirmed": "Confirmed",
    "failed": "Failed", "pending": "Pending", "not_tested": "Not tested", "playable": "Playable",
    "warning": "Warning", "unsupported": "Unsupported", "timeout": "Timed out",
}
_ZH = {"rule_only": "规则分类", "classified": "模型复核", "manual_confirmed": "人工确认",
       "failed": "失败", "pending": "待分类", "not_tested": "未测试", "playable": "可播放",
       "warning": "有警告", "unsupported": "不支持", "timeout": "超时"}


def value_label(value, language):
    return _ZH.get(value, value) if language == "zh" else _VALUES.get(value, value)


def asset_rows(store, versions, language):
    """Read stored labels only; listing never launches parsing or model calls."""
    rows = []
    for version in versions:
        classification = read_classification(store, version)
        final = classification.get("final", {})
        state = classification.get("status", "pending")
        rows.append({"key": f"{version.asset_id}:{version.version_id}", "version": version,
                     "name": version.title or version.xosc_name, "file": version.xosc_name,
                     "function": final.get("function_type", "未知"),
                     "road": final.get("label_road_type", "未知"), "classification": state,
                     "review": classification.get("needs_review", False), "preview": version.compatibility,
                     "created": version.created_at})
    return rows


def selection_signature(rows, filters=()):
    """Invalidate row offsets whenever the visible identities or filters change."""
    payload = json.dumps(([row["key"] for row in rows], filters), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _clear_selection():
    st.session_state.managed_asset_key = None
    st.session_state.asset_table_epoch = st.session_state.get("asset_table_epoch", 0) + 1


def _classification(store, version, language, busy):
    classification = read_classification(store, version)
    if not classification:
        st.info(label(language, "此版本尚无分类记录。可先生成规则分类，或使用已配置的模型复核。",
                      "This version has no classification. Generate rule labels or review with your configured model."))
        if st.button(label(language, "生成规则分类", "Generate rule labels"), disabled=busy, key="classify_asset_rules", icon=":material/category:"):
            classify_asset(store, version)
            st.rerun()
    if classification:
        final = classification["final"]
        st.caption(value_label(classification["status"], language))
        if classification.get("needs_review"):
            st.warning(label(language, "分类待复核", "Classification needs review"))
        if classification.get("error"):
            st.error(classification["error"])
        with st.form(f"asset_classification_{version.version_id}_{classification.get('saved_at', '')}"):
            function = st.selectbox(label(language, "功能", "Function"), FUNCTIONS,
                                    index=FUNCTIONS.index(final["function_type"]), format_func=lambda v: value_label(v, language), disabled=busy)
            road = st.selectbox(label(language, "道路类型", "Road type"), ROADS,
                                index=ROADS.index(final["label_road_type"]), format_func=lambda v: value_label(v, language), disabled=busy)
            targets = st.multiselect(label(language, "目标参与者", "Targets"), TARGETS,
                                     default=final["label_target_type"], format_func=lambda v: value_label(v, language), disabled=busy)
            actions = st.text_input(label(language, "动作标签", "Actions"), value=", ".join(final["label_actions"]), disabled=busy)
            intent = st.text_area(label(language, "场景意图", "Intent"), value=final["scenario_intent"], disabled=busy)
            confirm = st.form_submit_button(label(language, "保存并确认分类", "Save and confirm classification"), disabled=busy)
        if confirm:
            confirm_classification(store, version, {"function_type": function, "label_road_type": road,
                "label_target_type": targets, "label_actions": [v.strip() for v in actions.split(",") if v.strip()],
                "scenario_intent": intent})
            st.rerun()
        st.download_button(label(language, "下载分类记录", "Download classification record"),
                           json.dumps(classification, ensure_ascii=False, indent=2), "classification.json", "application/json",
                           key="download_asset_classification", icon=":material/download:")
    if busy:
        st.caption(label(language, "导入结束后可修改分类。", "Classification can be edited after the import finishes."))
    st.caption(label(language, "模型复核会将场景结构与描述发送给设置中的模型。", "Model review sends scenario structure and descriptions to the model in Settings."))
    if st.button(label(language, "用模型分类", "Classify with model"), key="classify_asset", icon=":material/category:", disabled=busy):
        from .import_jobs import start_import
        start_import(store, [], classify=True, versions=[version], force=True)
        st.rerun()


def _delete(store, version, language, busy):
    references = store.references(version)
    if references:
        st.warning(label(language, f"此版本已被 {len(references)} 条项目或报告记录引用，无法删除。",
                         f"This version is referenced by {len(references)} project or report items and cannot be deleted."))
    with st.popover(label(language, "更多", "More"), icon=":material/more_horiz:"):
        st.caption(label(language, "删除所选版本将移除它的本地记录与文件。", "Deleting the selected version removes its local record and files."))
        if references:
            st.caption(", ".join(references))
        if st.button(label(language, "删除此版本", "Delete this version"), disabled=bool(references) or busy,
                     key="delete_managed_version", icon=":material/delete:"):
            try:
                preview = st.session_state.get("preview_process")
                if preview and preview.version_id == version.version_id:
                    preview.stop()
                    st.session_state.pop("preview_process", None)
                store.delete_version(version)
                catalog, mapping = store.catalog()
                st.session_state.update(catalog=catalog, asset_versions=mapping, retrieval_results=[], text_results=[])
                _clear_selection()
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _detail(store, version, versions, language, busy, preview_controls, road_schematic, source_files):
    with st.container(key="asset_detail"):
        title, close = st.columns([5, 1])
        with title:
            st.subheader(version.title or version.xosc_name)
            st.caption(label(language, f"版本 {version.version_number} · {value_label(version.compatibility, language)}",
                             f"Version {version.version_number} · {value_label(version.compatibility, language)}"))
        with close:
            st.button(label(language, "关闭", "Close"), key="close_asset_detail", icon=":material/close:", on_click=_clear_selection)
        _delete(store, version, language, busy)
        overview, classification, source, history = st.tabs([
            label(language, "概览与预览", "Overview & preview"), label(language, "分类", "Classification"),
            label(language, "来源", "Source"), label(language, "版本历史", "Versions")])
        with overview:
            try:
                asset = store.load_asset(version)
                road = asset.bundle.road
                st.write(asset.title or version.xosc_name)
                st.caption(label(language, f"{len(asset.bundle.scenario.entities)} 个参与者 · 道路总长 {road.total_length:g} m · {road.lane_count} 个车道记录",
                                 f"{len(asset.bundle.scenario.entities)} entities · {road.total_length:g} m road · {road.lane_count} lane entries"))
                st.markdown(road_schematic(asset, scenario=True), unsafe_allow_html=True)
                st.caption(label(language, "示意图来自已解析的场景与道路，不代表仿真结果。", "Schematic derived from parsed scenario and road data; it is not a simulation result."))
                preview_controls(version, language, show_identity=False)
            except Exception as exc:
                st.error(label(language, "无法读取此版本：", "Cannot read this version: ") + str(exc))
        with classification:
            _classification(store, version, language, busy)
        with source:
            st.write(version.source_name)
            st.caption(label(language, "导入时间", "Imported") + ": " + version.created_at)
            st.caption("Asset ID: " + version.asset_id)
            st.caption("Version ID: " + version.version_id)
            st.dataframe([{label(language, "角色", "Role"): item["role"], label(language, "原始文件", "Original file"): item["original_name"],
                           "SHA-256": item["sha256"]} for item in version.files], use_container_width=True, hide_index=True)
            if st.button(label(language, "查看源文件", "Inspect source files"), key="inspect_managed_source", icon=":material/code:"):
                source_files(version, language)
            with st.expander(label(language, "版本原始记录", "Raw version record")):
                st.json(asdict(version))
                classification_record = read_classification(store, version)
                if classification_record:
                    st.json(classification_record)
        with history:
            related = sorted([v for v in versions if v.asset_id == version.asset_id], key=lambda v: v.version_number, reverse=True)
            choices = {f"{v.asset_id}:{v.version_id}": v for v in related}
            history_key = "managed_history_version"
            if st.session_state.get("managed_history_asset") != version.asset_id:
                st.session_state.managed_history_asset = version.asset_id
                st.session_state.pop(history_key, None)
            if st.session_state.get(history_key) not in choices:
                st.session_state.pop(history_key, None)
            chosen = st.selectbox(label(language, "版本", "Version"), list(choices), key=history_key,
                format_func=lambda key: f"v{choices[key].version_number} · {choices[key].created_at[:19].replace('T', ' ')}")
            historical = choices[chosen]
            st.caption(label(language, "此版本标识", "Version identity") + ": " + historical.version_id)
            st.caption(value_label(historical.compatibility, language))
            if st.button(label(language, "查看此版本", "Inspect this version"), key="inspect_asset_history", icon=":material/history:"):
                st.session_state.asset_table_epoch = st.session_state.get("asset_table_epoch", 0) + 1
                st.session_state.managed_asset_key = chosen
                st.rerun()
            if st.button(label(language, "查看此版本源文件", "Inspect version source"), key="inspect_history_source", icon=":material/code:"):
                source_files(historical, language)
            for role, name in (("scenario", historical.xosc_name), ("road", historical.xodr_name)):
                st.download_button(label(language, "下载 ", "Download ") + name.rsplit("/", 1)[-1], store.file_bytes(historical, role),
                                   name.replace("\\", "/").rsplit("/", 1)[-1], "application/xml", key=f"history_download_{role}", icon=":material/download:")


def _requirements(language):
    records = PdfStore().library()
    if not records:
        st.info(label(language, "在 PDF 工作流中核对场景，点击确认入库。", "Review and publish a scene from the PDF workflow."))
        return
    search = st.text_input(label(language, "搜索需求", "Search requirements"), key="requirement_library_search", placeholder=label(language, "名称或原文", "Name or source text"))
    records = [record for record in records if search.casefold() in (record["package"]["title"] + record["package"]["preferred_text"]).casefold()]
    if not records:
        st.info(label(language, "没有符合搜索条件的需求。", "No requirements match this search."))
        return
    st.caption(label(language, f"{len(records)} 条需求", f"{len(records)} requirements"))
    by_id = {record["library_id"]: record for record in records}
    if st.session_state.get("managed_requirement") not in by_id:
        st.session_state.pop("managed_requirement", None)
    choice = st.selectbox(label(language, "需求场景", "Requirement scene"), list(by_id),
                          format_func=lambda key: f"{by_id[key]['package']['title']} · r{by_id[key]['revision']}", key="managed_requirement")
    record = by_id[choice]
    st.write(record["package"]["preferred_text"])
    with st.expander(label(language, "分类与结构", "Classification and structure")):
        st.json({"classification": record["package"]["classification"], "structure": record["package"]["structure"]})
    st.download_button(label(language, "下载场景包", "Download scene package"), json.dumps(record, ensure_ascii=False, indent=2),
                       "requirement-scene.json", "application/json", icon=":material/download:")
    if st.button(label(language, "打开源文档", "Open source document"), icon=":material/description:"):
        st.session_state.project_to_select = record["project_id"]
        st.session_state.document_to_select = record["document_id"]
        st.session_state.scene_to_select = (record["project_id"], record["document_id"], record["scene_id"])
        st.session_state.active_page = "pdf_workflow"
        st.rerun()


def render(language, *, import_controls, import_progress, preview_controls, road_schematic, source_files):
    store = AssetStore()
    versions = store.versions()
    with st.container(key="asset_management"):
        with st.container(key="asset_library_header"):
            heading, search, action = st.columns([2.8, 3, 1.5], vertical_alignment="center")
            with heading:
                st.subheader(label(language, "资产管理", "Asset management"))
                st.caption(label(language, f"{len(store.latest())} 个资产 · {len(versions)} 个版本", f"{len(store.latest())} assets · {len(versions)} versions"))
            with search:
                query = st.text_input(label(language, "搜索资产", "Search assets"), key="asset_library_search", label_visibility="collapsed",
                                      placeholder=label(language, "搜索名称、文件或来源", "Search names, files or sources"))
            with action:
                st.button(label(language, "导入资产", "Import assets"), icon=":material/upload:", key="open_asset_import", use_container_width=True,
                          on_click=lambda: st.session_state.update(asset_import_open=not st.session_state.get("asset_import_open", False)))
        simulation, requirements = st.tabs([label(language, "仿真资产", "Simulation assets"), label(language, "PDF 需求场景", "PDF requirements")])
        with simulation:
            import_progress(language)
            if st.session_state.get("asset_import_open", False):
                import_controls(language, expanded=True, show_progress=False)
            state = status(store)
            busy = bool(state and state["status"] == "running")
            with st.container(key="asset_library_filters"):
                function_col, road_col, status_col, preview_col, sort_col = st.columns([1.1, 1.1, 1.3, 1.1, 1.2])
                all_rows = asset_rows(store, versions, language)
                def filter_box(column, name, values, key):
                    with column:
                        options = ["all", *sorted(set(values))]
                        if st.session_state.get(key) not in options:
                            st.session_state.pop(key, None)
                        return st.selectbox(name, options, key=key, format_func=lambda v: label(language, "全部", "All") if v == "all" else value_label(v, language))
                fn = filter_box(function_col, label(language, "功能", "Function"), [r["function"] for r in all_rows], "asset_function_filter")
                road = filter_box(road_col, label(language, "道路", "Road"), [r["road"] for r in all_rows], "asset_road_filter")
                cls = filter_box(status_col, label(language, "分类状态", "Classification"), [r["classification"] for r in all_rows], "asset_classification_filter")
                preview = filter_box(preview_col, label(language, "预览状态", "Preview"), [r["preview"] for r in all_rows], "asset_preview_filter")
                with sort_col:
                    sort = st.selectbox(label(language, "排序", "Sort"), ["newest", "name", "function", "road", "classification", "preview"], key="asset_sort",
                        format_func=lambda v: {"newest": label(language, "最近导入", "Newest first"), "name": label(language, "名称", "Name"),
                         "function": label(language, "功能", "Function"), "road": label(language, "道路", "Road"),
                         "classification": label(language, "分类状态", "Classification"), "preview": label(language, "预览状态", "Preview")}[v])
                latest = st.checkbox(label(language, "仅显示最新版本", "Latest versions only"), value=True, key="asset_latest_only")
            latest_keys = {f"{v.asset_id}:{v.version_id}" for v in store.latest()}
            rows = [r for r in all_rows if (not latest or r["key"] in latest_keys)
                    and (fn == "all" or r["function"] == fn) and (road == "all" or r["road"] == road)
                    and (cls == "all" or r["classification"] == cls) and (preview == "all" or r["preview"] == preview)
                    and query.casefold() in (r["name"] + " " + r["file"] + " " + r["version"].source_name).casefold()]
            rows.sort(key=lambda r: r["created"] if sort == "newest" else value_label(r[sort], language).casefold(), reverse=sort == "newest")
            signature = selection_signature(rows, (query, fn, road, cls, preview, sort, latest))
            previous_signature = st.session_state.get("asset_visible_signature")
            if previous_signature is not None and previous_signature != signature:
                _clear_selection()
            st.session_state.asset_visible_signature = signature
            selected = st.session_state.get("managed_asset_key")
            lookup = {f"{v.asset_id}:{v.version_id}": v for v in versions}
            if selected not in lookup:
                selected = None
                st.session_state.managed_asset_key = None
            if selected:
                listing, detail = st.columns([1.25, 1], gap="large")
            else:
                listing, detail = st.container(), None
            with listing:
                st.caption(label(language, f"显示 {len(rows)} 个版本 · 点击一行查看详情", f"Showing {len(rows)} versions · Select a row to inspect"))
                if rows:
                    columns = {"name": label(language, "名称", "Name"), "function": label(language, "功能", "Function"),
                               "road": label(language, "道路", "Road"), "classification": label(language, "分类状态", "Classification"),
                               "preview": label(language, "预览状态", "Preview")}
                    display = [{columns[field]: value_label(r[field], language) +
                                (label(language, " · 待复核", " · Review needed") if field == "classification" and r["review"] else "")
                                for field in columns} for r in rows]
                    if not latest:
                        for row, entry in zip(rows, display):
                            entry[label(language, "版本", "Version")] = f"v{row['version'].version_number}"
                    event = st.dataframe(display, use_container_width=True, hide_index=True,
                        on_select="rerun", selection_mode="single-cell", height=min(600, 36 * len(rows) + 40),
                        key=f"asset_table_{signature}_{st.session_state.get('asset_table_epoch', 0)}")
                    chosen_rows = [event.selection.cells[0][0]] if event.selection.cells else []
                    if chosen_rows and 0 <= chosen_rows[0] < len(rows):
                        chosen_key = rows[chosen_rows[0]]["key"]
                        # A history selection is intentional; do not let an old table event overwrite it.
                        table_event = (signature, st.session_state.get("asset_table_epoch", 0), chosen_key)
                        if st.session_state.get("asset_last_table_event") != table_event:
                            st.session_state.asset_last_table_event = table_event
                            st.session_state.managed_asset_key = chosen_key
                            st.rerun()
                elif versions:
                    st.info(label(language, "没有符合筛选条件的资产。调整筛选或搜索后重试。", "No assets match these filters. Adjust the filters or search."))
                else:
                    st.info(label(language, "资产库为空。点击“导入资产”，上传成对的 XOSC/XODR、SIM 或 ZIP。", "Your library is empty. Choose Import assets to add paired XOSC/XODR, SIM or ZIP files."))
            if detail is not None:
                with detail:
                    _detail(store, lookup[selected], versions, language, busy, preview_controls, road_schematic, source_files)
        with requirements:
            _requirements(language)
