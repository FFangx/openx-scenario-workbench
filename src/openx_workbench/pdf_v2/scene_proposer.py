"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Iterable, Sequence

from .figures import Figure
from .models import SectionTree
from .shared_containers import SharedContainerCandidate

SCENE_PROPOSER_VERSION = "scene-first-proposer-v1"
DEFAULT_SCENE_PROMPT_VERSION = "scene-first-prompt-v1"

MAX_OUTPUT_TOKENS = 64_000

MAX_INPUT_CHARS = 600_000

NODE_TEXT_LIMIT = 0

_PROMPT_SCENE_FIRST_V1 = """你是汽车测试标准的场景抽取专家。用户会给你一份完整的测试规程文档，按文档顺序逐节列出，每节带唯一 node_id、层级和正文。

你的任务：读完整份文档，列出其中定义的**全部试验场景**。

「一个试验场景」的判定标准：
- 它描述一次可独立执行的试验：有明确的被试车（ego）行为、目标物/环境、以及触发-结束的过程
- 它是场景搭建师会在仿真器里搭建的一个独立条目
- 它不是：术语定义、评分方法、管理规定、通用试验条件、目标物规格表

场景的构成：
- anchor_node_id：这个场景的**主节点**（场景的标题节点；若场景由若干子节点组成，取其共同父节点）
- member_node_ids：构成这个场景的全部节点（含 anchor 自身及其从属的工况/步骤/判定等子节点）
- shared_container_node_ids：**不在该场景子树内、但该场景执行时必须遵守的章节**。
  标准文档的常见写法是：先并列写若干场景，最后单开一节写「以上场景共用的
  试验要求 / 结束条件 / 注意事项 / 有效性判断方法」。这些章节虽然物理上不属于
  任何一个场景，但它们是每个场景的组成部分——搭建师搭这个场景时必须照做。
  请为**每个**场景逐一判断：它引用了哪些这样的章节。
  一个共享章节可以同时被多个场景引用，请在每个相关场景里都列出。

用户输入的末尾附有一份「疑似共享章节候选清单」，由确定性规则按标题关键词
预筛得到。它是**高召回、低精确**的（会有误报），仅供你定位，不是答案：
- 候选里确实是共用要求的，请挂到相应场景的 shared_container_node_ids
- 候选里其实属于某个场景自己的（如该场景专属的试验步骤），请放进那个场景的 member_node_ids
- 候选里其实是文档级通用配置（不针对具体场景，如「试验道路」「试验天气」）的，
  请放进顶层 shared_config_node_ids
- 清单之外的节点，只要你判断它是某场景的共用要求，同样可以列进 shared_container_node_ids

严格输出以下 JSON，不要任何额外文字：
{
  "scenes": [
    {
      "name": "场景名（简短中文）",
      "story": "一句话讲清这个场景发生了什么（ego 做什么、遇到什么、如何结束）",
      "actors": ["ego", "target_vehicle", "vru", "static_object", "occluder", "traffic_element", "other" 中的若干],
      "anchor_node_id": "...",
      "member_node_ids": ["...", "..."],
      "shared_container_node_ids": ["...", "..."],
      "confidence": 0.0
    }
  ],
  "shared_config_node_ids": ["...", "..."]
}

要求：
- 所有 node_id 必须是输入中真实出现过的 node_id，不得编造
- 宁可把粒度定在「搭建师会当成一个条目」的层级，也不要把同一场景拆成多个
- confidence 是你对该场景判定的把握（0-1）
"""

_PROMPT_SCENE_FIRST_V2 = """你是汽车测试标准的场景抽取专家。用户会给你一份完整的测试规程文档，按文档顺序逐节列出，每节带唯一 node_id、层级和正文。

你的任务有两个：
（一）读完整份文档，列出其中定义的**全部试验场景**；
（二）为每个场景，把文档文字描述的**场景结构**翻译成规定的结构化字段。

「一个试验场景」的判定标准：
- 它描述一次可独立执行的试验：有明确的被试车（ego）行为、目标物/环境、以及触发-结束的过程
- 它是场景搭建师会在仿真器里搭建的一个独立条目
- 它不是：术语定义、评分方法、管理规定、通用试验条件、目标物规格表

场景的构成：
- anchor_node_id：这个场景的**主节点**（场景的标题节点；若场景由若干子节点组成，取其共同父节点）
- member_node_ids：构成这个场景的全部节点（含 anchor 自身及其从属的工况/步骤/判定等子节点）
- shared_container_node_ids：**不在该场景子树内、但该场景执行时必须遵守的章节**。
  标准文档的常见写法是：先并列写若干场景，最后单开一节写「以上场景共用的
  试验要求 / 结束条件 / 注意事项 / 有效性判断方法」。这些章节虽然物理上不属于
  任何一个场景，但它们是每个场景的组成部分——搭建师搭这个场景时必须照做。
  请为**每个**场景逐一判断：它引用了哪些这样的章节。
  一个共享章节可以同时被多个场景引用，请在每个相关场景里都列出。

用户输入的末尾附有一份「疑似共享章节候选清单」，由确定性规则按标题关键词
预筛得到。它是**高召回、低精确**的（会有误报），仅供你定位，不是答案：
- 候选里确实是共用要求的，请挂到相应场景的 shared_container_node_ids
- 候选里其实属于某个场景自己的（如该场景专属的试验步骤），请放进那个场景的 member_node_ids
- 候选里其实是文档级通用配置（不针对具体场景，如「试验道路」「试验天气」）的，
  请放进顶层 shared_config_node_ids
- 清单之外的节点，只要你判断它是某场景的共用要求，同样可以列进 shared_container_node_ids

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
场景结构（structure）—— 只能用下列取值，**不得自创**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

这些字段要和已有场景库的描述方式对齐，所以取值是封闭的。写了枚举以外的词，
该字段会被丢弃，等于白写。

road_class（道路类型，单选）：
  直道 / 弯道 / 交叉口 / 环岛 / 停车场 / 匝道合流 / 高速路 / 未知

ego_actions（主车行为，可多选）：
  匀速行驶 / 变速 / 刹停 / 变道 / 定距跟车 / 被测系统控制 / 未知
  - 「被测系统控制」用于 AEB 介入、APA 自动泊车这类由被测系统接管主车的场景
  - 主车匀速开着等目标出现，就是「匀速行驶」

participants（除主车外的参与者，逐个列出）：
  kind（单选）：乘用车 / 卡车 / 客车 / 厢式车 / 挂车 / 摩托车 / 两轮车 / 三轮车 / 行人 / 障碍物 / 未知
    - 「两轮车」指自行车、电动自行车；「障碍物」指锥桶、纸箱、壁障等非交通参与者
  bearing（相对主车的方位，单选）：
    正前方 / 正后方 / 并排同车道 / 左前方 / 左后方 / 左并排 / 右前方 / 右后方 / 右并排 / 未知方位
  facing（相对主车的朝向，单选）：同向 / 对向 / 横向 / 未知
    - **横穿的目标就是「横向」**，不要另造词
  actions（可多选）：静止 / 匀速行驶 / 变速 / 刹停 / 变道 / 定距跟车
    - 「刹停」= 本来在跑，然后刹车减速（前车急刹、前车制动都属此类）
    - 「静止」= 从头到尾不动（前车静止、路边停放的车）
    - **「刹停」和「静止」是两个完全不同的场景，务必分清**
    - 切入 / 切出请写「变道」，方位与朝向会表达出它是从哪切的

relations（参与者之间的关系，可为空）：
  格式 [主体, 关系, 客体]，关系目前只有「遮挡」，主体与客体用上面的 kind 取值。
  - 「遮挡」= 一个物体挡住了主车看向另一个物体的视线。
    典型：路边停放的车挡住了突然横穿的行人（鬼探头）。
  - 这是三方几何关系，光靠「每个目标在哪个方位」表达不出来，所以要单独列。
  - 例：[["乘用车", "遮挡", "行人"]]

semantic_triggers（试验的触发条件，可多选，可为空）：
  TTC / 相对距离 / 绝对距离 / 车头时距 / 速度 / 相对速度
  - 只填**描述危险程度**的条件（如「TTC 达到 2.5s 时目标开始横穿」）
  - 「仿真第 3 秒」「上一步完成后」「车开到某个位置」这类是脚本调度手段，**不要填**

params（参数，文档没写就留 null / 空数组 / 未知）：
  ego_speed_kph：主车试验车速（数字，kph）
  target_speeds_kph：目标物速度（数字数组，kph）
  weather：晴天 / 雨天 / 雾天 / 雪天 / 沙尘 / 未知
  time_of_day：日间 / 夜间 / 未知
  ttc_value：触发用的 TTC 阈值（数字，秒）

🔴 **文档没写的，一律填「未知」/ null / 空数组，绝对不要猜。**
这些结果会拿去和真实场景库比对，猜错比留空的代价大得多——
留空只是少一条线索，猜错会让工程师照着错的去改场景。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

严格输出以下 JSON，不要任何额外文字：
{
  "scenes": [
    {
      "name": "场景名（简短中文）",
      "story": "一句话讲清这个场景发生了什么（ego 做什么、遇到什么、如何结束）",
      "actors": ["ego", "target_vehicle", "vru", "static_object", "occluder", "traffic_element", "other" 中的若干],
      "anchor_node_id": "...",
      "member_node_ids": ["...", "..."],
      "shared_container_node_ids": ["...", "..."],
      "confidence": 0.0,
      "structure": {
        "road_class": "直道",
        "ego_actions": ["匀速行驶"],
        "participants": [
          {"kind": "乘用车", "bearing": "正前方", "facing": "同向", "actions": ["静止"]}
        ],
        "relations": [],
        "semantic_triggers": ["TTC"],
        "params": {
          "ego_speed_kph": null,
          "target_speeds_kph": [],
          "weather": "未知",
          "time_of_day": "未知",
          "ttc_value": null
        }
      }
    }
  ],
  "shared_config_node_ids": ["...", "..."]
}

要求：
- 所有 node_id 必须是输入中真实出现过的 node_id，不得编造
- 宁可把粒度定在「搭建师会当成一个条目」的层级，也不要把同一场景拆成多个
- confidence 是你对该场景判定的把握（0-1）
- structure 的每个字段只能用上面列出的取值
"""

