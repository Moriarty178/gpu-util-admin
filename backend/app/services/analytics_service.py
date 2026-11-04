"""Phân tích (PLAN §6). SQL chỉ lấy mẫu hiệu lực + thống kê + liên kết IP + thu hồi; mọi phép tính nghiệp vụ qua gpu_core:
  * TB 1 server / vùng / mẫu hình / cờ VTNet / streak / nhận xét   → gpu_core.server_stats
  * TB toàn bộ server theo ngày (theo server | theo card)          → gpu_core.fleet_daily
  * ghép thống kê ↔ VTNet qua liên kết IP                          → gpu_core.apply_ip_links
  * ma trận vùng × đầu mối                                         → gpu_core.zone_owner_matrix
Service chỉ: chọn khoảng/ngưỡng, ghép bảng, lọc, đếm, gom ngày → tuần/tháng (mean các giá trị ngày), sắp xếp, phân trang.
Mọi hàm nhận `Scope` (GĐ1 luôn Scope.all()).
"""

from __future__ import annotations

import ipaddress
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import gpu_core as g
from app.errors import ServiceError
from app.repo import batch_repo, inventory_repo, settings_repo, util_repo
from app.repo.convert import jsonable, py
from app.scope import Scope

ZONES = ("danger", "warning", "safe")
ZONE_ORDER = {z: i for i, z in enumerate(ZONES)}
PATTERNS = ("idle", "bursty_idle", "memory_bound", "compute_bound", "high_load", "healthy")
UNMAPPED = "_unmapped"
DEFAULT_WINDOW_DAYS = 28  # khoảng xem mặc định = 4 tuần gần nhất có dữ liệu (người dùng chốt 04/11/2026, PLAN §14.8)
log = logging.getLogger(__name__)
Granularity = Literal["day", "week", "month"]
Weight = Literal["server", "gpu"]

ITEM_FIELDS = [
    "ip", "inventory_ip", "owner", "service", "model", "cluster", "managed_by", "gpu_type", "gpu_count", "gpu_model",
    "inventory_gpu_spec", "gpu_avg", "mem_avg", "gpu_peak", "gpu_p95", "mem_peak", "days", "coverage", "low_streak",
    "danger_days", "zone", "pattern", "vtnet_low_load", "thin_data", "assessment", "reclaimed", "mapped", "ip_linked",
    "pair_confirmed", "gpu_count_mismatch", "cards",
]  # fmt: skip
SORTABLE = {
    "ip", "owner", "zone", "pattern", "gpu_avg", "mem_avg", "gpu_peak", "gpu_p95", "days", "coverage",
    "low_streak", "danger_days", "cards", "gpu_model", "service",
}  # fmt: skip


# ------------------------------------------------------------------ tham số & cache


@dataclass(frozen=True)
class Filters:
    """Bộ lọc toàn cục (PLAN §7). owner có thể chứa '_unmapped' = server VTNet chưa có trong thống kê."""

    owner: tuple[str, ...] = ()
    gpu_model: tuple[str, ...] = ()
    cluster: tuple[str, ...] = ()
    managed_by: tuple[str, ...] = ()
    q: str | None = None


@dataclass(frozen=True)
class Context:
    start: date
    end: date
    threshold: float
    params: g.RuleParams
    has_data: bool
    requested: tuple[date, date] | None = None  # khoảng người dùng chọn khi đã bị cắt về ngày có dữ liệu

    @property
    def days_in_range(self) -> int:
        return (self.end - self.start).days + 1

    def as_params(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "threshold": self.threshold,
            "days_in_range": self.days_in_range,
            "clamped": self.requested is not None,
        }
        if self.requested is not None:
            out["requested_start"], out["requested_end"] = (d.isoformat() for d in self.requested)
        return out


@dataclass
class Bundle:
    ctx: Context
    raw: pd.DataFrame  # mẫu hiệu lực trong khoảng (ip, ts, gpu, mem, gpu_type, batch_id)
    stats: pd.DataFrame  # gpu_core.server_stats — 1 dòng / IP VTNet
    servers: pd.DataFrame  # stats ⟕ thống kê (qua liên kết IP) — 1 dòng / IP VTNet
    inventory: pd.DataFrame  # thống kê hiện hành (ip = IP phía VTNet, inventory_ip = IP gốc)
    links: pd.DataFrame
    reclaimed: pd.DataFrame
    reclaimed_ips: set[str] = field(default_factory=set)


