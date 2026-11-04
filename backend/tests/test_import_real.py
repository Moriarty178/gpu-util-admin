"""Nhập dữ liệu THẬT qua API (G1-M1). Số đối chiếu lấy từ CONTEXT §3 (VTNet tự tính / đếm thủ công), tự skip khi thiếu."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from realdata import INV7, INV10, T7, T8, T9, T10, has_sheet, needs


def stage(client: TestClient, path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        r = client.post("/api/v1/imports", files={"file": (path.name, f, "application/octet-stream")})
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


@needs(T10)
def test_real_t10_import(client: TestClient) -> None:
    b = stage(client, T10)
    sm, v = b["summary"], b["validation"]
    assert (b["schema_version"], sm["rows"], sm["n_ips"], sm["days"]) == ("t10", 2930, 92, 32)
    assert (b["period_start"], b["period_end"], b["period_label"]) == ("2026-10-01", "2026-11-01", "2026-10")
    assert v["overview"]["ok"] is True and v["overview"]["max_abs_diff_gpu"] < 1e-9
    assert client.post(f"/api/v1/imports/{b['id']}/commit", json={"acknowledge": True}).status_code == 200


@needs(T10)
def test_real_t10_reclaimed(client: TestClient) -> None:
    if not has_sheet(T10, "DS đã thu"):
        pytest.skip(f"{T10.name} không có sheet 'DS đã thu' (file gốc VTNet T10 có 30 server đã thu hồi)")
    assert stage(client, T10)["summary"]["reclaimed"] == 30


@needs(T7)
def test_real_t7_import(client: TestClient) -> None:
    b = stage(client, T7)
    assert b["schema_version"] in ("t7", "t10")  # bản T7 gốc (t7) hoặc bản xuất lại theo định dạng T10
    assert (b["summary"]["rows"], b["summary"]["n_ips"]) == (2627, 88)
    assert b["validation"]["overview"]["ok"] is True


@needs(INV10)
def test_real_inventory_t10_import(client: TestClient) -> None:
    b = stage(client, INV10)
    assert b["summary"]["rows"] == 137 and b["summary"]["by_owner"] == {"dungha7": 57, "kientt6": 80}
    assert b["summary"]["linked_ips"] == 9  # 10.207.188.1–9 có liên kết seed


@needs(INV7)
def test_real_inventory_t7_import_drops_invalid_ip(client: TestClient) -> None:
    """Q13: dòng IP sai định dạng (vd '10.29.95.16/17') bị bỏ + cảnh báo, không làm chặn file vì 'trùng IP'."""
    b = stage(client, INV7)
    bad = b["validation"]["invalid_ip_rows"]
    assert bad and all("/" in x["ip"] for x in bad)
    assert b["summary"]["rows"] == b["summary"]["n_ips"]


@pytest.mark.parametrize("path", [T8, T9], ids=["T8", "T9"])
def test_real_t8_t9_import_matches_vtnet_overview(client: TestClient, path: Path) -> None:
    """Golden độc lập: TB tự tính từ server_raw khớp sheet VTT_KPI_overview của VTNet (tiêu đề 'IP OS', 'Average of gpu (%)')."""
    if not path.exists():
        pytest.skip(f"thiếu dữ liệu thật trong samples/: {path.name}")
    b = stage(client, path)
    assert b["schema_version"] == "t10" and b["validation"]["overview"]["ok"] is True
    assert b["validation"]["overview"]["n_common"] == b["summary"]["n_ips"]
