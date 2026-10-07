"""Readable, self-contained export of a grounded reuse trace."""

from __future__ import annotations

from html import escape
import json
import re
from collections import defaultdict
from typing import Any
from .reuse_trace import checked_trace
from .presentation import display


_ZH = {
    "OpenX reuse trace": "OpenX 复用评估报告", "Exact asset version and source evidence for review.": "包含确切资产版本和原文证据，供复核使用。",
    "Decision": "评估结论", "Reuse level": "复用结论", "Structural match": "结构匹配", "Review scope": "复核范围",
    "Direct confirmation standard gate": "直接复用标准检查", "Estimated change cost": "修改成本（相对分值）",
    "Source scene": "来源需求", "Asset": "候选资产", "Asset ID": "资产标识", "PDF document ID": "PDF 文档标识",
    "PDF SHA-256": "PDF 内容 SHA-256", "Scene ID": "场景标识", "Scene revision": "事实修订",
    "Version ID": "资产版本标识", "Version number": "资产版本", "Content SHA-256": "资产内容 SHA-256",
    "Asset files": "资产文件", "File standard checks": "文件标准检查", "Retrieval scores": "检索相似度",
    "XSD structure checks do not certify simulation or complete ASAM conformance.": "XSD 检查针对文件结构；仿真能否运行需通过预览另行验证。",
    "Matched evidence": "匹配依据", "No matched reasons recorded.": "没有记录匹配依据。",
    "Differences and actions": "差异与建议操作", "Category": "差异类型", "Requested": "需求事实", "Candidate": "候选事实",
    "Action": "建议操作", "Blocking": "阻断复用", "Verified": "已核实", "Original PDF evidence": "原始 PDF 证据",
    "No PDF evidence was attached.": "未关联 PDF 证据。", "No structural differences recorded.": "未记录结构差异。",
    "Parameter and event evidence": "参数与事件证据", "Parsed source audit": "原始解析记录（技术详情）",
    "Schema revision": "标准定义版本", "Issues": "原始诊断", "Status": "状态", "Evidence explanation": "证据解释",
    "Citation locations": "引用位置", "OpenX document assessment": "OpenX 文档评估报告",
    "Review and missing candidates require follow-up; these are assessment snapshots.": "待复核和无候选场景需要继续处理；此报告保留评估时的快照。",
    "Document": "文档", "Scene": "需求场景", "Revision": "事实修订", "Top candidates": "候选（前三）", "Assessment": "评估结论", "Change cost": "修改成本（相对分值）",
    "Review sign-off": "复核确认", "Signed at": "确认时间", "Review item": "复核项", "Reason": "确认理由",
    "File standard checks did not pass or could not run": "文件标准检查未通过或未完成",
}


def _localized_templates(markup, language):
    """Translate exact template text nodes only, never substrings in source data."""
    if language != "zh":
        return markup
    return re.sub(r">([^<>]+)<", lambda m: ">" + _ZH.get(m[1], m[1]) + "<", markup)


