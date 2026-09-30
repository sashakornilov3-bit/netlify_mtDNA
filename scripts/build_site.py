#!/usr/bin/env python3
"""
build_site.py

Генерация sanitized статического dark-theme дашборда с SVG-графиками
для Netlify Drop.

Входы:
  config/deploy_manifest.json
  out/normalized.json
  out/reconciliation_report.json (опционально)
  data/curated/from_AMP.csv

Выходы:
  site/index.html
  site/netlify.toml

Security/privacy:
  - Публичный деплой блокируется, если манифест содержит real/personal/special category data.
  - SampleID маскируется через sample_label.
  - Гаплогруппа скрывается, если show_haplogroup=false.
  - HTML генерируется без JavaScript и внешних CDN.
  - Графики выполняются как inline SVG.
"""

import csv
import html
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve()


def detect_root() -> Path:
    """
    Автоматически определяет корень проекта.

    Поддерживает:
      Project/
      ├── scripts/
      │   └── build_site.py
      ├── config/
      ├── data/
      └── out/

    и плоскую структуру:
      Project/
      ├── build_site.py
      ├── config/
      ├── data/
      └── out/
    """

    if HERE.parent.name == "scripts":
        candidate = HERE.parents[1]
        if (candidate / "config").exists() or (candidate / "data").exists():
            return candidate

    if (HERE.parent / "config").exists() or (HERE.parent / "data").exists():
        return HERE.parent

    cwd = Path.cwd()
    if (cwd / "config").exists() or (cwd / "data").exists():
        return cwd

    return HERE.parent


ROOT = detect_root()

CONFIG = ROOT / "config" / "deploy_manifest.json"
NORMALIZED = ROOT / "out" / "normalized.json"
RECONCILIATION = ROOT / "out" / "reconciliation_report.json"
AMP_CSV = ROOT / "data" / "curated" / "from_AMP.csv"

SITE = ROOT / "site"
INDEX_HTML = SITE / "index.html"
NETLIFY_TOML = SITE / "netlify.toml"


TYPE_COLORS = {
    "Комплекс I": "#fb7185",
    "Комплекс III/IV": "#f59e0b",
    "рРНК": "#22d3ee",
    "тРНК": "#60a5fa",
    "D-loop": "#a78bfa",
    "Прочее": "#64748b",
}

TYPE_ORDER = [
    "Комплекс I",
    "Комплекс III/IV",
    "рРНК",
    "тРНК",
    "D-loop",
    "Прочее",
]


def esc(value):
    return html.escape(str(value if value is not None else ""))


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_deploy_target(manifest):
    return (
        os.environ.get("DEPLOY_TARGET")
        or manifest.get("default_target")
        or "netlify-drop-demo"
    )


def privacy_gate(manifest):
    """
    Блокирует публичную сборку, если данные не разрешены к публикации.
    """

    errors = []
    target = get_deploy_target(manifest)

    classification = manifest.get("classification")

    if not classification:
        errors.append("BLOCKED: classification is missing in deploy_manifest.json.")

    if classification == "real":
        errors.append("BLOCKED: real data cannot be deployed to public Netlify Drop.")

    if manifest.get("contains_personal_data") is True:
        errors.append("BLOCKED: personal data cannot be deployed to public Netlify Drop.")

    if manifest.get("contains_special_category_data") is True:
        errors.append("BLOCKED: special category data cannot be deployed to public Netlify Drop.")

    if manifest.get("contains_biometric_context") is True:
        errors.append("BLOCKED: biometric context cannot be deployed to public Netlify Drop.")

    if manifest.get("public_deploy_allowed") is False:
        errors.append("BLOCKED: public_deploy_allowed=false in deploy_manifest.json.")

    allowed_targets = manifest.get("allowed_targets") or []
    if target not in allowed_targets:
        errors.append(
            f"BLOCKED: deploy target '{target}' is not listed in allowed_targets."
        )

    if classification in {"sanitized", "aggregated", "derived"}:
        required_approvers = [
            "data_approver",
            "security_approver",
            "legal_approver",
            "approval_date",
        ]
        for field in required_approvers:
            if not manifest.get(field):
                errors.append(f"BLOCKED: missing approval field: {field}")

    return errors


def read_amp_rows():
    if not AMP_CSV.exists():
        raise FileNotFoundError(f"Missing curated file: {AMP_CSV}")

    rows = []

    with AMP_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for raw_row in reader:
            row = {}
            for key, value in raw_row.items():
                clean_key = (key or "").strip()
                if isinstance(value, str):
                    clean_value = value.strip()
                else:
                    clean_value = str(value).strip() if value is not None else ""
                row[clean_key] = clean_value
            rows.append(row)

    return rows


