#!/usr/bin/env python3
"""DXF 向量圖面標註網頁產生工具 for fire-review.

讀取 annotations.json 與 DXF 圖面，輸出單一 HTML。HTML 內嵌 SVG 圖面、
缺失標註、缺失清單導覽與縮放/平移互動。

Usage:
    python3 tools/dxf_svg_review.py --annotations output/{案件名}-{日期}/annotations.json
"""

import argparse
import html
import json
import math
import sys
import warnings
from pathlib import Path


SEVERITY_CLASS = {
    "重大缺失": "critical",
    "一般缺失": "major",
    "配置疑義": "question",
    "需人工判讀": "manual",
}

SEVERITY_COLOR = {
    "重大缺失": "#d71920",
    "一般缺失": "#e66b00",
    "配置疑義": "#b08b00",
    "需人工判讀": "#666666",
}


class ReviewInputError(Exception):
    """Raised when review inputs are missing or invalid."""


def resolve_input_path(raw_path, annotations_path):
    path = Path(raw_path)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return annotations_path.parent / path


def resolve_output_path(raw_path, annotations_path):
    path = Path(raw_path)
    if path.is_absolute():
        return path
    if len(path.parts) == 1:
        return annotations_path.parent / path
    return Path.cwd() / path


def import_ezdxf():
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"ezdxf\..*")
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"pyparsing\..*")
            import ezdxf
    except ImportError as exc:
        raise ReviewInputError(
            "缺少 ezdxf，請先安裝：python3 -m pip install -r requirements.txt"
        ) from exc
    return ezdxf


def point_tuple(point):
    return (float(point[0]), float(point[1]))


def entity_layer(entity):
    return html.escape(str(getattr(entity.dxf, "layer", "0")))


def collect_dxf_entities(dxf_path):
    ezdxf = import_ezdxf()
    doc = ezdxf.readfile(dxf_path)
    modelspace = doc.modelspace()
    entities = []
    warnings = []
    points = []
    layers = set()

    for entity in modelspace:
        dxftype = entity.dxftype()
        layers.add(str(getattr(entity.dxf, "layer", "0")))
        try:
            if dxftype == "LINE":
                start = point_tuple(entity.dxf.start)
                end = point_tuple(entity.dxf.end)
                entities.append({"type": "line", "points": [start, end], "layer": entity_layer(entity)})
                points.extend([start, end])
            elif dxftype == "LWPOLYLINE":
                poly_points = [(float(p[0]), float(p[1])) for p in entity.get_points()]
                if len(poly_points) >= 2:
                    entities.append(
                        {
                            "type": "polyline",
                            "points": poly_points,
                            "closed": bool(entity.closed),
                            "layer": entity_layer(entity),
                        }
                    )
                    points.extend(poly_points)
            elif dxftype == "POLYLINE":
                poly_points = [point_tuple(v.dxf.location) for v in entity.vertices]
                if len(poly_points) >= 2:
                    entities.append(
                        {
                            "type": "polyline",
                            "points": poly_points,
                            "closed": bool(entity.is_closed),
                            "layer": entity_layer(entity),
                        }
                    )
                    points.extend(poly_points)
            elif dxftype == "CIRCLE":
                center = point_tuple(entity.dxf.center)
                radius = float(entity.dxf.radius)
                entities.append(
                    {"type": "circle", "center": center, "radius": radius, "layer": entity_layer(entity)}
                )
                points.extend(
                    [
                        (center[0] - radius, center[1] - radius),
                        (center[0] + radius, center[1] + radius),
                    ]
                )
            elif dxftype == "ARC":
                center = point_tuple(entity.dxf.center)
                radius = float(entity.dxf.radius)
                start = float(entity.dxf.start_angle)
                end = float(entity.dxf.end_angle)
                entities.append(
                    {
                        "type": "arc",
                        "center": center,
                        "radius": radius,
                        "start": start,
                        "end": end,
                        "layer": entity_layer(entity),
                    }
                )
                points.extend(
                    [
                        (center[0] - radius, center[1] - radius),
                        (center[0] + radius, center[1] + radius),
                    ]
                )
            elif dxftype == "TEXT":
                insert = point_tuple(entity.dxf.insert)
                text = entity.dxf.text
                height = float(getattr(entity.dxf, "height", 2.5))
                entities.append(
                    {
                        "type": "text",
                        "insert": insert,
                        "text": str(text),
                        "height": height,
                        "layer": entity_layer(entity),
                    }
                )
                points.append(insert)
            elif dxftype == "MTEXT":
                insert = point_tuple(entity.dxf.insert)
                text = entity.plain_text()
                height = float(getattr(entity.dxf, "char_height", 2.5) or 2.5)
                entities.append(
                    {
                        "type": "text",
                        "insert": insert,
                        "text": str(text),
                        "height": height,
                        "layer": entity_layer(entity),
                    }
                )
                points.append(insert)
            else:
                warnings.append(f"不支援的 DXF 實體：{dxftype}（圖層 {getattr(entity.dxf, 'layer', '0')}）")
        except Exception as exc:  # pragma: no cover - defensive for malformed CAD entities
            warnings.append(f"無法解析 {dxftype}：{exc}")

    if not points:
        points = [(0.0, 0.0), (100.0, 100.0)]
        warnings.append("DXF 未解析到可繪製實體，已使用空白檢視框。")

    return {
        "entities": entities,
        "warnings": warnings,
        "bbox": bbox_from_points(points),
        "layers": sorted(layers),
    }


