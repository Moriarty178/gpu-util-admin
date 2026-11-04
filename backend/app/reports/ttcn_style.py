"""Phong cách slide báo cáo điều hành TT.CN — Viettel Telecom (bản Python của skill `viettel-report-slides`,
`assets/deck_helpers.js` + `references/design-spec.md`). Khổ 16:9 = 10 × 5.625 in.

Motif: nền trắng cho slide nội dung, navy 1F2433 cho bìa & kết; kicker đỏ IN HOA + tiêu đề Cambria; thẻ bo góc có icon
trong hình tròn; dải chốt hồng ở đáy. Không emoji, không gạch chân tiêu đề, không sọc trang trí ở mép.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lxml import etree
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

NAVY, RED, TEXT, MUTE, LINE = "1F2433", "EE0033", "232733", "5A6478", "E1E5EC"
CARD, PINK, PINKB, PINKT = "F4F6F9", "FDECEF", "F3C6D2", "8A0B27"
GREEN, GREENB, AMBER, AMBERB = "1E7A4C", "EAF5EF", "C98A00", "FFF2CC"
PLH, WHITE, DARKCARD, DARKCARDB, GRID = "9AA2B1", "FFFFFF", "2A3145", "3A4257", "EEF1F6"
HEAD, BODY = "Cambria", "Calibri"
SLIDE_W, SLIDE_H = 10.0, 5.625
# màu vùng trên slide: theo bảng trạng thái của design-spec (đạt / chú ý / thiếu) — đỏ chỉ cho Nguy hiểm
ZONE_COLOR = {"safe": GREEN, "warning": AMBER, "danger": RED}
ZONE_LABEL = {"danger": "Nguy hiểm", "warning": "Cảnh báo", "safe": "An toàn"}

Slide = Any  # pptx.slide.Slide (python-pptx không xuất kiểu công khai ổn định)


def vi_num(v: float, digits: int = 1) -> str:
    return f"{v:.{digits}f}".replace(".", ",")


def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


def text(
    s: Slide, t: str, x: float, y: float, w: float, h: float, *, size: float = 10.5, bold: bool = False,
    italic: bool = False, color: str = TEXT, font: str = BODY, align: str = "left", valign: str = "top",
    spacing: float = 0,
) -> Any:  # fmt: skip
    """Hộp chữ không lề trong; `t` có thể nhiều dòng (\\n → đoạn mới). spacing = giãn chữ (pt, như charSpacing)."""
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[valign]
    for i, line in enumerate(t.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
        r = p.add_run()
        r.text = line
        f = r.font
        f.name, f.size, f.bold, f.italic = font, Pt(size), bold, italic
        f.color.rgb = rgb(color)
        if spacing:
            r._r.get_or_add_rPr().set("spc", str(int(spacing * 100)))
    return box


def _shadow(shape: Any) -> None:
    sp_pr = shape._element.spPr
    eff = etree.SubElement(sp_pr, qn("a:effectLst"))
    sh = etree.SubElement(eff, qn("a:outerShdw"), blurRad="76200", dist="25400", dir="5400000", algn="t",
                          rotWithShape="0")  # fmt: skip
    clr = etree.SubElement(sh, qn("a:srgbClr"), val=PLH)
    etree.SubElement(clr, qn("a:alpha"), val="22000")


def shape(
    s: Slide, kind: Any, x: float, y: float, w: float, h: float, *, fill: str | None = None, line: str | None = None,
    line_w: float = 1, radius: float | None = None, shadow: bool = False,
) -> Any:  # fmt: skip
    shp = s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
    else:
        shp.fill.background()
    if line:
        shp.line.color.rgb = rgb(line)
        shp.line.width = Pt(line_w)
    else:
        shp.line.fill.background()
    if radius is not None:
        shp.adjustments[0] = min(0.5, radius / max(min(w, h), 1e-6))
    if shadow:
        _shadow(shp)
    else:
        shp.shadow.inherit = False
    return shp


def kicker(s: Slide, t: str) -> None:
    text(s, t.upper(), 0.5, 0.28, 8.5, 0.22, size=10.5, bold=True, color=RED, spacing=2)


def title(s: Slide, t: str) -> None:
    text(s, t, 0.5, 0.52, 9.0, 0.62, size=22, bold=True, color=NAVY, font=HEAD)


def card(s: Slide, x: float, y: float, w: float, h: float, fill: str = WHITE) -> None:
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill=fill, line=LINE, radius=0.07, shadow=True)


def card_title(s: Slide, x: float, y: float, w: float, t: str, color: str = RED) -> None:
    text(s, t.upper(), x, y, w, 0.26, size=12, bold=True, color=color, spacing=1)


def strip(s: Slide, t: str) -> None:
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.5, 4.82, 9.0, 0.5, fill=PINK, line=PINKB, radius=0.06)
    text(s, t, 0.72, 4.82, 8.56, 0.5, size=10.5, bold=True, color=PINKT, valign="middle")


def placeholder(s: Slide, t: str, x: float, y: float, w: float, h: float = 0.3) -> None:
    text(s, t, x, y, w, h, size=9.5, italic=True, color=PLH)


def icon(s: Slide, cx: float, cy: float, kind: str, fill: str = RED) -> None:
    """Icon trắng trong hình tròn màu (đường kính 0.48 in), tâm (cx, cy) — vẽ bằng hình đơn giản, không ảnh ngoài."""
    d, wc = 0.48, WHITE
    shape(s, MSO_SHAPE.OVAL, cx - d / 2, cy - d / 2, d, d, fill=fill)
    if kind == "bars":
        for dx, hh in ((0, 0.12), (0.10, 0.18), (0.20, 0.10)):
            shape(s, MSO_SHAPE.RECTANGLE, cx - 0.15 + dx, cy + 0.11 - hh, 0.06, hh, fill=wc)
    elif kind == "users":
        shape(s, MSO_SHAPE.OVAL, cx - 0.14, cy - 0.14, 0.11, 0.11, fill=wc)
        shape(s, MSO_SHAPE.OVAL, cx + 0.03, cy - 0.12, 0.10, 0.10, fill=wc)
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, cx - 0.16, cy, 0.15, 0.12, fill=wc, radius=0.05)
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, cx + 0.02, cy + 0.02, 0.14, 0.11, fill=wc, radius=0.05)
    elif kind == "target":
        shape(s, MSO_SHAPE.OVAL, cx - 0.15, cy - 0.15, 0.30, 0.30, line=wc, line_w=2)
        shape(s, MSO_SHAPE.OVAL, cx - 0.05, cy - 0.05, 0.10, 0.10, fill=wc)
    elif kind == "check":
        for x1, y1, x2, y2 in (
            (cx - 0.13, cy + 0.02, cx - 0.04, cy + 0.11),
            (cx - 0.04, cy + 0.11, cx + 0.13, cy - 0.07),
        ):
            ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
            ln.line.color.rgb = rgb(wc)
            ln.line.width = Pt(2.5)
    elif kind == "flag":
        shape(s, MSO_SHAPE.RECTANGLE, cx - 0.12, cy - 0.15, 0.035, 0.30, fill=wc)
        tri = shape(s, MSO_SHAPE.ISOSCELES_TRIANGLE, cx - 0.085, cy - 0.15, 0.22, 0.14, fill=wc)
        tri.rotation = 90
    elif kind == "alert":
        shape(s, MSO_SHAPE.ISOSCELES_TRIANGLE, cx - 0.15, cy - 0.14, 0.30, 0.28, fill=wc)
        shape(s, MSO_SHAPE.RECTANGLE, cx - 0.02, cy - 0.05, 0.04, 0.11, fill=fill)
        shape(s, MSO_SHAPE.RECTANGLE, cx - 0.02, cy + 0.08, 0.04, 0.035, fill=fill)
    elif kind == "doc":
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, cx - 0.11, cy - 0.15, 0.22, 0.30, fill=wc, radius=0.02)
        for dy in (0.0, 0.07, 0.14):
            shape(s, MSO_SHAPE.RECTANGLE, cx - 0.06, cy - 0.08 + dy, 0.12, 0.02, fill=fill)


def stat(s: Slide, x: float, y: float, w: float, h: float, value: str, label: str, note: str = "",
         kind: str = "bars", fill: str = NAVY) -> None:  # fmt: skip
    """Thẻ số lớn: icon + số (Cambria 28) + nhãn + ghi chú phụ."""
    card(s, x, y, w, h)
    icon(s, x + 0.42, y + 0.42, kind, fill)
    text(s, value, x + 0.78, y + 0.16, w - 0.9, 0.5, size=24, bold=True, color=NAVY, font=HEAD, valign="middle")
    text(s, label, x + 0.22, y + 0.78, w - 0.4, 0.26, size=10.5, bold=True, color=TEXT)
    if note:
        text(s, note, x + 0.22, y + 1.04, w - 0.4, h - 1.12, size=9.5, color=MUTE)


# ------------------------------------------------------------------ bìa & kết (nền tối)


def _dark(s: Slide) -> None:
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = rgb(NAVY)


def cover(s: Slide, *, kicker_t: str, title_t: str, subtitle: str, message: str, footer: str,
          chips: Sequence[str] = ()) -> None:  # fmt: skip
    _dark(s)
    text(s, kicker_t.upper(), 0.5, 1.1, 9, 0.3, size=12, bold=True, color=RED, align="center", spacing=3)
    text(s, title_t, 0.5, 1.48, 9, 0.75, size=30, bold=True, color=WHITE, font=HEAD, align="center", valign="middle")
    text(s, subtitle, 0.5, 2.28, 9, 0.35, size=13, color="C8CDD9", align="center")
    text(s, f"“{message}”", 1.0, 2.78, 8, 0.95, size=13, italic=True, color="EAECF2", font=HEAD, align="center")
    if chips:
        gap, cy = 0.12, 3.98
        ws = [max(0.6, 0.3 + len(c) * 0.085) for c in chips]
        cx = (SLIDE_W - sum(ws) - gap * (len(chips) - 1)) / 2
        for i, (c, w) in enumerate(zip(chips, ws, strict=True)):
            last = i == len(chips) - 1
            shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, cx, cy, w, 0.36, fill=RED if last else "2C3346",
                  line=RED if last else DARKCARDB, radius=0.18)  # fmt: skip
            text(s, c, cx, cy, w, 0.36, size=10.5, bold=True, color=WHITE, align="center", valign="middle")
            cx += w + gap
    text(s, footer, 0.5, 4.9, 9, 0.3, size=10.5, color="8A91A3", align="center")


def closing(s: Slide, *, kicker_t: str, message: str, recs: Sequence[tuple[str, str]], footer: str) -> None:
    _dark(s)
    text(s, kicker_t.upper(), 0.5, 0.5, 9, 0.3, size=12, bold=True, color=RED, align="center", spacing=3)
    text(s, message, 0.9, 0.9, 8.2, 0.95, size=15, bold=True, color=WHITE, font=HEAD, align="center",
         valign="middle")  # fmt: skip
    n = max(len(recs), 1)
    gap = 0.29
    cw = (9.0 - gap * (n - 1)) / n
    x = 0.5
    for i, (t, d) in enumerate(recs, start=1):
        shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 2.0, cw, 2.45, fill=DARKCARD, line=DARKCARDB, radius=0.06)
        shape(s, MSO_SHAPE.OVAL, x + 0.28, 2.24, 0.56, 0.56, fill=RED)
        text(s, str(i), x + 0.28, 2.24, 0.56, 0.56, size=22, bold=True, color=WHITE, font=HEAD, align="center",
             valign="middle")  # fmt: skip
        text(s, t, x + 0.28, 2.95, cw - 0.56, 0.5, size=12.5, bold=True, color=WHITE, font=HEAD)
        text(s, d, x + 0.28, 3.5, cw - 0.56, 0.88, size=10.5, color="C4CAD8")
        x += cw + gap
    text(s, footer, 0.5, 4.95, 9, 0.3, size=10, italic=True, color="8A91A3", align="center")


# ------------------------------------------------------------------ biểu đồ native (addChart)


def _style_axes(chart: Any, val_title: str | None, cat_title: str | None, vmax: float | None) -> None:
    va, ca = chart.value_axis, chart.category_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = rgb(GRID)
    va.major_gridlines.format.line.width = Pt(0.75)
    va.format.line.fill.background()
    va.minimum_scale = 0
    if vmax is not None:
        va.maximum_scale = vmax
    for ax, t in ((va, val_title), (ca, cat_title)):
        ax.tick_labels.font.size = Pt(8)
        ax.tick_labels.font.color.rgb = rgb(MUTE)
        if t:
            ax.has_title = True
            ax.axis_title.text_frame.text = t
            f = ax.axis_title.text_frame.paragraphs[0].runs[0].font
            f.size, f.bold = Pt(8.5), False
            f.color.rgb = rgb(MUTE)
    ca.format.line.color.rgb = rgb(LINE)


def _chart_title(chart: Any, t: str | None) -> None:
    chart.has_title = bool(t)
    if t:
        chart.chart_title.text_frame.text = t
        f = chart.chart_title.text_frame.paragraphs[0].runs[0].font
        f.size, f.bold = Pt(11), True
        f.color.rgb = rgb(TEXT)


def _legend(chart: Any) -> None:
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(8.5)
    chart.legend.font.color.rgb = rgb(TEXT)


def _add(s: Slide, kind: Any, data: CategoryChartData, x: float, y: float, w: float, h: float) -> Any:
    chart = s.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), data).chart
    chart.font.name = BODY
    chart.font.size = Pt(9)
    return chart


def line_chart(
    s: Slide, x: float, y: float, w: float, h: float, cats: Sequence[str], series: Sequence[tuple[str, Sequence[float]]],
    *, title_t: str, val_title: str, cat_title: str | None = None, colors: Sequence[str] = (RED, NAVY),
    vmax: float | None = 100, fmt: str = "0",
) -> Any:  # fmt: skip
    data = CategoryChartData(number_format=fmt)
    data.categories = list(cats)
    for name, vals in series:
        data.add_series(name, list(vals))
    chart = _add(s, XL_CHART_TYPE.LINE_MARKERS, data, x, y, w, h)
    _chart_title(chart, title_t)
    _legend(chart)
    _style_axes(chart, val_title, cat_title, vmax)
    plot = chart.plots[0]
    for ser, (_n, vals) in zip(plot.series, series, strict=True):
        for i, v in enumerate(vals):  # nhãn kiểu VN (38,9) — định dạng số của Office đổi theo locale máy xem
            lab = ser.points[i].data_label
            lab.has_text_frame = True
            lab.text_frame.text = vi_num(v)
            lab.position = XL_LABEL_POSITION.ABOVE
            f = lab.text_frame.paragraphs[0].runs[0].font
            f.size = Pt(8)
            f.color.rgb = rgb(NAVY)
    for ser, c in zip(plot.series, colors, strict=False):
        ser.smooth = False
        ser.format.line.color.rgb = rgb(c)
        ser.format.line.width = Pt(2.5)
        ser.marker.style = XL_MARKER_STYLE.CIRCLE
        ser.marker.size = 6
        ser.marker.format.fill.solid()
        ser.marker.format.fill.fore_color.rgb = rgb(c)
        ser.marker.format.line.color.rgb = rgb(c)
    return chart


def bar_chart(
    s: Slide, x: float, y: float, w: float, h: float, cats: Sequence[str], series: Sequence[tuple[str, Sequence[float]]],
    *, title_t: str, val_title: str, cat_title: str | None = None, colors: Sequence[str] = (NAVY,),
    gap: int = 60, legend: bool = True, fmt: str = "0",
) -> Any:  # fmt: skip
    data = CategoryChartData(number_format=fmt)
    data.categories = list(cats)
    for name, vals in series:
        data.add_series(name, list(vals))
    chart = _add(s, XL_CHART_TYPE.COLUMN_CLUSTERED, data, x, y, w, h)
    _chart_title(chart, title_t)
    if legend:
        _legend(chart)
    else:
        chart.has_legend = False
    _style_axes(chart, val_title, cat_title, None)
    plot = chart.plots[0]
    plot.gap_width = gap
    plot.overlap = -10
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format, dl.number_format_is_linked = fmt, False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size = Pt(8.5)
    dl.font.color.rgb = rgb(NAVY)
    for ser, c in zip(plot.series, colors, strict=False):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = rgb(c)
        ser.invert_if_negative = False
    return chart


def donut_chart(
    s: Slide, x: float, y: float, w: float, h: float, cats: Sequence[str], vals: Sequence[float],
    colors: Sequence[str], *, title_t: str, hole: int = 58,
) -> Any:  # fmt: skip
    data = CategoryChartData(number_format="0")
    data.categories = list(cats)
    data.add_series(title_t, list(vals))
    chart = _add(s, XL_CHART_TYPE.DOUGHNUT, data, x, y, w, h)
    _chart_title(chart, title_t)
    _legend(chart)
    plot = chart.plots[0]
    hs = plot._element.find(qn("c:holeSize"))
    if hs is None:
        hs = etree.SubElement(plot._element, qn("c:holeSize"))
    hs.set("val", str(hole))
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format, dl.number_format_is_linked = "0", False
    dl.font.size = Pt(11)
    dl.font.bold = True
    dl.font.color.rgb = rgb(WHITE)
    dl.show_value, dl.show_category_name, dl.show_percentage = True, False, False
    for i, c in enumerate(colors):
        pt = plot.series[0].points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = rgb(c)
        pt.format.line.color.rgb = rgb(WHITE)
    return chart


# ------------------------------------------------------------------ bảng


def table(
    s: Slide, x: float, y: float, widths: Sequence[float], header: Sequence[str], rows: Sequence[Sequence[str]], *,
    row_h: float = 0.25, size: float = 9, align: Sequence[str] | None = None, row_colors: Sequence[str | None] = (),
) -> Any:  # fmt: skip
    """Bảng gọn: hàng tiêu đề navy chữ trắng, hàng xen kẽ trắng / F4F6F9; `row_colors[i]` = màu chữ cột đầu dòng i."""
    n_rows, n_cols = len(rows) + 1, len(header)
    gf = s.shapes.add_table(n_rows, n_cols, Inches(x), Inches(y), Inches(sum(widths)), Inches(row_h * n_rows))
    tbl = gf.table
    tbl.first_row, tbl.horz_banding = True, False
    for j, w in enumerate(widths):
        tbl.columns[j].width = Inches(w)
    al = list(align or ["left"] * n_cols)
    for i in range(n_rows):
        tbl.rows[i].height = Emu(int(Inches(row_h)))
        for j in range(n_cols):
            cell = tbl.cell(i, j)
            val = header[j] if i == 0 else rows[i - 1][j]
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(NAVY if i == 0 else (WHITE if i % 2 else CARD))
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[al[j]]
            r = p.add_run()
            r.text = val
            f = r.font
            f.name, f.size, f.bold = BODY, Pt(size), i == 0
            color = WHITE if i == 0 else TEXT
            if i > 0 and j == 0 and i - 1 < len(row_colors) and row_colors[i - 1]:
                color = row_colors[i - 1] or TEXT
            f.color.rgb = rgb(color)
    return gf
