"""Translate controlled business vocabulary, preserving source identifiers."""
import re
from .scene_package import STRUCTURE_KINDS, STRUCTURE_BEARINGS, STRUCTURE_FACING, STRUCTURE_ACTIONS, STRUCTURE_TURNS

LABELS = {
    "direct": "可直接复用", "modify": "修改后复用", "major_modify": "大幅修改后复用", "rebuild": "需要重建",
    "new_build": "需要新建", "review": "待复核", "signed_off": "复核后确认",
    "undecidable": "事实不足，无法判断", "partial": "部分事实待核对", "standards": "文件标准待复核",
    "recall": "仅相似召回", "no_candidates": "没有候选资产",
    "scenario_structure_match": "场景结构匹配", "road_structure_match": "道路结构匹配", "partial_match": "部分匹配",
    "parameter_resolution": "参数解析", "participant_topology": "参与者关系", "participant": "参与者",
    "ego_action": "主车动作", "action": "动作", "entity": "参与者", "trigger": "触发条件",
    "road": "道路", "road_type": "道路类型", "weather": "天气", "time_of_day": "时段",
    "ego_speed_kph": "主车速度（km/h）", "lane_count": "车道数", "ttc_value": "TTC（s）",
    "lane_direction": "车道方向", "curve_radius_m": "弯道半径（m）", "end_condition": "结束条件",
    "ego_speed": "主车速度", "ttc": "碰撞时间", "speed": "速度", "target_speed": "目标速度",
    "straight": "直道", "curve": "弯道", "junction": "交叉口", "motorway": "高速路", "parking": "停车场",
    "roundabout": "环岛", "road_missing": "道路文件缺失",
    "cruise": "匀速行驶", "speed_change": "变速", "stop": "刹停", "lane_change": "变道",
    "follow": "定距跟车", "static": "静止", "unknown": "未知", "missing": "缺失",
    "not_tested": "未测试", "playable": "可播放", "failed": "失败", "valid": "通过",
    "invalid": "未通过", "unsupported": "暂不支持", "unavailable": "未完成检查",
    "True": "是", "False": "否", "None": "未明确", "total": "综合相似度", "vector": "语义相似度",
    "scenario": "场景相似度", "structural": "结构相似度", "semantic": "语义相似度",
    "resolved scenario parameters": "已解析的场景参数", "Not recorded": "未记录",
    "modify storyboard action": "修改场景动作", "modify participant behavior": "修改参与者行为",
    "rebuild participant interaction": "重建参与者交互",
    "function": "被测功能", "unverified": "未核实事实", "environment": "环境", "parameter": "参数",
    "not extracted": "未提取", "confirm tested function": "核对被测功能", "change tested function": "调整被测功能",
    "verify ego behavior": "核对主车行为", "modify ego behavior": "修改主车行为",
    "resolve parameter before confirming reuse": "解析参数后再确认复用", "verify declared requirement": "核对原文需求",
    "verify road classification": "核对道路分类", "select or modify OpenDRIVE": "选择或修改道路文件",
    "modify start trigger": "修改开始触发条件", "set target initial speeds": "设置目标初始速度",
    "set participant initial speed": "设置参与者初始速度",
    "verify or change environment": "核对或修改环境",
    "verify and set parameter in XOSC": "核对并设置场景参数", "set parameter in XOSC": "设置场景参数",
    "relations": "参与者关系", "participant_signature": "参与者", "background_participant": "背景参与者",
    "no additional participant": "无多余参与者", "remove extra participant": "删除多余参与者",
    "keep or remove background participants": "保留或删除背景参与者", "venue_features": "场地特征", "lane_marking": "车道线",
    "parking_operation": "泊车操作", "test_intent": "试验目的", "road_class": "道路类型",
    "lateral_direction": "横向方向", "fog_visibility_m": "能见度（m）", "ttc_s": "TTC（s）", "distance_m": "距离（m）",
    "car": "乘用车", "truck": "卡车", "pedestrian": "行人", "bicycle": "两轮车",
    "ahead": "正前方", "behind": "正后方", "same": "同向", "opposite": "对向",
    "dry": "晴天", "rain": "雨天", "fog": "雾天", "snow": "雪天", "day": "日间", "night": "夜间",
    "combined": "综合相似度",
    "relation": "参与者关系", "occludes": "遮挡", "not found": "未发现",
    "place an occluding participant": "布置遮挡参与者",
    "driver_intervention": "驾驶员干预", "no driver_intervention": "无驾驶员干预",
    "add driver input override": "添加驾驶员输入接管", "remove driver input override": "移除驾驶员输入接管",
    "park_in": "泊入", "park_out": "泊出", "no parking": "无泊车操作", "change parking operation": "调整泊车操作",
    "placement": "摆位", "move start position or retime trigger": "调整起点或触发时机",
    "turn standing participant": "调整静止参与者朝向",
    "not scripted": "文件未写", "confirm the system changes lanes": "核对被测系统自行换道",
    "ego_route": "主车路线", "not read": "未读出", "verify the ego's route": "核对主车路线",
    "change the ego's route": "修改主车路线",
    "traffic_light": "交通信号灯", "speed_limit": "限速标志", "no traffic_light": "无交通信号灯",
    "no speed_limit": "无限速标志", "no speed limit sign": "无限速标志", "road file missing": "道路文件缺失",
    "verify traffic control": "核对交通控制设施", "add traffic control to OpenDRIVE": "在道路文件中添加交通控制设施",
    "verify speed limit signs": "核对限速标志", "add a speed limit sign to OpenDRIVE": "在道路文件中添加限速标志",
    "set the speed limit sign value": "调整限速标志数值",
    "variant": "任选其一", "select or build the other alternatives": "其余任选项另选或另建素材",
}
LABELS.update({f"ego_turn={value}": "主车" + label for label, value in STRUCTURE_TURNS.items()})
for vocabulary in (STRUCTURE_KINDS, STRUCTURE_BEARINGS, STRUCTURE_FACING, STRUCTURE_ACTIONS):
    LABELS.update({value: key for key, value in vocabulary.items()})


