from __future__ import annotations

import json
from dataclasses import asdict, replace

import streamlit as st

from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.demo import DemoDownloadError, ESMINI_REPOSITORY, fetch_public_demo
from openx_workbench.i18n import tr
from openx_workbench.models import ParseBundle
from openx_workbench.pdf_pipeline import extract_scene_packages_from_pdf
from openx_workbench.retrieval import OpenXIndex, bundle_query_text
from openx_workbench.scene_package import scene_package_to_query
from openx_workbench.workflow import InputFile, InputValidationError, inspect_pair


st.set_page_config(page_title="OpenX Scenario Workbench", page_icon="🛣️", layout="wide")


@st.cache_data(show_spinner=False)
def _load_public_demo():
    return fetch_public_demo()


@st.cache_data(show_spinner=False)
def _extract_pdf(pdf_data: bytes, filename: str, source_standard: str):
    return extract_scene_packages_from_pdf(pdf_data, filename, source_standard)


def _rows(items: list[object]) -> list[dict[str, object]]:
    return [asdict(item) for item in items]


def _render_table(items: list[object], language: str) -> None:
    rows = _rows(items)
    if rows:
        translated = [
            {tr(language, key): value for key, value in row.items()}
            for row in rows
        ]
        st.dataframe(translated, use_container_width=True, hide_index=True)
    else:
        st.info(tr(language, "no_items"))


def _render_result(
    bundle: ParseBundle,
    language: str,
    xosc_name: str,
    xodr_name: str,
) -> None:
    result = bundle.to_dict()
    st.divider()
    st.subheader(tr(language, "loaded_files"))

    mismatch = "road_file_mismatch" in bundle.warnings
    if bundle.scenario.road_file is None:
        relation = tr(language, "reference_unknown")
    elif mismatch:
        relation = tr(language, "reference_mismatch")
    else:
        relation = tr(language, "reference_match")

    file_columns = st.columns(3)
    file_columns[0].markdown(
        f"**OpenSCENARIO**  \n{xosc_name}  \n"
        f"{tr(language, 'standard')}: {bundle.scenario.revision or '—'}"
    )
    file_columns[1].markdown(
        f"**OpenDRIVE**  \n{xodr_name}  \n"
        f"{tr(language, 'standard')}: {bundle.road.revision or '—'}"
    )
    file_columns[2].markdown(
        f"**{tr(language, 'reference')}**  \n"
        f"{bundle.scenario.road_file or '—'}  \n{relation}"
    )

    labels = ["overview", "entities", "actions", "triggers", "road", "warnings"]
    tabs = st.tabs([tr(language, label) for label in labels])

    with tabs[0]:
        metrics = st.columns(4)
        metrics[0].metric(tr(language, "entities"), len(bundle.scenario.entities))
        metrics[1].metric(tr(language, "actions"), len(bundle.scenario.actions))
        metrics[2].metric(tr(language, "triggers"), len(bundle.scenario.triggers))
        metrics[3].metric(tr(language, "roads"), len(bundle.road.road_ids))
        st.markdown(f"**{tr(language, 'scenario')}**: {bundle.scenario.name or '—'}")
        st.caption(bundle.scenario.description or "—")
        st.markdown(f"#### {tr(language, 'positions')}")
        _render_table(bundle.scenario.positions, language)

    with tabs[1]:
        _render_table(bundle.scenario.entities, language)

    with tabs[2]:
        _render_table(bundle.scenario.actions, language)

    with tabs[3]:
        _render_table(bundle.scenario.triggers, language)

    with tabs[4]:
        metrics = st.columns(5)
        values = (
            ("roads", len(bundle.road.road_ids)),
            ("lanes", bundle.road.lane_count),
            ("junctions", bundle.road.junction_count),
            ("signals", bundle.road.signal_count),
            ("objects", bundle.road.object_count),
        )
        for column, (label, value) in zip(metrics, values):
            column.metric(tr(language, label), value)
        st.caption(
            f"{tr(language, 'total_length')}: {bundle.road.total_length:g} m · "
            f"{tr(language, 'lane_types')}: {bundle.road.lane_types or '—'} · "
            f"{tr(language, 'geometry_types')}: {bundle.road.geometry_types or '—'}"
        )

    with tabs[5]:
        if bundle.warnings:
            for warning in bundle.warnings:
                st.warning(tr(language, warning))
        else:
            st.success(tr(language, "checks_passed"))

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    with st.expander(tr(language, "details"), expanded=False):
        st.json(result)
    st.download_button(
        tr(language, "download"),
        payload,
        "openx-summary.json",
        "application/json",
    )