class AnalyticsCache:
    """Bộ nhớ đệm phân tích trong tiến trình, khóa theo `data_version` (đổi khi xác nhận/hoàn tác lô, đổi liên kết,
    đổi cài đặt) → luôn đúng số liệu mới nhất.
      * store : TOÀN BỘ mẫu hiệu lực (util_effective) của phiên bản dữ liệu hiện tại — đọc CSDL 1 lần / phiên bản
      * bundles (LRU): kết quả tính cho từng (khoảng ngày, T, tham số luật)
    """

    def __init__(self, maxsize: int = 16) -> None:
        self._data: OrderedDict[Hashable, Bundle] = OrderedDict()
        self._lock = threading.Lock()
        self._store_lock = threading.Lock()
        self._store: tuple[Hashable, pd.DataFrame] | None = None
        self.maxsize = maxsize
        self.hits = self.misses = self.store_loads = 0

    def effective(self, version: Hashable, load: Callable[[], pd.DataFrame]) -> pd.DataFrame:
        with self._store_lock:  # 1 lần đọc / phiên bản dữ liệu, các request đồng thời chờ cùng 1 lần đọc
            if self._store is None or self._store[0] != version:
                self._store = (version, load())
                self.store_loads += 1
            return self._store[1]

    def get_or_build(self, key: Hashable, build: Callable[[], Bundle]) -> Bundle:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key]
        value = build()
        with self._lock:
            self.misses += 1
            self._data[key] = value
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)
        return value

    def clear(self, store: bool = False) -> None:
        with self._lock:
            self._data.clear()
        if store:
            with self._store_lock:
                self._store = None


def rule_params(settings: dict[str, Any]) -> g.RuleParams:
    d = g.DEFAULT_PARAMS
    return g.RuleParams(
        vtnet_low_load_t=float(settings.get("vtnet_low_load_t", d.vtnet_low_load_t)),
        bursty_peak=float(settings.get("bursty_peak", d.bursty_peak)),
        high_load=float(settings.get("high_load", d.high_load)),
        thin_coverage=float(settings.get("thin_coverage", d.thin_coverage)),
    )


def default_range(lo: date, hi: date) -> tuple[date, date]:
    """4 tuần gần nhất có dữ liệu: [ngày cuối có dữ liệu − 27, ngày cuối] (không sớm hơn ngày đầu có dữ liệu)."""
    return max(lo, hi - timedelta(days=DEFAULT_WINDOW_DAYS - 1)), hi