_V2_ROAD_CLASS_BLOCK = """road_class（道路类型，单选）：
  直道 / 弯道 / 交叉口 / 环岛 / 停车场 / 匝道合流 / 高速路 / 未知
"""

_V3_ROAD_CLASS_BLOCK = """road_class（道路类型，单选）—— 问的是**这次试验在什么场地进行**：
  按下面的顺序判断，**能判成靠前的就不要退回靠后的**：
  停车场 / 环岛 / 匝道合流 / 交叉口 / 弯道 / 高速路 / 直道 / 未知
  - **「直道」是兜底值**，只有当这段路确实就是一段普通直路时才用它。
  - 泊车类试验（泊入 / 泊出 / 车位 / 库位 / 自动泊车 / 代客泊车 / 记忆泊车 /
    遥控泊车 / 召唤）**一律填「停车场」**。即使文档写着「测试道路至少包含
    一条直道」，那说的是停车场内部的通道，**场地仍然是停车场**。
  - 同理：环岛通行填「环岛」；路口左转 / 右转 / 直行通过填「交叉口」；
    匝道汇入 / 驶出填「匝道合流」；沿弯道行驶填「弯道」。
  - 只有当文档既没交代场地、也无法从试验内容判断时，才填「未知」。
"""

_PROMPT_SCENE_FIRST_V3 = _PROMPT_SCENE_FIRST_V2.replace(
    _V2_ROAD_CLASS_BLOCK, _V3_ROAD_CLASS_BLOCK
)

_V4_TESTED_FUNCTION_BLOCK = """road_class（道路类型，单选）：
  直道 / 弯道 / 交叉口 / 环岛 / 停车场 / 匝道合流 / 高速路 / 未知

tested_function（这个试验在测哪个功能，单选）：
  NOA / AEB / ACC / LSS / APA / FCW / BSM / ALCA / RCTA / LDW / LDP / TSA /
  LKA / ELK / AVP / ISL / DFM / DAM / DOW / 未知
  - 问的是**被测系统是哪一个**，通常写在试验目的里：
    「测试 LDP 系统是否介入抑制偏离」→ LDP；「测试 DFM 系统报警」→ DFM。
  - 有些标准用带前缀的写法，请归到主功能上：
    City NOA / CNOA / 城市领航 / Highway NOA / HNOA / 高速领航 → 一律填 NOA
    BSD / 盲区检测 / 盲区监测 → 填 BSM
    ISLD / ISLI / ISLS / 限速识别 → 填 ISL
    代客泊车 / 记忆泊车 / 召唤 → 填 AVP；泊入 / 泊出 / 自动泊车 → 填 APA
  - **车道类的四个不要互相归并**，它们在场景库里是分开搭的：
    车道偏离预警（只报警不介入）→ LDW；车道偏离抑制/保持（会介入转向）→ LDP
    车道保持辅助（持续居中）→ LKA；紧急车道保持（防驶出/防对向碰撞）→ ELK
    只说「车道保持系统 / LSS」而分不出上面哪一种时 → 填 LSS
  - 🔴 **不要把场景代号当功能**：CCRs / CCRH / C2C / CPTA / CPLA / CPFAO /
    CSTA / TV1 / TV2 / VRU / ODD / MRM 这些是试验编号或参与者代号，不是被测功能。
    遇到它们要看上下文判断真正的被测功能（如 CCRs 属 AEB 或 FCW）。
  - 判不出来就填「未知」，**不要猜**。
"""

_PROMPT_SCENE_FIRST_V4 = _PROMPT_SCENE_FIRST_V2.replace(
    _V2_ROAD_CLASS_BLOCK, _V4_TESTED_FUNCTION_BLOCK
).replace(
    '        "road_class": "直道",\n',
    '        "road_class": "直道",\n        "tested_function": "AEB",\n',
)

