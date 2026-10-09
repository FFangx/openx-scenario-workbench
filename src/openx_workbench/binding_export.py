"""The reuse assessment of the PDFs shown together, as a file to hand on: one row per requirement clause with the
assets confirmed for reuse, or the model's suggestion while nobody has confirmed one yet; a clause with several test
conditions (工况) is followed by one row per condition with its asset."""

from __future__ import annotations

import csv
import html
import io
from datetime import datetime
from typing import Any

# The same four levels name a person's conclusions and the model's verdicts (kept in its own words).
STATUS = {"same": ("直接复用", "Direct reuse"), "modify": ("修改复用", "Modify and reuse"), "none": ("不适用", "Not applicable"),
          "unconfirmed": ("待确认", "To confirm")}
VERDICT = {"同一测试": STATUS["same"], "同一测试但要改": STATUS["modify"], "不是": STATUS["none"], "拿不准": ("无法判断", "Undetermined")}
STALE = {"scene": ("条款的需求事实已修改", "the clause's facts were edited"), "asset": ("素材有新版本", "an asset has a newer version")}
SOURCE = {"suggestion": ("采纳模型建议", "Adopted from the model"), "manual": ("人工指定", "Specified by a person")}
HEADINGS = (("PDF", "PDF"), ("条款", "Clause"), ("条款标题", "Title"), ("工况", "Test condition"),
            ("复用结论", "Reuse conclusion"), ("复用素材（首选）", "Reused asset (preferred)"),
            ("同组可选素材", "Alternative assets"), ("修改内容", "Changes"),
            ("待重新确认", "Reconfirm"), ("结论来源", "Source"), ("确认时间", "Confirmed at"),
            ("模型建议（待确认）", "Model suggestion (to confirm)"), ("建议一致性", "Consistency"))


def _say(pair: tuple[str, str], lang: str) -> str:
    return pair[0] if lang == "zh" else pair[1]


def _suggested(suggestion: dict[str, Any] | None, lang: str) -> tuple[str, str]:
    """The preferred asset of a usable suggestion with its verdict, and how many assessments agreed on it."""
    if not suggestion or suggestion.get("failure") or suggestion.get("outdated"):
        return "", ""
    preferred = next((item for item in suggestion["candidates"] if item["id"] == suggestion.get("preferred")), None)
    verdict = _say(VERDICT.get(preferred["verdict"], (preferred["verdict"],) * 2), lang) if preferred else ""
    unsure = any(item["verdict"] == "拿不准" for item in suggestion["candidates"])
    words = (f"{preferred['title']}（{verdict}）" if lang == "zh" else f"{preferred['title']} ({verdict})") if preferred \
        else _say(VERDICT["拿不准" if unsure else "不是"], lang)
    stable = suggestion.get("stable")
    if stable is None:
        return words, ""
    agreed = f"{suggestion['agree']}/{suggestion['readings']}"
    return words, _say((f"一致 {agreed}", f"Consistent {agreed}") if stable else (f"不一致 {agreed}", f"Inconsistent {agreed}"), lang)


def _covered(conditions: list[dict[str, Any]], has_asset, lang: str) -> str:
    """How many of a scene's test conditions have an asset: "工况 3/4 有素材"."""
    if not conditions:
        return ""
    count = sum(bool(has_asset(item)) for item in conditions)
    return f"工况 {count}/{len(conditions)} 有素材" if lang == "zh" else f"{count} of {len(conditions)} conditions with an asset"


