"""Readable, self-contained export of a grounded reuse trace."""

from __future__ import annotations

from html import escape
import json
from typing import Any
from .reuse_trace import checked_trace


def _report_body(trace: dict[str, Any]) -> str:
    trace = checked_trace(trace)
    source = trace.get("source") or {}
    candidate = trace.get("candidate") or {}
    reuse = trace.get("reuse") or {}
    scores = trace.get("scores") or {}
    evidence = source.get("evidence") or []

    def value(item: Any) -> str:
        return escape(str(item if item is not None else "—"), quote=True)

    def row(label: str, item: Any) -> str:
        return f"<tr><th>{value(label)}</th><td>{value(item)}</td></tr>"

    evidence_html = "".join(
        "<article class='evidence'>"
        f"<h3>{value(item.get('source_pdf'))} · pages {value(item.get('page_start'))}–{value(item.get('page_end'))}</h3>"
        f"<p><strong>Section:</strong> {value(item.get('section_id'))}</p>"
        f"<blockquote>{value(item.get('source_text'))}</blockquote>"
        "</article>" for item in evidence
    ) or "<p>No PDF evidence was attached.</p>"
    differences = "".join(
        "<tr>" + "".join(f"<td>{value(item.get(key))}</td>"
                            for key in ("category", "requested", "candidate", "action", "blocking", "verified")) + "</tr>"
        for item in reuse.get("differences", [])
    ) or "<tr><td colspan='6'>No structural differences recorded.</td></tr>"
    reasons = "".join(f"<li>{value(reason)}</li>" for reason in reuse.get("reasons", []))
    validation = (candidate.get("parsed_facts") or {}).get("validation") or {}
    validation_html = "".join(
        row(record.get("standard") or role, f"{record.get('version') or ''} · {record.get('status', 'unavailable')}")
        + row("Schema revision", record.get("source_revision"))
        + row("Issues", "; ".join(f"L{issue['line']}: {issue['message']}" for issue in record.get("issues", [])) or record.get("detail") or "—")
        for role, record in validation.items()
    )
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
        f"<h2>Evidence explanation</h2><p>Method: {value(explanation.get('method'))}. "
        f"The structural verdict above remains authoritative.</p><ul>{observations_html}</ul>"
        f"<h3>Citation locations</h3><ul>{evidence_locations}</ul>"
    ) if explanation else ""
    scenario = (candidate.get("parsed_facts") or {}).get("scenario") or {}
    parameter_audit = {key: scenario.get(key, []) for key in
                       ("parameters", "parameter_resolutions", "parameter_issues", "events")}
    parameter_html = ("<h2>Parameter and event evidence</h2><details><summary>Parsed source audit</summary><pre>"
                      + value(json.dumps(parameter_audit, ensure_ascii=False, indent=2)) + "</pre></details>")
    return f"""<h1>OpenX reuse trace</h1><p class="muted">Exact asset version and source evidence for review.</p>
<h2>Decision</h2><table>{row('Reuse level', reuse.get('level'))}{row('Structural match', reuse.get('structural_level', reuse.get('level')))}{row('Review scope', reuse.get('review_kind') or '—')}{row('Direct confirmation standard gate', (trace.get('standard_checks') or {}).get('passed', 'Not recorded'))}{row('Estimated change cost', reuse.get('estimated_change_cost'))}
{row('Source scene', source.get('title'))}{row('Asset', candidate.get('title'))}{row('Asset ID', candidate.get('asset_id'))}
{row('PDF document ID', source.get('document_id'))}{row('PDF SHA-256', source.get('pdf_sha256'))}
{row('Scene ID', source.get('scene_id'))}{row('Scene revision', source.get('revision'))}
{row('Version ID', candidate.get('version_id'))}{row('Version number', candidate.get('version_number'))}
{row('Content SHA-256', candidate.get('content_sha256'))}</table>
<h2>Asset files</h2><table>{row('OpenSCENARIO', candidate.get('xosc'))}{row('OpenDRIVE', candidate.get('xodr'))}</table>
<h2>File standard checks</h2><p>XSD structure checks do not certify simulation or complete ASAM conformance.</p><table>{validation_html or row('Status', 'Not recorded')}</table>
<h2>Retrieval scores</h2><table>{''.join(row(key, val) for key, val in scores.items())}</table>
<h2>Matched evidence</h2><ul>{reasons or '<li>No matched reasons recorded.</li>'}</ul>
<h2>Differences and actions</h2><table class="wide"><thead><tr><th>Category</th><th>Requested</th><th>Candidate</th><th>Action</th><th>Blocking</th><th>Verified</th></tr></thead><tbody>{differences}</tbody></table>
{parameter_html}
{explanation_html}
<h2>Original PDF evidence</h2>{evidence_html}
"""


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


def render_report(trace: dict[str, Any]) -> str:
    trace = checked_trace(trace)
    if trace.get("kind") != "batch_match":
        body = _report_body(trace)
    else:
        rows = []
        details = []
        for entry in trace.get("entries", []):
            source = entry["source"]
            candidates = entry.get("candidates", [])
            assessment = entry["assessment"]
            best = candidates[0]["candidate"] if candidates else {}
            values = (source.get("title"), source.get("revision"), best.get("xosc", "—"),
                      assessment.get("review_kind") or assessment["level"], assessment.get("estimated_change_cost", "—"))
            rows.append("<tr>" + "".join("<td>" + escape(str(value), quote=True) + "</td>" for value in values) + "</tr>")
            details.extend(_report_body(candidate) for candidate in candidates)
        body = ("<h1>OpenX document assessment</h1><p>" + escape(str(trace["source"]["title"]))
                + "</p><p>Encoder: " + escape(str(trace["encoder"])) + "</p><p>Scene counts: "
                + escape(str(trace.get("counts", {}))) + "</p><p>Review and missing candidates require follow-up; these are assessment snapshots.</p>"
                + "<table class=wide><thead><tr><th>Scene</th><th>Revision</th><th>Best candidate</th><th>Assessment</th><th>Change cost</th></tr></thead><tbody>"
                + "".join(rows) + "</tbody></table>" + "".join(details))
    return _REPORT_HEADER + body + "</body></html>"
