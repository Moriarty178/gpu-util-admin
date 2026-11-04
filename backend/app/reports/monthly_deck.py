"""Deck báo cáo tháng (7 slide, người dùng chốt 04/11/2026 — BGĐ TT.CN, giao ban tháng):
1 bìa · 2 tổng quan tháng · 3 xu hướng · 4 so với tháng trước · 5 theo đầu mối · 6 server Nguy hiểm · 7 kết luận & kiến nghị.

Chỉ trình bày số trong `data` (report_service.monthly). Số thiếu → placeholder `[Cần bổ sung số liệu]`, không bịa.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import date
from typing import Any

from pptx import Presentation
from pptx.util import Inches

from app.reports import ttcn_style as st
from app.services.analytics_service import UNMAPPED

ZONES = ("danger", "warning", "safe")
UNMAPPED_LABEL = "Chưa có trong thống kê"
MAX_OWNERS = 7  # cột trên biểu đồ đầu mối; nhiều hơn → gộp "Khác"
MAX_DANGER_ROWS = 12


def pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}".replace(".", ",") + "%"


def pts(v: float) -> str:
    return f"{v:+.1f}".replace(".", ",").replace("-", "−")


def short(month: str) -> str:
    return f"T{int(month[5:7])}/{month[:4]}"


def ddmm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def clip(t: str | None, n: int) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def build(data: dict[str, Any], message: str, recs: Sequence[tuple[str, str]], today: date) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(st.SLIDE_W), Inches(st.SLIDE_H)
    blank = prs.slide_layouts[6]

    def new() -> Any:
        return prs.slides.add_slide(blank)

    label, t = data["label"], data["threshold"]
    scope = f" · Phạm vi: {data['scope_owner']}" if data.get("scope_owner") else ""
    period = f"{ddmm(data['start'])}–{ddmm(data['end'])}"
    footer = f"TTCN-VTT · Lập từ GPU Util Admin ngày {today:%d/%m/%Y}{scope}"

    # 1. Bìa
    st.cover(
        new(), kicker_t="Báo cáo giao ban tháng", title_t=f"Tình hình sử dụng GPU {label}",
        subtitle=f"Số liệu tải GPU VTNet {period} · Ngưỡng T = {t:g}%", message=message, footer=footer,
        chips=[short(m["month"]) for m in data["trend"]] or [short(data["month"])],
    )  # fmt: skip

    _overview(new(), data)
    _trend(new(), data)
    _compare(new(), data)
    _owners(new(), data)
    _danger(new(), data)

    # 7. Kết luận & kiến nghị
    st.closing(new(), kicker_t="Kết luận & kiến nghị", message=message, recs=list(recs)[:3],
               footer=f"Vùng theo ngưỡng T = {t:g}% trên TB tháng của từng server · {footer}")  # fmt: skip
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _overview(s: Any, d: dict[str, Any]) -> None:
    k, prev = d["kpi"], d["previous"]
    z, n = k["zones"], k["n_servers"]
    st.kicker(s, "Tổng quan tháng")
    st.title(s, f"Tải GPU {d['label']}: TB {pct(k['gpu_avg'])} GPU, {pct(k['mem_avg'])} VRAM")
    st.card(s, 0.5, 1.28, 4.6, 3.35)
    st.donut_chart(s, 0.62, 1.38, 4.36, 3.15, [st.ZONE_LABEL[x] for x in ZONES], [z[x] for x in ZONES],
                   [st.ZONE_COLOR[x] for x in ZONES], title_t=f"Số server theo vùng (T = {d['threshold']:g}%)")  # fmt: skip
    vs = f"so với {short(prev['month'])}" if prev else ""
    g_note = f"{pts(k['gpu_avg'] - prev['gpu_avg'])} điểm {vs}" if prev and prev["gpu_avg"] is not None else ""
    m_note = f"{pts(k['mem_avg'] - prev['mem_avg'])} điểm {vs}" if prev and prev["mem_avg"] is not None else ""
    x0, w, h, gap = 5.4, 1.98, 1.6, 0.14
    st.stat(s, x0, 1.28, w, h, pct(k["gpu_avg"]), "TB GPU (SM bận)", g_note, "bars", st.RED)
    st.stat(s, x0 + w + gap, 1.28, w, h, pct(k["mem_avg"]), "TB VRAM", m_note, "bars")
    st.stat(s, x0, 1.28 + h + gap, w, h, str(n), "Server có số liệu",
            f"{k['n_mapped']} có trong thống kê, {k['n_unmapped']} chưa có", "users")  # fmt: skip
    st.stat(s, x0 + w + gap, 1.28 + h + gap, w, h, str(k["cards"]), "Card GPU",
            f"Nguy hiểm {k['cards_total']['danger']} · Cảnh báo {k['cards_total']['warning']}", "target")  # fmt: skip
    share = f" ({z['danger'] / n * 100:.1f}%)".replace(".", ",") if n else ""
    st.strip(s, f"{z['danger']}/{n} server{share} ở vùng Nguy hiểm, giữ {k['cards_total']['danger']}/{k['cards']} "
                "card GPU; GPU là % thời gian SM bận — luôn đọc kèm VRAM.")  # fmt: skip


def _trend(s: Any, d: dict[str, Any]) -> None:
    tr = d["trend"]
    st.kicker(s, "Xu hướng")
    if len(tr) < 2:  # 1 kỳ → không vẽ đường 1 điểm (design-spec)
        st.title(s, f"Xu hướng: mới có dữ liệu {d['label']}")
        st.card(s, 0.5, 1.28, 9.0, 3.35)
        st.placeholder(s, "[Cần bổ sung số liệu] — cần ít nhất 2 tháng đã nhập để vẽ xu hướng.", 0.8, 2.7, 8.4)
        st.strip(s, "Xu hướng sẽ hiện khi có từ 2 tháng dữ liệu VTNet trở lên.")
        return
    a, b = tr[0], tr[-1]
    st.title(s, f"Xu hướng {short(a['month'])} → {short(b['month'])}")
    cats = [short(m["month"]) for m in tr]
    st.card(s, 0.5, 1.28, 4.4, 3.35)
    st.line_chart(s, 0.6, 1.36, 4.2, 3.2, cats,
                  [("TB GPU", [m["gpu_avg"] or 0 for m in tr]), ("TB VRAM", [m["mem_avg"] or 0 for m in tr])],
                  title_t="TB toàn bộ server theo tháng (%)", val_title="%")  # fmt: skip
    st.card(s, 5.1, 1.28, 4.4, 3.35)
    st.bar_chart(s, 5.2, 1.36, 4.2, 3.2, cats,
                 [(st.ZONE_LABEL[z], [m["zones"][z] for m in tr]) for z in ZONES],
                 title_t="Số server mỗi vùng", val_title="Server",
                 colors=[st.ZONE_COLOR[z] for z in ZONES], gap=80)  # fmt: skip
    st.strip(s, f"Nguy hiểm {a['zones']['danger']} → {b['zones']['danger']} server "
                f"({short(a['month'])} → {short(b['month'])}); TB GPU {pct(a['gpu_avg'])} → {pct(b['gpu_avg'])}.")  # fmt: skip


MOVE_META = [  # (khóa, nhãn, icon, màu)
    ("worsened", "Xấu đi", "alert", st.AMBER),
    ("improved", "Cải thiện", "check", st.GREEN),
    ("new", "Mới xuất hiện", "flag", st.NAVY),
    ("gone", "Không còn số liệu", "doc", st.NAVY),
]


def _compare(s: Any, d: dict[str, Any]) -> None:
    prev, mv, k = d["previous"], d["movement"], d["kpi"]
    st.kicker(s, "So với tháng trước")
    if not prev or not mv:
        st.title(s, "So với tháng trước: chưa có kỳ để so sánh")
        st.card(s, 0.5, 1.28, 9.0, 3.35)
        st.placeholder(s, "[Cần bổ sung số liệu] — chưa nhập tháng nào trước tháng báo cáo.", 0.8, 2.7, 8.4)
        st.strip(s, "Nhập file VTNet tháng trước để có so sánh chuyển vùng.")
        return
    c = mv["counts"]
    p = short(prev["month"])
    st.title(s, f"So với {p}: {c['worsened']} server xấu đi, {c['improved']} cải thiện")
    w, h, gap = 1.9, 1.6, 0.14
    for i, (key, lab, ic, col) in enumerate(MOVE_META):
        x = 0.5 + (i % 2) * (w + gap)
        y = 1.28 + (i // 2) * (h + gap)
        st.stat(s, x, y, w, h, str(c[key]), lab, "" if i else f"cùng T = {d['threshold']:g}%", ic, col)
    st.card(s, 4.65, 1.28, 4.85, 3.35)
    st.card_title(s, 4.85, 1.42, 4.5, "Chuyển vùng (server)", st.NAVY)
    rows_from = [*ZONES, "new"]
    cols_to = [*ZONES, "gone"]
    names = {**st.ZONE_LABEL, "new": "Mới", "gone": "Không còn"}
    header = [f"T{int(prev['month'][5:7])} → T{int(d['month'][5:7])}", *[names[x] for x in cols_to]]
    rows = [[names[r], *[str(mv["matrix"][r][cto]) for cto in cols_to]] for r in rows_from]
    st.table(s, 4.85, 1.82, [1.2, 0.8, 0.8, 0.8, 0.85], header, rows, row_h=0.34, size=9.5,
             align=["left", "center", "center", "center", "center"],
             row_colors=[st.ZONE_COLOR.get(r) for r in rows_from])  # fmt: skip
    st.text(s, "Hàng = vùng tháng trước, cột = vùng tháng này; đường chéo = giữ nguyên vùng.", 4.85, 3.68, 4.5, 0.4,
            size=9, color=st.MUTE)  # fmt: skip
    dg = pts(k["gpu_avg"] - prev["gpu_avg"]) if k["gpu_avg"] is not None and prev["gpu_avg"] is not None else "—"
    st.strip(s, f"TB GPU {pct(prev['gpu_avg'])} → {pct(k['gpu_avg'])} ({dg} điểm); Nguy hiểm "
                f"{prev['zones']['danger']} → {k['zones']['danger']} server.")  # fmt: skip


def _owners(s: Any, d: dict[str, Any]) -> None:
    m = d["owners"]
    st.kicker(s, "Theo đầu mối")
    st.title(s, "Phân bố vùng theo đầu mối")
    owners = list(m["owners"])
    tot = {o: sum(m["rows"][z].get(o, 0) for z in ZONES) for o in owners}
    named = sorted((o for o in owners if o != UNMAPPED), key=lambda o: (-tot[o], o))
    keep, rest = named[:MAX_OWNERS], named[MAX_OWNERS:]
    cats = list(keep) + (["Khác"] if rest else []) + ([UNMAPPED_LABEL] if UNMAPPED in owners and tot[UNMAPPED] else [])

    def val(z: str, c: str) -> int:
        if c == "Khác":
            return sum(m["rows"][z].get(o, 0) for o in rest)
        return m["rows"][z].get(UNMAPPED if c == UNMAPPED_LABEL else c, 0)

    st.card(s, 0.5, 1.28, 6.0, 3.35)
    if cats:
        st.bar_chart(s, 0.6, 1.36, 5.8, 3.2, cats, [(st.ZONE_LABEL[z], [val(z, c) for c in cats]) for z in ZONES],
                     title_t=f"Số server mỗi vùng theo đầu mối (T = {d['threshold']:g}%)", val_title="Server",
                     colors=[st.ZONE_COLOR[z] for z in ZONES], gap=70)  # fmt: skip
    else:
        st.placeholder(s, "[Cần bổ sung số liệu] — chưa có server nào trong phạm vi.", 0.8, 2.7, 5.4)
    st.card(s, 6.8, 1.28, 2.7, 3.35, st.CARD)
    st.icon(s, 7.22, 1.7, "users", st.NAVY)
    st.card_title(s, 7.6, 1.58, 1.8, "Nguy hiểm", st.NAVY)
    lines = [f"{c}: {val('danger', c)}/{sum(val(z, c) for z in ZONES)} server" for c in cats[:8]]
    st.text(s, "\n".join(lines) or "—", 7.02, 2.12, 2.3, 2.4, size=10.5)
    if UNMAPPED in owners and tot[UNMAPPED]:
        tail = f"{tot[UNMAPPED]} server chưa có trong thống kê (chưa xác định đầu mối)."
    else:
        tail = "Mọi server có số liệu đều đã có trong thống kê."
    lead = max(keep, key=lambda o: (m["rows"]["danger"].get(o, 0), tot[o]), default=None)
    head = f"Nhiều server Nguy hiểm nhất: {lead} ({m['rows']['danger'].get(lead, 0)}). " if lead else ""
    st.strip(s, head + tail)


def _danger(s: Any, d: dict[str, Any]) -> None:
    rows, k = d["danger"], d["kpi"]
    st.kicker(s, "Server Nguy hiểm")
    st.title(s, f"{len(rows)} server Nguy hiểm ({k['cards_total']['danger']} card) — {d['label']}")
    if not rows:
        st.card(s, 0.5, 1.28, 9.0, 3.35)
        st.icon(s, 1.0, 2.9, "check", st.GREEN)
        st.text(s, "Không có server nào ở vùng Nguy hiểm trong tháng.", 1.4, 2.75, 7.5, 0.3, size=12)
        st.strip(s, "Không có server Nguy hiểm — tiếp tục theo dõi hằng tháng.")
        return
    shown = rows[:MAX_DANGER_ROWS]
    header = ["IP", "Đầu mối", "Dịch vụ", "GPU", "Card", "TB GPU", "TB VRAM", "Liên tiếp"]
    body = [
        [r["ip"], clip(r["owner"], 12) if r["mapped"] else "(chưa có)", clip(r["service"], 42),
         clip(r["gpu_model"], 10), str(r["cards"] or "—"), pct(r["gpu_avg"]), pct(r["mem_avg"]),
         f"{'≥' if r['streak_open'] else ''}{r['streak_months']} tháng"]
        for r in shown
    ]  # fmt: skip
    row_h = 0.25 if len(shown) > 9 else 0.28
    st.table(s, 0.5, 1.28, [1.3, 0.95, 2.75, 0.9, 0.55, 0.8, 0.8, 0.95], header, body, row_h=row_h, size=9,
             align=["left", "left", "left", "left", "center", "right", "right", "center"])  # fmt: skip
    more = len(rows) - len(shown)
    if more:
        st.placeholder(s, f"+{more} server Nguy hiểm khác — đủ danh sách trong file Excel xuất từ trang Cảnh báo.",
                       0.5, 4.48, 9.0)  # fmt: skip
    if any(r["streak_open"] for r in rows) and not more:
        first = short(d["trend"][0]["month"]) if d["trend"] else ""
        st.placeholder(s, f"≥ = Nguy hiểm từ tháng đầu có dữ liệu ({first}) — có thể đã kéo dài hơn.",
                       0.5, 4.48, 9.0)  # fmt: skip
    long = sum(1 for r in rows if r["streak_months"] >= 3)
    low = sum(1 for r in rows if r["vtnet_low_load"])
    vt = d.get("vtnet_t", 10)
    st.strip(s, f"{long} server Nguy hiểm từ 3 tháng liên tiếp trở lên; {low} server dưới ngưỡng thấp tải VTNet "
                f"(GPU và VRAM < {vt:g}%).")  # fmt: skip
