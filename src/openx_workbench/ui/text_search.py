"""Text search page: similar assets without a reuse decision."""

from __future__ import annotations

import streamlit as st

from openx_workbench.catalog import OpenXAsset
from openx_workbench.retrieval import RetrievalResult
from openx_workbench.ui.assets import asset_summary, preview_controls
from openx_workbench.ui.common import encoder_control, index_for, tx


def text_search_page(language: str) -> None:
    st.subheader(tx(language, "text_search"))
    catalog: list[OpenXAsset] = st.session_state.get("catalog", [])
    if not catalog:
        st.info(tx(language, "no_assets"))
        return
    query = st.text_input("Search scenario assets" if language == "en" else "描述要查找的场景",
                          key="text_search_query")
    encoder = encoder_control(language)
    if st.button(tx(language, "search"), type="primary", disabled=not query.strip(), key="text_search_button", icon=":material/search:"):
        try:
            st.session_state.text_results = index_for(catalog, encoder).search(
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
    asset_summary(asset, language)
    version = st.session_state.get("asset_versions", {}).get(asset.asset_id)
    if version:
        preview_controls(version, language)
