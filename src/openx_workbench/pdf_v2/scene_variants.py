"""The test conditions (工况) of one requirement scene.

A clause often defines several runs of the same test that differ in what a scenario file contains:
a speed or a sign value per parameter-table row, day and night, a target per run, a branch chosen by
the tested vehicle (M1 or not, its declared top speed), a pre-test without the target. The model lists
them per scene after its structure; each dimension quotes the sentence it rests on, checked against
the scene's text like the structure's evidence. A scene with one run has none.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from .scene_proposer import SceneResponseInvalid, _response_object
from .structure_evidence import normalize, quote_found

VARIANT_PROMPT_VERSION = "scene-variants-prompt-v2"
MAX_VARIANTS = 100  # a table this long is a sweep; the rest is cut and a person is told

VariantHow = Literal["都要做", "按被测车选一", "任选一"]
DimensionKind = Literal["主车车速", "目标速度", "目标物", "时段", "天气", "被测车类别", "限速", "触发条件",
                        "碰撞位置", "道路", "干扰参与者", "试验阶段", "子试验", "其他"]
_HOW = frozenset(get_args(VariantHow))
_KINDS = frozenset(get_args(DimensionKind))


class VariantDimension(BaseModel):
    """One way the runs differ: what it is, whether every value is run or one is chosen, and the
    sentence that says so (`review` when that sentence is not in the scene's text)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=30)
    kind: DimensionKind = "其他"
    how: VariantHow = "都要做"
    quote: str | None = Field(default=None, max_length=200)
    review: str | None = Field(default=None, max_length=200)


class SceneVariant(BaseModel):
    """One run: a short label and its value per dimension (a dimension that does not apply to it,
    such as the vehicle class of a pre-test, has no entry)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=60)
    values: dict[str, str] = Field(default_factory=dict)


class SceneVariants(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimensions: tuple[VariantDimension, ...] = ()
    variants: tuple[SceneVariant, ...] = ()
    review_flags: tuple[str, ...] = ()


NONE = SceneVariants()

_PROMPT_SCENE_VARIANTS_V1 = """你是汽车测试标准的试验工况整理专家。用户会给你测试规程里**一个**试验场景的原文：
先是全文档共用的试验条件，再是这个场景用到的章节（每节带 node_id、层级和正文），最后是场景名。

你的任务：列出原文为这个场景规定的**全部工况**。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
什么是工况
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 同一个试验场景下，原文规定要分别进行、或按条件选其中一个进行的几次试验，它们在场景搭建上不同，
  也就是仿真场景文件里要写得不一样：主车或目标的速度、目标物种类、日间或夜间、天气和降雨量或能见度、
  限速标志的数值、触发或结束条件的数值（TTC、距离、时距）、碰撞点或横向位置、道路形状、
  有没有某个参与者、预试验（例如「在无目标的情况下进行三次预试验」）。
- 常见写法：参数表的每一行；「分别以 X、Y 进行试验」「X、Y 各进行一次」；「若……则……」按被试车辆的
  属性或厂商声明选取的分支；「在夜间条件下重复试验」；同一节下并列的几个子试验。
- 这些**不是**工况：数值的允许误差或区间（60±2 km/h、1.5 s～2.5 s）；同一工况重复几次；同一次试验里
  先后进行的几个步骤（先……再……，合起来是一个工况）；评分、合格判定、数据记录、测量方法；被试车辆自身的
  设置和准备（灯光、雨刮、驾驶模式、跟车时距档位、载荷等）；试验地点，以及在公共道路上按路线行驶的测试
  的路线、路段和出行时段；原文没有给出具体取值、由厂商或试验方自行确定的参数（「以厂商声明的车速」）；
  只是举例的写法（「例如……」）。
- 被试车辆是否具备某项能力只决定某次试验做不做时（如具备某功能才做的预试验），把那次试验列为工况，
  不要把「具备 / 不具备」当成一个维度。
- 只列**这个场景**自己的工况。给出的章节里混进了与场景名无关的其他试验时，不列它们；共用章节里写给
  别的场景的取值也不列。
- 场景名或场景自己的章节已经限定的条件不再拆开（场景名是「夜间……」就只有夜间）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
怎么写
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 先找出这些试验在哪几方面不同，每一方面是一个维度（dimensions）：
   - name：维度名，简短（如「限速标志」「时段」「被试车辆类型」「试验项」）
   - kind（单选）：主车车速 / 目标速度 / 目标物 / 时段 / 天气 / 被测车类别 / 限速 / 触发条件 / 碰撞位置 /
     道路 / 干扰参与者 / 试验阶段 / 子试验 / 其他
   - how（单选）：
     - 都要做：每个取值都要做一次（参数表各行、分别进行、日间夜间各一次、预试验和正式试验、并列的子试验）
     - 按被测车选一：按被试车辆的属性、配置或厂商声明，一辆车只做其中一个取值（车速区间对应的标志、
       车辆类别对应的参数、厂商声明的等级对应的条件）
     - 任选一：原文让试验方任选或随机选一个
     以车辆能力为前提追加的试验（「若系统可在夜间激活，应在夜间条件下重复」）仍是「都要做」。
   - quote：照抄原文里说明这个维度的一句（连续原文，不超过 60 字，不改字、不加省略号；表格只抄单元格里的字）
2. 再列出全部工况（variants），每个工况：
   - label：给人看的短名，由区分它的取值组成（如「乘用车 · 夜间」「限速 60 km/h」「预试验」）
   - values：每个维度在这个工况下的取值，键是维度的 name；某个维度对它不适用时（如预试验不分车型）不写这个键
   - 按原文的组合列：参数表的一行就是一个工况，行里的几个数一起写进 values；几个维度互相独立时才两两组合
     （如车型分支 × 日间夜间），不编原文没有的组合。
   - 表格或列举给出的取值逐个列出，不要把几个取值合成一个笼统的工况（如「厂商申报值」）。
3. 原文没有规定任何分别、分支、重复条件或预试验时，只有一个工况：dimensions 和 variants 都输出空列表。

严格输出以下 JSON，不要任何额外文字：
{
  "dimensions": [
    {"name": "目标物", "kind": "目标物", "how": "都要做", "quote": "分别使用乘用车目标和行人目标进行试验"},
    {"name": "时段", "kind": "时段", "how": "都要做", "quote": "应在夜间条件下重复上述试验"}
  ],
  "variants": [
    {"label": "乘用车 · 日间", "values": {"目标物": "乘用车", "时段": "日间"}},
    {"label": "乘用车 · 夜间", "values": {"目标物": "乘用车", "时段": "夜间"}},
    {"label": "行人 · 日间", "values": {"目标物": "行人", "时段": "日间"}},
    {"label": "行人 · 夜间", "values": {"目标物": "行人", "时段": "夜间"}}
  ]
}
"""

# v2 (2026-10-10): names, labels and values in the source's language, like the scene name. v1 wrote them in
# the prompt's Chinese, so an English standard listed 「向左偏离」 under its English clauses.
_V1_LAST_RULE = "3. 原文没有规定任何分别、分支、重复条件或预试验时，只有一个工况：dimensions 和 variants 都输出空列表。\n"

_V2_LANGUAGE_RULE = """4. name、label、values 用原文的语言写，和场景名一样：英文原文写英文（如 label「Departure left · 0.2 m/s」），
   中文原文写中文；kind 和 how 只用上面列出的取值。
"""

_PROMPT_SCENE_VARIANTS_V2 = _PROMPT_SCENE_VARIANTS_V1.replace(_V1_LAST_RULE, _V1_LAST_RULE + _V2_LANGUAGE_RULE)

_PROMPTS = {
    "scene-variants-prompt-v1": (_PROMPT_SCENE_VARIANTS_V1, "293349de8c24d1f877cab8a20a8b66857f84e635cc624a5e651cd2826f7e9a81"),
    "scene-variants-prompt-v2": (_PROMPT_SCENE_VARIANTS_V2, "9279e30640aecc16fc5580a64b8a1bb8e0225de14e7eaaa367e47908ca97cfad"),
}


def resolve_variant_prompt(version: str = VARIANT_PROMPT_VERSION) -> str:
    prompt, expected = _PROMPTS[version]
    actual = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if actual != expected:
        raise RuntimeError(f"variant prompt {version} drifted: expected {expected}, got {actual}")
    return prompt


def build_variant_request(context_view: str, scene_view: str, scene_name: str, *, model: str,
                          max_output_tokens: int = 64_000) -> dict[str, Any]:
    """One scene for the variant prompt: the document-wide conditions first (the same prefix for every
    scene), then the scene's own and referenced sections, then its name."""
    text = ("===== 全文档共用的试验条件 =====\n" + (context_view or "（无）")
            + "\n\n===== 本场景用到的章节 =====\n" + scene_view
            + "\n\n===== 场景名 =====\n" + scene_name)
    return {
        "model": model,
        "messages": [{"role": "system", "content": resolve_variant_prompt()}, {"role": "user", "content": text}],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled"},
        "max_tokens": max_output_tokens,
    }


def _text(value: object, limit: int) -> str:
    return " ".join(str(value).split())[:limit] if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def parse_variant_response(envelope: dict[str, Any]) -> SceneVariants:
    """The scene's variants from a reply. A dimension of an unknown kind is kept as 「其他」; one with an
    unknown `how` makes the reply invalid (it decides what a person has to cover). A scene of one run is NONE."""
    parsed = _response_object(envelope)
    dimensions_raw, variants_raw = parsed.get("dimensions"), parsed.get("variants")
    if not isinstance(dimensions_raw, list) or not isinstance(variants_raw, list):
        raise SceneResponseInvalid("response must contain dimensions and variants lists")
    dimensions: dict[str, VariantDimension] = {}
    for item in dimensions_raw:
        if not isinstance(item, dict) or not (name := _text(item.get("name"), 30)):
            continue
        how = item.get("how")
        if how not in _HOW:
            raise SceneResponseInvalid(f"dimension {name}: how must be one of {sorted(_HOW)}")
        kind = item.get("kind") if item.get("kind") in _KINDS else "其他"
        dimensions.setdefault(name, VariantDimension(name=name, kind=kind, how=how,
                                                     quote=_text(item.get("quote"), 200) or None))
    variants: list[SceneVariant] = []
    labels: Counter[str] = Counter()
    for item in variants_raw:
        if not isinstance(item, dict):
            continue
        raw_values = item.get("values") if isinstance(item.get("values"), dict) else {}
        values = {name: text for name, value in raw_values.items()
                  if name in dimensions and (text := _text(value, 60))}
        label = _text(item.get("label"), 56) or " · ".join(values.values())[:56]
        if not label:
            continue
        labels[label] += 1
        # Two runs with one label are told apart by their place in the list.
        variants.append(SceneVariant(label=label if labels[label] == 1 else f"{label} ({labels[label]})", values=values))
    if len(variants) <= 1:
        return NONE
    flags = ()
    if len(variants) > MAX_VARIANTS:
        flags = (f"原文列出 {len(variants)} 个工况，只保留前 {MAX_VARIANTS} 个，请核对",)
        variants = variants[:MAX_VARIANTS]
    used = {name for variant in variants for name in variant.values}
    return SceneVariants(dimensions=tuple(d for d in dimensions.values() if d.name in used),
                         variants=tuple(variants), review_flags=flags)


def ground_variants(variants: SceneVariants, source_text: str) -> SceneVariants:
    """Mark each dimension whose quote is not in the scene's text; nothing is dropped, since a missed
    run costs a person more than one to strike out."""
    source = normalize(source_text)
    dimensions = tuple(
        dimension if dimension.quote and quote_found(dimension.quote, source)
        else dimension.model_copy(update={"review": "引句在本场景原文中找不到，请核对" if dimension.quote else "没有引用原文，请核对"})
        for dimension in variants.dimensions)
    return variants.model_copy(update={"dimensions": dimensions})


def reconcile_variant_readings(readings: list[SceneVariants | None]) -> SceneVariants | None:
    """One list from independent readings: the count most readings agree on, from the first reading
    that has it; without a majority the median count. Readings that disagree ask a person to check."""
    present = [reading for reading in readings if reading is not None]
    if not present:
        return None
    counts = [len(reading.variants) or 1 for reading in present]
    count, votes = Counter(counts).most_common(1)[0]
    if votes * 2 <= len(present):
        count = sorted(counts)[(len(counts) - 1) // 2]
    chosen = present[counts.index(count)]
    if len(set(counts)) == 1:
        return chosen
    shown = " / ".join(str(item) for item in counts)
    return chosen.model_copy(update={"review_flags": (*chosen.review_flags, f"{len(present)} 次读出的工况数不同（{shown}），请核对")})