_V4_PARTICIPANTS_HEAD = """participants（除主车外的参与者，逐个列出）：
  kind（单选）：乘用车 / 卡车 / 客车 / 厢式车 / 挂车 / 摩托车 / 两轮车 / 三轮车 / 行人 / 障碍物 / 未知
    - 「两轮车」指自行车、电动自行车；「障碍物」指锥桶、纸箱、壁障等非交通参与者
  bearing（相对主车的方位，单选）：
"""

_V5_PARTICIPANTS_HEAD = """participants（除主车外的参与者，逐个列出）：
  kind（单选）：乘用车 / 卡车 / 客车 / 厢式车 / 挂车 / 摩托车 / 两轮车 / 三轮车 / 行人 / 障碍物 / 未知
    - 「两轮车」指自行车、电动自行车；「障碍物」指锥桶、纸箱、壁障等非交通参与者
    - 🔴 **文档要求摆放的布景也要列进来**：锥桶阵、施工设施、纸箱、水马、立柱
      这类文字里写明要摆放/设置的东西，列成 kind=障碍物 的参与者。
      每**类**列一条即可，不必按个数重复（施工区 50 个锥桶 = 1 条「障碍物」）。
      只在叙述里提一句而不列出来，比对层会以为文档不需要它们。
  age（仅行人填，单选）：儿童 / 成人 / 未知
    - 「儿童目标」「小孩」→ 儿童；「成人」「成年行人」→ 成人；没写 → 未知
    - 非行人参与者一律填「未知」
  bearing（相对主车的方位，单选）：
"""

_V4_PARAMS_HEAD = """params（参数，文档没写就留 null / 空数组 / 未知）：
"""

_V5_NEW_TOP_FIELDS = """venue_features（场地特征，可多选，可为空）：
  隧道 / 收费站 / 服务区
  - 试验在这些特殊场地里/穿越这些设施时才填，普通道路留空
  - 与 road_class 不冲突：隧道里的直道 = road_class 直道 + venue_features [隧道]

lane_marking（涉事车道线的线型，单选）：实线 / 虚线 / 未知
  - 只在文档明确写了偏离/压过的车道线是实线还是虚线时才填，没写填「未知」

parking_operation（泊车方向，单选）：泊入 / 泊出 / 未知
  - 仅泊车类场景：驶入车位 = 泊入；驶出车位、召唤驶离 = 泊出
  - 非泊车场景一律填「未知」

test_intent（这个试验考核什么，单选）：
  功能试验 / 误作用试验 / 激活边界试验 / 驾驶员干预试验 / 未知
  - 功能试验：考核功能正常工作时的表现（绝大多数场景）
  - 误作用试验：考核系统**不应**动作（「不应触发」「不应误制动」「误作用」「误响应」）
  - 激活边界试验：考核激活条件 / ODD 边界（「尝试激活」「验证允许/不允许激活」，
    如车速边界、日间夜间边界、雨天雾天边界识别与响应）
  - 驾驶员干预试验：考核驾驶员干预/接管时系统的响应（拨杆换道、踩踏板、
    转向盘施加力矩、脱手、接管）
  - 分不清就填「未知」，不要猜

params（参数，文档没写就留 null / 空数组 / 未知）：
"""

_V4_PARAMS_TAIL = """  ttc_value：触发用的 TTC 阈值（数字，秒）
"""

_V5_PARAMS_TAIL = """  ttc_value：触发用的 TTC 阈值（数字，秒）
  lateral_direction：左 / 右 / 未知 —— 偏离或换道的方向（「向左偏离」→ 左）
  curve_radius_m：弯道半径（数字，米；文档写明才填）
  lane_count：车道数要求（数字；文档写明才填，「单向双车道」→ 2）
  lane_direction：单向 / 双向 / 未知 —— 上面的车道数说的是单向还是双向。
    文档没写方向就填「未知」，**不要按双向平分去猜**
  end_condition：试验结束条件的简短原文（如「碰撞或目标越过主车路径后 2s」；
    没写留 null）
"""

_V4_EXAMPLE_TOP = """        "relations": [],
        "semantic_triggers": ["TTC"],
"""

_V5_EXAMPLE_TOP = """        "relations": [],
        "semantic_triggers": ["TTC"],
        "venue_features": [],
        "lane_marking": "未知",
        "parking_operation": "未知",
        "test_intent": "功能试验",
"""

_V4_EXAMPLE_PARTICIPANT = (
    '          {"kind": "乘用车", "bearing": "正前方", "facing": "同向", "actions": ["静止"]}\n'
)

_V5_EXAMPLE_PARTICIPANT = (
    '          {"kind": "乘用车", "bearing": "正前方", "facing": "同向",'
    ' "actions": ["静止"], "age": "未知"}\n'
)

_V4_EXAMPLE_PARAMS = """          "weather": "未知",
          "time_of_day": "未知",
          "ttc_value": null
"""

_V5_EXAMPLE_PARAMS = """          "weather": "未知",
          "time_of_day": "未知",
          "ttc_value": null,
          "lateral_direction": "未知",
          "curve_radius_m": null,
          "lane_count": null,
          "lane_direction": "未知",
          "end_condition": null
"""

_PROMPT_SCENE_FIRST_V5 = (
    _PROMPT_SCENE_FIRST_V4
    .replace(_V4_PARTICIPANTS_HEAD, _V5_PARTICIPANTS_HEAD)
    .replace(_V4_PARAMS_HEAD, _V5_NEW_TOP_FIELDS)
    .replace(_V4_PARAMS_TAIL, _V5_PARAMS_TAIL)
    .replace(_V4_EXAMPLE_TOP, _V5_EXAMPLE_TOP)
    .replace(_V4_EXAMPLE_PARTICIPANT, _V5_EXAMPLE_PARTICIPANT)
    .replace(_V4_EXAMPLE_PARAMS, _V5_EXAMPLE_PARAMS)
)

_V5_EGO_ACTIONS_BLOCK = """ego_actions（主车行为，可多选）：
  匀速行驶 / 变速 / 刹停 / 变道 / 定距跟车 / 被测系统控制 / 未知
  - 「被测系统控制」用于 AEB 介入、APA 自动泊车这类由被测系统接管主车的场景
  - 主车匀速开着等目标出现，就是「匀速行驶」
"""

_V6_EGO_ACTIONS_BLOCK = """ego_actions（主车行为，可多选）：
  匀速行驶 / 变速 / 刹停 / 变道 / 定距跟车 / 倒车 / 被测系统控制 / 未知
  - 「被测系统控制」用于 AEB 介入、APA 自动泊车这类由被测系统接管主车的场景
  - 主车匀速开着等目标出现，就是「匀速行驶」
  - 「倒车」= 主车倒着行驶（倒车驶出车位、倒车通过通道这类），文档写明才填
"""

