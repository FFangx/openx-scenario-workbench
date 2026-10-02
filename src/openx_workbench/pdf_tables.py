"""Serialize detected native cells without guessing missing values or page joins."""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from html import escape

_TOLERANCE = .5  # PDF points; collapse detector jitter, not separate cell edges.


def _text(value):
    return escape("" if value is None else str(value)).replace("\n", "<br>")


def _edges(values):
    edges = []
    for value in sorted(values):
        if not edges or value - edges[-1] > _TOLERANCE:
            edges.append(value)
    return edges


def _edge_index(edges, value):
    start = bisect_left(edges, value - _TOLERANCE)
    end = bisect_right(edges, value + _TOLERANCE)
    if end - start != 1:
        raise ValueError("Cell edge does not match a unique grid boundary")
    return start


def native_table_html(table, rows):
    """Return HTML and review kind; each detected cell owns its value exactly once."""
    try:
        cells = []
        geometry_rows = table.rows
        if len(rows) != len(geometry_rows):
            raise ValueError("Cell geometry and text rows differ")
        for geometry, values in zip(geometry_rows, rows):
            if len(geometry.cells) != len(values):
                raise ValueError("Cell geometry and text columns differ")
            for box, value in zip(geometry.cells, values):
                if box is None:
                    if value is not None:
                        raise ValueError("Text has no cell geometry")
                    continue
                if len(box) != 4 or any(not math.isfinite(v) for v in box) or box[0] >= box[2] or box[1] >= box[3]:
                    raise ValueError("Cell geometry is invalid")
                cells.append((box, value))
        if not cells:
            raise ValueError("Table has no cells")
        xs = _edges(v for box, _ in cells for v in (box[0], box[2]))
        ys = _edges(v for box, _ in cells for v in (box[1], box[3]))
        if (len(xs) - 1) * (len(ys) - 1) > 50_000:
            raise ValueError("Table grid is too large")
        owners, anchors = {}, {}
        merged = False
        for index, (box, value) in enumerate(cells):
            x0, y0, x1, y1 = (_edge_index(edges, value) for edges, value in zip((xs, ys, xs, ys), box))
            if x0 >= x1 or y0 >= y1:
                raise ValueError("Cell collapsed during grid alignment")
            for r in range(y0, y1):
                for c in range(x0, x1):
                    if (r, c) in owners:
                        raise ValueError("Detected cells overlap")
                    owners[r, c] = index
            anchors[y0, x0] = (value, y1 - y0, x1 - x0)
            merged |= y1 - y0 > 1 or x1 - x0 > 1
        if len(owners) != (len(xs) - 1) * (len(ys) - 1):
            raise ValueError("Table grid contains unresolved holes")
        rendered = []
        for r in range(len(ys) - 1):
            row = []
            for c in range(len(xs) - 1):
                if (r, c) not in anchors:
                    continue  # Covered by a cell anchored in an earlier row/column.
                value, rowspan, colspan = anchors[r, c]
                attributes = (f' rowspan="{rowspan}"' if rowspan > 1 else "") + (f' colspan="{colspan}"' if colspan > 1 else "")
                row.append(f"<td{attributes}>{_text(value)}</td>")
            rendered.append("<tr>" + "".join(row) + "</tr>")
        return "<table>" + "".join(rendered) + "</table>", "table_merged_cells" if merged else None
    except (ValueError, TypeError, AttributeError):
        # Preserve extracted slots when geometry is ambiguous; never forward-fill.
        html = "<table>" + "".join("<tr>" + "".join(
            '<td data-unresolved="true"></td>' if value is None else "<td>" + _text(value) + "</td>"
            for value in row) + "</tr>" for row in rows) + "</table>"
        return html, "table_geometry_unresolved"
