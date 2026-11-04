"""Báo cáo tháng cho lãnh đạo (Roadmap §14.2): gom số liệu 1 tháng + xu hướng + so với tháng trước + đầu mối + server
Nguy hiểm, rồi dựng deck .pptx phong cách TT.CN (app/reports/monthly_deck.py).

Không công thức mới: mỗi tháng là 1 Bundle (gpu_core.server_stats, luật vùng, T như các trang khác);
xu hướng = compare_service.trend_zones; so sánh = compare_service.compare (gpu_core.compare_periods).
Tháng = tháng dương lịch (01 → cuối tháng); danh sách tháng = nhãn kỳ các lô VTNet đã xác nhận
(ngày tràn kỳ như 01/11 trong file T10 không tạo "tháng 11").
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.errors import ServiceError
from app.repo import batch_repo
from app.scope import Scope
from app.services import compare_service
from app.services.analytics_service import (
    UNMAPPED,
    AnalyticsCache,
    Filters,
    alerts,
    apply_scope,
    fleet_summary,
    get_bundle,
    resolve_context,
)

TREND_MONTHS = 6  # số tháng tối đa trên biểu đồ xu hướng (gồm tháng báo cáo)
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
NO_FILTERS = Filters()


def month_bounds(month: str) -> tuple[date, date]:
    y, m = int(month[:4]), int(month[5:7])
    start = date(y, m, 1)
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return start, nxt - timedelta(days=1)


def month_label(month: str) -> str:
    return f"tháng {int(month[5:7])}/{month[:4]}"


def available_months(s: Session) -> list[str]:
    """Tháng có lô VTNet đã xác nhận (nhãn kỳ = tháng chiếm nhiều ngày nhất của file), mới nhất trước."""
    labels = {b.period_label for b in batch_repo.committed_batches(s, "vtnet_util") if b.period_label}
    return sorted((m for m in labels if _MONTH.match(m)), reverse=True)


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}".replace(".", ",") + "%"


def _pts(v: float) -> str:
    return f"{v:+.1f}".replace(".", ",").replace("-", "−")


def monthly(
    s: Session, cache: AnalyticsCache, month: str | None, threshold: float | None, scope: Scope
) -> dict[str, Any]:
    months = available_months(s)
    if not months:
        raise ServiceError(422, "Chưa có file tải VTNet nào được xác nhận — chưa lập được báo cáo tháng.")
    month = month or months[0]
    if not _MONTH.match(month):
        raise ServiceError(422, "Tháng phải có dạng YYYY-MM.")
    if month not in months:
        raise ServiceError(404, f"Chưa có dữ liệu VTNet cho {month_label(month)}. Có: {', '.join(months)}")
    start, end = month_bounds(month)
    ctx = resolve_context(s, start, end, threshold)
    b = get_bundle(s, cache, ctx)
    fs = fleet_summary(b, NO_FILTERS, scope)

    # --- xu hướng: các tháng có dữ liệu ≤ tháng báo cáo (tối đa TREND_MONTHS)
    chosen = sorted(m for m in months if m <= month)[-TREND_MONTHS:]
    tz = compare_service.trend_zones(s, cache, month_bounds(chosen[0])[0], end, ctx.threshold, NO_FILTERS, scope)
    trend = [
        {k: m[k] for k in ("month", "n_servers", "zones", "cards", "gpu_avg", "mem_avg")}
        for m in tz["months"]
        if m["month"] in chosen
    ]

    # --- so với tháng trước có dữ liệu
    earlier = [m for m in months if m < month]
    previous = movement = None
    if earlier:
        p = earlier[0]
        cmp = compare_service.compare(s, cache, month_bounds(p), (start, end), ctx.threshold, NO_FILTERS, scope)
        a = cmp["a"]
        previous = {"month": p, **{k: a[k] for k in ("gpu_avg", "mem_avg", "n_servers", "zones", "cards_total")}}
        movement = {"counts": cmp["counts"], "matrix": cmp["matrix"]}

    # --- server Nguy hiểm + số tháng liên tiếp ở vùng Nguy hiểm (tính trên các tháng xu hướng liền nhau)
    al = alerts(b, NO_FILTERS, scope, zones=("danger",), sort="gpu_avg,mem_avg", page_size=500)
    danger_by_month: dict[str, set[str]] = {}
    for m in chosen:
        bm = get_bundle(s, cache, resolve_context(s, *month_bounds(m), ctx.threshold))
        srv = apply_scope(bm.servers, scope)
        danger_by_month[m] = set(srv.loc[srv["zone"] == "danger", "ip"]) if not srv.empty else set()

    def streak(ip: str) -> tuple[int, bool]:
        """(số tháng liên tiếp, chạm tháng sớm nhất đang xét → có thể dài hơn: hiển thị '≥')."""
        n, cur = 0, month
        while cur in danger_by_month and ip in danger_by_month[cur]:
            n += 1
            prev_start = month_bounds(cur)[0] - timedelta(days=1)
            cur = f"{prev_start:%Y-%m}"
        return n, n > 0 and cur not in danger_by_month and cur < chosen[0]

    danger = [
        {
            "ip": r["ip"],
            "owner": r["owner"],
            "service": r["service"],
            "gpu_model": r["gpu_model"],
            "cards": r["cards"],
            "gpu_avg": r["gpu_avg"],
            "mem_avg": r["mem_avg"],
            "pattern": r["pattern"],
            "vtnet_low_load": r["vtnet_low_load"],
            "mapped": r["mapped"],
            "streak_months": streak(r["ip"])[0],
            "streak_open": streak(r["ip"])[1],
        }
        for r in al["items"]
    ]
    kpi = {
        k: fs[k]
        for k in ("gpu_avg", "mem_avg", "n_servers", "n_mapped", "n_unmapped", "zones", "cards_total", "patterns",
                  "vtnet_low_load", "thin_data")
    }  # fmt: skip
    kpi["cards"] = sum(fs["cards_total"].values())
    data: dict[str, Any] = {
        "month": month,
        "label": month_label(month),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "threshold": ctx.threshold,
        "vtnet_t": ctx.params.vtnet_low_load_t,
        "scope_owner": scope.owner_key if scope.kind == "owner" else None,
        "available_months": months,
        "kpi": kpi,
        "trend": trend,
        "previous": previous,
        "movement": movement,
        "owners": fs["matrix"],
        "danger": danger,
    }
    data["suggestion"] = suggest(data)
    return data


def suggest(d: dict[str, Any]) -> dict[str, Any]:
    """Thông điệp chính + kiến nghị gợi ý — chỉ dùng số đã tính, admin sửa được trước khi tải."""
    k, prev, label = d["kpi"], d["previous"], d["label"]
    nd, n = k["zones"]["danger"], k["n_servers"]
    cd = k["cards_total"]["danger"]
    msg = f"TB GPU {label} đạt {_pct(k['gpu_avg'])}"
    if prev and prev["gpu_avg"] is not None and k["gpu_avg"] is not None:
        msg += f" ({_pts(k['gpu_avg'] - prev['gpu_avg'])} điểm so với {month_label(prev['month'])})"
    msg += f"; {nd}/{n} server Nguy hiểm ({cd} card) cần rà soát với đầu mối."

    recs: list[dict[str, str]] = []
    if nd:
        by_owner = sorted(
            ((o, d["owners"]["rows"]["danger"].get(o, 0)) for o in d["owners"]["owners"] if o != UNMAPPED),
            key=lambda x: (-x[1], x[0]),
        )
        who = ", ".join(f"{o} ({c})" for o, c in by_owner if c)
        long = sum(1 for r in d["danger"] if r["streak_months"] >= 3)
        detail = f"Làm việc với đầu mối {who} về nhu cầu thực." if who else "Xác định đầu mối và nhu cầu thực."
        if long:
            detail += f" {long} server Nguy hiểm từ 3 tháng liên tiếp trở lên."
        recs.append({"title": f"Rà soát {nd} server Nguy hiểm ({cd} card)", "detail": detail})
    if d["movement"] and d["movement"]["counts"]["worsened"]:
        w = d["movement"]["counts"]["worsened"]
        recs.append({
            "title": f"Theo dõi {w} server xấu đi",
            "detail": f"Chuyển sang vùng kém hơn so với {month_label(prev['month'])} (cùng ngưỡng T = "
            f"{d['threshold']:g}%).",
        })  # fmt: skip
    if k["n_unmapped"]:
        recs.append({
            "title": "Cập nhật file thống kê server",
            "detail": f"{k['n_unmapped']} IP có trong số liệu VTNet nhưng chưa có trong thống kê — chưa xác định "
            "được đầu mối.",
        })  # fmt: skip
    if not recs:
        recs.append({"title": "Duy trì theo dõi hằng tháng", "detail": "Không có server Nguy hiểm trong tháng."})
    return {"message": msg, "recommendations": recs[:3]}