_V5_FN_ENUM_LINES = """tested_function（这个试验在测哪个功能，单选）：
  NOA / AEB / ACC / LSS / APA / FCW / BSM / ALCA / RCTA / LDW / LDP / TSA /
  LKA / ELK / AVP / ISL / DFM / DAM / DOW / 未知
"""

_V6_FN_ENUM_LINES = """tested_function（这个试验在测哪个功能，单选）：
  NOA / AEB / ACC / LSS / APA / FCW / BSM / ALCA / RCTA / LDW / LDP / TSA /
  LKA / ELK / AVP / ISL / DFM / DAM / DOW / 未知
  - 缩写含义：NOA 领航辅助 · AEB 自动紧急制动 · ACC 自适应巡航 · LSS 车道辅助统称 ·
    APA 自动泊车 · FCW 前碰预警 · BSM 盲区监测 · ALCA 自动变道 · RCTA 倒车横向来车预警 ·
    LDW 车道偏离预警 · LDP 车道偏离抑制 · TSA 交通标志辅助 · LKA 车道保持 ·
    ELK 紧急车道保持 · AVP 代客泊车 · ISL 智能限速 · DFM 疲劳监测 · DAM 注意力监测 ·
    DOW 开门预警
"""

_V5_FN_TAIL_LINE = """  - 判不出来就填「未知」，**不要猜**。
"""

_V6_FN_TAIL_LINE = """  - 判不出来就填「未知」，**不要猜**。

tested_function_raw（自由文本，可为 null）：
  tested_function 填了「未知」、但文档明确写了被测系统名字时，把文档的原始叫法
  抄在这里（如「CPD 儿童存在检测」「OMS 乘员监测系统」）。
  - 上面枚举里有的功能不用写这里；文档没写任何系统名就留 null
  - 这个字段不参与匹配，只供人工审核，别把整段场景描述抄进来
"""

_V5_END_CONDITION_LINES = """  end_condition：试验结束条件的简短原文（如「碰撞或目标越过主车路径后 2s」；
    没写留 null）
"""

_V6_END_CONDITION_LINES = """  fog_visibility_m：雾天能见度（数字，米）——「能见度不大于 200m」→ 200；
    文档只说「雾天」没给数值就留 null
  end_condition：试验结束条件的简短原文（如「碰撞或目标越过主车路径后 2s」；
    没写留 null）
"""

_V5_EXAMPLE_FN_LINE = '        "road_class": "直道",\n        "tested_function": "AEB",\n'

_V6_EXAMPLE_FN_LINE = (
    '        "road_class": "直道",\n        "tested_function": "AEB",\n'
    '        "tested_function_raw": null,\n'
)

_V5_EXAMPLE_PARAMS_TAIL = """          "lane_direction": "未知",
          "end_condition": null
"""

_V6_EXAMPLE_PARAMS_TAIL = """          "lane_direction": "未知",
          "fog_visibility_m": null,
          "end_condition": null
"""

_PROMPT_SCENE_FIRST_V6 = (
    _PROMPT_SCENE_FIRST_V5
    .replace(_V5_EGO_ACTIONS_BLOCK, _V6_EGO_ACTIONS_BLOCK)
    .replace(_V5_FN_ENUM_LINES, _V6_FN_ENUM_LINES)
    .replace(_V5_FN_TAIL_LINE, _V6_FN_TAIL_LINE)
    .replace(_V5_END_CONDITION_LINES, _V6_END_CONDITION_LINES)
    .replace(_V5_EXAMPLE_FN_LINE, _V6_EXAMPLE_FN_LINE)
    .replace(_V5_EXAMPLE_PARAMS_TAIL, _V6_EXAMPLE_PARAMS_TAIL)
)

_V6_AGE_LINES = """    - 非行人参与者一律填「未知」
"""

_V7_AGE_AND_SPEED_LINES = """    - 非行人参与者一律填「未知」
  speed_kph（这个参与者自己的初始速度，数字，km/h；文档没写留 null）
    - 「目标车以 20 km/h 行驶」→ 这辆目标车填 20；文档写明静止的目标填 0
    - 多个目标速度不同时，逐个填在对应的参与者上；
      分不清哪个速度属于哪个参与者就留 null，只写进 params.target_speeds_kph
"""

_V7_EXAMPLE_PARTICIPANT = (
    '          {"kind": "乘用车", "bearing": "正前方", "facing": "同向",'
    ' "actions": ["静止"], "age": "未知", "speed_kph": null}\n'
)

_PROMPT_SCENE_FIRST_V7 = (
    _PROMPT_SCENE_FIRST_V6
    .replace(_V6_AGE_LINES, _V7_AGE_AND_SPEED_LINES)
    .replace(_V5_EXAMPLE_PARTICIPANT, _V7_EXAMPLE_PARTICIPANT)
)

_V7_BEARING_LINES = """  bearing（相对主车的方位，单选）：
    正前方 / 正后方 / 并排同车道 / 左前方 / 左后方 / 左并排 / 右前方 / 右后方 / 右并排 / 未知方位
"""

_V8_BEARING_LINES = """  bearing（相对主车的方位，单选）：
    正前方 / 正后方 / 并排同车道 / 左前方 / 左后方 / 左并排 / 右前方 / 右后方 / 右并排 / 未知方位
    - 指**试验开始时**（主车驶近之前）目标所在的位置，不是相遇、碰撞那一刻的位置
    - 前后看纵向位置，左右看**所在车道**：在主车本车道 = 正前方 / 正后方；
      在左侧车道（含对向车道）= 左前方 / 左后方 / 左并排；右侧同理
    - 主车将要驶过的静止目标都在前方：路两侧停放的车 = 左前方 / 右前方，不是并排
    - 对向车道驶来的车（靠右行驶）= 左前方 + facing「对向」
"""

_V7_SPEED_TAIL = """      分不清哪个速度属于哪个参与者就留 null，只写进 params.target_speeds_kph
"""

_V8_SPEED_TAIL_AND_GROUP = """      分不清哪个速度属于哪个参与者就留 null，只写进 params.target_speeds_kph
  alternative_group（任选组，字符串，可为 null）
    - 文档写明几种目标**任选其一**、每次试验只出现其中一种时（「乘用车/快递三轮车/行人
      任选其一」「乘用车（或快递三轮车）」「成人或儿童行人」），每种各列一个参与者，
      并给它们填**同一个**组名（如 "A"；另有一组任选就写 "B"）
    - 同时出现的参与者（行人群里的每个人、两侧停放的每辆车）一律填 null
"""

_V8_TURN_AND_CONTROLS = """ego_turn（主车在路口 / 环岛的走向，单选）：直行 / 左转 / 右转 / 掉头 / 未知
  - 只在文档写明时填：「主车左转通过路口」→ 左转；「确保车辆在交叉口直行」→ 直行
  - 不经过路口、环岛的场景，或文档没说主车怎么走，填「未知」

traffic_controls（试验要用到的交通控制设施，可多选，可为空）：交通信号灯 / 限速标志
  - 只填试验靠它进行的：信号灯识别与响应、限速标志识别这类试验
  - 只作位置参照提到的（「距停止线 21m 处」），或写明「无信号灯 / 信号灯熄灭」的，不要填

test_intent（这个试验考核什么，单选）：
"""

