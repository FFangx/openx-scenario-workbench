"""Overview page: library health and saved project decisions."""

from __future__ import annotations

import csv
import io
import json

import streamlit as st

from openx_workbench.asset_management import label as localized
from openx_workbench.asset_store import AssetStore
from openx_workbench.overview_table import recent_imports_table
from openx_workbench.pdf_store import PdfStore
from openx_workbench.project_store import ProjectStore
from openx_workbench.report_html import render_report
from openx_workbench.reuse_trace import checked_trace
from openx_workbench.ui.common import batch_summary, tx, verdict_label


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
            batch_summary(trace, language)
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
        st.write(verdict_label(language, trace["reuse"]["level"], trace["reuse"].get("review_kind", "")))
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


def home_page(language: str) -> None:
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
    with st.container(key="overview_metrics"):
        cols = st.columns(4)
        for col, label, value in zip(cols, (("资产", "版本", "可播放", "未检测") if language == "zh" else ("Assets", "Versions", "Playable", "Not tested")),
                                     (len(latest), len(versions), counts["playable"], counts["untested"])):
            col.metric(label, value)
    if not latest:
        st.info(tx(language, "no_assets"))
        st.caption("Recent imports: none" if language == "en" else "最近导入：暂无")
        return
    tested = len(latest) - counts["untested"]
    with st.container(key="overview_coverage"):
        coverage, playable = st.columns(2)
        with coverage:
            st.caption("Preview test coverage" if language == "en" else "预览检测覆盖率")
            st.progress(tested / len(latest), text=f"已检测 {tested}/{len(latest)} 个资产" if language == "zh" else f"{tested}/{len(latest)} assets tested")
        with playable:
            st.caption("Playable among tested assets" if language == "en" else "已检测资产的可播放比例")
            if tested:
                st.progress(counts["playable"] / tested, text=f"{counts['playable']}/{tested} 可播放" if language == "zh" else f"{counts['playable']}/{tested} playable")
            else:
                st.caption("尚未检测" if language == "zh" else "No assets tested yet")
    st.caption(f"预览失败 {counts['unavailable']} 个 · 状态仅代表已检测的版本。" if language == "zh" else f"Preview failures: {counts['unavailable']} · Status reflects tested versions only.")
    recent = sorted(versions, key=lambda item: item.created_at, reverse=True)[:8]
    from openx_workbench.asset_management import value_label
    headings = ("资产", "来源", "版本", "预览状态", "导入时间") if language == "zh" else (
        "Asset", "Source", "Version", "Preview", "Imported")
    rows = [{"values": [item.title, item.source_name, item.version_number,
                         value_label(item.compatibility, language), item.created_at[:19].replace("T", " ")],
             "status": item.compatibility} for item in recent]
    export = io.StringIO()
    writer = csv.writer(export)
    writer.writerow(headings)
    writer.writerows(row["values"] for row in rows)
    with st.container(key="recent_import_heading"):
        title, download = st.columns([1, .15])
        title.subheader("Recent imports" if language == "en" else "最近导入")
        download.download_button("导出 CSV" if language == "zh" else "Export CSV", export.getvalue().encode("utf-8-sig"),
                                 "openx-recent-imports.csv", "text/csv", key="recent_imports_csv", icon=":material/download:")
    recent_imports_table(headings, rows, language)
