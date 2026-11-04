"""Hiệu năng (PLAN §1.4, §9): API phân tích ≤ 1 s cho 12 tháng × ~100 server, trên CSDL có 3 năm × 120 server.
Kho mẫu hiệu lực được đọc sẵn 1 lần / phiên bản dữ liệu (khi khởi động, sau xác nhận/hoàn tác lô).
Dữ liệu tổng hợp (IP 198.18.x.x — dải benchmark), ghi thẳng vào CSDL (bỏ qua bước đọc xlsx). Đánh dấu `slow`."""

from __future__ import annotations

import datetime as dt
import statistics
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert
from sqlalchemy.orm import Session

from app.db.models import ImportBatch, InventoryItem, UtilSample
from app.services.analytics_service import warm_up

N_SERVERS, DAYS = 120, 3 * 365 + 1
START = dt.datetime(2023, 11, 1)
LIMIT_S = 1.0


@pytest.fixture
def big(client: TestClient, engine: Engine) -> TestClient:
    rng = np.random.default_rng(7)
    now = dt.datetime(2026, 11, 3)
    ips = [f"198.18.{i // 200}.{i % 200 + 1}" for i in range(N_SERVERS)]
    base = rng.uniform(0, 100, size=(N_SERVERS, 2))
    with Session(engine) as s, s.begin():
        vt = ImportBatch(kind="vtnet_util", file_name="perf.xlsx", file_sha256="0" * 64, file_path="perf.xlsx",
                         status="committed", uploaded_by="test", uploaded_at=now, committed_by="test",
                         committed_at=now, period_start=START.date(),
                         period_end=(START + dt.timedelta(days=DAYS - 1)).date())  # fmt: skip
        inv = ImportBatch(kind="inventory", file_name="inv.xlsx", file_sha256="1" * 64, file_path="inv.xlsx",
                          status="committed", uploaded_by="test", uploaded_at=now, committed_by="test",
                          committed_at=now)  # fmt: skip
        s.add_all([vt, inv])
        s.flush()
        rows = []
        for i, ip in enumerate(ips):
            noise = rng.normal(0, 10, size=(DAYS, 2))
            vals = np.clip(base[i] + noise, 0, 100)
            for d in range(DAYS):
                rows.append({"batch_id": vt.id, "ip": ip, "ts": START + dt.timedelta(days=d), "gpu": float(vals[d, 0]),
                             "mem": float(vals[d, 1]), "gpu_type": "4×NVIDIA L40S", "don_vi": "VTT"})  # fmt: skip
        s.execute(insert(UtilSample), rows)
        owners = ["dungha7", "kientt6"]
        s.execute(
            insert(InventoryItem),
            [{"batch_id": inv.id, "ip": ip, "excel_row": i + 2, "owner": owners[i % 2], "gpu_spec": "4*L40S",
              "gpu_count": 4, "gpu_model": "L40S", "service": f"svc-{i}", "managed_by": "cụm k8s", "cluster": "1",
              "extra": {}} for i, ip in enumerate(ips[:100])],
        )  # fmt: skip
    return client


@pytest.mark.slow
def test_analytics_12_months_under_1s(big: TestClient) -> None:
    params = {"start": "2025-11-01", "end": "2026-10-31", "threshold": 40}
    cache = big.app.state.analytics_cache  # type: ignore[attr-defined]
    cases = [
        ("/alerts", {}),
        ("/fleet/timeseries", {}),
        ("/fleet/timeseries", {"granularity": "month", "weight": "gpu"}),
        ("/fleet/summary", {}),
        ("/servers", {}),
        ("/servers/198.18.0.1/timeseries", {}),
    ]
    t0 = time.perf_counter()
    warm_up(big.app.state.engine, cache)  # type: ignore[attr-defined]  # như lúc khởi động / sau xác nhận lô
    load_s = time.perf_counter() - t0
    assert cache.store_loads == 1
    timings: dict[str, float] = {}
    for path, extra in cases:
        runs = []
        for _ in range(3):  # trung vị 3 lần đo khi CHƯA có kết quả tính sẵn cho khoảng này — bớt nhiễu máy
            cache.clear()  # xóa kết quả tính (bundle); giữ kho mẫu hiệu lực đã đọc sẵn
            t0 = time.perf_counter()
            r = big.get(f"/api/v1{path}", params={**params, **extra})
            runs.append(time.perf_counter() - t0)
            assert r.status_code == 200, r.text
        timings[f"{path} {extra}"] = statistics.median(runs)
    print(f"Đọc sẵn 3 năm × {N_SERVERS} server: {load_s:.2f}s (1 lần / phiên bản dữ liệu, chạy nền)")
    print("Thời gian (trung vị, chưa tính sẵn):", {k: round(v, 3) for k, v in timings.items()})
    assert cache.store_loads == 1  # không đọc lại CSDL khi dữ liệu không đổi
    a = big.get("/api/v1/alerts", params=params).json()
    assert a["total"] == N_SERVERS and a["params"]["days_in_range"] == 365
    slow = {k: round(v, 3) for k, v in timings.items() if v > LIMIT_S}
    assert not slow, f"vượt {LIMIT_S}s: {slow}"
    t0 = time.perf_counter()
    big.get("/api/v1/alerts", params={**params, "zones": "danger"})
    assert time.perf_counter() - t0 < 0.3  # có cache: chỉ lọc/sắp xếp trên bộ đã tính
