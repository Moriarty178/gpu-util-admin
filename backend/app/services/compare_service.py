"""So sánh kỳ · xu hướng vùng theo tháng · so sánh ≤ 5 server (G2-M3, PLAN §1.1 B5b/B6, §8.6).

Không công thức mới: mỗi kỳ / mỗi tháng là 1 Bundle (gpu_core.server_stats, cùng luật vùng, cùng T);
chuyển vùng giữa 2 kỳ = gpu_core.compare_periods (improved = sang vùng tốt hơn, worsened = xấu hơn, new / gone).
Mọi hàm áp `Scope` + bộ lọc toàn cục như các trang phân tích khác.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

import pandas as pd
from sqlalchemy.orm import Session

import gpu_core as g
from app.errors import ServiceError
from app.repo import batch_repo, util_repo
from app.repo.convert import py
from app.scope import Scope
from app.services.analytics_service import (
    ZONES,
    AnalyticsCache,
    Bundle,
    Context,
    Filters,
    Granularity,
    apply_scope,
    filter_servers,
    fleet_summary,
    get_bundle,
    resolve_context,
    server_detail,
    server_timeseries,
)

MOVEMENTS = ("worsened", "improved", "same", "new", "gone")
MAX_COMPARE_SERVERS = 5
MAX_TREND_MONTHS = 36
MAX_TREND_WEEKS = 156  # 3 năm theo tuần ISO
TrendGranularity = Literal["month", "week"]
META = ["inventory_ip", "owner", "service", "model", "gpu_type", "gpu_model", "cards", "mapped"]


def default_periods(s: Session) -> tuple[tuple[date, date], tuple[date, date]] | None:
    """Mặc định = 2 kỳ file VTNet gần nhất (A = kỳ trước, B = kỳ mới nhất)."""
    ps = [b for b in batch_repo.committed_batches(s, "vtnet_util") if b.period_start and b.period_end]
    if len(ps) < 2:
        return None
    b, a = ps[0], ps[1]
    assert a.period_start and a.period_end and b.period_start and b.period_end
    return (a.period_start, a.period_end), (b.period_start, b.period_end)


def _kpi(b: Bundle, f: Filters, scope: Scope) -> dict[str, Any]:
    fs = fleet_summary(b, f, scope)
    return {
        "params": fs["params"],
        "gpu_avg": fs["gpu_avg"],
        "mem_avg": fs["mem_avg"],
        "n_servers": fs["n_servers"],
        "zones": fs["zones"],
        "cards_total": fs["cards_total"],
    }


def compare(
    s: Session,
    cache: AnalyticsCache,
    a: tuple[date | None, date | None],
    b: tuple[date | None, date | None],
    threshold: float | None,
    f: Filters,
    scope: Scope,
) -> dict[str, Any]:
    if None in (*a, *b):
        d = default_periods(s)
        if d is None:
            raise ServiceError(422, "Cần chọn 2 khoảng ngày (mới có dưới 2 kỳ file VTNet để chọn sẵn).")
        a = (a[0] or d[0][0], a[1] or d[0][1])
        b = (b[0] or d[1][0], b[1] or d[1][1])
    ctx_a = resolve_context(s, a[0], a[1], threshold)
    ctx_b = resolve_context(s, b[0], b[1], threshold)
    ba, bb = get_bundle(s, cache, ctx_a), get_bundle(s, cache, ctx_b)
    sa = filter_servers(apply_scope(ba.servers, scope), f)
    sb = filter_servers(apply_scope(bb.servers, scope), f)
    cols = ["ip", "zone", "gpu_avg", "mem_avg"]
    empty = pd.DataFrame(columns=cols)
    if sa.empty and sb.empty:
        cmp = pd.DataFrame(columns=["ip", "zone_prev", "zone_cur", "movement", "d_gpu"])
    else:
        cmp = g.compare_periods(sa[cols] if not sa.empty else empty, sb[cols] if not sb.empty else empty)
    meta = pd.concat([sb[["ip", *META]], sa[["ip", *META]]]).drop_duplicates("ip") if len(sa) + len(sb) else None
    if meta is not None and not cmp.empty:
        cmp = cmp.merge(meta, on="ip", how="left")
    counts = {m: int((cmp["movement"] == m).sum()) if not cmp.empty else 0 for m in MOVEMENTS}
    rows_from = (*ZONES, "new")
    cols_to = (*ZONES, "gone")
    matrix = {z: dict.fromkeys(cols_to, 0) for z in rows_from}
    for r in cmp.to_dict("records"):
        zp = r["zone_prev"] if isinstance(r["zone_prev"], str) else "new"
        zc = r["zone_cur"] if isinstance(r["zone_cur"], str) else "gone"
        matrix[zp][zc] += 1
    order = {m: i for i, m in enumerate(MOVEMENTS)}
    if not cmp.empty:
        cmp = cmp.assign(_m=cmp["movement"].map(order))
        cmp = cmp.sort_values(["_m", "d_gpu", "ip"], na_position="last").drop(columns="_m")
    fields = ["ip", *META, "zone_prev", "zone_cur", "gpu_avg_prev", "gpu_avg_cur", "mem_avg_prev", "mem_avg_cur",
              "d_gpu", "d_mem", "movement"]  # fmt: skip
    items = [{k: py(r.get(k)) for k in fields} for r in cmp.to_dict("records")]
    return {
        "a": _kpi(ba, f, scope),
        "b": _kpi(bb, f, scope),
        "threshold": ctx_b.threshold,
        "counts": counts,
        "matrix": matrix,
        "items": items,
    }


def _weeks(start: date, end: date) -> list[tuple[date, date]]:
    """Tuần ISO (thứ 2 → CN) cắt theo [start, end] — tuần đầu/cuối có thể ngắn hơn 7 ngày."""
    out = []
    cur = start - timedelta(days=start.weekday())
    while cur <= end:
        out.append((max(cur, start), min(cur + timedelta(days=6), end)))
        cur += timedelta(days=7)
    return out


def _months(start: date, end: date) -> list[tuple[date, date]]:
    out = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append((max(cur, start), min(nxt - timedelta(days=1), end)))
        cur = nxt
    return out


def trend_zones(
    s: Session, cache: AnalyticsCache, start: date | None, end: date | None, threshold: float | None, f: Filters,
    scope: Scope, granularity: TrendGranularity = "month",
) -> dict[str, Any]:  # fmt: skip
    """Số server từng vùng theo tháng hoặc tuần ISO (mỗi kỳ tính riêng: TB kỳ → vùng theo T). Mặc định = toàn bộ dữ liệu.
    Kỳ đầu/cuối cắt theo ngày có dữ liệu (`start`/`end`, `n_days`)."""
    lo, hi = util_repo.data_range(s)
    if lo is None or hi is None:
        return {"threshold": resolve_context(s, None, None, threshold).threshold, "granularity": granularity,
                "months": []}  # fmt: skip
    start, end = max(start or lo, lo), min(end or hi, hi)
    if start > end:
        raise ServiceError(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    periods = _weeks(start, end) if granularity == "week" else _months(start, end)
    limit = MAX_TREND_WEEKS if granularity == "week" else MAX_TREND_MONTHS
    if len(periods) > limit:
        raise ServiceError(422, f"Khoảng quá dài — tối đa {limit} {'tuần' if granularity == 'week' else 'tháng'}.")
    out = []
    t = None
    for m_start, m_end in periods:
        ctx: Context = resolve_context(s, m_start, m_end, threshold)
        t = ctx.threshold
        b = get_bundle(s, cache, ctx)
        srv = filter_servers(apply_scope(b.servers, scope), f)
        zones = {z: int((srv["zone"] == z).sum()) if not srv.empty else 0 for z in ZONES}
        cards = {z: int(srv.loc[srv["zone"] == z, "cards"].sum()) if not srv.empty else 0 for z in ZONES}
        fs = fleet_summary(b, f, scope)
        iso = m_start.isocalendar()
        out.append(
            {
                "period": f"{iso[0]}-W{iso[1]:02d}" if granularity == "week" else f"{m_start:%Y-%m}",
                "month": None if granularity == "week" else f"{m_start:%Y-%m}",
                "start": m_start.isoformat(),
                "n_days": (m_end - m_start).days + 1,
                "end": m_end.isoformat(),
                "n_servers": len(srv),
                "zones": zones,
                "cards": cards,
                "gpu_avg": fs["gpu_avg"],
                "mem_avg": fs["mem_avg"],
            }
        )
    return {"threshold": t, "granularity": granularity, "months": out}


def servers_timeseries(b: Bundle, ips: list[str], scope: Scope, granularity: Granularity) -> dict[str, Any]:
    """Chuỗi tải của tối đa 5 server cùng khoảng (so sánh trên 1 biểu đồ). Server ngoài phạm vi → 404 như trang Server."""
    ips = list(dict.fromkeys(ip.strip() for ip in ips if ip.strip()))
    if not ips:
        raise ServiceError(422, "Chọn ít nhất 1 server.")
    if len(ips) > MAX_COMPARE_SERVERS:
        raise ServiceError(422, f"So sánh tối đa {MAX_COMPARE_SERVERS} server.")
    series = []
    for ip in ips:
        d = server_detail(b, ip, scope)
        ts = server_timeseries(b, ip, scope, granularity)
        st = d["stats"] or {}
        inv = d["inventory"] or {}
        series.append(
            {
                "ip": d["ip"],
                "inventory_ip": d["inventory_ip"],
                "owner": inv.get("owner") or st.get("owner"),
                "service": inv.get("service") or st.get("service"),
                "gpu_type": st.get("gpu_type"),
                "zone": st.get("zone"),
                "gpu_avg": st.get("gpu_avg"),
                "mem_avg": st.get("mem_avg"),
                "points": ts["points"],
            }
        )
    return {"params": b.ctx.as_params(), "granularity": granularity, "series": series}