def _store_result(
    bundle: ParseBundle,
    xosc_name: str,
    xosc_data: bytes,
    xodr_name: str,
    xodr_data: bytes,
    source: str,
) -> None:
    st.session_state["inspection_result"] = {
        "bundle": bundle,
        "xosc_name": xosc_name,
        "xosc_data": xosc_data,
        "xodr_name": xodr_name,
        "xodr_data": xodr_data,
        "source": source,
    }


def _show_error(language: str, exc: Exception) -> None:
    if isinstance(exc, InputValidationError):
        st.error(tr(language, exc.code))
    elif isinstance(exc, DemoDownloadError):
        st.error(tr(language, "demo_download_error"))
    else:
        st.error(tr(language, "parse_error"))
    with st.expander(tr(language, "technical_details"), expanded=False):
        st.code(str(exc))


def _render_inspector(language: str) -> None:
    source = st.radio(
        tr(language, "input_source"),
        ["demo", "upload"],
        format_func=lambda value: tr(
            language, "public_demo" if value == "demo" else "upload_files"
        ),
        horizontal=True,
    )

    if source == "demo":
        st.info(tr(language, "demo_intro"))
        st.markdown(f"[{tr(language, 'demo_source')}]({ESMINI_REPOSITORY})")
        if st.button(tr(language, "load_demo"), type="primary", use_container_width=True):
            try:
                with st.spinner(tr(language, "loading_demo")):
                    demo = _load_public_demo()
                    bundle = inspect_pair(
                        InputFile(demo.xosc_name, demo.xosc_data),
                        InputFile(demo.xodr_name, demo.xodr_data),
                    )
                _store_result(
                    bundle,
                    demo.xosc_name,
                    demo.xosc_data,
                    demo.xodr_name,
                    demo.xodr_data,
                    source,
                )
            except Exception as exc:  # noqa: BLE001 - converted to a user-facing error
                _show_error(language, exc)
    else:
        left, right = st.columns(2)
        with left:
            xosc = st.file_uploader(tr(language, "xosc"), type=["xosc"])
        with right:
            xodr = st.file_uploader(tr(language, "xodr"), type=["xodr"])

        if st.button(tr(language, "inspect"), type="primary", use_container_width=True):
            if not xosc or not xodr:
                st.warning(tr(language, "need_files"))
            else:
                try:
                    bundle = inspect_pair(
                        InputFile(xosc.name, xosc.getvalue()),
                        InputFile(xodr.name, xodr.getvalue()),
                    )
                    _store_result(
                        bundle,
                        xosc.name,
                        xosc.getvalue(),
                        xodr.name,
                        xodr.getvalue(),
                        source,
                    )
                except Exception as exc:  # noqa: BLE001 - converted to a user-facing error
                    _show_error(language, exc)

    stored = st.session_state.get("inspection_result")
    if stored and stored["source"] == source:
        _render_result(
            stored["bundle"],
            language,
            stored["xosc_name"],
            stored["xodr_name"],
        )