def _condition_lines(row: dict[str, Any], lang: str) -> list[list[str]]:
    """One line per test condition: the confirmed asset, or the suggested one while nothing is confirmed."""
    binding, suggestion = row.get("binding"), row.get("suggestion")
    head = [row["filename"], row["section_id"], row["title"]]
    if binding:
        return [[*head, f"{item['id']} {item['label']}", _say(STATUS[item["status"]], lang), item["title"] or "", "",
                 item["changes"], "", "", "", "", ""] for item in binding.get("conditions", [])]
    if not suggestion or suggestion.get("failure") or suggestion.get("outdated"):
        return []
    titles = {item["id"]: item["title"] for item in suggestion["candidates"]}
    lines = []
    for item in suggestion.get("conditions", []):
        verdict = _say(STATUS["same" if item["fit"] == "直接复用" else "modify"] if item["asset"] else STATUS["none"], lang)
        words = (f"{titles[item['asset']]}（{verdict}）" if lang == "zh" else f"{titles[item['asset']]} ({verdict})") \
            if item["asset"] else verdict
        agreed = f"{item['agree']}/{suggestion['readings']}"
        settled = _say((f"一致 {agreed}", f"Consistent {agreed}") if item["agree"] == suggestion["readings"]
                       else (f"不一致 {agreed}", f"Inconsistent {agreed}"), lang)
        lines.append([*head, f"{item['id']} {item['label']}", _say(STATUS["unconfirmed"], lang), "", "", "", "", "", "",
                      words, settled])
    return lines


def table(rows: list[dict[str, Any]], lang: str) -> list[list[str]]:
    """Heading line and one line per scene, from the rows the binding view lists, each scene with test
    conditions followed by a line per condition."""
    lines = [[_say(pair, lang) for pair in HEADINGS]]
    for row in rows:
        binding = row.get("binding")
        assets = sorted(binding["assets"], key=lambda item: not item["preferred"]) if binding else []
        suggested, settled = _suggested(row.get("suggestion"), lang) if not binding else ("", "")
        if binding and binding.get("conditions"):
            covered = _covered(binding["conditions"], lambda item: item["asset_id"], lang)
        elif not binding and suggested and row["suggestion"].get("conditions"):
            covered = _covered(row["suggestion"]["conditions"], lambda item: item["asset"], lang)
            suggested = covered
        else:
            covered = ""
        lines.append([
            row["filename"], row["section_id"], row["title"], covered,
            _say(STATUS[binding["status"] if binding else "unconfirmed"], lang),
            assets[0]["title"] if assets else "",
            "；".join(item["title"] for item in assets[1:]) if lang == "zh" else "; ".join(item["title"] for item in assets[1:]),
            binding.get("changes", "") if binding else "",
            ("；" if lang == "zh" else "; ").join(_say(STALE.get(reason, (reason, reason)), lang) for reason in binding["stale"]) if binding else "",
            _say(SOURCE.get(binding["source"], (binding["source"], binding["source"])), lang) if binding else "",
            binding["confirmed_at"][:16].replace("T", " ") if binding else "",
            suggested, settled,
        ])
        lines.extend(_condition_lines(row, lang))
    return lines


def to_csv(lines: list[list[str]]) -> bytes:
    """UTF-8 with a byte order mark, so a spreadsheet opens the Chinese text as written."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\r\n").writerows(lines)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def to_html(lines: list[list[str]], documents: list[str], lang: str) -> bytes:
    title = _say(("条款复用评估表", "Clause reuse assessment"), lang)
    counts = {}
    condition_column, status_column = 3, 4
    for line in lines[1:]:
        if line[condition_column][:1] == "V":  # a test condition's line, counted with its clause
            continue
        counts[line[status_column]] = counts.get(line[status_column], 0) + 1
    summary = " · ".join(f"{name} {count}" for name, count in counts.items())
    head = "".join(f"<th>{html.escape(cell)}</th>" for cell in lines[0])
    body = "".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in line) + "</tr>" for line in lines[1:])
    page = f"""<!doctype html>
<html lang="{'zh-CN' if lang == 'zh' else 'en'}"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font:13px/1.5 system-ui,"Microsoft YaHei",sans-serif;margin:24px;color:#1f2937}}
h1{{font-size:18px;margin:0 0 4px}} .meta{{color:#6b7280;margin:0 0 16px}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #e5e7eb;padding:4px 8px;text-align:left;vertical-align:top}}
th{{background:#f3f4f6;font-weight:600;position:sticky;top:0}} tr:nth-child(even) td{{background:#fafafa}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="meta">{html.escape(' · '.join(documents))}<br>{html.escape(summary)} · {datetime.now():%Y-%m-%d %H:%M}</p>
<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
</body></html>
"""
    return page.encode("utf-8")
