# -*- coding: utf-8 -*-
"""Các phép tính trên dữ liệu thô (ip, ts, gpu, mem) — định nghĩa CHUẨN cho cả API lẫn test.

Định nghĩa đã đối soát với file VTNet T10:
  * Trung bình 1 server trong khoảng [start, end]  = mean các mẫu ngày của server đó
        -> khớp sheet VTT_KPI_overview (sai số ~1e-14) khi khoảng = toàn bộ kỳ trong file.
  * Tải trung bình toàn bộ server theo ngày        = mean đơn giản qua các server CÓ số liệu ngày đó
        -> khớp sheet "HSSD theo ngay VTT" (sai số ~1e-14).
  * Grand Total của overview                         = mean tất cả các dòng raw (trọng số theo số mẫu).
"""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np
import pandas as pd

from .rules import (DEFAULT_PARAMS, DEFAULT_THRESHOLD, RuleParams, assessment_text, classify_pattern,
                    classify_zone, is_danger, vtnet_low_load)


def _clip(raw: pd.DataFrame, start=None, end=None, ips: Optional[Iterable[str]] = None) -> pd.DataFrame:
    df = raw
    if start is not None:
        df = df[df["ts"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["ts"] < pd.Timestamp(end) + pd.Timedelta(days=1)]   # end inclusive (cả ngày)
    if ips is not None:
        df = df[df["ip"].isin(set(ips))]
    return df


def to_daily(raw: pd.DataFrame) -> pd.DataFrame:
    """Gom mẫu theo GIỜ về theo NGÀY: mỗi (ip, ngày) = mean gpu/mem các mẫu trong ngày (PLAN §5.4).
    Dữ liệu đã theo ngày (giờ 00:00) -> trả nguyên, nên mọi số đối soát VTNet không đổi."""
    if raw.empty:
        return raw.copy()
    day = raw["ts"].dt.normalize()
    if bool((raw["ts"] == day).all()):
        return raw.copy()
    df = raw.assign(ts=day).sort_values(["ip", "ts"], kind="stable")
    spec = {"gpu": ("gpu", "mean"), "mem": ("mem", "mean")}
    for c in ("gpu_type", "don_vi"):
        if c in df.columns:
            spec[c] = (c, "last")                 # last bỏ qua giá trị rỗng
    return df.groupby(["ip", "ts"], sort=True).agg(**spec).reset_index()


def days_in_range(start, end) -> int:
    return int((pd.Timestamp(end).normalize() - pd.Timestamp(start).normalize()).days) + 1


def low_load_streak(daily: pd.DataFrame, threshold: float, metric: str = "both") -> int:
    """Số ngày LIÊN TIẾP gần nhất (tính từ ngày cuối có dữ liệu) rơi vào vùng Nguy hiểm (mặc định gpu<=T và mem<=T)."""
    n = 0
    for g, m in zip(daily["gpu"].to_numpy()[::-1], daily["mem"].to_numpy()[::-1]):
        if is_danger(g, m, threshold, metric):
            n += 1
        else:
            break
    return n


def server_stats(raw: pd.DataFrame, start=None, end=None, threshold: float = DEFAULT_THRESHOLD,
                 ips: Optional[Iterable[str]] = None, params: RuleParams = DEFAULT_PARAMS) -> pd.DataFrame:
    """1 dòng / server: avg, peak, p95, số ngày, coverage, streak, zone, pattern, cờ VTNet, nhận xét.
    Dữ liệu theo giờ được gom về ngày trước (to_daily) -> avg/đỉnh/p95/streak luôn tính trên mẫu NGÀY."""
    df = to_daily(_clip(raw, start, end, ips))
    if df.empty:
        return pd.DataFrame(columns=["ip"])
    s = pd.Timestamp(start) if start is not None else df["ts"].min()
    e = pd.Timestamp(end) if end is not None else df["ts"].max()
    span = days_in_range(s, e)
    # Tính gộp theo nhóm (cùng định nghĩa với bản lặp từng server cũ — đã đối chiếu, nhanh hơn ~10 lần)
    df = df.sort_values(["ip", "ts"], kind="stable").reset_index(drop=True)
    df["_low"] = is_danger(df["gpu"], df["mem"], threshold, params.zone_metric)   # ngày nguy hiểm theo chế độ đang áp
    df["_day"] = df["ts"].dt.normalize()
    gb = df.groupby("ip", sort=True)
    agg = gb.agg(gpu_avg=("gpu", "mean"), mem_avg=("mem", "mean"), gpu_peak=("gpu", "max"),
                 mem_peak=("mem", "max"), days=("_day", "nunique"), danger_days=("_low", "sum"),
                 first_ts=("ts", "min"), last_ts=("ts", "max"), _n=("ts", "size"))
    agg["gpu_p95"] = gb["gpu"].quantile(0.95)
    agg["gpu_type"] = gb["gpu_type"].last()                # mẫu mới nhất có gpu_type (bỏ qua rỗng)
    # streak thấp tải = số ngày nguy hiểm liên tiếp tính từ ngày cuối có dữ liệu
    pos = gb.cumcount()
    last_not_low = pos.where(~df["_low"]).groupby(df["ip"]).max()
    agg["low_streak"] = (agg["_n"] - (last_not_low.reindex(agg.index).fillna(-1) + 1)).astype(int)
    rows = []
    for ip, r in agg.iterrows():
        gpu, mem, peak = float(r["gpu_avg"]), float(r["mem_avg"]), float(r["gpu_peak"])
        days = int(r["days"])
        cov = days / span if span else np.nan
        rows.append(dict(
            ip=ip,
            gpu_type=r["gpu_type"] if isinstance(r["gpu_type"], str) else None,
            gpu_avg=gpu, mem_avg=mem, gpu_peak=peak,
            gpu_p95=float(r["gpu_p95"]), mem_peak=float(r["mem_peak"]),
            days=days, days_in_range=span, coverage=cov,
            low_streak=int(r["low_streak"]),
            danger_days=int(r["danger_days"]),
            zone=classify_zone(gpu, mem, threshold, params.zone_metric),
            pattern=classify_pattern(gpu, mem, threshold, peak, params),
            vtnet_low_load=vtnet_low_load(gpu, mem, params.vtnet_low_load_t),
            thin_data=bool(cov < params.thin_coverage),
            assessment=assessment_text(gpu, mem, threshold, peak, cov, days, span, params),
            first_ts=r["first_ts"], last_ts=r["last_ts"],
        ))
    return pd.DataFrame(rows)


def fleet_daily(raw: pd.DataFrame, start=None, end=None, ips: Optional[Iterable[str]] = None,
                weight: str = "server", gpu_count: Optional[dict] = None) -> pd.DataFrame:
    """Tải trung bình toàn bộ server theo ngày.
    weight="server" (mặc định, = định nghĩa VTNet) | "gpu" (trọng số theo số card, cần gpu_count{ip:n})."""
    df = to_daily(_clip(raw, start, end, ips))
    df["day"] = df["ts"].dt.normalize()
    if weight == "gpu":
        if not gpu_count:
            raise ValueError("weight='gpu' cần gpu_count {ip: số card}")
        df["w"] = df["ip"].map(gpu_count).fillna(1).astype(float)
        df["_gw"], df["_mw"] = df["gpu"] * df["w"], df["mem"] * df["w"]
        out = df.groupby("day").agg(_gw=("_gw", "sum"), _mw=("_mw", "sum"), n_gpus=("w", "sum"),
                                    n_servers=("ip", "nunique"))
        out["gpu"], out["mem"] = out["_gw"] / out["n_gpus"], out["_mw"] / out["n_gpus"]   # = np.average(..., weights)
        return out[["gpu", "mem", "n_servers", "n_gpus"]].reset_index()
    out = df.groupby("day").agg(gpu=("gpu", "mean"), mem=("mem", "mean"), n_servers=("ip", "nunique"))
    return out.reset_index()


def zone_owner_matrix(stats: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """Bảng 'Tổng thể': số server theo vùng × đầu mối (chỉ server map được với inventory)."""
    m = stats.merge(inventory[["ip", "owner"]].drop_duplicates("ip"), on="ip", how="inner")
    t = pd.crosstab(m["zone"], m["owner"], margins=True, margins_name="Tổng")
    return t.reindex(["safe", "warning", "danger", "Tổng"]).fillna(0).astype(int)


def validate_overview(raw: pd.DataFrame, overview: pd.DataFrame, tol: float = 0.01) -> dict:
    """Đối soát trung bình VTNet (overview) với trung bình tự tính từ raw trên toàn kỳ của file."""
    calc = raw.groupby("ip")[["gpu", "mem"]].mean()
    ov = overview.set_index("ip")[["gpu", "mem"]]
    common = calc.index.intersection(ov.index)
    d = (calc.loc[common] - ov.loc[common]).abs()
    bad = d[(d["gpu"] > tol) | (d["mem"] > tol)]
    return dict(
        n_overview=int(len(ov)), n_raw=int(len(calc)), n_common=int(len(common)),
        only_overview=sorted(set(ov.index) - set(calc.index)),
        only_raw=sorted(set(calc.index) - set(ov.index)),
        max_abs_diff_gpu=float(d["gpu"].max()) if len(d) else 0.0,
        max_abs_diff_mem=float(d["mem"].max()) if len(d) else 0.0,
        mismatched_ips=sorted(bad.index.tolist()),
        ok=bool(len(bad) == 0 and set(ov.index) == set(calc.index)),
    )


def validate_daily(raw: pd.DataFrame, daily: pd.DataFrame, tol: float = 0.01) -> dict:
    """Đối soát sheet VTNet 'HSSD theo ngay VTT' với TB toàn bộ server theo ngày tự tính (fleet_daily) trên raw.
    Ngày chỉ có trong raw (vd 01/11 tràn kỳ ở file T10) không tính là lệch; ngày chỉ có trong sheet là lệch."""
    calc = fleet_daily(raw).set_index("day")
    ref = daily.drop_duplicates("day", keep="last").set_index("day")
    common = calc.index.intersection(ref.index)
    d = (calc.loc[common, ["gpu", "mem"]] - ref.loc[common, ["gpu", "mem"]]).abs()
    n_ref = ref.loc[common, "n_servers"]
    n_bad = n_ref.notna() & (calc.loc[common, "n_servers"] != n_ref)
    bad = d[(d["gpu"] > tol) | (d["mem"] > tol) | n_bad]
    only_sheet = sorted(set(ref.index) - set(calc.index))
    fmt = lambda xs: [pd.Timestamp(x).date().isoformat() for x in xs]  # noqa: E731
    return dict(
        n_sheet=int(len(ref)), n_calc=int(len(calc)), n_common=int(len(common)),
        only_sheet=fmt(only_sheet), only_raw=fmt(sorted(set(calc.index) - set(ref.index))),
        max_abs_diff_gpu=float(d["gpu"].max()) if len(d) else 0.0,
        max_abs_diff_mem=float(d["mem"].max()) if len(d) else 0.0,
        mismatched_days=fmt(sorted(bad.index)),
        ok=bool(len(bad) == 0 and not only_sheet),
    )


def compare_periods(stats_prev: pd.DataFrame, stats_cur: pd.DataFrame) -> pd.DataFrame:
    """So sánh 2 kỳ: chuyển vùng & chênh lệch tải từng server."""
    a = stats_prev.set_index("ip")[["zone", "gpu_avg", "mem_avg"]]
    b = stats_cur.set_index("ip")[["zone", "gpu_avg", "mem_avg"]]
    j = a.add_suffix("_prev").join(b.add_suffix("_cur"), how="outer")  # = join(lsuffix, rsuffix) — pandas 4 bỏ tham số đó
    order = {"danger": 0, "warning": 1, "safe": 2}
    def move(r):
        if pd.isna(r["zone_prev"]):
            return "new"
        if pd.isna(r["zone_cur"]):
            return "gone"
        d = order[r["zone_cur"]] - order[r["zone_prev"]]
        return "improved" if d > 0 else ("worsened" if d < 0 else "same")
    j["movement"] = j.apply(move, axis=1)
    j["d_gpu"] = j["gpu_avg_cur"] - j["gpu_avg_prev"]
    j["d_mem"] = j["mem_avg_cur"] - j["mem_avg_prev"]
    return j.reset_index()