def bbox_from_points(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def union_bbox(boxes):
    valid = [b for b in boxes if b]
    if not valid:
        return [0.0, 0.0, 100.0, 100.0]
    return [
        min(b[0] for b in valid),
        min(b[1] for b in valid),
        max(b[2] for b in valid),
        max(b[3] for b in valid),
    ]


def pad_bbox(bbox):
    x0, y0, x1, y1 = bbox
    width = max(x1 - x0, 1.0)
    height = max(y1 - y0, 1.0)
    pad = max(width, height) * 0.05
    return [x0 - pad, y0 - pad, x1 + pad, y1 + pad]


def svg_y(y, max_y):
    return max_y - y


def svg_point(point, max_y):
    return (point[0], svg_y(point[1], max_y))


def render_entities(entities, max_y):
    parts = []
    for entity in entities:
        layer = entity["layer"]
        if entity["type"] == "line":
            (x1, y1), (x2, y2) = [svg_point(p, max_y) for p in entity["points"]]
            parts.append(
                f'<line class="cad-entity" data-layer="{layer}" '
                f'x1="{x1:.4f}" y1="{y1:.4f}" x2="{x2:.4f}" y2="{y2:.4f}" />'
            )
        elif entity["type"] == "polyline":
            pts = " ".join(f"{x:.4f},{y:.4f}" for x, y in [svg_point(p, max_y) for p in entity["points"]])
            tag = "polygon" if entity.get("closed") else "polyline"
            parts.append(f'<{tag} class="cad-entity" data-layer="{layer}" points="{pts}" />')
        elif entity["type"] == "circle":
            cx, cy = svg_point(entity["center"], max_y)
            parts.append(
                f'<circle class="cad-entity" data-layer="{layer}" '
                f'cx="{cx:.4f}" cy="{cy:.4f}" r="{entity["radius"]:.4f}" />'
            )
        elif entity["type"] == "arc":
            parts.append(render_arc(entity, max_y))
        elif entity["type"] == "text":
            x, y = svg_point(entity["insert"], max_y)
            text = html.escape(entity["text"])
            parts.append(
                f'<text class="cad-text" data-layer="{layer}" '
                f'x="{x:.4f}" y="{y:.4f}" font-size="{entity["height"]:.4f}">{text}</text>'
            )
    return "\n".join(parts)


def render_arc(entity, max_y):
    cx, cy = entity["center"]
    radius = entity["radius"]
    start_rad = math.radians(entity["start"])
    end_rad = math.radians(entity["end"])
    sx, sy = cx + radius * math.cos(start_rad), cy + radius * math.sin(start_rad)
    ex, ey = cx + radius * math.cos(end_rad), cy + radius * math.sin(end_rad)
    sx, sy = svg_point((sx, sy), max_y)
    ex, ey = svg_point((ex, ey), max_y)
    sweep = 0
    large_arc = 1 if (entity["end"] - entity["start"]) % 360 > 180 else 0
    layer = entity["layer"]
    return (
        f'<path class="cad-entity" data-layer="{layer}" '
        f'd="M {sx:.4f} {sy:.4f} A {radius:.4f} {radius:.4f} 0 {large_arc} {sweep} {ex:.4f} {ey:.4f}" />'
    )


def normalize_annotation_bbox(annotation):
    raw = annotation.get("bbox") or annotation.get("rect")
    if not raw or len(raw) != 4:
        raise ReviewInputError(f"標註 #{annotation.get('issue_id', '?')} 缺少 bbox。")
    x0, y0, x1, y1 = [float(v) for v in raw]
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def render_annotations(annotations, max_y):
    parts = []
    for annotation in annotations:
        bbox = normalize_annotation_bbox(annotation)
        x0, y0, x1, y1 = bbox
        sx0, sy_top = svg_point((x0, y1), max_y)
        sx1, sy_bottom = svg_point((x1, y0), max_y)
        width = max(sx1 - sx0, 1.0)
        height = max(sy_bottom - sy_top, 1.0)
        cx = sx0 + width / 2
        cy = sy_top + height / 2
        issue_id = html.escape(str(annotation["issue_id"]))
        severity = annotation.get("severity", "一般缺失")
        css_class = SEVERITY_CLASS.get(severity, "major")
        label = html.escape(annotation.get("label", ""))
        color = SEVERITY_COLOR.get(severity, SEVERITY_COLOR["一般缺失"])
        parts.append(
            f'<g id="svg-issue-{issue_id}" class="issue-marker {css_class}" '
            f'data-issue-id="{issue_id}" data-drawing-id="{html.escape(str(annotation.get("drawing_id", "")))}" '
            f'tabindex="0" role="button" aria-label="缺失 {issue_id} {label}">'
            f'<ellipse cx="{cx:.4f}" cy="{cy:.4f}" rx="{width / 2:.4f}" ry="{height / 2:.4f}" '
            f'stroke="{color}" />'
            f'<circle class="issue-badge" cx="{sx0:.4f}" cy="{sy_top:.4f}" r="7" fill="{color}" />'
            f'<text class="issue-number" x="{sx0:.4f}" y="{sy_top + 3:.4f}">{issue_id}</text>'
            f"</g>"
        )
    return "\n".join(parts)


def render_issue_list(annotations):
    rows = []
    for annotation in annotations:
        issue_id = html.escape(str(annotation["issue_id"]))
        severity = html.escape(annotation.get("severity", ""))
        label = html.escape(annotation.get("label", ""))
        note = html.escape(annotation.get("note", ""))
        drawing_id = html.escape(str(annotation.get("drawing_id", "")))
        confidence = html.escape(annotation.get("position_confidence", ""))
        rows.append(
            f'<button class="issue-card" type="button" data-issue-id="{issue_id}" '
            f'onclick="selectIssue(\'{issue_id}\')">'
            f'<span class="issue-meta">#{issue_id}｜{severity}｜{drawing_id}｜位置信心度 {confidence}</span>'
            f"<strong>{label}</strong>"
            f"<span>{note}</span>"
            f"</button>"
        )
    return "\n".join(rows)


def render_review_html(spec, drawings):
    annotations = spec.get("annotations", [])
    has_low_confidence = any(a.get("position_confidence") == "low" for a in annotations)
    drawing_bboxes = [d["parsed"]["bbox"] for d in drawings]
    annotation_bboxes = [normalize_annotation_bbox(a) for a in annotations]
    view_box = pad_bbox(union_bbox(drawing_bboxes + annotation_bboxes))
    x0, y0, x1, y1 = view_box
    width = max(x1 - x0, 1.0)
    height = max(y1 - y0, 1.0)
    max_y = y1
    svg_min_y = svg_y(y1, max_y)
    warnings = []
    for drawing in drawings:
        warnings.extend(drawing["parsed"]["warnings"])
    warning_html = ""
    if has_low_confidence:
        warnings.insert(0, "部分圈選位置為 AI 推定（position_confidence: low），以問題清單文字說明為準。")
    if warnings:
        warning_html = '<section class="warnings">' + "".join(
            f"<p>{html.escape(w)}</p>" for w in warnings
        ) + "</section>"

    svg_groups = []
    for drawing in drawings:
        drawing_id = html.escape(str(drawing["drawing_id"]))
        floor = html.escape(str(drawing.get("floor", "")))
        svg_groups.append(
            f'<g class="drawing" data-drawing-id="{drawing_id}" data-floor="{floor}">'
            f"{render_entities(drawing['parsed']['entities'], max_y)}"
            f"</g>"
        )

    title = f"{spec.get('case_name', '案件')}-圖面審查"
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{html.escape(spec.get('case_name', '案件'))} 圖面審查</h1>
  <p>本 SVG 標註由 AI 審圖輔助系統產生，僅供審查參考；缺失認定以問題清單、工具計算記錄與現行法規為準。</p>
</header>
{warning_html}
<main>
  <section class="viewer-panel" aria-label="DXF SVG 圖面">
    <div class="toolbar">
      <button type="button" onclick="zoomBy(0.82)">放大</button>
      <button type="button" onclick="zoomBy(1.22)">縮小</button>
      <button type="button" onclick="resetView()">重設</button>
    </div>
    <svg id="review-svg" viewBox="{x0:.4f} {svg_min_y:.4f} {width:.4f} {height:.4f}" xmlns="http://www.w3.org/2000/svg">
      <rect class="sheet-bg" x="{x0:.4f}" y="{svg_min_y:.4f}" width="{width:.4f}" height="{height:.4f}" />
      {chr(10).join(svg_groups)}
      <g id="issue-layer">
      {render_annotations(annotations, max_y)}
      </g>
    </svg>
  </section>
  <aside>
    <h2>缺失導覽</h2>
    <div id="review-list">
    {render_issue_list(annotations)}
    </div>
  </aside>
</main>
<script>{JS}</script>
</body>
</html>
"""


def load_review_spec(annotations_path):
    with annotations_path.open(encoding="utf-8") as f:
        spec = json.load(f)
    drawings = []
    source_drawings = spec.get("source_drawings") or []
    if not source_drawings and spec.get("source_dxf"):
        source_drawings = [{"drawing_id": "drawing-1", "path": spec["source_dxf"]}]
    if not source_drawings:
        raise ReviewInputError("annotations.json 缺少 source_drawings。")

    for drawing in source_drawings:
        if "drawing_id" not in drawing:
            raise ReviewInputError("source_drawings 每筆都必須包含 drawing_id。")
        if "path" not in drawing:
            raise ReviewInputError(f"圖面 {drawing['drawing_id']} 缺少 path。")
        dxf_path = resolve_input_path(drawing["path"], annotations_path)
        if not dxf_path.exists():
            raise ReviewInputError(f"找不到 DXF 圖面：{dxf_path}")
        drawings.append({**drawing, "path": dxf_path, "parsed": collect_dxf_entities(dxf_path)})
    return spec, drawings


def default_output_path(spec, annotations_path):
    if spec.get("output_html"):
        return resolve_output_path(spec["output_html"], annotations_path)
    case_name = spec.get("case_name", "案件")
    return annotations_path.parent / f"{case_name}-圖面審查.html"


def main(argv=None):
    parser = argparse.ArgumentParser(description="DXF 向量圖面標註網頁產生")
    parser.add_argument("--annotations", required=True, help="annotations.json 路徑")
    parser.add_argument("--output", help="輸出 HTML 路徑")
    args = parser.parse_args(argv)

    annotations_path = Path(args.annotations)
    spec, drawings = load_review_spec(annotations_path)
    out = Path(args.output) if args.output else default_output_path(spec, annotations_path)
    html_doc = render_review_html(spec, drawings)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(f"已輸出圖面審查 HTML：{out}（{len(spec.get('annotations', []))} 處標註）")


CSS = """
:root { color-scheme: light; --ink: #1f2933; --muted: #667085; --line: #d0d5dd; --panel: #f8fafc; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Noto Sans TC", "Microsoft JhengHei", Arial, sans-serif; color: var(--ink); background: #fff; }
header { padding: 20px 24px 12px; border-bottom: 1px solid var(--line); }
h1 { margin: 0 0 6px; font-size: 1.35rem; }
h2 { margin: 0 0 12px; font-size: 1rem; }
p { margin: 0; color: var(--muted); line-height: 1.5; }
main { display: grid; grid-template-columns: minmax(0, 1fr) 360px; min-height: calc(100vh - 98px); }
.viewer-panel { min-width: 0; background: #eef2f6; border-right: 1px solid var(--line); position: relative; }
.toolbar { display: flex; gap: 8px; padding: 10px; border-bottom: 1px solid var(--line); background: #fff; }
button { border: 1px solid var(--line); background: #fff; color: var(--ink); border-radius: 6px; padding: 7px 10px; cursor: pointer; font: inherit; }
button:hover { border-color: #8da2bd; }
svg { display: block; width: 100%; height: calc(100vh - 142px); background: #f7f9fb; cursor: grab; }
svg.dragging { cursor: grabbing; }
.sheet-bg { fill: #fff; stroke: #cfd8e3; stroke-width: .4; }
.cad-entity { fill: none; stroke: #263238; stroke-width: .45; vector-effect: non-scaling-stroke; }
.cad-text { fill: #475467; stroke: none; dominant-baseline: middle; }
.issue-marker ellipse { fill: rgba(215, 25, 32, .08); stroke-width: 2.8; vector-effect: non-scaling-stroke; }
.issue-marker .issue-number { fill: #fff; text-anchor: middle; font-size: 8px; font-weight: 700; pointer-events: none; }
.issue-marker.active ellipse { stroke-width: 5; fill: rgba(215, 25, 32, .18); }
aside { padding: 16px; overflow: auto; max-height: calc(100vh - 98px); }
#review-list { display: grid; gap: 10px; }
.issue-card { display: grid; gap: 5px; width: 100%; text-align: left; border-radius: 8px; padding: 10px; }
.issue-card.active { outline: 3px solid #d71920; border-color: #d71920; }
.issue-card strong { font-size: .96rem; }
.issue-card span { color: var(--muted); font-size: .85rem; line-height: 1.45; }
.issue-meta { color: #475467; font-size: .78rem; }
.warnings { margin: 0; padding: 10px 24px; border-bottom: 1px solid #f2c94c; background: #fff8d6; }
.warnings p { color: #7a4d00; font-size: .9rem; }
@media (max-width: 900px) {
  main { grid-template-columns: 1fr; }
  aside { max-height: none; border-top: 1px solid var(--line); }
  svg { height: 62vh; }
}
"""


JS = """
const svg = document.getElementById('review-svg');
const initialViewBox = svg.getAttribute('viewBox').split(' ').map(Number);
let currentViewBox = [...initialViewBox];
let dragStart = null;

function applyViewBox() {
  svg.setAttribute('viewBox', currentViewBox.map(v => Number(v).toFixed(4)).join(' '));
}

function zoomBy(factor) {
  const [x, y, w, h] = currentViewBox;
  const nw = w * factor;
  const nh = h * factor;
  currentViewBox = [x + (w - nw) / 2, y + (h - nh) / 2, nw, nh];
  applyViewBox();
}

function resetView() {
  currentViewBox = [...initialViewBox];
  applyViewBox();
  selectIssue(null);
}

function selectIssue(issueId) {
  document.querySelectorAll('.issue-marker, .issue-card').forEach(el => el.classList.remove('active'));
  if (!issueId) return;
  const marker = document.querySelector(`.issue-marker[data-issue-id="${issueId}"]`);
  const card = document.querySelector(`.issue-card[data-issue-id="${issueId}"]`);
  if (marker) {
    marker.classList.add('active');
    const box = marker.getBBox();
    const pad = Math.max(box.width, box.height, 20) * 1.8;
    currentViewBox = [box.x - pad, box.y - pad, box.width + pad * 2, box.height + pad * 2];
    applyViewBox();
  }
  if (card) {
    card.classList.add('active');
    card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

svg.addEventListener('click', event => {
  const marker = event.target.closest('.issue-marker');
  if (marker) selectIssue(marker.dataset.issueId);
});

svg.addEventListener('wheel', event => {
  event.preventDefault();
  zoomBy(event.deltaY < 0 ? 0.9 : 1.1);
}, { passive: false });

svg.addEventListener('pointerdown', event => {
  dragStart = { x: event.clientX, y: event.clientY, viewBox: [...currentViewBox] };
  svg.classList.add('dragging');
  svg.setPointerCapture(event.pointerId);
});

svg.addEventListener('pointermove', event => {
  if (!dragStart) return;
  const dx = (event.clientX - dragStart.x) * dragStart.viewBox[2] / svg.clientWidth;
  const dy = (event.clientY - dragStart.y) * dragStart.viewBox[3] / svg.clientHeight;
  currentViewBox = [dragStart.viewBox[0] - dx, dragStart.viewBox[1] - dy, dragStart.viewBox[2], dragStart.viewBox[3]];
  applyViewBox();
});

svg.addEventListener('pointerup', event => {
  dragStart = null;
  svg.classList.remove('dragging');
  svg.releasePointerCapture(event.pointerId);
});
"""


if __name__ == "__main__":
    try:
        main()
    except ReviewInputError as exc:
        sys.exit(str(exc))