def _render_retrieval(language: str) -> None:
    st.caption(tr(language, "retrieval_intro"))
    pdf_file = st.file_uploader(
        tr(language, "pdf_source"),
        type=["pdf"],
        key="retrieval_pdf",
    )
    source_standard = st.text_input(
        tr(language, "source_standard"),
        placeholder=tr(language, "source_standard_placeholder"),
    )
    selected_package = None
    if pdf_file:
        try:
            packages = _extract_pdf(pdf_file.getvalue(), pdf_file.name, source_standard.strip())
            if packages:
                selected_package = st.selectbox(
                    tr(language, "scene_package"),
                    packages,
                    format_func=lambda item: f"{item.package_id} · {item.title}",
                )
                evidence = selected_package.evidence[0]
                st.caption(
                    tr(language, "pdf_evidence").format(
                        pages=f"{evidence.page_start}–{evidence.page_end}",
                        section=evidence.section_id,
                    )
                )
            else:
                st.warning(tr(language, "no_scene_packages"))
        except Exception as exc:  # noqa: BLE001 - PDF failures are shown beside the input
            st.error(f"{tr(language, 'pdf_parse_error')}: {exc}")

    library_files = st.file_uploader(
        tr(language, "asset_files"),
        type=["xosc", "xodr"],
        accept_multiple_files=True,
        key="asset_library_files",
    )
    query_text = st.text_area(
        tr(language, "retrieval_query"),
        placeholder=tr(language, "retrieval_placeholder"),
    )

    stored = st.session_state.get("inspection_result")
    if stored:
        st.caption(tr(language, "current_pair_hint"))

    if st.button(tr(language, "search_assets"), type="primary", use_container_width=True):
        files = [AssetFile(item.name, item.getvalue()) for item in library_files]
        if not files and stored:
            files = [
                AssetFile(stored["xosc_name"], stored["xosc_data"]),
                AssetFile(stored["xodr_name"], stored["xodr_data"]),
            ]
        if not files:
            st.warning(tr(language, "need_asset_files"))
            return
        if not query_text.strip() and not stored and not selected_package:
            st.warning(tr(language, "need_query"))
            return

        try:
            assets = build_catalog(files)
            query_bundle = stored["bundle"] if stored and not selected_package else None
            query = scene_package_to_query(selected_package) if selected_package else None
            if query and query_text.strip():
                query = replace(query, text=f"{query.text} {query_text.strip()}")
            effective_query = query_text.strip() or (
                query.text if query else bundle_query_text(query_bundle)
            )
            results = OpenXIndex(assets).search(
                effective_query,
                query_bundle=query_bundle,
                query=query,
                top_k=min(5, len(assets)),
            )
        except Exception as exc:  # noqa: BLE001 - shown as a focused catalog error
            st.error(f"{tr(language, 'catalog_error')}: {exc}")
            return

        st.subheader(tr(language, "retrieval_results"))
        st.caption(tr(language, "asset_count").format(count=len(assets)))
        rows = [
            {
                tr(language, "rank"): rank,
                tr(language, "scenario"): result.asset.title,
                tr(language, "score"): result.score,
                tr(language, "vector_score"): result.vector_score,
                tr(language, "scenario_score"): result.scenario_score,
                tr(language, "road_score"): result.road_score,
                tr(language, "reuse_level"): tr(language, result.reuse_level),
                "XOSC": result.asset.xosc_name,
                "XODR": result.asset.xodr_name,
                tr(language, "evidence"): ", ".join(
                    tr(language, reason) for reason in result.reasons
                ),
                tr(language, "differences"): "; ".join(
                    f"{item.category}: {item.requested} → {item.action}"
                    for item in result.differences
                ) or tr(language, "no_differences"),
            }
            for rank, result in enumerate(results, start=1)
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


heading, language_control = st.columns([7, 1])
with language_control:
    language_label = st.selectbox(
        "语言 / Language",
        ["中文", "English"],
        label_visibility="collapsed",
    )
language = "zh" if language_label == "中文" else "en"

with heading:
    st.title(tr(language, "title"))
st.caption(tr(language, "subtitle"))

inspection_tab, retrieval_tab = st.tabs(
    [tr(language, "inspection_workspace"), tr(language, "asset_retrieval")]
)
with inspection_tab:
    _render_inspector(language)
with retrieval_tab:
    _render_retrieval(language)
