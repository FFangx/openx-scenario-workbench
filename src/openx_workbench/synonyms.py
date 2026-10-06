"""Colloquial search words mapped to the terms scenario libraries use (ported from ScenarioManager).

People search with everyday words (急刹, 加塞, 鬼探头); assets are titled and described in test
terms (制动, 前车切入, 横穿). `expand_query` appends the terms a search text refers to before it
is encoded, so free-text recall meets the library halfway. Aliases shorter than two characters
never match, so a single character cannot set off a term.
"""

from __future__ import annotations

import re

# Behaviors: the library term, then words people use for it.
ACTION_SYNONYMS: dict[str, tuple[str, ...]] = {
    "制动": ("急刹", "急刹车", "紧急刹车", "刹车", "紧急制动", "猛刹车", "全力制动"),
    "换道": ("超车", "变道", "并线", "变道超车", "借道超车", "换车道"),
    "横穿": ("行人横穿", "鬼探头", "人过马路", "横穿马路", "穿行"),
    "前车切入": ("加塞", "插队", "切入", "切进来", "强行并入", "别车"),
    "跟车": ("跟随", "跟随前车", "排队行驶", "跟车行驶", "跟车巡航"),
    "启停": ("走走停停", "堵车跟车", "拥堵跟车", "低速启停", "走停"),
    "避障": ("紧急避让", "紧急避障", "躲避障碍", "避让", "绕行"),
    "制动停车": ("紧急停车", "急停", "紧急停止", "停车制动"),
    "前车切出": ("前车变道离开", "前车并线离开"),
}

# Tested functions: the abbreviation, then the words people use for it.
FUNCTION_SYNONYMS: dict[str, tuple[str, ...]] = {
    "AEB": ("自动刹车", "紧急制动", "自动紧急制动", "防追尾", "自动避撞", "碰撞预防", "自动制动", "主动制动",
            "自动刹停", "紧急刹停", "防碰撞", "障碍物探测与响应", "障碍物响应"),
    "ACC": ("自动跟车", "自适应巡航", "跟车巡航", "定速跟车", "跟车", "自适应定速", "巡航跟车", "定速巡航", "巡航",
            "巡航系统", "巡航辅助", "跟车系统", "车速巡航"),
    "APA": ("自动泊车", "停车入库", "自动停车", "泊车辅助", "智能泊车", "自动入库", "泊车", "自动泊入", "自动泊出",
            "停车辅助", "泊车系统"),
    "NOA": ("高速领航", "领航辅助", "智能领航", "高速辅助", "自动驾驶辅助", "领航驾驶", "高速自动驾驶", "领航系统",
            "导航辅助驾驶", "智驾领航", "城市领航", "领航辅助驾驶", "高快领航"),
    "LKA": ("车道保持", "压线纠正", "保持车道", "车道居中", "道路居中保持", "居中保持", "车道保持辅助", "方向纠偏"),
    "LDW": ("偏线预警", "车道偏离", "压线报警", "偏道报警", "车道偏离预警", "跑偏预警", "压线提醒", "偏离提醒"),
    "LDP": ("车道偏离保护", "跑偏纠偏", "偏离修正", "车道偏离干预", "偏离保护", "车道纠偏", "偏离防护"),
    "ALCA": ("自动变道", "自动换道", "辅助变道", "智能换道", "自动并线", "超车", "变道", "并线", "自动超车", "并道",
             "变道辅助", "换道", "换道试验"),
    "FCW": ("前碰撞预警", "追尾预警", "碰撞报警", "前向碰撞", "前方碰撞预警", "碰撞提醒", "追尾提醒", "前碰撞提醒"),
    "BSM": ("盲区监测", "盲区预警", "侧方来车", "并线辅助", "侧盲区", "盲点监测", "盲点提醒", "侧后方来车提醒"),
    "DOW": ("开门预警", "开门警示", "安全开门", "车门开启预警", "开门防撞", "下车开门预警", "开门防碰撞"),
    "RCTA": ("倒车预警", "倒车碰撞", "后方来车", "倒车横向预警", "倒车横穿预警", "后方穿行预警", "倒车侧向来车",
             "倒车横向来车预警", "后方横向来车"),
    "LSS": ("车道支持", "道路保持", "车道支撑系统", "车道支持系统", "横向辅助", "车道辅助系统", "行驶支持系统"),
    "TSA": ("交通标志识别", "限速识别", "标志识别", "交通标志辅助", "限速牌识别", "交通标识识别", "标牌识别", "限速提醒",
            "限速", "限速试验", "限速标志"),
}

# Targets: the library term, then words people use for it. Ambiguous short words ("人", "车辆",
# "静止") are left out: as substrings they would match almost anything.
TARGET_SYNONYMS: dict[str, tuple[str, ...]] = {
    "乘用车": ("轿车", "小车", "汽车", "小汽车", "前车", "目标车"),
    "行人": ("路人", "穿行者", "步行者"),
    "摩托车": ("摩托", "电摩", "骑摩托", "摩托车手"),
    "自行车": ("单车", "骑自行车", "自行车手"),
    "电动自行车": ("电动车", "电瓶车", "电单车", "骑电动车"),
    "卡车": ("货车", "大车", "重车", "大货车"),
    "静止车辆": ("停着的车", "停驶车辆", "静止目标车"),
    "障碍物": ("临时障碍物", "纸箱", "褐色纸箱", "掉落物", "散落物", "散落货物"),
}

# "乘用车" after these words is the vehicle under test (M1类车, 试验车辆为乘用车), not a target.
_GENERIC_CARS = frozenset({"乘用车", "轿车", "小车", "汽车", "小汽车"})
_EGO_MARKERS = ("试验车辆", "主车", "本车", "自车", "ego")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.casefold())


def _mentions(text: str, label: str, aliases: tuple[str, ...]) -> bool:
    return any(len(alias) >= 2 and _normalize(alias) in text for alias in (label, *aliases))


def _names_a_target(text: str, label: str, aliases: tuple[str, ...]) -> bool:
    """A target term occurs other than as the vehicle under test."""
    for alias in (_normalize(item) for item in (label, *aliases)):
        if len(alias) < 2:
            continue
        start = text.find(alias)
        while start != -1:
            before = text[max(0, start - 12):start]
            if alias not in _GENERIC_CARS or not (before.endswith("类") or any(marker in before for marker in _EGO_MARKERS)):
                return True
            start = text.find(alias, start + len(alias))
    return False


def query_terms(text: str) -> list[str]:
    """The library terms a search text refers to, in table order."""
    normalized = _normalize(text)
    terms = [label for table in (ACTION_SYNONYMS, FUNCTION_SYNONYMS) for label, aliases in table.items()
             if _mentions(normalized, label, aliases)]
    terms += [label for label, aliases in TARGET_SYNONYMS.items() if _names_a_target(normalized, label, aliases)]
    return list(dict.fromkeys(terms))


def expand_query(text: str) -> str:
    """The search text with the library terms it refers to appended: 急刹超车 -> 急刹超车 制动 换道 ALCA."""
    terms = [term for term in query_terms(text) if _normalize(term) not in _normalize(text)]
    return " ".join((text, *terms)) if terms else text
