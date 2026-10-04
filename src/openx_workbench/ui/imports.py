"""Asset import controls and background import progress."""

from __future__ import annotations

import time
from typing import NamedTuple

import streamlit as st

from openx_workbench.asset_management import label
from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.demo import fetch_public_demo
from openx_workbench.ui.common import tx


@st.cache_data(show_spinner=False)
def _demo_files() -> list[AssetFile]:
    demo = fetch_public_demo()
    return [AssetFile(demo.xosc_name, demo.xosc_data), AssetFile(demo.xodr_name, demo.xodr_data)]


@st.fragment(run_every="1s")
def import_progress(language: str) -> None:
    from openx_workbench.import_jobs import status
    from openx_workbench.classification import read_classification
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
    facts = _job_facts(state, language) if state else None
    with st.container(key="asset_job_strip"):
        summary, actions = st.columns([4, 1.4], vertical_alignment="top")
        with summary:
            if state:
                _job_summary(state, facts, active, language)
            elif pending:
                st.caption(label(language, f"{len(pending)} 个版本待模型复核", f"{len(pending)} versions await model review"))
        with actions:
            _job_actions(store, state, active, retry_available, pending, language)
        if state:
            _job_details(state, facts, active, retry_available, language)


class _JobFacts(NamedTuple):
    """Stage label and import counts shared by the job summary and its details."""
    stage: str
    total_cases: int
    skipped: int
    missing: int
    warning_count: int


def _job_facts(state: dict, language: str) -> _JobFacts:
    names = {"queued": label(language, "准备导入", "Preparing import"),
             "expanding": label(language, "展开场景文件", "Expanding archive"),
             "parsing": label(language, "解析场景与道路", "Parsing scenarios and roads"),
             "saving": label(language, "保存资产", "Saving assets"),
             "classifying": label(language, "复核分类", "Reviewing classification")}
    stage = names.get(state["stage"], state["stage"])
    reports = state.get("reports", [])
    total_cases = sum(report["case_count"] for report in reports)
    paired_cases = sum(report["imported_count"] for report in reports)
    skipped = max(0, total_cases - paired_cases)
    missing = sum(len(report["missing_road_references"]) for report in reports)
    return _JobFacts(stage, total_cases, skipped, missing, int(state.get("failed", 0)) + skipped)


def _job_summary(state: dict, facts: _JobFacts, active: bool, language: str) -> None:
    stage, total_cases, skipped, missing, warning_count = facts
    states = {"completed": label(language, "导入完成", "Import completed"),
              "stopped": label(language, "任务已停止", "Import stopped"),
              "interrupted": label(language, "任务已中断", "Import interrupted"),
              "failed": label(language, "任务失败", "Import failed")}
    title = stage if active else states.get(state["status"], state["status"])
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


def _job_actions(store: AssetStore, state: dict | None, active: bool, retry_available: bool,
                 pending: list, language: str) -> None:
    from openx_workbench.import_jobs import current_job, start_import
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


def _job_details(state: dict, facts: _JobFacts, active: bool, retry_available: bool, language: str) -> None:
    stage, _, skipped, missing, warning_count = facts
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


def library_controls(language: str, *, expanded: bool, show_progress: bool = True) -> None:
    from openx_workbench.import_jobs import start_import, status
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
        import_progress(language)