def _report_body(trace: dict[str, Any], language="en") -> str:
    trace = checked_trace(trace)
    source = trace.get("source") or {}
    candidate = trace.get("candidate") or {}
    reuse = trace.get("reuse") or {}
    scores = trace.get("scores") or {}
    evidence = source.get("evidence") or []

    def value(item: Any) -> str:
        return escape(str(item if item is not None else "—"), quote=True)

    def row(label: str, item: Any) -> str:
        translated = display(item, language) if label in {"Reuse level", "Structural match", "Review scope", "Direct confirmation standard gate"} else item
        return f"<tr><th>{value(_ZH.get(label, label) if language == 'zh' else label)}</th><td>{value(translated)}</td></tr>"

    evidence_html = "".join(
        "<article class='evidence'>"
        f"<h3>{value(item.get('source_pdf'))} · {'页码' if language == 'zh' else 'pages'} {value(item.get('page_start'))}–{value(item.get('page_end'))}</h3>"
        f"<p><strong>{'条款：' if language == 'zh' else 'Section:'}</strong> {value(item.get('section_id'))}</p>"
        f"<blockquote>{value(item.get('source_text'))}</blockquote>"
        "</article>" for item in evidence
    ) or "<p>No PDF evidence was attached.</p>"
    differences = "".join(
        "<tr>" + "".join(f"<td>{value(display(item.get(key), language))}</td>"
                            for key in ("category", "requested", "candidate", "action", "blocking", "verified")) + "</tr>"
        for item in reuse.get("differences", [])
    ) or "<tr><td colspan='6'>No structural differences recorded.</td></tr>"
    reasons = "".join(f"<li>{value(display(reason, language))}</li>" for reason in reuse.get("reasons", []))
    signoff = reuse.get("review_signoff")
    signoff_html = ("<h2>Review sign-off</h2><p>" + value(signoff.get("signed_at")) + "</p><table class='wide'><thead><tr>"
                    "<th>Review item</th><th>Reason</th></tr></thead><tbody>" + "".join(
                        "<tr><td>" + (value(display(" · ".join(str(item["difference"].get(key)) for key in
                                                               ("category", "requested", "candidate")), language))
                                      if item.get("difference") else
                                      "File standard checks did not pass or could not run")
                        + f"</td><td>{value(item.get('reason'))}</td></tr>" for item in signoff.get("items", []))
                    + "</tbody></table>") if signoff else ""
    validation = (candidate.get("parsed_facts") or {}).get("validation") or {}
    validation_parts = []
    for role, record in validation.items():
        validation_parts.append(row(record.get("standard") or role, f"{record.get('version') or ''} · {display(record.get('status', 'unavailable'), language)}"))
        groups = defaultdict(list)
        for issue in record.get("issues", []):
            groups[issue["message"]].append(issue.get("line"))
        if groups or record.get("detail"):
            label = (f"{sum(map(len, groups.values()))} 处问题 · {len(groups)} 类 · 查看原始诊断" if language == "zh" else
                     f"{sum(map(len, groups.values()))} issues · {len(groups)} groups · Original diagnostics")
            detail = "\n".join(f"L{','.join(str(line) for line in dict.fromkeys(lines))}: {message}" for message, lines in groups.items()) or record.get("detail", "")
            validation_parts.append(f"<tr><th>{'诊断' if language == 'zh' else 'Diagnostics'}</th><td><details><summary>{value(label)}</summary><pre>{value(detail)}</pre></details></td></tr>")
    validation_html = "".join(validation_parts)
    explanation = trace.get("explanation") or {}
    observations_html = "".join(
        f"<li>{value(item.get('text'))} <small>[{value(', '.join(item.get('citations') or []))}]</small></li>"
        for item in explanation.get("observations", [])
    )
    evidence_locations = "".join(
        f"<li>[{value(item.get('evidence_id'))}] {value(item.get('location'))}</li>"
        for item in explanation.get("evidence", [])
    )
    explanation_html = (
        f"<h2>Evidence explanation</h2><p>{'解释方法：' if language == 'zh' else 'Method: '}{value(display(explanation.get('method'), language))}. "
        f"{'解释供复核参考，结构评估结论保持不变。' if language == 'zh' else 'The structural verdict above remains authoritative.'}</p><ul>{observations_html}</ul>"
        f"<h3>Citation locations</h3><ul>{evidence_locations}</ul>"
    ) if explanation else ""
    scenario = (candidate.get("parsed_facts") or {}).get("scenario") or {}
    parameter_audit = {key: scenario.get(key, []) for key in
                       ("parameters", "parameter_resolutions", "parameter_issues", "events")}
    parameter_html = ("<h2>Parameter and event evidence</h2><details><summary>Parsed source audit</summary><pre>"
                      + value(json.dumps(parameter_audit, ensure_ascii=False, indent=2)) + "</pre></details>")
    return _localized_templates(f"""<h1>OpenX reuse trace</h1><p class="muted">Exact asset version and source evidence for review.</p>
<h2>Decision</h2><table>{row('Reuse level', reuse.get('level'))}{row('Structural match', reuse.get('structural_level', reuse.get('level')))}{row('Review scope', reuse.get('review_kind') or '—')}{row('Direct confirmation standard gate', (trace.get('standard_checks') or {}).get('passed', 'Not recorded'))}{row('Estimated change cost', reuse.get('estimated_change_cost'))}
{row('Source scene', source.get('title'))}{row('Asset', candidate.get('title'))}</table>
{signoff_html}
<details><summary>{'版本与证据追踪信息' if language == 'zh' else 'Version and source identity'}</summary><table>{row('Asset ID', candidate.get('asset_id'))}
{row('PDF document ID', source.get('document_id'))}{row('PDF SHA-256', source.get('pdf_sha256'))}
{row('Scene ID', source.get('scene_id'))}{row('Scene revision', source.get('revision'))}
{row('Version ID', candidate.get('version_id'))}{row('Version number', candidate.get('version_number'))}
{row('Content SHA-256', candidate.get('content_sha256'))}</table></details>
<h2>Asset files</h2><table>{row('OpenSCENARIO', candidate.get('xosc'))}{row('OpenDRIVE', candidate.get('xodr'))}</table>
<h2>File standard checks</h2><p>XSD structure checks do not certify simulation or complete ASAM conformance.</p><table>{validation_html or row('Status', 'Not recorded')}</table>
<h2>Retrieval scores</h2><table>{''.join(row(display(key, language), val) for key, val in scores.items())}</table>
<h2>Matched evidence</h2><ul>{reasons or '<li>No matched reasons recorded.</li>'}</ul>
<h2>Differences and actions</h2><table class="wide"><thead><tr><th>Category</th><th>Requested</th><th>Candidate</th><th>Action</th><th>Blocking</th><th>Verified</th></tr></thead><tbody>{differences}</tbody></table>
{parameter_html}
{explanation_html}
<h2>Original PDF evidence</h2>{evidence_html}
""", language)


