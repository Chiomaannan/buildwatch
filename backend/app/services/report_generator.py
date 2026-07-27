"""
report_generator.py — Assemble data, render HTML, and produce a PDF via WeasyPrint.

Designed to run synchronously inside asyncio.to_thread() so it doesn't block
the FastAPI event loop during the potentially slow WeasyPrint render step.
"""

import base64
import logging
from datetime import date, datetime, timezone

from jinja2 import Environment
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.image import Image, InferenceResult
from app.models.project import Project
from app.models.schedule import ScheduleMilestone
from app.models.worker import WorkerAlert
from app.services.minio_client import download_to_bytes

logger = logging.getLogger(__name__)
settings = get_settings()

_MWPI_MAX = {"foundation": 20.0, "column": 30.0, "wall": 50.0}

_jenv = Environment()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_report_pdf(
    project: Project,
    db: Session,
    date_from: date,
    date_to: date,
) -> bytes:
    """
    Build the full PDF for a project over the given date range.
    All I/O is synchronous — call via asyncio.to_thread() from async endpoints.
    """
    from weasyprint import HTML  # imported here so the module loads without WeasyPrint if unused

    context = _build_context(project, db, date_from, date_to)
    html = _TEMPLATE.render(**context)
    return HTML(string=html, base_url=None).write_pdf()


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------

def _build_context(project: Project, db: Session, date_from: date, date_to: date) -> dict:
    dt_from = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    dt_to   = datetime(date_to.year,   date_to.month,   date_to.day, 23, 59, 59, tzinfo=timezone.utc)

    # ── All completed inference results in period, joined with Image ──────────
    rows = (
        db.query(InferenceResult, Image)
        .join(Image, Image.id == InferenceResult.image_id)
        .filter(
            InferenceResult.project_id == project.id,
            InferenceResult.mwpi_score.isnot(None),
            InferenceResult.processed_at >= dt_from,
            InferenceResult.processed_at <= dt_to,
        )
        .filter(
            or_(
                Image.image_metadata.is_(None),
                func.json_extract_path_text(Image.image_metadata, "capture_type").is_(None),
                func.json_extract_path_text(Image.image_metadata, "capture_type") != "presence_check",
            )
        )
        .order_by(InferenceResult.processed_at.asc())
        .all()
    )

    results = [r for r, _ in rows]
    img_for = {r.id: img for r, img in rows}
    latest  = results[-1] if results else None

    # ── Trend points (pre-computed for SVG) ───────────────────────────────────
    trend_raw = [
        {"date": r.processed_at.strftime("%d %b"), "mwpi": round((r.mwpi_score or 0) * 100, 1)}
        for r in results
    ]
    svg_polyline, svg_circles = _make_svg_chart(trend_raw, chart_w=480, chart_h=80)

    # ── Average detection confidence across the period ────────────────────────
    total_conf, total_dets = 0.0, 0
    for r in results:
        for d in (r.yolo_detections or []):
            total_conf += d.get("confidence", 0)
            total_dets += 1
    avg_confidence = round(total_conf / max(total_dets, 1) * 100, 1)

    # ── Component breakdown bars (foundation / column / wall) ─────────────────
    cp = latest.component_progress or {} if latest else {}
    component_bars = [
        {
            "cls":    cls,
            "actual": round(cp.get(cls, 0), 1),
            "max":    max_pct,
            "fill":   round(min(cp.get(cls, 0) / max_pct * 100, 100), 1),
        }
        for cls, max_pct in _MWPI_MAX.items()
    ]

    # ── Schedule comparison table ─────────────────────────────────────────────
    milestones = (
        db.query(ScheduleMilestone)
        .filter(ScheduleMilestone.project_id == project.id)
        .order_by(ScheduleMilestone.week_number)
        .all()
    )
    # Build captured_at-indexed lookup for schedule comparison (same logic as schedule router)
    reversed_rows = list(reversed(rows))
    schedule_table = []
    for m in milestones:
        actual_r = next(
            (r for r, img in reversed_rows if img.captured_at[:10] <= m.planned_date),
            None,
        )
        actual_pct  = round((actual_r.mwpi_score or 0) * 100, 1) if actual_r else None
        planned_pct = round(m.planned_mwpi * 100, 1)
        deviation   = round(actual_pct - planned_pct, 1) if actual_pct is not None else None

        if deviation is None:
            status, color = "Pending", "#9CA3AF"
        elif deviation >= 0:
            status, color = "On schedule", "#0F6E56"
        elif deviation >= -10:
            status, color = "Slightly behind", "#D97706"
        else:
            status, color = "Delayed", "#DC2626"

        schedule_table.append({
            "week": m.week_number,
            "label": m.label or f"Week {m.week_number}",
            "planned_date": m.planned_date,
            "planned_mwpi": planned_pct,
            "actual_mwpi": actual_pct,
            "deviation": deviation,
            "status": status,
            "status_color": color,
        })

    # ── Worker alerts in period ───────────────────────────────────────────────
    alerts = (
        db.query(WorkerAlert)
        .filter(
            WorkerAlert.project_id == project.id,
            WorkerAlert.severity.in_(["critical", "warning"]),
            WorkerAlert.triggered_at >= dt_from,
            WorkerAlert.triggered_at <= dt_to,
        )
        .order_by(WorkerAlert.triggered_at.desc())
        .all()
    )
    alert_rows = [
        {
            "severity": a.severity,
            "message":  a.message,
            "time":     a.triggered_at.strftime("%d %b, %H:%M"),
        }
        for a in alerts
    ]

    # ── Top-4 site images embedded as base64 ─────────────────────────────────
    sorted_rows = sorted(
        rows,
        key=lambda pair: _avg_conf(pair[0]),
        reverse=True,
    )[:4]

    image_data = []
    for r, img in sorted_rows:
        if not img.raw_storage_path:
            continue
        try:
            raw = download_to_bytes(
                bucket=settings.minio_raw_bucket,
                object_name=img.raw_storage_path,
            )
            image_data.append({
                "src":             f"data:image/jpeg;base64,{base64.b64encode(raw).decode()}",
                "timestamp":       r.processed_at.strftime("%d %b %Y, %H:%M"),
                "detected_classes": r.detected_classes or [],
                "mwpi":            round((r.mwpi_score or 0) * 100, 1),
            })
        except Exception as e:
            logger.warning(f"Could not embed image {img.raw_storage_path}: {e}")

    return {
        "project":       project,
        "date_from":     date_from.strftime("%d %b %Y"),
        "date_to":       date_to.strftime("%d %b %Y"),
        "generated_at":  datetime.now().strftime("%d %b %Y at %H:%M"),
        "current_mwpi":  round((latest.mwpi_score or 0) * 100, 1) if latest else None,
        "ai_confidence": avg_confidence,
        "total_images":  len(results),
        "explanation":   latest.explanation if latest else None,
        "component_bars": component_bars,
        "trend_raw":     trend_raw,
        "svg_polyline":  svg_polyline,
        "svg_circles":   svg_circles,
        "schedule_table": schedule_table,
        "alert_rows":    alert_rows,
        "images":        image_data,
        "has_trend":     len(trend_raw) > 1,
        "has_schedule":  bool(schedule_table),
        "has_alerts":    bool(alert_rows),
        "has_images":    bool(image_data),
    }