def resolve_context(s: Session, start: date | None, end: date | None, threshold: float | None) -> Context:
    """Khoảng mặc định = 4 tuần gần nhất có dữ liệu; T = cài đặt. Khoảng chọn vượt ra ngoài ngày có dữ liệu → CẮT về
    [ngày đầu, ngày cuối có dữ liệu] (người dùng chốt 04/11/2026): mẫu số "ngày trong khoảng" (độ phủ → dữ liệu mỏng,
    ngày nguy hiểm…) chỉ tính ngày đã có thể có số liệu — xem 01–31/10 khi mới có tới 18/10 không gắn mỏng cả loạt.
    Khoảng hoàn toàn ngoài dữ liệu → giữ nguyên (kết quả rỗng)."""
    settings = settings_repo.all_values(s)
    t = float(threshold if threshold is not None else settings.get("default_threshold", g.DEFAULT_THRESHOLD))
    lo, hi = util_repo.data_range(s)
    if lo is None or hi is None:
        today = date.today()
        start, end = start or today, end or today
    elif start is None and end is None:
        start, end = default_range(lo, hi)
    else:
        start, end = start or lo, end or hi
    if start > end:
        raise ServiceError(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    requested = None
    if lo is not None and hi is not None and start <= hi and end >= lo and (start < lo or end > hi):
        requested, start, end = (start, end), max(start, lo), min(end, hi)
    return Context(start=start, end=end, threshold=t, params=rule_params(settings), has_data=lo is not None,
                   requested=requested)  # fmt: skip


def get_bundle(s: Session, cache: AnalyticsCache, ctx: Context) -> Bundle:
    version = batch_repo.data_version(s)
    key = (ctx.start, ctx.end, ctx.threshold, ctx.params, ctx.requested, version)

    def build() -> Bundle:
        store = cache.effective(version, lambda: util_repo.effective_frame(s))
        lo, hi = pd.Timestamp(ctx.start), pd.Timestamp(ctx.end) + pd.Timedelta(days=1)  # end tính trọn ngày
        return _build_bundle(s, ctx, store[(store["ts"] >= lo) & (store["ts"] < hi)].reset_index(drop=True))

    return cache.get_or_build(key, build)


def warm_up(engine: Engine, cache: AnalyticsCache) -> None:
    """Đọc sẵn dữ liệu + tính sẵn khoảng mặc định (4 tuần gần nhất) với T mặc định (gọi nền khi khởi động / sau xác nhận, hoàn tác lô)."""
    try:
        with Session(engine) as s:
            get_bundle(s, cache, resolve_context(s, None, None, None))
    except Exception:  # làm nóng thất bại không được làm hỏng request nào
        log.exception("Làm nóng bộ nhớ đệm phân tích thất bại")


# ------------------------------------------------------------------ dựng dữ liệu (1 lần / khóa cache)


def _gpu_spec_parts(spec: Any) -> tuple[int | None, str | None]:
    count, model = g.parse_gpu_spec(spec if isinstance(spec, str) else None)
    return count, model


def _build_bundle(s: Session, ctx: Context, raw: pd.DataFrame) -> Bundle:
    if raw.empty:
        stats = pd.DataFrame(columns=["ip", "gpu_type", "gpu_avg", "mem_avg", "zone", "pattern"])
    else:
        stats = g.server_stats(raw, ctx.start, ctx.end, ctx.threshold, params=ctx.params)

    links = inventory_repo.links_frame(s)
    inv_raw = inventory_repo.current_frame(s)
    try:
        inv = g.apply_ip_links(inv_raw, links)  # ip = IP phía VTNet, inventory_ip = IP trong file thống kê
    except ValueError as exc:
        raise ServiceError(409, f"Liên kết IP mâu thuẫn với file thống kê hiện hành: {exc}") from exc
    inv = inv.rename(
        columns={"gpu_spec": "inventory_gpu_spec", "gpu_count": "inv_gpu_count", "gpu_model": "inv_gpu_model"}
    )
    reclaimed = inventory_repo.reclaim_frame(s)
    reclaimed_ips = set(reclaimed["ip"])
    confirmed = dict(zip(links["vtnet_ip"], links["pair_confirmed"].astype(bool), strict=True))

    srv = stats.merge(inv, on="ip", how="left") if not stats.empty else stats.assign(inventory_ip=None)
    if not srv.empty:
        vt = [_gpu_spec_parts(t) for t in srv["gpu_type"]]
        vt_count = [py(c) for c, _ in vt]
        vt_model = [m for _, m in vt]
        inv_count = [py(v) for v in srv["inv_gpu_count"]]
        idx = srv.index

        def col(values: list[Any]) -> pd.Series:
            return pd.Series(values, index=idx, dtype=object)  # giữ None (không ép NaN/NA)

        srv["mapped"] = srv["inventory_ip"].notna()
        srv["ip_linked"] = col([bool(v) if py(v) is not None else False for v in srv["ip_linked"]]).astype(bool)
        srv["pair_confirmed"] = col([confirmed.get(ip) if lk else None for ip, lk in zip(srv["ip"], srv["ip_linked"])])
        # Số card: VTNet gpu_type → thống kê → (thiếu); `cards` (trọng số, card theo vùng) = số card hoặc 1 (PLAN §6)
        counts = [v if v is not None else i for v, i in zip(vt_count, inv_count, strict=True)]
        srv["gpu_count"] = col(counts)
        srv["gpu_model"] = col([v or py(i) for v, i in zip(vt_model, srv["inv_gpu_model"], strict=True)])
        srv["cards"] = [int(c) if c else 1 for c in counts]
        srv["gpu_count_mismatch"] = [
            bool(m and py(spec) is not None and v is not None and (i is None or int(i) != int(v)))
            for m, spec, v, i in zip(srv["mapped"], srv["inventory_gpu_spec"], vt_count, inv_count, strict=True)
        ]
        srv["reclaimed"] = [
            ip in reclaimed_ips or (py(iip) in reclaimed_ips) for ip, iip in zip(srv["ip"], srv["inventory_ip"])
        ]
    return Bundle(
        ctx=ctx,
        raw=raw,
        stats=stats,
        servers=srv,
        inventory=inv,
        links=links,
        reclaimed=reclaimed,
        reclaimed_ips=reclaimed_ips,
    )


# ------------------------------------------------------------------ lọc & tiện ích


def apply_scope(df: pd.DataFrame, scope: Scope) -> pd.DataFrame:
    """GĐ2: owner + data_scope=own → chỉ server của đầu mối. GĐ1 luôn Scope.all() → giữ nguyên."""
    if scope.kind == "owner" and not df.empty:
        return df[df["owner"] == scope.owner_key]
    return df


def filter_servers(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    if df.empty:
        return df
    mask = pd.Series(True, index=df.index)
    if f.owner:
        mask &= df["owner"].isin(f.owner) | ((~df["mapped"]) & (UNMAPPED in f.owner))
    for col in ("cluster", "managed_by"):
        vals = getattr(f, col)
        if vals:
            mask &= df[col].isin(vals)  # chỉ server map được với thống kê
    if f.gpu_model:
        mask &= df["gpu_model"].isin(f.gpu_model)
    if f.q:
        needle = f.q.strip().casefold()
        cols = [c for c in ("ip", "inventory_ip", "owner", "service", "model", "gpu_type", "cluster") if c in df]
        hay = df[cols].astype("string").fillna("").agg(" ".join, axis=1).str.casefold()
        mask &= hay.str.contains(needle, regex=False)
    return df[mask]


def _ip_key(ip: Any) -> int:
    try:
        return int(ipaddress.IPv4Address(str(ip)))
    except ValueError:
        return 0


def sort_frame(df: pd.DataFrame, sort: str) -> pd.DataFrame:
    """sort = 'zone,gpu_avg' | '-gpu_avg' … (dấu '-' = giảm dần)."""
    if df.empty:
        return df
    keys, asc = [], []
    for part in [p.strip() for p in sort.split(",") if p.strip()]:
        name = part.lstrip("-")
        if name not in SORTABLE:
            raise ServiceError(422, f"Không sắp xếp được theo '{name}'. Cho phép: {sorted(SORTABLE)}")
        if name not in df.columns:
            continue
        keys.append(name)
        asc.append(not part.startswith("-"))
    keys.append("ip")
    asc.append(True)

    def key(col: pd.Series) -> pd.Series:
        if col.name == "zone":
            return col.map(ZONE_ORDER)
        if col.name == "ip":
            return col.map(_ip_key)
        return col

    return df.sort_values(keys, ascending=asc, key=key, kind="stable", na_position="last")


def records(df: pd.DataFrame, fields: list[str]) -> list[dict[str, Any]]:
    cols = [c for c in fields if c in df.columns]
    return [{c: py(v) for c, v in zip(cols, row, strict=True)} for row in df[cols].itertuples(index=False)]


def zone_counts(df: pd.DataFrame) -> dict[str, int]:
    vc = df["zone"].value_counts() if not df.empty else pd.Series(dtype=int)
    return {z: int(vc.get(z, 0)) for z in ZONES}


def pattern_counts(df: pd.DataFrame) -> dict[str, int]:
    vc = df["pattern"].value_counts() if not df.empty else pd.Series(dtype=int)
    return {p: int(vc.get(p, 0)) for p in PATTERNS}


def cards_by_zone(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {z: {} for z in ZONES}
    if df.empty:
        return out
    grp = df.assign(m=df["gpu_model"].fillna("(không rõ)")).groupby(["zone", "m"])["cards"].sum()
    for (z, m), n in grp.items():
        out[str(z)][str(m)] = int(n)
    return {z: dict(sorted(v.items(), key=lambda kv: (-kv[1], kv[0]))) for z, v in out.items()}


def zone_owner_matrix(b: Bundle, df: pd.DataFrame, with_unmapped: bool = True) -> dict[str, Any]:
    """Vùng × đầu mối (server map được, qua gpu_core.zone_owner_matrix) + cột '_unmapped' cho IP VTNet-only
    (bỏ cột này khi phạm vi là 1 đầu mối — server chưa map không thuộc ai)."""
    mapped = df[df["mapped"]] if not df.empty else df
    owners: list[str] = sorted(str(o) for o in mapped["owner"].dropna().unique()) if not mapped.empty else []
    rows: dict[str, dict[str, int]] = {z: dict.fromkeys(owners, 0) for z in ZONES}
    if not mapped.empty:
        mtx = g.zone_owner_matrix(b.stats[b.stats["ip"].isin(mapped["ip"])], b.inventory)
        for z in ZONES:
            for o in owners:
                rows[z][o] = int(mtx.loc[z, o]) if (z in mtx.index and o in mtx.columns) else 0
    unmapped = df[~df["mapped"]] if not df.empty else df
    if with_unmapped:
        for z in ZONES:
            rows[z][UNMAPPED] = int((unmapped["zone"] == z).sum()) if not unmapped.empty else 0
    return {
        "owners": [*owners, UNMAPPED] if with_unmapped else owners,
        "rows": rows,
        "totals": zone_counts(df),
        "mapped_total": len(mapped),
    }


def _bucket(day: pd.Series, granularity: Granularity) -> pd.Series:
    if granularity == "week":  # tuần ISO, bắt đầu thứ Hai
        return day - pd.to_timedelta(day.dt.day_of_week, unit="D")
    if granularity == "month":
        return day.dt.to_period("M").dt.to_timestamp()
    return day


# ------------------------------------------------------------------ Tổng quan


def fleet_timeseries(
    b: Bundle, f: Filters, scope: Scope, granularity: Granularity = "day", weight: Weight = "server"
) -> dict[str, Any]:
    srv = filter_servers(apply_scope(b.servers, scope), f)
    out: dict[str, Any] = {"params": b.ctx.as_params(), "granularity": granularity, "weight": weight}
    if srv.empty:
        return {**out, "points": [], "avg": {"gpu": None, "mem": None}, "n_servers": 0}
    ips = list(srv["ip"])
    cards = dict(zip(srv["ip"], srv["cards"], strict=True))
    daily = g.fleet_daily(b.raw, b.ctx.start, b.ctx.end, ips=ips, weight=weight, gpu_count=cards)
    daily["bucket"] = _bucket(daily["day"], granularity)
    if granularity == "day":
        srv_per_bucket = daily.set_index("bucket")["n_servers"]
    else:  # số server có số liệu trong tuần/tháng (đếm IP khác nhau)
        raw = b.raw[b.raw["ip"].isin(set(ips))]
        srv_per_bucket = (
            raw.assign(bucket=_bucket(raw["ts"].dt.normalize(), granularity)).groupby("bucket")["ip"].nunique()
        )
    agg = daily.groupby("bucket").agg(gpu=("gpu", "mean"), mem=("mem", "mean"), n_days=("day", "nunique"))
    points = [
        {
            "date": d.date().isoformat(),
            "gpu": float(r.gpu),
            "mem": float(r.mem),
            "n_servers": int(srv_per_bucket.get(d, 0)),
            "n_days": int(r.n_days),
        }
        for d, r in agg.iterrows()
    ]
    # KPI 'TB toàn khoảng' = mean chuỗi NGÀY (PLAN §6) — khác Grand Total VTNet (trọng số theo mẫu)
    return {
        **out,
        "points": points,
        "avg": {"gpu": float(daily["gpu"].mean()), "mem": float(daily["mem"].mean())},
        "n_servers": len(ips),
    }


def fleet_summary(b: Bundle, f: Filters, scope: Scope) -> dict[str, Any]:
    srv = filter_servers(apply_scope(b.servers, scope), f)
    ts = fleet_timeseries(b, f, scope)
    cz = cards_by_zone(srv)
    return {
        "params": b.ctx.as_params(),
        "gpu_avg": ts["avg"]["gpu"],
        "mem_avg": ts["avg"]["mem"],
        "n_servers": len(srv),
        "n_mapped": int(srv["mapped"].sum()) if not srv.empty else 0,
        "n_unmapped": int((~srv["mapped"]).sum()) if not srv.empty else 0,
        "zones": zone_counts(srv),
        "patterns": pattern_counts(srv),
        "vtnet_low_load": int(srv["vtnet_low_load"].sum()) if not srv.empty else 0,
        "thin_data": int(srv["thin_data"].sum()) if not srv.empty else 0,
        "cards_by_zone": cz,
        "cards_total": {z: sum(v.values()) for z, v in cz.items()},
        "matrix": zone_owner_matrix(b, srv, with_unmapped=scope.kind != "owner"),
    }


# ------------------------------------------------------------------ Cảnh báo


def alerts(
    b: Bundle,
    f: Filters,
    scope: Scope,
    zones: tuple[str, ...] = (),
    patterns: tuple[str, ...] = (),
    vtnet_flag: bool = False,
    only_mapped: bool = False,
    sort: str = "zone,gpu_avg",
    page: int = 1,
    page_size: int = 50,
    notes: dict[str, Any] | None = None,
    hide_exempt: bool = False,
) -> dict[str, Any]:
    """`notes`: IP → NoteFlags (note_service.flags, đọc riêng mỗi request — không vào cache). Miễn trừ KHÔNG đổi vùng:
    chỉ gắn `exempt_until` / `notes_count` và cho phép ẩn (`hide_exempt`)."""
    notes = notes or {}
    exempt_ips = {ip for ip, fl in notes.items() if fl.exempt_until is not None}
    srv = filter_servers(apply_scope(b.servers, scope), f)
    out: dict[str, Any] = {
        "params": b.ctx.as_params(),
        "matrix": zone_owner_matrix(b, srv, with_unmapped=scope.kind != "owner"),
        "pattern_counts": pattern_counts(srv),
        "cards_by_zone": cards_by_zone(srv),
    }
    items = srv
    if not items.empty:
        if zones:
            items = items[items["zone"].isin(zones)]
        if patterns:
            items = items[items["pattern"].isin(patterns)]
        if vtnet_flag:
            items = items[items["vtnet_low_load"]]
        if only_mapped:
            items = items[items["mapped"]]
    n_exempt = int(items["ip"].isin(exempt_ips).sum()) if not items.empty else 0
    if hide_exempt and not items.empty:
        items = items[~items["ip"].isin(exempt_ips)]
    items = sort_frame(items, sort)
    page_rows = items.iloc[(page - 1) * page_size : page * page_size]
    summary = {
        "zones": zone_counts(items),
        "patterns": pattern_counts(items),
        "cards": int(items["cards"].sum()) if not items.empty else 0,
        "vtnet_low_load": int(items["vtnet_low_load"].sum()) if not items.empty else 0,
        "thin_data": int(items["thin_data"].sum()) if not items.empty else 0,
        "exempt": n_exempt,
    }
    rows = records(page_rows, ITEM_FIELDS)
    for r in rows:
        fl = notes.get(r["ip"])
        r["notes_count"] = fl.count if fl else 0
        r["exempt_until"] = fl.exempt_until if fl else None
    return {
        **out,
        "summary": summary,
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "items": jsonable(rows),
    }


# ------------------------------------------------------------------ Danh mục server & chi tiết

CATALOG_FIELDS = [
    "row_type", "data_status", "inventory_ip", "ip", "ip_linked", "pair_confirmed", "stt", "excel_row", "owner",
    "inventory_gpu_spec", "gpu_type", "gpu_count", "gpu_model", "gpu_count_mismatch", "model", "service",
    "input_load", "managed_by", "cluster", "zone", "pattern", "gpu_avg", "mem_avg", "days", "coverage",
    "vtnet_low_load", "reclaimed",
]  # fmt: skip


def catalog(b: Bundle, f: Filters, scope: Scope, sort: str | None = None) -> dict[str, Any]:
    """Thống kê hiện hành ⟕ chỉ số tải khoảng đang chọn + nhóm 'VTNet có – thống kê thiếu' ở cuối (PLAN §8.4)."""
    inv = b.inventory.copy()
    measured = b.servers.set_index("ip") if not b.servers.empty else pd.DataFrame()
    stat_cols = ["gpu_type", "gpu_count", "gpu_model", "gpu_count_mismatch", "zone", "pattern", "gpu_avg", "mem_avg",
                 "days", "coverage", "vtnet_low_load"]  # fmt: skip
    for c in stat_cols:
        inv[c] = inv["ip"].map(measured[c]) if c in measured else None
    has = inv["ip"].isin(measured.index) if not measured.empty else pd.Series(False, index=inv.index)
    rec = inv["ip"].isin(b.reclaimed_ips) | inv["inventory_ip"].isin(b.reclaimed_ips)
    inv["reclaimed"] = rec
    inv["data_status"] = ["has_data" if h else ("reclaimed" if r else "no_data") for h, r in zip(has, rec, strict=True)]
    inv["mapped"] = True
    inv["row_type"] = "inventory"
    linked_vt = set(b.links["vtnet_ip"])
    conf = dict(zip(b.links["vtnet_ip"], b.links["pair_confirmed"].astype(bool), strict=True))
    inv["ip_linked"] = inv["ip"].isin(linked_vt) & (inv["ip"] != inv["inventory_ip"])
    inv["pair_confirmed"] = [conf.get(ip) if lk else None for ip, lk in zip(inv["ip"], inv["ip_linked"], strict=True)]
    inv["gpu_count_mismatch"] = inv["gpu_count_mismatch"].map(lambda v: bool(v) if py(v) is not None else False)
    # chưa có số liệu VTNet → số card / model theo file thống kê
    inv["gpu_count"] = pd.Series(
        [py(v) if py(v) is not None else py(i) for v, i in zip(inv["gpu_count"], inv["inv_gpu_count"], strict=True)],
        index=inv.index,
        dtype=object,
    )
    inv["gpu_model"] = [py(v) or py(i) for v, i in zip(inv["gpu_model"], inv["inv_gpu_model"], strict=True)]

    vt_only = b.servers[~b.servers["mapped"]].copy() if not b.servers.empty else pd.DataFrame(columns=CATALOG_FIELDS)
    if not vt_only.empty:
        vt_only["row_type"] = "vtnet_only"
        vt_only["data_status"] = "vtnet_only"
    inv = filter_servers(apply_scope(inv, scope), f)
    vt_only = filter_servers(apply_scope(vt_only, scope), f) if not vt_only.empty else vt_only
    if sort:
        inv = sort_frame(inv, sort)
        vt_only = sort_frame(vt_only, sort)
    elif not vt_only.empty:
        vt_only = sort_frame(vt_only, "ip")
    counts = {
        "inventory_rows": len(inv),
        "has_data": int((inv["data_status"] == "has_data").sum()),
        "reclaimed": int((inv["data_status"] == "reclaimed").sum()),
        "no_data": int((inv["data_status"] == "no_data").sum()),
        "vtnet_only": len(vt_only),
        "linked": int(inv["ip_linked"].sum()),
        "gpu_count_mismatch": int(inv["gpu_count_mismatch"].sum()),
    }
    rows = records(inv, CATALOG_FIELDS) + records(vt_only, CATALOG_FIELDS)
    return {"params": b.ctx.as_params(), "counts": counts, "items": rows}


INVENTORY_DETAIL = [
    "inventory_ip", "excel_row", "stt", "server_class", "config", "cpu", "ram", "disk", "hba", "inventory_gpu_spec",
    "inv_gpu_count", "inv_gpu_model", "serial", "owner", "model", "input_load", "service", "managed_by", "cluster",
]  # fmt: skip


def _find(b: Bundle, ip: str) -> tuple[str | None, pd.Series | None, pd.Series | None]:
    """Trả (IP VTNet, dòng server có số liệu, dòng thống kê). ip có thể là IP VTNet hoặc IP trong thống kê."""
    srv = b.servers
    inv = b.inventory
    s_row = None
    if not srv.empty:
        hit = srv[(srv["ip"] == ip) | (srv["inventory_ip"] == ip)]
        s_row = hit.iloc[0] if len(hit) else None
    i_hit = inv[(inv["ip"] == ip) | (inv["inventory_ip"] == ip)]
    i_row = i_hit.iloc[0] if len(i_hit) else None
    vt_ip = str(s_row["ip"]) if s_row is not None else (str(i_row["ip"]) if i_row is not None else None)
    return vt_ip, s_row, i_row


def server_detail(b: Bundle, ip: str, scope: Scope) -> dict[str, Any]:
    vt_ip, s_row, i_row = _find(b, ip)
    reclaim = b.reclaimed[b.reclaimed["ip"].isin({ip, vt_ip, py(i_row["inventory_ip"]) if i_row is not None else ip})]
    if s_row is None and i_row is None and reclaim.empty:
        raise ServiceError(404, f"Không có server {ip} trong thống kê hiện hành, số liệu VTNet hay danh sách thu hồi.")
    owner = py(i_row["owner"]) if i_row is not None else None
    if scope.kind == "owner" and owner != scope.owner_key:
        raise ServiceError(404, f"Không có server {ip}.")
    link = b.links[b.links["vtnet_ip"] == vt_ip] if vt_ip else b.links.iloc[0:0]
    if s_row is not None:
        status = "has_data" if s_row["mapped"] else "vtnet_only"
    else:
        status = "reclaimed" if not reclaim.empty else "no_data"
    return {
        "params": b.ctx.as_params(),
        "ip": vt_ip or ip,
        "inventory_ip": py(i_row["inventory_ip"]) if i_row is not None else None,
        "data_status": status,
        "inventory": {c: py(i_row.get(c)) for c in INVENTORY_DETAIL} if i_row is not None else None,
        "link": jsonable(link.iloc[0].to_dict()) if len(link) else None,
        "reclaim": jsonable(reclaim.iloc[0].to_dict()) if not reclaim.empty else None,
        "stats": {c: py(s_row.get(c)) for c in ITEM_FIELDS} if s_row is not None else None,
    }


def server_timeseries(b: Bundle, ip: str, scope: Scope, granularity: Granularity = "day") -> dict[str, Any]:
    detail = server_detail(b, ip, scope)  # 404 / phạm vi
    vt_ip = detail["ip"]
    raw = b.raw[b.raw["ip"] == vt_ip]
    out: dict[str, Any] = {"params": b.ctx.as_params(), "ip": vt_ip, "granularity": granularity}
    if raw.empty:
        return {**out, "points": []}
    daily = g.to_daily(raw)
    daily = daily.assign(bucket=_bucket(daily["ts"].dt.normalize(), granularity))
    agg = daily.groupby("bucket").agg(gpu=("gpu", "mean"), mem=("mem", "mean"), n_days=("ts", "nunique"))
    t = b.ctx.threshold
    points = [
        {
            "date": d.date().isoformat(),
            "gpu": float(r.gpu),
            "mem": float(r.mem),
            "zone": g.classify_zone(float(r.gpu), float(r.mem), t),
            "vtnet_low_load": g.vtnet_low_load(float(r.gpu), float(r.mem), b.ctx.params.vtnet_low_load_t),
            "n_days": int(r.n_days),
        }
        for d, r in agg.iterrows()
    ]
    return {**out, "points": points}


# ------------------------------------------------------------------ meta (bộ lọc, kỳ, cài đặt)


def meta(s: Session, scope: Scope) -> dict[str, Any]:
    lo, hi = util_repo.data_range(s)
    periods = [
        {
            "batch_id": x.id,
            "label": x.period_label,
            "start": x.period_start,
            "end": x.period_end,
            "file_name": x.file_name,
            "committed_at": x.committed_at,
        }
        for x in batch_repo.committed_batches(s, "vtnet_util")
    ]
    models = {_gpu_spec_parts(t)[1] for t in util_repo.distinct_gpu_types(s)} | set(
        inventory_repo.distinct_values(s, "gpu_model")
    )
    inv_batch = batch_repo.latest_committed(s, "inventory")
    out: dict[str, Any] = jsonable(
        {
            "gpu_core": g.__version__,
            "data_range": {"start": lo, "end": hi},
            "default_range": None if lo is None or hi is None else dict(zip(("start", "end"), default_range(lo, hi))),
            "periods": periods,
            "inventory": None
            if inv_batch is None
            else {"batch_id": inv_batch.id, "file_name": inv_batch.file_name, "committed_at": inv_batch.committed_at},
            # đầu mối phạm vi 'own' chỉ thấy chính mình trong bộ lọc
            "owners": [scope.owner_key] if scope.kind == "owner" else inventory_repo.distinct_values(s, "owner"),
            "gpu_models": sorted(m for m in models if m),
            "clusters": inventory_repo.distinct_values(s, "cluster"),
            "managed_by": inventory_repo.distinct_values(s, "managed_by"),
            "settings": settings_repo.all_values(s),
        }
    )
    return out