def get_field(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def get_type_category(typ: str) -> str:
    t = (typ or "").lower()

    if "комплекс i" in t:
        return "Комплекс I"

    if "комплекс iii" in t or "комплекс iv" in t or "атф" in t:
        return "Комплекс III/IV"

    if "рнк" in t or "rrna" in t:
        return "рРНК"

    if "трнк" in t or "trna" in t:
        return "тРНК"

    if "контрольная" in t or "d-loop" in t or "d-петля" in t:
        return "D-loop"

    return "Прочее"


def priority_by_type(typ: str):
    """
    Условный визуальный приоритет на основе типа гена.
    Не является клинической классификацией.
    """

    category = get_type_category(typ)

    if category == "Комплекс I":
        return "Высокий", "high"

    if category in {"Комплекс III/IV", "рРНК"}:
        return "Средний", "medium"

    if category == "тРНК":
        return "Низкий", "low"

    if category == "D-loop":
        return "Минимальный", "minimal"

    return "Не определён", "unknown"


def gene_short(gene: str) -> str:
    g = (gene or "").strip()
    if not g:
        return "—"
    return g.split()[0]


def class_color(klass: str) -> str:
    k = (klass or "").upper()

    if "VUS" in k:
        return "#f59e0b"

    if "PATHOGEN" in k or "ПАТОГЕН" in k:
        return "#fb7185"

    if "BENIGN" in k or "ДОБРО" in k:
        return "#10b981"

    if "LIKELY" in k or "ВЕРОЯТНО" in k:
        return "#22d3ee"

    return "#64748b"


def write_netlify_toml():
    NETLIFY_TOML.write_text(
        """[[headers]]
  for = "/*"
  [headers.values]
    X-Content-Type-Options = "nosniff"
    X-Frame-Options = "DENY"
    Referrer-Policy = "no-referrer"
    Permissions-Policy = "camera=(), microphone=(), geolocation=()"
    Content-Security-Policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
""",
        encoding="utf-8",
    )


def svg_hbar_chart(items, title, subtitle=""):
    """
    Горизонтальная столбчатая диаграмма как inline SVG.
    items: list[{"label": str, "value": int, "color": str}]
    """

    width = 680
    row_height = 38
    top = 70 if subtitle else 54
    height = top + max(1, len(items)) * row_height + 24
    bar_x = 210
    bar_width = width - bar_x - 70

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(title)}">'
    ]

    parts.append(f'<text class="chart-title" x="0" y="24">{esc(title)}</text>')

    if subtitle:
        parts.append(f'<text class="chart-subtitle" x="0" y="46">{esc(subtitle)}</text>')

    if not items:
        parts.append(
            f'<text class="chart-empty" x="0" y="{top + 20}">Нет данных для отображения</text>'
        )
        parts.append("</svg>")
        return "\n".join(parts)

    max_value = max(int(item.get("value", 0)) for item in items) or 1

    for idx, item in enumerate(items):
        y = top + idx * row_height
        label = item.get("label", "")
        value = int(item.get("value", 0))
        color = item.get("color", "#64748b")

        bar_len = 0
        if value > 0:
            bar_len = max(8, int((value / max_value) * bar_width))

        parts.append(
            f'<text class="bar-label" x="0" y="{y + 18}">{esc(label)}</text>'
        )

        parts.append(
            f'<rect x="{bar_x}" y="{y + 4}" width="{bar_width}" height="18" '
            f'rx="9" fill="#1f2937"></rect>'
        )

        if bar_len:
            parts.append(
                f'<rect x="{bar_x}" y="{y + 4}" width="{bar_len}" height="18" '
                f'rx="9" fill="{esc(color)}" fill-opacity="0.92"></rect>'
            )

        parts.append(
            f'<text class="value-label" x="{width - 8}" y="{y + 18}" '
            f'text-anchor="end">{esc(value)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def svg_donut_chart(segments, center_value, center_label, title="", size=280):
    """
    Круговая диаграмма как inline SVG.
    segments: list[{"label": str, "value": int, "color": str}]
    """

    cx = size / 2
    cy = size / 2
    r = 78
    stroke = 32
    circumference = 2 * math.pi * r
    total = sum(int(seg.get("value", 0)) for seg in segments)

    parts = [
        f'<svg class="chart donut" viewBox="0 0 {size} {size}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(title or "Donut chart")}">'
    ]

    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
        f'stroke="#111827" stroke-width="{stroke}"></circle>'
    )

    if total > 0:
        offset = 0.0

        for seg in segments:
            value = int(seg.get("value", 0))
            if value <= 0:
                continue

            fraction = value / total
            dash = fraction * circumference
            gap = circumference - dash
            color = seg.get("color", "#64748b")

            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
                f'stroke="{esc(color)}" stroke-width="{stroke}" '
                f'stroke-linecap="butt" '
                f'stroke-dasharray="{dash:.2f} {gap:.2f}" '
                f'stroke-dashoffset="{-offset:.2f}" '
                f'transform="rotate(-90 {cx} {cy})"></circle>'
            )

            offset += dash

    parts.append(
        f'<text class="donut-center-value" x="{cx}" y="{cy - 2}">'
        f'{esc(center_value)}</text>'
    )

    parts.append(
        f'<text class="donut-center-label" x="{cx}" y="{cy + 22}">'
        f'{esc(center_label)}</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


def svg_position_map(annotation_positions, amp_positions, align_positions):
    """
    Карта позиций мтДНК как inline SVG.
    """

    width = 980
    height = 260
    left = 155
    right = 30
    top = 70
    bottom = 50
    plot_width = width - left - right
    max_pos = 16569

    def x_pos(pos):
        try:
            p = int(pos)
        except Exception:
            p = 0
        p = max(0, min(max_pos, p))
        return left + (p / max_pos) * plot_width

    parts = [
        f'<svg class="chart position-map" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Карта позиций мтДНК">'
    ]

    parts.append(
        '<text class="chart-title" x="0" y="24">Карта позиций мтДНК</text>'
    )

    parts.append(
        '<text class="chart-subtitle" x="0" y="46">'
        'Аннотированные позиции, AMP-кандидаты и ALIGN-артефакты'
        '</text>'
    )

    lanes = [
        ("Все аннотированные", 105, "#64748b"),
        ("AMP кандидаты", 155, "#22d3ee"),
        ("ALIGN исключены", 205, "#fb7185"),
    ]

    for label, y, color in lanes:
        parts.append(
            f'<circle cx="18" cy="{y}" r="5" fill="{esc(color)}"></circle>'
        )
        parts.append(
            f'<text class="lane-label" x="32" y="{y + 4}">{esc(label)}</text>'
        )

    ticks = [0, 5000, 10000, 16569]

    for tick in ticks:
        x = x_pos(tick)
        parts.append(
            f'<line class="grid-line" x1="{x:.2f}" y1="{top - 10}" '
            f'x2="{x:.2f}" y2="{height - bottom + 10}"></line>'
        )
        parts.append(
            f'<text class="tick-text" x="{x:.2f}" y="{height - bottom + 30}" '
            f'text-anchor="middle">{esc(tick)}</text>'
        )

    parts.append(
        f'<line class="axis-line" x1="{left}" y1="{height - bottom + 10}" '
        f'x2="{width - right}" y2="{height - bottom + 10}"></line>'
    )

    for pos in annotation_positions:
        x = x_pos(pos)
        parts.append(
            f'<circle cx="{x:.2f}" cy="105" r="5" fill="#64748b" '
            f'fill-opacity="0.85"></circle>'
        )

    for pos in amp_positions:
        x = x_pos(pos)
        parts.append(
            f'<circle cx="{x:.2f}" cy="155" r="7" fill="#22d3ee" '
            f'stroke="#0b1020" stroke-width="2"></circle>'
        )

    for pos in align_positions:
        x = x_pos(pos)
        parts.append(
            f'<line x1="{x - 6:.2f}" y1="{199}" x2="{x + 6:.2f}" y2="{211}" '
            f'stroke="#fb7185" stroke-width="3" stroke-linecap="round"></line>'
        )
        parts.append(
            f'<line x1="{x - 6:.2f}" y1="{211}" x2="{x + 6:.2f}" y2="{199}" '
            f'stroke="#fb7185" stroke-width="3" stroke-linecap="round"></line>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def html_legend(items):
    if not items:
        return ""

    parts = ['<ul class="legend">']

    for item in items:
        color = item.get("color", "#64748b")
        label = item.get("label", "")
        value = item.get("value", 0)

        parts.append(
            f'<li>'
            f'<span class="legend-dot" style="background:{esc(color)}"></span>'
            f'<span class="legend-label">{esc(label)}</span>'
            f'<strong class="legend-value">{esc(value)}</strong>'
            f'</li>'
        )

    parts.append("</ul>")
    return "\n".join(parts)


def build_html(manifest, normalized, reconciliation, amp_rows):
    target = get_deploy_target(manifest)

    expected_count = manifest.get("expected_variant_count")
    if expected_count is not None and len(amp_rows) != int(expected_count):
        raise SystemExit(
            f"BLOCKED: expected_variant_count={expected_count}, actual={len(amp_rows)}"
        )

    sample_label = manifest.get("sample_label", "DEMO-001")
    show_hg = bool(manifest.get("show_haplogroup", False))

    haplogroups = normalized.get("haplogroups", [])
    haplogroup_text = ", ".join(haplogroups) if show_hg else "скрыто"

    annotation_positions = normalized.get("annotation_positions", [])
    align_positions = normalized.get("align_positions", [])
    expected_amp_positions = normalized.get("expected_amp_positions", [])
    private_positions = normalized.get("private_positions", [])
    missing_positions = normalized.get("missing_positions", [])
    qc_messages = normalized.get("qc_messages", [])

    reconciliation = reconciliation or {}
    recon_status = reconciliation.get("status", "NOT_RUN")
    issues = reconciliation.get("issues", [])
    warnings = reconciliation.get("warnings", [])

    category_counter = Counter()
    class_counter = Counter()
    gene_counter = Counter()

    high_count = 0

    for row in amp_rows:
        typ = get_field(row, "Тип гена", "Type", "тип")
        category = get_type_category(typ)
        category_counter[category] += 1

        klass = get_field(row, "Класс (предварит.)", "Class", "класс") or "Не указан"
        class_counter[klass.upper()] += 1

        gene = gene_short(get_field(row, "Ген", "Gene", "ген"))
        gene_counter[gene] += 1

        if priority_by_type(typ)[0] == "Высокий":
            high_count += 1

    vus_count = class_counter.get("VUS", 0)

    category_items = [
        {
            "label": category,
            "value": category_counter.get(category, 0),
            "color": TYPE_COLORS.get(category, "#64748b"),
        }
        for category in TYPE_ORDER
        if category_counter.get(category, 0) > 0
    ]

    class_segments = [
        {
            "label": klass,
            "value": count,
            "color": class_color(klass),
        }
        for klass, count in class_counter.most_common()
    ]

    gene_items = [
        {
            "label": gene,
            "value": count,
            "color": "#22d3ee",
        }
        for gene, count in gene_counter.most_common(8)
    ]

    css = """
:root {
  --bg: #070b18;
  --bg-2: #0b1020;
  --surface: #0f172a;
  --surface-2: #111827;
  --surface-3: #162033;
  --border: #1f2937;
  --border-strong: #334155;
  --text: #e5e7eb;
  --text-strong: #f8fafc;
  --muted: #94a3b8;
  --primary: #6366f1;
  --primary-2: #8b5cf6;
  --cyan: #22d3ee;
  --emerald: #10b981;
  --amber: #f59e0b;
  --rose: #fb7185;
  --blue: #60a5fa;
  --slate: #64748b;
  --shadow: 0 18px 50px rgba(0, 0, 0, 0.35);
  --radius: 20px;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", Roboto, Arial, sans-serif;
  background:
    radial-gradient(circle at top left, rgba(99, 102, 241, 0.18), transparent 28%),
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.12), transparent 24%),
    linear-gradient(180deg, var(--bg), var(--bg-2));
  color: var(--text);
  line-height: 1.45;
  min-height: 100vh;
}

a {
  color: var(--cyan);
}

.hero {
  padding: 38px 24px 46px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.hero-inner,
.container {
  max-width: 1440px;
  margin: 0 auto;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.14);
  border: 1px solid rgba(129, 140, 248, 0.25);
  color: #c7d2fe;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 750;
  margin-bottom: 14px;
}

.hero h1 {
  margin: 0 0 12px;
  font-size: clamp(30px, 4.2vw, 48px);
  line-height: 1.05;
  letter-spacing: -0.035em;
  color: var(--text-strong);
}

.hero p {
  margin: 0;
  max-width: 1040px;
  color: rgba(226, 232, 240, 0.78);
  font-size: 15px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 20px;
}

.chip {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid var(--border);
  font-size: 12px;
  color: #cbd5e1;
}

.banner {
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.16), rgba(251, 113, 133, 0.12));
  border-bottom: 1px solid rgba(245, 158, 11, 0.28);
  color: #fde68a;
  padding: 14px 24px;
  font-weight: 700;
}

.banner-inner {
  max-width: 1440px;
  margin: 0 auto;
}

.container {
  padding: 24px;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px;
  margin-bottom: 22px;
}

.metric {
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.96), rgba(17, 24, 39, 0.92));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
  box-shadow: var(--shadow);
  position: relative;
  overflow: hidden;
}

.metric::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 5px;
  background: var(--primary);
}

.metric-indigo::before { background: var(--primary); }
.metric-red::before { background: var(--rose); }
.metric-amber::before { background: var(--amber); }
.metric-green::before { background: var(--emerald); }
.metric-blue::before { background: var(--blue); }
.metric-cyan::before { background: var(--cyan); }
.metric-slate::before { background: var(--slate); }

.metric-value {
  font-size: 34px;
  font-weight: 850;
  letter-spacing: -0.04em;
  color: var(--text-strong);
}

.metric-label {
  margin-top: 4px;
  font-weight: 750;
  color: #dbeafe;
}

.metric-note {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}

.grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 18px;
  margin-bottom: 22px;
}

.panel {
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.97), rgba(11, 16, 32, 0.94));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 20px;
  margin-bottom: 22px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.panel h2 {
  margin: 0;
  font-size: 20px;
  letter-spacing: -0.02em;
  color: var(--text-strong);
}

.panel h3 {
  margin: 18px 0 10px;
  font-size: 15px;
  color: #e2e8f0;
}

.panel-tag {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.10);
  border: 1px solid var(--border);
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.chart-wrap {
  width: 100%;
  overflow: hidden;
}

.chart {
  width: 100%;
  height: auto;
  display: block;
}

.chart-title {
  fill: var(--text-strong);
  font-size: 15px;
  font-weight: 850;
}

.chart-subtitle,
.chart-empty {
  fill: var(--muted);
  font-size: 12px;
}

.bar-label,
.value-label,
.lane-label {
  fill: #e2e8f0;
  font-size: 12px;
  font-weight: 700;
}

.tick-text {
  fill: #64748b;
  font-size: 11px;
}

.grid-line,
.axis-line {
  stroke: #1f2937;
  stroke-width: 1;
}

.donut-center-value {
  fill: var(--text-strong);
  font-size: 34px;
  font-weight: 850;
  text-anchor: middle;
}

.donut-center-label {
  fill: var(--muted);
  font-size: 12px;
  text-anchor: middle;
}

.legend {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.legend li {
  display: grid;
  grid-template-columns: 14px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.08);
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  display: inline-block;
}

.legend-label {
  color: #e2e8f0;
  font-size: 13px;
  font-weight: 650;
}

.legend-value {
  color: var(--text-strong);
  font-size: 13px;
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.profile-item {
  background: rgba(148, 163, 184, 0.06);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
}

.profile-label {
  display: block;
  font-size: 12px;
  color: var(--muted);
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.profile-value {
  display: block;
  margin-top: 6px;
  font-size: 16px;
  font-weight: 800;
  color: var(--text-strong);
  word-break: break-word;
}

.qc-list,
.issue-list,
.warning-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}

.qc-item,
.issue-item,
.warning-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(148, 163, 184, 0.06);
}

.qc-severity {
  flex: 0 0 auto;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 850;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.qc-error .qc-severity {
  background: rgba(251, 113, 133, 0.16);
  color: #fda4af;
}

.qc-warning .qc-severity {
  background: rgba(245, 158, 11, 0.16);
  color: #fcd34d;
}

.qc-info .qc-severity {
  background: rgba(96, 165, 250, 0.16);
  color: #93c5fd;
}

.issue-item {
  background: rgba(251, 113, 133, 0.10);
  border-color: rgba(251, 113, 133, 0.22);
  color: #fecdd3;
}

.warning-item {
  background: rgba(245, 158, 11, 0.10);
  border-color: rgba(245, 158, 11, 0.22);
  color: #fde68a;
}

.status-banner {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 999px;
  font-weight: 850;
  font-size: 13px;
  margin-bottom: 14px;
}

.status-pass {
  background: rgba(16, 185, 129, 0.14);
  color: #6ee7b7;
  border: 1px solid rgba(16, 185, 129, 0.25);
}

.status-fail {
  background: rgba(251, 113, 133, 0.14);
  color: #fda4af;
  border: 1px solid rgba(251, 113, 133, 0.25);
}

.status-neutral {
  background: rgba(148, 163, 184, 0.12);
  color: #cbd5e1;
  border: 1px solid rgba(148, 163, 184, 0.20);
}

.variants-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 14px;
}

.variant-card {
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(17, 24, 39, 0.92));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  box-shadow: var(--shadow);
  transition: transform 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
}

.variant-card:hover {
  transform: translateY(-2px);
  border-color: rgba(99, 102, 241, 0.35);
  box-shadow: 0 20px 55px rgba(0, 0, 0, 0.42);
}

.variant-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.variant-pos {
  font-size: 13px;
  color: var(--muted);
  font-weight: 750;
}

.variant-gene {
  font-size: 20px;
  font-weight: 850;
  letter-spacing: -0.02em;
  margin-top: 2px;
  color: var(--text-strong);
}

.variant-badges {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.pill {
  display: inline-block;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 850;
  white-space: nowrap;
  border: 1px solid transparent;
}

.pill-high {
  background: rgba(251, 113, 133, 0.14);
  color: #fda4af;
  border-color: rgba(251, 113, 133, 0.24);
}

.pill-medium {
  background: rgba(245, 158, 11, 0.14);
  color: #fcd34d;
  border-color: rgba(245, 158, 11, 0.24);
}

.pill-low {
  background: rgba(96, 165, 250, 0.14);
  color: #93c5fd;
  border-color: rgba(96, 165, 250, 0.24);
}

.pill-minimal {
  background: rgba(148, 163, 184, 0.14);
  color: #cbd5e1;
  border-color: rgba(148, 163, 184, 0.24);
}

.pill-unknown {
  background: rgba(100, 116, 139, 0.16);
  color: #94a3b8;
  border-color: rgba(100, 116, 139, 0.28);
}

.pill-class {
  background: rgba(139, 92, 246, 0.16);
  color: #c4b5fd;
  border-color: rgba(139, 92, 246, 0.28);
}

.variant-change {
  margin-top: 12px;
  display: inline-flex;
  padding: 7px 10px;
  border-radius: 10px;
  background: rgba(99, 102, 241, 0.14);
  color: #c7d2fe;
  font-weight: 850;
  font-size: 14px;
  border: 1px solid rgba(99, 102, 241, 0.20);
}

.variant-meta {
  margin: 14px 0 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.variant-meta > div {
  background: rgba(148, 163, 184, 0.06);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
  min-width: 0;
}

.variant-meta dt {
  font-size: 11px;
  color: var(--muted);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.variant-meta dd {
  margin: 5px 0 0;
  font-size: 13px;
  font-weight: 700;
  color: #e2e8f0;
  word-break: break-word;
}

.variant-role {
  margin: 14px 0 0;
  padding: 12px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.06);
  border: 1px solid var(--border);
  color: #cbd5e1;
  font-size: 13px;
}

.timeline {
  margin: 0;
  padding-left: 22px;
  color: #cbd5e1;
}

.timeline li {
  margin: 8px 0;
}

.muted {
  color: var(--muted);
  font-size: 13px;
}

.footer {
  padding: 18px 24px 34px;
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}

code {
  background: rgba(99, 102, 241, 0.14);
  color: #c7d2fe;
  padding: 2px 6px;
  border-radius: 6px;
  font-size: 0.92em;
}

@media (max-width: 760px) {
  .hero {
    padding: 24px 16px 30px;
  }

  .container {
    padding: 16px;
  }

  .panel {
    padding: 16px;
  }

  .grid-2 {
    grid-template-columns: 1fr;
  }

  .variant-meta {
    grid-template-columns: 1fr;
  }

  .variant-head {
    flex-direction: column;
  }

  .variant-badges {
    align-items: flex-start;
    flex-direction: row;
    flex-wrap: wrap;
  }
}
"""

    parts = []

    parts.append("<!doctype html>")
    parts.append('<html lang="ru">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append('<meta name="color-scheme" content="dark">')
    parts.append("<title>мтДНК × Психиатрия — Dark Demo Dashboard</title>")
    parts.append("<style>")
    parts.append(css)
    parts.append("</style>")
    parts.append("</head>")
    parts.append("<body>")

    # Hero
    parts.append('<header class="hero">')
    parts.append('<div class="hero-inner">')
    parts.append('<div class="eyebrow">mtDNA · Psychiatry · Research demo</div>')
    parts.append("<h1>Дашборд предварительного анализа мтДНК</h1>")
    parts.append(
        "<p>Тёмный статический sanitized-дашборд с SVG-графиками, собранный локально из "
        "<code>snps.annotations.txt</code>, <code>samples.qc.txt</code> и "
        "<code>from_AMP.csv</code>. Предназначен для демонстрации pipeline, "
        "а не для клинического использования.</p>"
    )

    parts.append('<div class="chips">')
    parts.append(
        f'<span class="chip">dataset: {esc(manifest.get("dataset_id", "unknown"))}</span>'
    )
    parts.append(
        f'<span class="chip">version: {esc(manifest.get("version", "unknown"))}</span>'
    )
    parts.append(
        f'<span class="chip">classification: {esc(manifest.get("classification", "unknown"))}</span>'
    )
    parts.append(f'<span class="chip">target: {esc(target)}</span>')
    parts.append(f'<span class="chip">sample: {esc(sample_label)}</span>')
    parts.append("</div>")

    parts.append("</div>")
    parts.append("</header>")

    # Banner
    parts.append('<div class="banner">')
    parts.append('<div class="banner-inner">')
    parts.append(
        "⚠️ Демо-режим. Используются только synthetic/sanitized/aggregated данные. "
        "Результат не является медицинским заключением, диагнозом или рекомендацией по лечению."
    )
    parts.append("</div>")
    parts.append("</div>")

    parts.append('<main class="container">')

    # Metrics
    parts.append('<section class="metrics">')

    metrics = [
        ("Всего вариантов", len(amp_rows), "из from_AMP.csv", "indigo"),
        ("Высокий приоритет", high_count, "условно: Комплекс I", "red"),
        ("Класс VUS", vus_count, "предварительная классификация", "amber"),
        ("ALIGN исключено", len(align_positions), "артефакты выравнивания", "slate"),
        ("Warnings", len(warnings), "неблокирующие замечания", "blue"),
        ("Issues", len(issues), "критические расхождения", "green" if not issues else "red"),
    ]

    for label, value, note, tone in metrics:
        parts.append(f'<article class="metric metric-{esc(tone)}">')
        parts.append(f'<div class="metric-value">{esc(value)}</div>')
        parts.append(f'<div class="metric-label">{esc(label)}</div>')
        parts.append(f'<div class="metric-note">{esc(note)}</div>')
        parts.append("</article>")

    parts.append("</section>")

    # Charts row
    parts.append('<section class="grid-2">')

    parts.append('<div class="panel">')
    parts.append(
        '<div class="panel-header"><h2>Распределение по типу гена</h2>'
        '<span class="panel-tag">bar chart</span></div>'
    )
    parts.append('<div class="chart-wrap">')
    parts.append(
        svg_hbar_chart(
            category_items,
            "Функциональные категории вариантов",
            "Условная группировка по типу гена из from_AMP.csv",
        )
    )
    parts.append("</div>")
    parts.append(html_legend(category_items))
    parts.append("</div>")

    parts.append('<div class="panel">')
    parts.append(
        '<div class="panel-header"><h2>Классы ACMG/AMP</h2>'
        '<span class="panel-tag">donut chart</span></div>'
    )
    parts.append('<div class="chart-wrap">')
    parts.append(
        svg_donut_chart(
            class_segments,
            center_value=len(amp_rows),
            center_label="вариантов",
            title="Классы ACMG/AMP",
        )
    )
    parts.append("</div>")
    parts.append(html_legend(class_segments))
    parts.append("</div>")

    parts.append("</section>")

    # Position map
    parts.append('<section class="panel">')
    parts.append(
        '<div class="panel-header"><h2>Геномная карта</h2>'
        '<span class="panel-tag">position map</span></div>'
    )
    parts.append('<div class="chart-wrap">')
    parts.append(
        svg_position_map(
            annotation_positions=annotation_positions,
            amp_positions=amp_positions_from_normalized(expected_amp_positions),
            align_positions=align_positions,
        )
    )
    parts.append("</div>")
    parts.append(
        '<p class="muted">'
        "Серые точки — все аннотированные позиции. Голубые — AMP-кандидаты. "
        "Красные крестики — ALIGN-артефакты, исключённые из дальнейшего анализа."
        "</p>"
    )
    parts.append("</section>")

    # Top genes
    parts.append('<section class="panel">')
    parts.append(
        '<div class="panel-header"><h2>Топ генов</h2>'
        '<span class="panel-tag">top 8</span></div>'
    )
    parts.append('<div class="chart-wrap">')
    parts.append(
        svg_hbar_chart(
            gene_items,
            "Наиболее частые гены в выборке",
            "Подсчёт по полю «Ген» из from_AMP.csv",
        )
    )
    parts.append("</div>")
    parts.append(html_legend(gene_items))
    parts.append("</section>")

    # Profile panel
    parts.append('<section class="panel">')
    parts.append(
        '<div class="panel-header"><h2>Профиль образца и QC</h2>'
        '<span class="panel-tag">sanitized view</span></div>'
    )

    parts.append('<div class="profile-grid">')

    profile_items = [
        ("Sample label", sample_label),
        ("Haplogroup", haplogroup_text),
        ("Annotation positions", len(annotation_positions)),
        ("ALIGN excluded", ", ".join(map(str, align_positions)) or "—"),
        ("Expected AMP positions", len(expected_amp_positions)),
        ("Global private detected", len(private_positions)),
        ("Missing detected", len(missing_positions)),
        ("Reconciliation status", recon_status),
    ]

    for label, value in profile_items:
        parts.append('<div class="profile-item">')
        parts.append(f'<span class="profile-label">{esc(label)}</span>')
        parts.append(f'<span class="profile-value">{esc(value)}</span>')
        parts.append("</div>")

    parts.append("</div>")
    parts.append("</section>")

    # QC messages
    parts.append('<section class="panel">')
    parts.append(
        '<div class="panel-header"><h2>QC-сообщения</h2>'
        f'<span class="panel-tag">{len(qc_messages)} items</span></div>'
    )

    if qc_messages:
        parts.append('<ul class="qc-list">')
        for item in qc_messages:
            typ = (item.get("type") or "info").lower()
            msg = item.get("message") or ""
            css_class = (
                "qc-error"
                if typ == "error"
                else "qc-warning"
                if typ == "warning"
                else "qc-info"
            )
            parts.append(f'<li class="qc-item {esc(css_class)}">')
            parts.append(f'<span class="qc-severity">{esc(typ)}</span>')
            parts.append(f"<span>{esc(msg)}</span>")
            parts.append("</li>")
        parts.append("</ul>")
    else:
        parts.append('<p class="muted">QC-сообщения не найдены.</p>')

    parts.append("</section>")

    # Data quality
    parts.append('<section class="panel">')
    parts.append(
        '<div class="panel-header"><h2>Качество данных</h2>'
        '<span class="panel-tag">reconciliation</span></div>'
    )

    status_class = (
        "status-pass"
        if recon_status == "PASS"
        else "status-fail"
        if recon_status == "FAIL"
        else "status-neutral"
    )

    parts.append(
        f'<div class="status-banner {esc(status_class)}">Status: {esc(recon_status)}</div>'
    )

    if issues:
        parts.append("<h3>Критические расхождения</h3>")
        parts.append('<ul class="issue-list">')
        for issue in issues:
            parts.append(f'<li class="issue-item">{esc(issue)}</li>')
        parts.append("</ul>")
    else:
        parts.append('<p class="muted">Критические расхождения не выявлены.</p>')

    if warnings:
        parts.append("<h3>Предупреждения</h3>")
        parts.append('<ul class="warning-list">')
        for warning in warnings:
            parts.append(f'<li class="warning-item">{esc(warning)}</li>')
        parts.append("</ul>")

    parts.append("</section>")

    # Variants
    parts.append('<section class="panel">')
    parts.append(
        '<div class="panel-header"><h2>Варианты</h2>'
        f'<span class="panel-tag">{len(amp_rows)} cards</span></div>'
    )

    parts.append('<div class="variants-grid">')

    for row in amp_rows:
        num = get_field(row, "#")
        pos = get_field(row, "Позиция (р. мтДНК)", "Position", "позиция")
        gene = get_field(row, "Ген", "Gene", "ген")
        change = get_field(row, "Замена", "Change", "замена")
        typ = get_field(row, "Тип гена", "Type", "тип")
        freq = get_field(row, "Популяц. частота (оценка)", "Frequency", "частота")
        pred = get_field(row, "Функц. предиктор (рекомендация)", "Predictor", "предиктор")
        acmg = get_field(row, "Критерии ACMG/AMP (предварит.)", "ACMG", "acmg")
        klass = get_field(row, "Класс (предварит.)", "Class", "класс")
        role = get_field(row, "Роль в психиатрии", "Role", "роль")

        priority_label, priority_css = priority_by_type(typ)

        parts.append('<article class="variant-card">')

        parts.append('<div class="variant-head">')
        parts.append("<div>")
        parts.append(f'<div class="variant-pos">#{esc(num)} · {esc(pos)}</div>')
        parts.append(f'<div class="variant-gene">{esc(gene)}</div>')
        parts.append("</div>")

        parts.append('<div class="variant-badges">')
        parts.append(
            f'<span class="pill pill-{esc(priority_css)}">{esc(priority_label)}</span>'
        )
        parts.append(f'<span class="pill pill-class">{esc(klass or "—")}</span>')
        parts.append("</div>")

        parts.append("</div>")

        parts.append(f'<div class="variant-change">{esc(change or "—")}</div>')

        parts.append('<dl class="variant-meta">')

        meta_items = [
            ("Тип", typ),
            ("Частота", freq),
            ("Предиктор", pred),
            ("ACMG/AMP", acmg),
        ]

        for label, value in meta_items:
            parts.append("<div>")
            parts.append(f"<dt>{esc(label)}</dt>")
            parts.append(f"<dd>{esc(value or '—')}</dd>")
            parts.append("</div>")

        parts.append("</dl>")

        parts.append(f'<p class="variant-role">{esc(role or "Роль не указана.")}</p>')

        parts.append("</article>")

    parts.append("</div>")

    parts.append(
        '<p class="muted">'
        "* Приоритет — условный порядок визуализации на основе типа гена, "
        "не клиническая классификация."
        "</p>"
    )

    parts.append("</section>")

    # Methodology
    parts.append('<section class="panel">')
    parts.append(
        '<div class="panel-header"><h2>Методология</h2>'
        '<span class="panel-tag">pipeline</span></div>'
    )

    parts.append('<ol class="timeline">')
    parts.append("<li>Чтение <code>snps.annotations.txt</code>: позиции, REF, ALT.</li>")
    parts.append(
        "<li>Чтение <code>samples.qc.txt</code>: QC, гаплогруппа, missing/private mutations, ALIGN-артефакты.</li>"
    )
    parts.append(
        "<li>Формирование ожидаемого AMP-набора: annotation positions минус ALIGN positions.</li>"
    )
    parts.append("<li>Сверка с кураторской таблицей <code>from_AMP.csv</code>.</li>")
    parts.append(
        "<li>Генерация sanitized статического HTML без JavaScript и внешних CDN.</li>"
    )
    parts.append(
        "<li>Графики выполняются как inline SVG для снижения surface area.</li>"
    )
    parts.append(
        "<li>Pre-deploy security/privacy проверка через <code>predeploy_check.py</code>.</li>"
    )
    parts.append("</ol>")

    parts.append("</section>")

    parts.append("</main>")

    # Footer
    parts.append('<footer class="footer">')
    parts.append("Сборка: ")
    parts.append(esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))
    parts.append(" · dataset: ")
    parts.append(esc(manifest.get("dataset_id", "unknown")))
    parts.append(" · version: ")
    parts.append(esc(manifest.get("version", "unknown")))
    parts.append("</footer>")

    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


def amp_positions_from_normalized(expected_amp_positions):
    """
    Для карты позиций используем expected AMP positions как основной набор.
    Если нужно, позже можно объединять с amp_csv_positions.
    """
    return expected_amp_positions or []


def main():
    manifest = load_json(CONFIG)

    errors = privacy_gate(manifest)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        raise SystemExit(1)

    if not NORMALIZED.exists():
        raise SystemExit("Run scripts/parse_sources.py first.")

    normalized = load_json(NORMALIZED)
    reconciliation = load_optional_json(RECONCILIATION)
    amp_rows = read_amp_rows()

    SITE.mkdir(parents=True, exist_ok=True)

    write_netlify_toml()

    html_text = build_html(manifest, normalized, reconciliation, amp_rows)
    INDEX_HTML.write_text(html_text, encoding="utf-8")

    print(f"Created: {INDEX_HTML}")
    print(f"Created: {NETLIFY_TOML}")
    print(f"Rows: {len(amp_rows)}")


if __name__ == "__main__":
    main()