_V8_SPEED_LIMIT_LINES = """  fog_visibility_m：雾天能见度（数字，米）——「能见度不大于 200m」→ 200；
    文档只说「雾天」没给数值就留 null
  speed_limits_kph：限速标志的数值（数字数组，km/h）——「设置限速 60 km/h 标志」→ [60]；
    按条件任选其一的几个值都列上（「按设定车速选取 100/80/60/40 km/h 标志」→ [100, 80, 60, 40]）；
    试验没有限速标志就留空数组
"""

_V7_EXAMPLE_INTENT = """        "test_intent": "功能试验",
"""

_V8_EXAMPLE_INTENT = """        "test_intent": "功能试验",
        "ego_turn": "未知",
        "traffic_controls": [],
"""

_V8_EXAMPLE_PARTICIPANT = (
    '          {"kind": "乘用车", "bearing": "正前方", "facing": "同向",'
    ' "actions": ["静止"], "age": "未知", "speed_kph": null, "alternative_group": null}\n'
)

_V8_EXAMPLE_PARAMS_TAIL = """          "fog_visibility_m": null,
          "speed_limits_kph": [],
          "end_condition": null
"""

_PROMPT_SCENE_FIRST_V8 = (
    _PROMPT_SCENE_FIRST_V7
    .replace(_V7_BEARING_LINES, _V8_BEARING_LINES)
    .replace(_V7_SPEED_TAIL, _V8_SPEED_TAIL_AND_GROUP)
    .replace("test_intent（这个试验考核什么，单选）：\n", _V8_TURN_AND_CONTROLS)
    .replace(_V6_END_CONDITION_LINES.split("  end_condition")[0], _V8_SPEED_LIMIT_LINES)
    .replace(_V7_EXAMPLE_INTENT, _V8_EXAMPLE_INTENT)
    .replace(_V7_EXAMPLE_PARTICIPANT, _V8_EXAMPLE_PARTICIPANT)
    .replace('          "fog_visibility_m": null,\n          "end_condition": null\n', _V8_EXAMPLE_PARAMS_TAIL)
)

# ---------- v9: find the scenes once, then read each batch's structure with evidence ----------
# Scene finding keeps the v1 instructions unchanged (v2-v8 only added the structure to them). The
# structure prompt keeps v8's field definitions with three changes: either-or targets also come
# from parameter-table rows; the bearing keeps only definitions that map from the wording itself
# (v8's "at test start / by lane" lines made the model infer an unstated ego lane); and every
# spatial field names its source with a verbatim quote, checked in code (structure_evidence).

_V8_STRUCTURE_START = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n场景结构（structure）"
_V8_STRUCTURE_END = "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n严格输出"


def _v8_structure_section() -> str:
    start = _PROMPT_SCENE_FIRST_V8.index(_V8_STRUCTURE_START)
    return _PROMPT_SCENE_FIRST_V8[start:_PROMPT_SCENE_FIRST_V8.index(_V8_STRUCTURE_END, start)]


_STRUCTURE_V9_HEAD = """你是汽车测试标准的场景结构化专家。用户会给你一份测试规程里若干个试验场景的原文：
先是全文档共用的试验条件，再是本批场景用到的章节（每节带 node_id、层级和正文），
最后是本批场景清单（scene_id、场景名、所在章节、属于它的 node_id）。

你的任务：为清单里的**每个**场景，把原文描述的场景结构翻译成规定的结构化字段，
并为空间字段写明依据。只根据给出的原文，不要用常识补全原文没写的东西。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
通用术语（适用于各类标准）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 我国道路靠右行驶：对向车道在主车左侧。
- 主车 = 试验车辆 = 被试车辆 = SV（subject vehicle）；TV = 目标车辆（TV1、TV2 是不同的目标车）；
  TO = 目标物（target object）；VRU = 弱势交通参与者（行人、骑行者等）。
- 本车道 = 主车所在的车道；相邻车道 = 紧挨本车道的同向车道（在左还是在右，看原文）；
  对向车道 = 迎面方向的车道。
- 近端 = 从主车右侧（靠近主车的路边）出发；远端 = 从主车左侧（道路另一侧）出发。
- 参数表（<table>）里每一行是一个独立的试验工况。

"""

_V8_GROUP_LINES = """    - 同时出现的参与者（行人群里的每个人、两侧停放的每辆车）一律填 null
"""

_V9_GROUP_LINES = """    - 参数表每行一个工况：各行的目标物类型（或目标组合）不同时，这些目标也是任选，
      每种各列一个参与者、填同一个组名；「分别用 X、Y 各做一次试验」同理
    - 同时出现的参与者（行人群里的每个人、两侧停放的每辆车）一律填 null
"""

_V9_BEARING_LINES = """  bearing（相对主车的方位，单选）：
    正前方 / 正后方 / 并排同车道 / 左前方 / 左后方 / 左并排 / 右前方 / 右后方 / 右并排 / 未知方位
    - 对向车道驶来的车（靠右行驶）= 左前方 + facing「对向」
    - 原文没写清目标在主车哪一侧、或要看主车在哪条车道才能定而原文没写主车车道时，
      填「未知方位」，不要猜（由原文必然推出的除外，见下面的「依据」）；
      只画在图里、文字没写的位置（「如图 X 所示」）也填未知
"""

_V8_TURN_HEAD = "ego_turn（主车在路口 / 环岛的走向，单选）"

_V9_EGO_LANE = """ego_lane（主车在本方向车道中的位置，单选）：最左侧车道 / 最右侧车道 / 中间车道 / 未知
  - 只在原文写明或能必然推出时填（见下面的「依据」）；没写就填「未知」

"""

_STRUCTURE_V9_EVIDENCE = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
空间字段的依据（evidence）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
下面这些字段只要填了非未知的值，就必须写依据：每个参与者的 bearing、facing、
alternative_group（填了组名时），以及场景的 ego_turn、ego_lane。每条依据：
  {"source": "原文" 或 "推出" 或 "未知", "quote": "原文引句", "reason": "推理（仅推出时写）"}
- 原文：原文直接写了。quote 照抄原文里连续的一段（不超过 60 字，不改字、不加省略号；
  表格只抄单元格里的字）。
- 推出：原文没直接写，但由原文的几句话**必然**得出（不这样就与原文矛盾）。quote 抄出所依据的
  原文，reason 用一句话写推理。例：原文「试验道路为单向两车道，主车沿右侧车道行驶，目标车在
  相邻车道」→ 相邻车道只能在主车左侧，目标车 bearing 填左前方（或左并排、左后方，看前后），source=推出。
- 未知：原文和推理都定不了。值填「未知 / 未知方位」，不必写依据。
  「一般 / 通常 / 大概」不算推出。