_REPORT_HEADER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenX reuse trace</title><style>
body{font:16px/1.55 system-ui,sans-serif;max-width:960px;margin:48px auto;padding:0 24px;color:#183044;background:#fff}
h1{font-size:30px;margin:0 0 8px}h2{margin-top:38px;border-bottom:2px solid #0b6b92;padding-bottom:7px}
table{border-collapse:collapse;width:100%;margin:12px 0}th,td{text-align:left;padding:9px 11px;border:1px solid #d3e0e7;vertical-align:top}
th{background:#eff5f7;width:190px}.wide{display:block;overflow-x:auto}.wide th{width:auto}td{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}blockquote{margin:12px 0;padding:12px 16px;border-left:1px solid #0b6b92;background:#f5f9fa;white-space:pre-wrap}
.evidence{margin:20px 0}.muted{color:#526b78}@media print{body{margin:0;max-width:none}}
</style></head><body>
"""


def render_report(trace: dict[str, Any], *, language="en") -> str:
    trace = checked_trace(trace)
    if trace.get("kind") != "batch_match":
        body = _report_body(trace, language)
    else:
        rows = []
        details = []
        grouped = len(trace["source"].get("documents") or []) > 1  # one summary of several PDFs names each row's
        for entry in trace.get("entries", []):
            source = entry["source"]
            candidates = entry.get("candidates", [])
            assessment = entry["assessment"]
            # The top candidates, each with its own verdict: an engineer checks all of them.
            top = "<br>".join(escape(f"{rank}. {item['candidate'].get('xosc', '—')} "
                                     f"({display(item['reuse'].get('review_kind') or item['reuse']['level'], language)})",
                                     quote=True) for rank, item in enumerate(candidates[:3], 1)) or "—"
            values = (source.get("title"), source.get("revision"), top,
                      display(assessment.get("review_kind") or assessment["level"], language), assessment.get("estimated_change_cost", "—"))
            cells = ["<td>" + (value if index == 2 else escape(str(value), quote=True)) + "</td>"
                     for index, value in enumerate(values)]
            if grouped:
                cells.insert(0, "<td>" + escape(str(source.get("filename") or "—"), quote=True) + "</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
            details.extend(_report_body(candidate, language) for candidate in candidates)
        body = ("<h1>OpenX document assessment</h1><p>" + escape(str(trace["source"]["title"]))
                + "</p><p>" + ("检索编码器：" if language == "zh" else "Encoder: ") + escape(str(trace["encoder"])) + "</p><p>" + ("场景数量：" if language == "zh" else "Scene counts: ")
                + escape(" · ".join(f"{display(k, language)}: {v}" for k, v in trace.get("counts", {}).items())) + "</p><p>Review and missing candidates require follow-up; these are assessment snapshots.</p>"
                + "<table class=wide><thead><tr>" + ("<th>Document</th>" if grouped else "") + "<th>Scene</th><th>Revision</th><th>Top candidates</th><th>Assessment</th><th>Change cost</th></tr></thead><tbody>"
                + "".join(rows) + "</tbody></table>" + "".join(details))
    header = _REPORT_HEADER.replace('lang="en"', 'lang="zh-CN"') if language == "zh" else _REPORT_HEADER
    return _localized_templates(header, language) + _localized_templates(body, language) + "</body></html>"
