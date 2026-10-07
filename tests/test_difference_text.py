"""Differences read Chinese in Chinese: whole sentences and phrases with values, not word by word."""
import ast
import re
from pathlib import Path

import pytest

from openx_workbench import demo_workspace
from openx_workbench.asset_store import AssetStore
from openx_workbench.pdf_store import PdfStore
from openx_workbench.presentation import difference_text, display
from openx_workbench.retrieval import HashingEncoder, OpenXIndex
from openx_workbench.scene_package import scene_package_to_query

SOURCE = Path(__file__).parents[1] / "src" / "openx_workbench"
ENGLISH = re.compile(r"\b[a-z]{2,}\b")  # function names (AEB, NOA) and quoted source text are upper case or Chinese
UNITS = {"km", "m", "s"}
FIELDS = ("category", "requested", "candidate", "action")


def english(text: str) -> list[str]:
    return [word for word in ENGLISH.findall(text) if word not in UNITS]


def literal_phrases() -> set[str]:
    """Every fixed text the comparison writes into a difference, read from its source."""
    found = set()

    def strings(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.IfExp):
            yield from strings(node.body)
            yield from strings(node.orelse)
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                yield from strings(value)

    for name in ("reuse_structured.py", "reuse_legacy.py", "reuse_differences.py"):
        tree = ast.parse((SOURCE / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {"ReuseDifference", "missing"}:
                arguments = list(node.args[:4]) + [item.value for item in node.keywords if item.arg in FIELDS]
                found.update(text for argument in arguments for text in strings(argument))
            if isinstance(node, ast.FunctionDef) and node.name == "_placement":
                found.update(text for item in ast.walk(node) if isinstance(item, ast.Return) and item.value
                             for text in strings(item.value))
    return {text for text in found if text.strip()}


def test_every_fixed_phrase_of_a_difference_has_a_chinese_sentence():
    phrases = literal_phrases()
    assert "decide by hand whether this is the same test" in phrases and "move start position or retime trigger" in phrases
    left = {phrase: display(phrase) for phrase in phrases if english(display(phrase))}
    # "scenario" is also a similarity score's name; the old comparison's category keeps that label.
    assert set(left) <= {"scenario"}, left


@pytest.mark.parametrize("raw, shown", [
    ("target speeds=(3.0, 5.0, 12.0)", "目标速度=(3.0, 5.0, 12.0)"),
    ("curve radius 787 m", "弯道半径 787 m"),
    ("lines: solid, broken", "车道线：实线、虚线"),
    ("broken lane line", "虚线车道线"),
    ("participant age=儿童", "参与者年龄=儿童"),
    ("speed=20 km/h", "速度=20 km/h"),
    ("ego_action=system_control", "主车动作=被测系统控制"),
    ("ego_action=cruise,stop", "主车动作=匀速行驶,刹停"),
    ("end_condition=target car stops", "结束条件=target car stops"),  # a quoted requirement stays as written
    ("at least 2 lanes in total", "至少 2 条车道（双向合计）"),
    ("same", "同向"),
])
def test_phrases_with_values_read_as_whole_phrases(raw, shown):
    assert display(raw) == shown
    assert display(raw, "en") == raw


@pytest.mark.parametrize("dataset", ["fixtures", "benchmark"])
def test_the_demo_differences_read_chinese(tmp_path, monkeypatch, dataset):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    seeded = demo_workspace.seed(tmp_path, dataset)
    store = AssetStore()
    catalog, _ = store.catalog()
    index = OpenXIndex(catalog, HashingEncoder(64))
    pdf = PdfStore(store)
    lines = []
    for document in seeded["documents"]:
        for scene in pdf.scenes(seeded["project_id"], document["document_id"]):
            for result in index.search("", query=scene_package_to_query(scene.package), top_k=10):
                lines.extend(difference_text(item, "zh") for item in result.differences)
    assert lines
    assert not [line for line in lines if english(line)]