- quote 必须来自上面给出的原文章节（不能抄场景清单里的场景名），且只能抄**这个场景自己**的章节或共用章节。
  程序会逐条核对：原文里找不到的引句，该字段会被改成未知并标记待复核。
"""

_STRUCTURE_V9_OUTPUT = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

严格输出以下 JSON，不要任何额外文字：
{
  "scenes": [
    {
      "scene_id": "（场景清单里的 scene_id，原样照抄）",
      "structure": {
        "road_class": "直道",
        "tested_function": "AEB",
        "tested_function_raw": null,
        "ego_actions": ["匀速行驶"],
        "participants": [
          {"kind": "乘用车", "bearing": "正前方", "facing": "未知", "actions": ["静止"], "age": "未知",
           "speed_kph": null, "alternative_group": null,
           "evidence": {"bearing": {"source": "原文", "quote": "前方同车道有静止车辆目标", "reason": null}}}
        ],
        "relations": [],
        "semantic_triggers": ["TTC"],
        "venue_features": [],
        "lane_marking": "未知",
        "parking_operation": "未知",
        "test_intent": "功能试验",
        "ego_turn": "未知",
        "ego_lane": "未知",
        "traffic_controls": [],
        "evidence": {},
        "params": {
          "ego_speed_kph": null,
          "target_speeds_kph": [],
          "weather": "未知",
          "time_of_day": "未知",
          "ttc_value": null,
          "lateral_direction": "未知",
          "curve_radius_m": null,
          "lane_count": null,
          "lane_direction": "未知",
          "fog_visibility_m": null,
          "speed_limits_kph": [],
          "end_condition": null
        }
      }
    }
  ]
}

要求：
- 场景清单里的每个场景都输出一项，scene_id 原样照抄，不要漏、不要合并、不要新增
- structure 的每个字段只能用上面列出的取值
- 每个非未知的空间字段都有依据，引句是给出原文里连续的原句
"""

_PROMPT_SCENE_STRUCTURE_V9 = (
    _STRUCTURE_V9_HEAD
    + _v8_structure_section()
    .replace(_V8_BEARING_LINES, _V9_BEARING_LINES)
    .replace(_V8_GROUP_LINES, _V9_GROUP_LINES)
    .replace(_V8_TURN_HEAD, _V9_EGO_LANE + _V8_TURN_HEAD)
    + _STRUCTURE_V9_EVIDENCE
    + _STRUCTURE_V9_OUTPUT
)

# ---------- v10: the scene's figures come with its text ----------
# A model that reads images gets each scene's figures (pdf_v2.figures). A position the text leaves
# to a figure ("如图C.10所示") is read from it, with the figure's number as the quote and what it
# shows as the reason; the text still wins over a figure. A crossing target's bearing is the side
# it starts from (v9 left the moment open, and readings named where it meets the ego).

_V9_HEAD_SCENE_LIST = "最后是本批场景清单（scene_id、场景名、所在章节、属于它的 node_id）。\n"

_V10_HEAD_SCENE_LIST = """最后是本批场景清单（scene_id、场景名、所在章节、属于它的 node_id、它的示意图）。
场景章节里有示意图时，图片附在最后，每张前面写着图号和图题。
"""

_V9_BEARING_FIGURE_LINE = "      只画在图里、文字没写的位置（「如图 X 所示」）也填未知\n"

_V10_BEARING_FIGURE_LINES = """      文字没写、只画在示意图里的位置（「如图 X 所示」）：附了这张图就按图读（依据来源填「图」，
      见下面的「读示意图」），没附图就填未知
    - 横穿的目标（行人、骑行者、横穿的车）按它**出发的一侧**定方位：从主车右侧出发 = 右前方，
      从左侧出发 = 左前方；不是相遇、碰撞那一刻它在哪
"""

_V9_EVIDENCE_SOURCES = '  {"source": "原文" 或 "推出" 或 "未知", "quote": "原文引句", "reason": "推理（仅推出时写）"}\n'

_V10_EVIDENCE_SOURCES = """  {"source": "原文" 或 "推出" 或 "图" 或 "未知", "quote": "原文引句（看图时写图号）",
   "reason": "推理（推出时写）或图里看到的（看图时写）"}
"""

_V9_EVIDENCE_UNKNOWN = "- 未知：原文和推理都定不了。"

_V10_EVIDENCE_FIGURE = """- 图：原文没写、附给这个场景的示意图里画清楚了。quote 只写图号（如「图C.10」），reason 用一句话写
  图里看到的（如「图中儿童从主车右侧路边出发，被右前方停放的车挡住」）。原文写了的一律按原文。
- 未知：原文、推理和附图都定不了。"""

_V10_FIGURE_SECTION = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
读示意图（附了图时）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 示意图多是俯视图。先找主车（试验车辆 / 被试车辆 / SV / VUT / 主车）和它的行驶方向（车头朝向、箭头）。
- 左右、前后都按**主车行驶方向**换算，不是图片的左右：主车朝图片右边开时，图片上方是主车左侧、
  下方是主车右侧；主车朝图片上方开时，图片左边是主车左侧。
- 参与者以原文为准：图只用来定原文提到的参与者的方位、朝向和主车车道、主车走向；不要因为图里
  多画了东西就新增参与者，也不要用图改掉原文写明的事实。
- 一个场景附了几张图（如不同目标物各一张）时，每个参与者按画它的那张图读。
- 图里看不清、或几张图画得互相矛盾时，填未知。
"""

_V9_OUTPUT_REQUIREMENT = "- 每个非未知的空间字段都有依据，引句是给出原文里连续的原句\n"

_V10_OUTPUT_REQUIREMENT = """- 每个非未知的空间字段都有依据，引句是给出原文里连续的原句；看图的依据只写附给这个场景的图号
"""

_PROMPT_SCENE_STRUCTURE_V10 = (
    _PROMPT_SCENE_STRUCTURE_V9
    .replace(_V9_HEAD_SCENE_LIST, _V10_HEAD_SCENE_LIST)
    .replace(_V9_BEARING_FIGURE_LINE, _V10_BEARING_FIGURE_LINES)
    .replace(_V9_EVIDENCE_SOURCES, _V10_EVIDENCE_SOURCES)
    .replace(_V9_EVIDENCE_UNKNOWN, _V10_EVIDENCE_FIGURE)
    .replace(_STRUCTURE_V9_OUTPUT, _V10_FIGURE_SECTION + _STRUCTURE_V9_OUTPUT)
    .replace(_V9_OUTPUT_REQUIREMENT, _V10_OUTPUT_REQUIREMENT)
)

# ---------- v11: a lane departure is its own ego behavior ----------
# Lane departure warning and keeping tests drift the ego towards or over a line without taking the
# next lane. v10 had no word for it: readings wrote 匀速行驶 (or 变道), and the comparison then took
# every lane departure asset for a lane change.

_V11_EGO_ACTIONS_BLOCK = """ego_actions（主车行为，可多选）：
  匀速行驶 / 变速 / 刹停 / 变道 / 定距跟车 / 倒车 / 偏离车道 / 被测系统控制 / 未知
  - 「被测系统控制」用于 AEB 介入、APA 自动泊车这类由被测系统接管主车的场景
  - 主车匀速开着等目标出现，就是「匀速行驶」
  - 「倒车」= 主车倒着行驶（倒车驶出车位、倒车通过通道这类），文档写明才填
  - 「偏离车道」= 试验让主车横向漂移、驶向或越过车道线，但不换到相邻车道（车道偏离预警、
    偏离抑制、车道保持这类试验的偏离过程）；换到相邻车道才是「变道」。偏离方向写在
    params.lateral_direction，两侧都要做时填未知
