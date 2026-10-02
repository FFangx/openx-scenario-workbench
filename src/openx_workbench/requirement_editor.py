"""Native fact controls; narrative never silently overrides structured facts."""
from copy import deepcopy
from typing import get_args

import streamlit as st
import pandas as pd

from .pdf_v2 import scene_schemas as schema
from .asset_management import value_label


def edit_structure(structure, language):
    zh = language == "zh"
    draft = deepcopy(structure)
    params = draft.setdefault("params", {})

    def choice(target, field, label, annotation, default="未知"):
        options = list(get_args(annotation))
        current = target.get(field, default)
        target[field] = st.selectbox(label, options, index=options.index(current),
                                     format_func=lambda v: value_label(v, language))

    def many(target, field, label, annotation):
        target[field] = st.multiselect(label, list(get_args(annotation)), default=target.get(field, []),
                                       format_func=lambda v: value_label(v, language))

    left, right = st.columns(2)
    with left:
        choice(draft, "road_class", "道路类型" if zh else "Road type", schema.RoadClass)
        choice(draft, "tested_function", "被测功能" if zh else "Tested function", schema.TestedFunction)
        many(draft, "ego_actions", "主车动作" if zh else "Ego actions", schema.EgoAction)
    with right:
        choice(draft, "test_intent", "试验目的" if zh else "Test intent", schema.TestIntent)
        choice(params, "weather", "天气" if zh else "Weather", schema.Weather)
        choice(params, "time_of_day", "时段" if zh else "Time of day", schema.TimeOfDay)
    st.caption("空白表示原文未明确；只有下面的数值字段参与匹配。文字说明不会自动转换为参数。" if zh else
               "Blank means unspecified. Matching uses these numeric fields; narrative does not automatically update them.")
    numeric = (("ego_speed_kph", "主车速度（km/h）", "Ego speed (km/h)"),
               ("ttc_value", "碰撞时间 TTC（s）", "Time to collision (s)"),
               ("lane_count", "车道数量", "Lane count"),
               ("curve_radius_m", "弯道半径（m）", "Curve radius (m)"),
               ("fog_visibility_m", "能见度（m）", "Visibility (m)"))
    cols = st.columns(2)
    for i, (field, cn, en) in enumerate(numeric):
        with cols[i % 2]:
            params[field] = st.number_input(cn if zh else en, min_value=0.0,
                                           value=float(params[field]) if params.get(field) is not None else None)
    params["end_condition"] = st.text_input("结束条件" if zh else "End condition", value=params.get("end_condition") or "") or None
    many(draft, "semantic_triggers", "触发条件类型" if zh else "Trigger types", schema.SemanticTrigger)
    st.markdown("**其他参与者**" if zh else "**Other participants**")
    st.caption("可添加或删除行；动作可用逗号分隔。原文未说明的字段请保留未知。" if zh else
               "Add or remove rows. Separate actions with commas. Keep unspecified facts unknown.")
    headings = {"kind": "类型", "bearing": "相对方位", "facing": "朝向", "actions": "动作", "age": "年龄"} if zh else {
        "kind": "Type", "bearing": "Bearing", "facing": "Facing", "actions": "Actions", "age": "Age"}
    actors = [{**item, "actions": ", ".join(item.get("actions", []))} for item in draft.get("participants", [])]
    table = pd.DataFrame(actors, columns=list(headings))
    annotations = {"kind": schema.ParticipantKind, "bearing": schema.Bearing, "facing": schema.Facing, "age": schema.PedestrianAge}
    edited = st.data_editor(table, hide_index=True, num_rows="dynamic", width="stretch",
                            column_config={field: st.column_config.SelectboxColumn(headings[field], options=list(get_args(annotation)), required=True)
                                           for field, annotation in annotations.items()} | {
                                "actions": st.column_config.TextColumn(headings["actions"], help="静止, 匀速行驶, 变速, 刹停, 变道, 定距跟车" if zh else "Use schema action names")})
    draft["participants"] = [{field: (str(item[field]).strip() if pd.notna(item[field]) else
                                      ("未知方位" if field == "bearing" else "未知")) for field in annotations} | {
        "actions": [value.strip() for value in str(item["actions"]).replace("，", ",").split(",") if value.strip()]
        if pd.notna(item["actions"]) else []} for item in edited.to_dict("records")]
    # Keep topology, target speeds, relations and specialized fields intact.
    # Advanced editing remains available separately for uncommon structures.
    return draft
