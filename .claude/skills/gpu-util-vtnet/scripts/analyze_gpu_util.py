#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gpu-util-vtnet v2 — đánh giá tải GPU VTNet -> ghi nhận xét vào file thống kê server TTCN-VTT.

  python analyze_gpu_util.py --vtnet <file VTNet> --inventory <Thong_ke...xlsx> --out <KetQua.xlsx>
         [--threshold 40] [--start 2026-10-01 --end 2026-10-31] [--history gpu_util_history.csv]

Nhận cả 2 schema VTNet: "t10" (VTT_KPI_overview header dòng 3 + server_raw + DS đã thu) và
"t7" (VTT_KPI_overview + VTT_GPU_Server_RAW). Toàn bộ logic nằm trong gpu_core/ (cùng thư mục) —
đây là bản sao của backend/gpu_core trong project gpu-util-admin (đồng bộ bằng scripts/sync_skill.sh).
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings("ignore", category=UserWarning)

import pandas as pd  # noqa: E402

import gpu_core as g  # noqa: E402
from gpu_core.export import write_assessed_inventory  # noqa: E402


def run(vtnet, inventory, out, threshold=g.DEFAULT_THRESHOLD, start=None, end=None, history=None,
        ip_links=None):
    wbv = g.read_vtnet_workbook(vtnet)
    s = pd.Timestamp(start) if start else wbv.raw["ts"].min()
    e = pd.Timestamp(end) if end else wbv.raw["ts"].max()
    label = wbv.dominant_month if not (start or end) else f"{s:%Y-%m-%d}_{e:%Y-%m-%d}"
    stats = g.server_stats(wbv.raw, s, e, threshold)
    links = g.load_ip_links(ip_links) if ip_links else None
    inv_raw = g.read_inventory(inventory)
    inv = g.apply_ip_links(inv_raw, links)          # cột ip = IP phía VTNet

    movement = None
    if history:
        cur = stats[["ip", "zone", "gpu_avg", "mem_avg"]].assign(period=label)
        hist = pd.read_csv(history) if os.path.exists(history) else pd.DataFrame(columns=cur.columns)
        prev = sorted(p for p in hist["period"].astype(str).unique() if p < label)
        if prev:
            movement = (prev[-1], g.compare_periods(hist[hist["period"].astype(str) == prev[-1]], cur))
        pd.concat([hist[hist["period"].astype(str) != label], cur], ignore_index=True).to_csv(history, index=False)

    res = write_assessed_inventory(inventory, out, stats, inv_raw, threshold, s, e,
                                   reclaimed=wbv.reclaimed, movement=movement, ip_links=links)
    matched = stats[stats["ip"].isin(set(inv["ip"]))]
    return dict(schema=wbv.schema, period=(s.date(), e.date()), label=label, matched=res["matched"],
                linked=int(inv["ip_linked"].sum()),
                vtnet_only=sorted(set(stats["ip"]) - set(inv["ip"])),
                inv_only=sorted(set(inv["ip"]) - set(stats["ip"])),
                zones=matched["zone"].value_counts().to_dict(),
                vtnet_low_load=int(stats["vtnet_low_load"].sum()),
                warnings=wbv.warnings + inv_raw.attrs.get("warnings", []), movement=movement)


def main():
    ap = argparse.ArgumentParser(description="Đánh giá tải GPU VTNet (gpu-util-vtnet v2)")
    ap.add_argument("--vtnet", required=True)
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=float, default=g.DEFAULT_THRESHOLD)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--history")
    ap.add_argument("--ip-links", help="CSV inventory_ip,vtnet_ip,pair_confirmed,reason")
    a = ap.parse_args()
    r = run(a.vtnet, a.inventory, a.out, a.threshold, a.start, a.end, a.history, a.ip_links)
    print(f"Schema: {r['schema']} | Kỳ: {r['period'][0]} → {r['period'][1]} ({r['label']}) | Ngưỡng: {a.threshold:g}%")
    print(f"Map được: {r['matched']} (qua liên kết IP: {r['linked']}) | VTNet-only: {len(r['vtnet_only'])} | "
          f"Inventory-only: {len(r['inv_only'])}")
    print("Vùng (server map được):", {g.ZONE_LABEL_VI[k]: v for k, v in r["zones"].items()})
    print("Dưới ngưỡng THẤP TẢI VTNet:", r["vtnet_low_load"])
    if r["warnings"]:
        print("Cảnh báo dữ liệu:", *r["warnings"], sep="\n  - ")
    if r["movement"]:
        cmp = r["movement"][1]
        print(f"So với {r['movement'][0]}: xấu đi {int((cmp.movement == 'worsened').sum())} | "
              f"cải thiện {int((cmp.movement == 'improved').sum())}")
    print("Đã ghi:", a.out)


if __name__ == "__main__":
    main()