"""

# The drift's lateral speed is what tells lane departure tests of one function apart (0.2 against
# 0.5 m/s); stated values are test conditions, a stated range lets any speed in it do.

_V10_LATERAL_LINE = "  lateral_direction：左 / 右 / 未知 —— 偏离或换道的方向（「向左偏离」→ 左）\n"

_V11_LATERAL_LINES = _V10_LATERAL_LINE + """  lateral_speeds_mps：主车横向（偏离、漂移）速度（数字数组，m/s）——试验要逐个做的值都列上
    （「横向速度 0.2 m/s 和 0.5 m/s」→ [0.2, 0.5]）；文档没写就留空数组
  lateral_speed_range_mps：只给了范围、范围内任取一个速度时填 [下限, 上限]
    （「横向偏离速度在 0.1 至 0.5 m/s 之间」→ [0.1, 0.5]），这时 lateral_speeds_mps 留空
"""

_V10_EXAMPLE_LATERAL = '          "lateral_direction": "未知",\n'

_V11_EXAMPLE_LATERAL = _V10_EXAMPLE_LATERAL + """          "lateral_speeds_mps": [],
          "lateral_speed_range_mps": [],
"""

_PROMPT_SCENE_STRUCTURE_V11 = (
    _PROMPT_SCENE_STRUCTURE_V10
    .replace(_V6_EGO_ACTIONS_BLOCK, _V11_EGO_ACTIONS_BLOCK)
    .replace(_V10_LATERAL_LINE, _V11_LATERAL_LINES)
    .replace(_V10_EXAMPLE_LATERAL, _V11_EXAMPLE_LATERAL)
)

_PROMPT_REGISTRY: dict[str, str] = {
    "scene-first-prompt-v1": _PROMPT_SCENE_FIRST_V1,
    "scene-first-prompt-v2": _PROMPT_SCENE_FIRST_V2,
    "scene-first-prompt-v3": _PROMPT_SCENE_FIRST_V3,
    "scene-first-prompt-v4": _PROMPT_SCENE_FIRST_V4,
    "scene-first-prompt-v5": _PROMPT_SCENE_FIRST_V5,
    "scene-first-prompt-v6": _PROMPT_SCENE_FIRST_V6,
    "scene-first-prompt-v7": _PROMPT_SCENE_FIRST_V7,
    "scene-first-prompt-v8": _PROMPT_SCENE_FIRST_V8,
    # Finds the scenes only; their structure comes from STRUCTURE_PROMPTS below.
    "scene-first-prompt-v9": _PROMPT_SCENE_FIRST_V1,
    "scene-structure-prompt-v9": _PROMPT_SCENE_STRUCTURE_V9,
    "scene-first-prompt-v10": _PROMPT_SCENE_FIRST_V1,
    "scene-structure-prompt-v10": _PROMPT_SCENE_STRUCTURE_V10,
    "scene-first-prompt-v11": _PROMPT_SCENE_FIRST_V1,
    "scene-structure-prompt-v11": _PROMPT_SCENE_STRUCTURE_V11,
}

# Scene prompts whose structure is read in a second step, per batch of scenes.
STRUCTURE_PROMPTS: dict[str, str] = {"scene-first-prompt-v9": "scene-structure-prompt-v9",
                                     "scene-first-prompt-v10": "scene-structure-prompt-v10",
                                     "scene-first-prompt-v11": "scene-structure-prompt-v11"}

_FROZEN_PROMPT_SHA256: dict[str, str] = {
    "scene-first-prompt-v1": (
        "3c9b020cf9a664a8a2174b57692dbdb02f4dc6e527c0514d15144fa70659fd22"
    ),

    "scene-first-prompt-v2": (
        "3e99fd694d9f120852299555307d2ea3be635004014f20b3ee9a182d39cb7e79"
    ),

    "scene-first-prompt-v3": (
        "1d4de5b45bed47151a7dab2a127f46949441dc3abccbbbbd2a9c5dba040f606c"
    ),

    "scene-first-prompt-v4": (
        "35b4cdb32b69191adf817bc2c8c198bb621a6fbafc4f7a4537f95a6f505aeed7"
    ),

    "scene-first-prompt-v5": (
        "bd6f50d7be7dee7385a87558a28a34a8ecf2842c6965f20bda24a5ccc1a17356"
    ),

    "scene-first-prompt-v6": (
        "3f54e06e035a3891191c39437bdd4966e4902d4288ca59f564f4213c93436f5d"
    ),

    "scene-first-prompt-v7": (
        "dc279fa0d19751439643ec4a670918a4aadecfb2430fe97765494825baa5fcac"
    ),

    "scene-first-prompt-v8": (
        "de57b2c17c038fe88f3fd0a924797d9521acbd042e54907c709010f56bcc208a"
    ),
    # The v1 scene-finding text, unchanged.
    "scene-first-prompt-v9": (
        "3c9b020cf9a664a8a2174b57692dbdb02f4dc6e527c0514d15144fa70659fd22"
    ),

    "scene-structure-prompt-v9": (
        "77af239241bf7b3a1606af59475fc3f677e6720c2e87ed0ad921bcaa0773414a"
    ),
    # The v1 scene-finding text, unchanged.
    "scene-first-prompt-v10": (
        "3c9b020cf9a664a8a2174b57692dbdb02f4dc6e527c0514d15144fa70659fd22"
    ),

    "scene-structure-prompt-v10": (
        "140d79943591ef131e72be4ead8dbd02b7ba246c3aee1821769373e143887b06"
    ),
    # The v1 scene-finding text, unchanged.
    "scene-first-prompt-v11": (
        "3c9b020cf9a664a8a2174b57692dbdb02f4dc6e527c0514d15144fa70659fd22"
    ),

    "scene-structure-prompt-v11": (
        "490168fbce59b07984e8eca45c2fcca77ff0745e8fe2c79ad9a915f371c76bb8"
    ),
}

class ScenePromptDrift(RuntimeError):
    pass

class SceneResponseTruncated(RuntimeError):
    pass

class SceneResponseInvalid(RuntimeError):
    pass

class SceneDocumentTooLarge(RuntimeError):
    pass

def _reject_json_constant(value: str) -> None:

    raise ValueError(f"invalid JSON constant: {value}")

def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def resolve_scene_prompt(version: str = DEFAULT_SCENE_PROMPT_VERSION) -> str:

    prompt = _PROMPT_REGISTRY.get(version)
    if prompt is None:
        raise KeyError(f"unknown scene prompt version: {version}")
    expected = _FROZEN_PROMPT_SHA256.get(version)
    actual = _sha256_text(prompt)
    if expected != actual:
        raise ScenePromptDrift(
            f"scene prompt {version} drifted: expected {expected}, got {actual}"
        )
    return prompt

def build_document_view(
    tree: SectionTree,
    text_by_node: dict[str, str],
    *,
    node_text_limit: int = NODE_TEXT_LIMIT,
) -> str:

    parts: list[str] = []
    for node in tree.nodes:
        head = f"[{node.node_id}] (L{node.level}) {node.title}"
        body = (text_by_node.get(node.node_id) or "").strip()
        if node_text_limit > 0:
            body = body[:node_text_limit]
        parts.append(f"{head}\n{body}" if body else head)
    return "\n\n".join(parts)

def build_shared_container_appendix(
    candidates: tuple[SharedContainerCandidate, ...],
    title_by_node: dict[str, str],
) -> str:

    if not candidates:
        return ""
    lines = [
        f"[{candidate.node_id}] {title_by_node.get(candidate.node_id, '')}"
        f"  ← 命中「{candidate.matched_keyword}」（{candidate.signal}）"
        for candidate in candidates
    ]
    return (
        "\n\n===== 附：疑似共享章节候选清单（确定性预筛，高召回低精确，仅供定位）=====\n"
        + "\n".join(lines)
    )

_CJK = re.compile(r"[一-鿿]")
_LATIN = re.compile(r"[A-Za-z]")

def build_language_note(texts: Iterable[str]) -> str:
    """For a document written in English, a note after it asking for English scene names and stories (the
    frozen prompt asks for Chinese ones); empty for any other document, whose request stays as it was. A
    document is English when its Chinese characters number under a quarter of its Latin letters, so a
    Chinese standard quoting km/h, TTC or ISO stays Chinese."""
    text = "\n".join(texts)
    if len(_CJK.findall(text)) * 4 >= len(_LATIN.findall(text)):
        return ""
    return "\n\n===== 输出语言 =====\n这份文档是英文的：每个场景的 name 和 story 用英文写，与原文同语言。"

def build_scene_request(
    document_view: str,
    *,
    model: str,
    prompt_version: str = DEFAULT_SCENE_PROMPT_VERSION,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
    max_input_chars: int = MAX_INPUT_CHARS,
) -> dict[str, Any]:

    prompt = resolve_scene_prompt(prompt_version)
    total_chars = len(prompt) + len(document_view)
    if total_chars > max_input_chars:
        raise SceneDocumentTooLarge(
            f"document view is {total_chars:,} chars, exceeding the {max_input_chars:,} "
            "limit; split the document by top-level appendix before proposing"
        )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": document_view},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled"},
        "max_tokens": max_output_tokens,
    }

def build_structure_request(
    context_view: str,
    batch_view: str,
    scene_list: str,
    *,
    model: str,
    prompt_version: str,
    figures: Sequence[Figure] = (),
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
    max_input_chars: int = MAX_INPUT_CHARS,
) -> dict[str, Any]:
    """One batch of scenes for the structure prompt. The document-wide conditions come first, the
    same in every batch, so the service can reuse that prefix across batches. The scenes' figures
    follow the text as images (OpenAI content parts), each after a line with its number and caption."""
    prompt = resolve_scene_prompt(prompt_version)
    text = ("===== 全文档共用的试验条件 =====\n" + (context_view or "（无）")
            + "\n\n===== 本批场景用到的章节 =====\n" + batch_view
            + "\n\n===== 本批场景清单 =====\n" + scene_list)
    if len(prompt) + len(text) > max_input_chars:
        raise SceneDocumentTooLarge(
            f"structure batch is {len(prompt) + len(text):,} chars, exceeding the {max_input_chars:,} limit"
        )
    content: str | list[dict[str, Any]] = text
    if figures:
        content = [{"type": "text", "text": text + f"\n\n===== 本批场景的示意图（{len(figures)} 张，附在下面）====="}]
        for figure in figures:
            content.append({"type": "text", "text": f"{figure.label}（第 {figure.page_number} 页）：{figure.caption}"})
            content.append({"type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + base64.b64encode(figure.png).decode()}})
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled"},
        "max_tokens": max_output_tokens,
    }

def request_sha256(request_body: dict[str, Any]) -> str:

    raw = json.dumps(request_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(raw)

def parse_structure_response(envelope: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The structures of a batch response by scene_id; entries without one are skipped."""
    parsed = _response_object(envelope)
    if not isinstance(parsed.get("scenes"), list):
        raise SceneResponseInvalid("response must contain a scenes list")
    result: dict[str, dict[str, Any]] = {}
    for entry in parsed["scenes"]:
        if isinstance(entry, dict) and isinstance(entry.get("scene_id"), str) and isinstance(entry.get("structure"), dict):
            result.setdefault(entry["scene_id"].strip(), entry["structure"])
    if not result:
        raise SceneResponseInvalid("response contains no scene structure with a scene_id")
    return result