def _avg_conf(r: InferenceResult) -> float:
    dets = r.yolo_detections or []
    if not dets:
        return 0.0
    return sum(d.get("confidence", 0) for d in dets) / len(dets)


def _make_svg_chart(
    points: list[dict],
    chart_w: int = 480,
    chart_h: int = 80,
) -> tuple[str | None, list[dict]]:
    n = len(points)
    if n < 2:
        return None, []
    polyline_pts = " ".join(
        f"{round(i / (n - 1) * chart_w, 1)},{round(chart_h - (pt['mwpi'] / 100 * chart_h), 1)}"
        for i, pt in enumerate(points)
    )
    circles = [
        {
            "x": round(i / (n - 1) * chart_w, 1),
            "y": round(chart_h - (pt["mwpi"] / 100 * chart_h), 1),
        }
        for i, pt in enumerate(points)
    ]
    return polyline_pts, circles


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_TEMPLATE_SRC = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
@page {
  size: A4;
  margin: 20mm 18mm 20mm 18mm;
  @bottom-right {
    content: "Page " counter(page) " of " counter(pages);
    font-size: 8pt;
    color: #9CA3AF;
    font-family: 'Helvetica Neue', Arial, sans-serif;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Helvetica Neue', Arial, sans-serif;
  font-size: 10pt;
  color: #1A1A1A;
  background: #fff;
  line-height: 1.5;
}

/* ── Header ── */
.page-header {
  border-bottom: 2px solid #0F6E56;
  padding-bottom: 14px;
  margin-bottom: 22px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}
.logo { font-size: 17pt; font-weight: 700; color: #1A1A1A; letter-spacing: -0.5px; }
.logo-accent { color: #D97706; }
.meta { text-align: right; font-size: 8pt; color: #6B7280; line-height: 1.8; }
.report-title { font-size: 21pt; font-weight: 700; color: #1A1A1A; margin-bottom: 3px; letter-spacing: -0.5px; }
.report-sub { font-size: 10pt; color: #6B7280; margin-bottom: 18px; }

/* ── Sections ── */
.section { margin-top: 26px; }
.section-title {
  font-size: 7.5pt;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: #9CA3AF;
  border-bottom: 0.5px solid #E4E4E0;
  padding-bottom: 5px;
  margin-bottom: 13px;
}

/* ── KPI row — 3-column table ── */
.kpi-table { width: 100%; border-collapse: separate; border-spacing: 10px 0; }
.kpi-cell {
  border: 1px solid #E4E4E0;
  border-radius: 8px;
  padding: 12px 14px;
  width: 33%;
  vertical-align: top;
}
.kpi-label { font-size: 7.5pt; color: #9CA3AF; margin-bottom: 5px; }
.kpi-value { font-size: 21pt; font-weight: 700; line-height: 1; font-family: 'Courier New', monospace; }
.kpi-value.teal  { color: #0F6E56; }
.kpi-value.amber { color: #D97706; }
.kpi-value.red   { color: #DC2626; }
.kpi-value.grey  { color: #D1D5DB; }
.kpi-sub { font-size: 7.5pt; color: #9CA3AF; margin-top: 3px; }

/* ── AI explanation ── */
.explanation {
  margin-top: 14px;
  background: #F9FAFB;
  border: 1px solid #E4E4E0;
  border-left: 3px solid #0F6E56;
  border-radius: 6px;
  padding: 12px 14px;
}
.explanation-label { font-size: 7.5pt; font-weight: 600; color: #0F6E56; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 5px; }
.explanation-text  { font-size: 10pt; color: #374151; line-height: 1.65; }

/* ── Component bars ── */
.bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 7px; }
.bar-label { font-size: 8pt; color: #6B7280; width: 72px; flex-shrink: 0; text-transform: capitalize; }
.bar-track { flex: 1; height: 5px; background: #F3F4F6; border-radius: 3px; }
.bar-fill  { height: 5px; border-radius: 3px; }
.bar-pct   { font-size: 7.5pt; font-family: 'Courier New', monospace; color: #9CA3AF; width: 60px; text-align: right; flex-shrink: 0; }

/* ── Schedule table ── */
table.schedule { width: 100%; border-collapse: collapse; }
table.schedule th {
  font-size: 7.5pt; font-weight: 600; color: #9CA3AF;
  text-align: left; padding: 5px 8px;
  border-bottom: 1px solid #E4E4E0; background: #F9FAFB;
}
table.schedule td {
  font-size: 8.5pt; color: #374151;
  padding: 7px 8px; border-bottom: 0.5px solid #F3F4F6; vertical-align: middle;
}
.mono { font-family: 'Courier New', monospace; }
.badge {
  display: inline-block; font-size: 7pt; font-weight: 600;
  padding: 2px 7px; border-radius: 20px;
}

/* ── Image grid — 2 per row ── */
.image-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.image-cell { width: calc(50% - 6px); }
.image-cell img { width: 100%; border-radius: 7px; border: 1px solid #E4E4E0; display: block; }
.image-caption { font-size: 7.5pt; color: #9CA3AF; margin-top: 4px; font-family: 'Courier New', monospace; }
.pill { display: inline-block; font-size: 6.5pt; font-weight: 600; padding: 2px 6px; border-radius: 20px; background: #ECFDF5; color: #0F6E56; text-transform: capitalize; margin: 2px 2px 0 0; }

/* ── Alerts ── */
.alert-row { display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; border-bottom: 0.5px solid #F3F4F6; }
.dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
.dot.critical { background: #DC2626; }
.dot.warning  { background: #D97706; }
.alert-msg  { font-size: 9pt; color: #374151; flex: 1; }
.alert-time { font-size: 7.5pt; color: #9CA3AF; font-family: 'Courier New', monospace; flex-shrink: 0; }

/* ── Device stats ── */
.stat-row { display: flex; gap: 10px; }
.stat-box { flex: 1; background: #F9FAFB; border-radius: 7px; padding: 11px 13px; }
.stat-box-label { font-size: 7.5pt; color: #9CA3AF; margin-bottom: 4px; }
.stat-box-value { font-size: 14pt; font-weight: 700; font-family: 'Courier New', monospace; color: #1A1A1A; }

/* ── Footer ── */
.report-footer {
  margin-top: 28px; padding-top: 10px;
  border-top: 0.5px solid #E4E4E0;
  display: flex; justify-content: space-between;
  font-size: 7.5pt; color: #D1D5DB;
}

/* ── SVG chart ── */
.trend-svg { width: 100%; height: 100px; }

.page-break { page-break-before: always; }
</style>
</head>
<body>

<!-- ── HEADER ── -->
<div class="page-header">
  <div>
    <div class="logo">Build<span class="logo-accent">Watch</span></div>
    <div style="font-size:7.5pt; color:#9CA3AF; margin-top:2px;">AI-powered construction monitoring</div>
  </div>
  <div class="meta">
    <div>Generated {{ generated_at }}</div>
    <div>Period: {{ date_from }} – {{ date_to }}</div>
  </div>
</div>

<div class="report-title">{{ project.name }}</div>
<div class="report-sub">
  {%- if project.location %}{{ project.location }} · {% endif -%}
  Progress Report · {{ date_from }} – {{ date_to }}
</div>

<!-- ── SECTION 1: PROGRESS SUMMARY ── -->
<div class="section">
  <div class="section-title">Progress summary</div>

  <table class="kpi-table">
    <tr>
      <td class="kpi-cell">
        <div class="kpi-label">Build progress (MWPI)</div>
        {% if current_mwpi is not none %}
          <div class="kpi-value {% if current_mwpi >= 70 %}teal{% elif current_mwpi >= 40 %}amber{% else %}red{% endif %}">{{ current_mwpi }}%</div>
        {% else %}
          <div class="kpi-value grey">—</div>
        {% endif %}
        <div class="kpi-sub">Overall build completion</div>
      </td>
      <td class="kpi-cell">
        <div class="kpi-label">Images captured</div>
        <div class="kpi-value">{{ total_images }}</div>
        <div class="kpi-sub">This reporting period</div>
      </td>
      <td class="kpi-cell">
        <div class="kpi-label">AI confidence</div>
        <div class="kpi-value teal">{{ ai_confidence }}%</div>
        <div class="kpi-sub">Avg. detection confidence</div>
      </td>
    </tr>
  </table>

  <!-- Component bars -->
  {% if current_mwpi is not none %}
  <div style="margin-top:16px;">
    <div style="font-size:7.5pt; color:#9CA3AF; margin-bottom:9px;">Structural class breakdown</div>
    {% set bar_colors = {"foundation": "#0F6E56", "column": "#2563EB", "wall": "#D97706"} %}
    {% for bar in component_bars %}
    <div class="bar-row">
      <div class="bar-label">{{ bar.cls }}</div>
      <div class="bar-track">
        <div class="bar-fill" style="width:{{ bar.fill }}%; background:{{ bar_colors.get(bar.cls, '#9CA3AF') }};"></div>
      </div>
      <div class="bar-pct">{{ bar.actual }} / {{ bar.max }}%</div>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <!-- AI explanation -->
  {% if explanation %}
  <div class="explanation">
    <div class="explanation-label">✦ AI site reading</div>
    <div class="explanation-text">{{ explanation }}</div>
  </div>
  {% endif %}
</div>

<!-- ── SECTION 2: PROGRESS TREND ── -->
{% if has_trend %}
<div class="section">
  <div class="section-title">Progress trend</div>
  <svg viewBox="0 0 480 92" class="trend-svg" xmlns="http://www.w3.org/2000/svg">
    <!-- Grid lines -->
    {% for pct in [25, 50, 75, 100] %}
      {% set gy = 80 - (pct / 100 * 80) %}
      <line x1="28" y1="{{ gy }}" x2="480" y2="{{ gy }}" stroke="#F3F4F6" stroke-width="0.5"/>
      <text x="0" y="{{ gy + 3 }}" font-size="7" fill="#D1D5DB" font-family="monospace">{{ pct }}%</text>
    {% endfor %}
    <!-- Trend line -->
    <polyline
      points="{{ svg_polyline }}"
      fill="none" stroke="#0F6E56" stroke-width="1.8" stroke-linejoin="round"
      transform="translate(28,0)"/>
    <!-- Data circles -->
    {% for c in svg_circles %}
    <circle cx="{{ c.x + 28 }}" cy="{{ c.y }}" r="2.5" fill="#0F6E56"/>
    {% endfor %}
    <!-- X labels -->
    <text x="28" y="92" font-size="7" fill="#9CA3AF" font-family="monospace">{{ trend_raw[0].date }}</text>
    <text x="480" y="92" font-size="7" fill="#9CA3AF" text-anchor="end" font-family="monospace">{{ trend_raw[-1].date }}</text>
  </svg>
</div>
{% endif %}

<!-- ── SECTION 3: SCHEDULE ── -->
{% if has_schedule %}
<div class="section">
  <div class="section-title">Plan vs actual schedule</div>
  <table class="schedule">
    <thead>
      <tr>
        <th>Wk</th>
        <th>Milestone</th>
        <th>Planned date</th>
        <th style="text-align:center;">Planned</th>
        <th style="text-align:center;">Actual</th>
        <th style="text-align:center;">Variance</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {% for row in schedule_table %}
      <tr>
        <td class="mono" style="color:#9CA3AF;">{{ row.week }}</td>
        <td>{{ row.label }}</td>
        <td class="mono" style="color:#9CA3AF; font-size:8pt;">{{ row.planned_date }}</td>
        <td class="mono" style="text-align:center;">{{ row.planned_mwpi }}%</td>
        <td class="mono" style="text-align:center;">
          {% if row.actual_mwpi is not none %}{{ row.actual_mwpi }}%{% else %}—{% endif %}
        </td>
        <td class="mono" style="text-align:center; color:{% if row.deviation is none %}#D1D5DB{% elif row.deviation >= 0 %}#0F6E56{% else %}#DC2626{% endif %};">
          {% if row.deviation is not none %}{% if row.deviation > 0 %}+{% endif %}{{ row.deviation }}pp{% else %}—{% endif %}
        </td>
        <td>
          <span class="badge" style="background:{{ row.status_color }}1A; color:{{ row.status_color }};">
            {{ row.status }}
          </span>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

<!-- ── SECTION 4: SITE IMAGES ── -->
{% if has_images %}
<div class="section page-break">
  <div class="section-title">Site images — {{ images|length }} selected from this period</div>
  <div class="image-grid">
    {% for img in images %}
    <div class="image-cell">
      <img src="{{ img.src }}" alt="Site capture">
      <div class="image-caption">{{ img.timestamp }} · {{ img.mwpi }}% MWPI</div>
      <div>
        {% for cls in img.detected_classes %}<span class="pill">{{ cls }}</span>{% endfor %}
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}

<!-- ── SECTION 5: ALERTS ── -->
{% if has_alerts %}
<div class="section">
  <div class="section-title">Alerts — {{ alert_rows|length }} flagged this period</div>
  {% for a in alert_rows %}
  <div class="alert-row">
    <div class="dot {{ a.severity }}"></div>
    <div class="alert-msg">{{ a.message }}</div>
    <div class="alert-time">{{ a.time }}</div>
  </div>
  {% endfor %}
</div>
{% endif %}

<!-- ── SECTION 6: DEVICE & SYSTEM ── -->
<div class="section">
  <div class="section-title">Device and system</div>
  <div class="stat-row">
    <div class="stat-box">
      <div class="stat-box-label">Images captured</div>
      <div class="stat-box-value">{{ total_images }}</div>
    </div>
    <div class="stat-box">
      <div class="stat-box-label">Avg. AI confidence</div>
      <div class="stat-box-value">{{ ai_confidence }}%</div>
    </div>
    <div class="stat-box">
      <div class="stat-box-label">Project status</div>
      <div class="stat-box-value" style="font-size:10pt; font-weight:600; color:#0F6E56; font-family:'Helvetica Neue',Arial,sans-serif;">{{ project.status | capitalize }}</div>
    </div>
  </div>
</div>

<!-- ── FOOTER ── -->
<div class="report-footer">
  <div>BuildWatch · AI-powered construction monitoring</div>
  <div>{{ project.name }} · {{ date_from }} – {{ date_to }}</div>
</div>

</body>
</html>
"""

_TEMPLATE = _jenv.from_string(_TEMPLATE_SRC)
