from __future__ import annotations

import json

import streamlit as st

from openx_workbench.i18n import tr
from openx_workbench.parser import parse_bundle


st.set_page_config(page_title="OpenX Scenario Workbench", page_icon="🛣️", layout="wide")
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

left, right = st.columns(2)
with left:
    xosc = st.file_uploader(tr(language, "xosc"), type=["xosc", "xml"])
with right:
    xodr = st.file_uploader(tr(language, "xodr"), type=["xodr", "xml"])

if st.button(tr(language, "inspect"), type="primary", use_container_width=True):
    if not xosc or not xodr:
        st.warning(tr(language, "need_files"))
    else:
        try:
            bundle = parse_bundle(xosc.getvalue(), xodr.getvalue(), xodr.name)
            result = bundle.to_dict()
            st.subheader(tr(language, "scenario"))
            a, b, c = st.columns(3)
            a.metric(tr(language, "entities"), len(bundle.scenario.entities))
            b.metric(tr(language, "actions"), len(bundle.scenario.actions))
            c.metric(tr(language, "triggers"), len(bundle.scenario.triggers))
            st.subheader(tr(language, "road"))
            a, b = st.columns(2)
            a.metric(tr(language, "roads"), len(bundle.road.road_ids))
            b.metric(tr(language, "lanes"), bundle.road.lane_count)
            if bundle.warnings:
                st.subheader(tr(language, "warnings"))
                for warning in bundle.warnings:
                    st.warning(tr(language, warning))
            payload = json.dumps(result, ensure_ascii=False, indent=2)
            with st.expander(tr(language, "details"), expanded=True):
                st.json(result)
            st.download_button(tr(language, "download"), payload, "openx-summary.json", "application/json")
        except Exception as exc:
            st.error(f"{tr(language, 'parse_error')}: {exc}")