def _response_object(envelope: dict[str, Any]) -> dict[str, Any]:

    choices = envelope.get("choices") or []
    if not choices:
        raise SceneResponseInvalid("response contains no choices")

    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length":
        completion = (envelope.get("usage") or {}).get("completion_tokens")
        raise SceneResponseTruncated(
            "model output hit max_tokens and the JSON is incomplete "
            f"(completion_tokens={completion}); raise max_output_tokens or split the document"
        )

    if finish_reason != "stop":
        raise SceneResponseInvalid("model did not finish a complete response")
    content = (choice.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise SceneResponseInvalid("response message content is empty")

    try:
        parsed = json.loads(content, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as error:

        raise SceneResponseInvalid(f"model returned malformed JSON: {error}") from error

    if not isinstance(parsed, dict):
        raise SceneResponseInvalid("model returned a JSON value that is not an object")
    return parsed

def parse_scene_response(envelope: dict[str, Any]) -> dict[str, Any]:

    parsed = _response_object(envelope)
    if not isinstance(parsed.get('scenes'), list) or not isinstance(parsed.get('shared_config_node_ids', []), list):
        raise SceneResponseInvalid('response must contain a scenes list and optional shared_config_node_ids list')
    for scene in parsed['scenes']:
        if not isinstance(scene, dict) or not all(isinstance(scene.get(key), str) and scene[key].strip() for key in ('name', 'story', 'anchor_node_id')):
            raise SceneResponseInvalid('scene name, story and anchor are required')
        if not isinstance(scene.get('confidence'), (int, float)) or not 0 <= scene['confidence'] <= 1:
            raise SceneResponseInvalid('scene confidence must be in [0, 1]')
        for key in ('actors', 'member_node_ids', 'shared_container_node_ids'):
            if not isinstance(scene.get(key, []), list) or any(not isinstance(item, str) for item in scene.get(key, [])):
                raise SceneResponseInvalid('scene references and actors must be lists of strings')
    return parsed