def display(value, language="zh"):
    text = str(value if value is not None else "—")
    if language != "zh":
        return text
    if text in LABELS:
        return LABELS[text]
    # Translate tokens in controlled signatures, never file paths or XML identifiers.
    return re.sub(r"[a-z][a-z_]+", lambda m: LABELS.get(m[0], m[0]), text)


def difference_text(difference, language):
    category = display(difference.category, language)
    requested = display(difference.requested, language)
    action = display(difference.action, language)
    if language == "zh" and action == difference.action:
        action = "核对原文与候选结构" if not difference.verified else "调整候选场景"
    return f"{category}：{requested} → {action}"


def asset_display_title(asset, language="zh"):
    """Short display names for machine-named assets; source titles stay intact."""
    title = asset.title or asset.xosc_name
    if language != "zh" or title.count("_") < 3:
        return title
    functions = {"LDW": "车道偏离预警", "LKA": "车道保持辅助", "AEB": "自动紧急制动",
                 "ACC": "自适应巡航", "DOW": "开门预警", "RCTA": "后方交叉来车预警",
                 "FCW": "前向碰撞预警", "BSD": "盲区监测", "LCA": "变道辅助"}
    function = asset.classification.get("function_type", "")
    if function not in functions:
        token = re.search(r"(?:^|_)(" + "|".join(functions) + r")(?:_|$)", title)
        function = token[1] if token else function
    if function not in functions:
        return title
    parts = [functions[function]]
    road = asset.classification.get("label_road_type", "")
    if road and road != "未知":
        parts.append(road)
    # Preserve explicit name tokens as a name abbreviation, not inferred facts.
    speed = re.search(r"(?:^|_)ego(\d+(?:\.\d+)?)kph(?:_|$)", title)
    if speed:
        parts.append(f"主车 {speed[1]} km/h")
    direction = {"right": "右侧", "left": "左侧", "L2R": "左向右", "R2L": "右向左"}
    tail = title.rsplit("_", 1)[-1]
    if tail in direction:
        parts.append(direction[tail])
    return " · ".join(parts)
