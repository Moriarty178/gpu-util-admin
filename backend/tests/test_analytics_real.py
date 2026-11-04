"""Golden ĐỘC LẬP qua API (G1-M2, CONTEXT §7, PLAN §7–8): sheet VTNet tự tính, kết quả skill v1 tháng 7, số trong CONTEXT.
Mỗi nhóm dùng 1 CSDL tạm (module scope) đã nhập file thật qua API; tự skip theo đúng file/sheet thiếu trong samples/."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from conftest import DbFactory, app_client, make_settings
from fastapi.testclient import TestClient
from realdata import INV7, INV10, T7, T10, has_sheet, needs
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.migrate import upgrade
from app.db.models import IpLink
from app.db.seed import seed
from app.db.session import make_engine

PERIOD = {"start": "2026-10-01", "end": "2026-11-01"}  # 'Theo kỳ file' T10 (có ngày tràn 01/11)
OCT = {"start": "2026-10-01", "end": "2026-10-31"}


def _client(new_database: DbFactory, tmp: Path, files: list[Path], links: bool) -> Iterator[TestClient]:
    settings = make_settings(new_database(tmp), tmp)
    eng = make_engine(settings.database_url)
    upgrade(eng)
    seed(eng)
    if not links:
        with Session(eng) as s, s.begin():
            s.execute(delete(IpLink))
    with app_client(settings) as c:
        for f in files:
            if f.exists():
                with f.open("rb") as fh:
                    r = c.post("/api/v1/imports", files={"file": (f.name, fh, "application/octet-stream")})
                assert r.status_code == 201, r.text
                assert c.post(f"/api/v1/imports/{r.json()['id']}/commit", json={"acknowledge": True}).status_code == 200
        yield c
    eng.dispose()


@pytest.fixture(scope="module")
def t10(new_database: DbFactory, tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    if not T10.exists():
        pytest.skip(f"thiếu dữ liệu thật trong samples/: {T10.name}")
    yield from _client(new_database, tmp_path_factory.mktemp("t10"), [T10, INV10], links=True)


@pytest.fixture(scope="module")
def t10_nolinks(new_database: DbFactory, tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    yield from _client(new_database, tmp_path_factory.mktemp("t10n"), [T10, INV10], links=False)


@pytest.fixture(scope="module")
def t7_nolinks(new_database: DbFactory, tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    yield from _client(new_database, tmp_path_factory.mktemp("t7"), [T7, INV7], links=False)


def get(c: TestClient, path: str, **params: Any) -> Any:
    r = c.get(f"/api/v1{path}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def mapped_totals(matrix: dict[str, Any]) -> tuple[int, int, int]:
    def tot(z: str) -> int:
        return sum(n for o, n in matrix["rows"][z].items() if o != "_unmapped")

    return tot("safe"), tot("warning"), tot("danger")


def owner_row(matrix: dict[str, Any], owner: str) -> tuple[int, int, int]:
    return tuple(matrix["rows"][z][owner] for z in ("safe", "warning", "danger"))  # type: ignore[return-value]


# ------------------------------------------------------------------ chỉ cần file VTNet T10


@needs(T10)
def test_fleet_matches_vtnet_daily_sheet(t10: TestClient) -> None:
    """Biểu đồ toàn bộ 01/10–31/10 = sheet 'HSSD theo ngay VTT' (VTNet tự tính), 31 điểm, ≤ 1e-6."""
    ts = get(t10, "/fleet/timeseries", **OCT)
    ref = pd.read_excel(T10, sheet_name="HSSD theo ngay VTT", header=2).dropna(subset=["GPU Core %"])
    ref = ref.assign(date=pd.to_datetime(ref["Ngày"]).dt.strftime("%Y-%m-%d")).set_index("date")
    assert len(ts["points"]) == 31
    for p in ts["points"]:
        r = ref.loc[p["date"]]
        assert abs(p["gpu"] - r["GPU Core %"]) < 1e-6 and abs(p["mem"] - r["GPU Memory %"]) < 1e-6
        assert p["n_servers"] == r["Số server"]
    first = ts["points"][0]
    assert (round(first["gpu"], 3), round(first["mem"], 3), first["n_servers"]) == (34.761, 70.878, 91)
    oct_ref = ref[ref.index.str.startswith("2026-10")]
    assert get(t10, "/fleet/summary", **OCT)["gpu_avg"] == pytest.approx(oct_ref["GPU Core %"].mean(), abs=1e-9)


@needs(T10)
def test_alerts_t40_period_all_vtnet_servers(t10: TestClient) -> None:
    a = get(t10, "/alerts", threshold=40, page_size=500, **PERIOD)
    assert a["params"]["days_in_range"] == 32
    assert a["matrix"]["totals"] == {"safe": 35, "warning": 46, "danger": 11}
    assert a["pattern_counts"] == {
        "memory_bound": 46,
        "healthy": 18,
        "high_load": 17,
        "idle": 7,
        "bursty_idle": 4,
        "compute_bound": 0,
    }
    assert [i["ip"] for i in a["items"] if i["vtnet_low_load"]] == ["10.221.122.33"]
    thin = [(i["ip"], i["days"]) for i in a["items"] if i["thin_data"]]
    assert thin == [("10.254.135.34", 21)]
    assert get(t10, "/alerts")["matrix"]["totals"] == a["matrix"]["totals"]  # mặc định = 'Theo kỳ file' + T cài đặt


@needs(T10)
def test_alerts_example_item_and_cards(t10: TestClient) -> None:
    """Số trong ví dụ PLAN §7 (đã kiểm trên file VTNet): server 10.207.163.82 và card vùng Nguy hiểm (37)."""
    a = get(t10, "/alerts", threshold=40, zones="danger", **PERIOD)
    assert a["total"] == 11 and a["summary"]["cards"] == 37
    assert a["cards_by_zone"]["danger"] == {"A30": 14, "L40": 12, "RTX 6000": 8, "L4": 3}
    i = next(x for x in a["items"] if x["ip"] == "10.207.163.82")
    assert (round(i["gpu_avg"], 1), round(i["mem_avg"], 1), round(i["gpu_peak"], 1)) == (1.2, 23.9, 37.2)
    assert (i["days"], i["coverage"], i["low_streak"], i["danger_days"]) == (32, 1.0, 20, 20)
    assert (i["zone"], i["pattern"], i["gpu_count"], i["gpu_type"]) == ("danger", "idle", 1, "1×NVIDIA A30")


# ------------------------------------------------------------------ cần thêm file thống kê T10


@needs(T10, INV10)
def test_matrix_with_rtx6000_links(t10: TestClient) -> None:
    m = get(t10, "/alerts", threshold=40, **PERIOD)["matrix"]
    assert m["mapped_total"] == 89 and mapped_totals(m) == (34, 45, 10)
    assert owner_row(m, "dungha7") == (18, 18, 5) and owner_row(m, "kientt6") == (16, 27, 5)
    assert owner_row(m, "_unmapped") == (1, 1, 1)
    assert get(t10, "/alerts", owner="kientt6", **PERIOD)["total"] == 48  # phạm vi đầu mối (GĐ2) — 48 server
    m30 = get(t10, "/alerts", threshold=30, **OCT)["matrix"]
    assert mapped_totals(m30) == (40, 43, 6)


@needs(T10, INV10)
def test_example_item_inventory_fields(t10: TestClient) -> None:
    i = next(x for x in get(t10, "/alerts", zones="danger", **PERIOD)["items"] if x["ip"] == "10.207.163.82")
    assert (i["owner"], i["inventory_gpu_spec"], i["gpu_count_mismatch"], i["ip_linked"]) == (
        "kientt6",
        "3*A30",
        True,
        False,
    )


@needs(T10, INV10)
def test_catalog_t10(t10: TestClient) -> None:
    c = get(t10, "/servers", **PERIOD)["counts"]
    assert (c["inventory_rows"], c["has_data"], c["vtnet_only"], c["linked"]) == (137, 89, 3, 9)
    assert c["gpu_count_mismatch"] == 8
    if has_sheet(T10, "DS đã thu"):
        assert (c["reclaimed"], c["no_data"]) == (13, 35)
    else:
        assert c["reclaimed"] + c["no_data"] == 48  # thiếu sheet 'DS đã thu' → chưa tách được 13 / 35
    items = get(t10, "/servers", **PERIOD)["items"]
    assert [i["ip"] for i in items if i["row_type"] == "vtnet_only"] == [
        "10.221.122.33",
        "10.221.155.36",
        "10.221.155.37",
    ]


@needs(T10, INV10)
def test_matrix_without_links(t10_nolinks: TestClient) -> None:
    m = get(t10_nolinks, "/alerts", threshold=40, **PERIOD)["matrix"]
    assert m["mapped_total"] == 80 and mapped_totals(m) == (33, 38, 9)
    assert owner_row(m, "dungha7") == (18, 18, 5) and owner_row(m, "kientt6") == (15, 20, 4)
    assert owner_row(m, "_unmapped") == (2, 8, 2)
    assert mapped_totals(get(t10_nolinks, "/alerts", threshold=30, **OCT)["matrix"]) == (36, 38, 6)


# ------------------------------------------------------------------ tháng 7 (skill v1)


@needs(T7, INV7)
def test_t7_reproduces_skill_v1(t7_nolinks: TestClient) -> None:
    """Q14: golden T7 tính KHÔNG liên kết IP → kiểm ở CSDL chưa seed liên kết."""
    m = get(t7_nolinks, "/alerts", threshold=40)["matrix"]
    assert mapped_totals(m) == (15, 44, 18) and m["mapped_total"] == 77
    assert owner_row(m, "dungha7") == (8, 21, 14) and owner_row(m, "kientt6") == (7, 23, 4)


# ------------------------------------------------------------------ xuất Excel trên dữ liệu thật


def _formulas(wb_bytes_or_path: Any, sheet: str) -> dict[str, str]:
    import io

    import openpyxl

    src = io.BytesIO(wb_bytes_or_path) if isinstance(wb_bytes_or_path, bytes) else wb_bytes_or_path
    ws = openpyxl.load_workbook(src)[sheet]
    return {
        c.coordinate: c.value
        for row in ws.iter_rows()
        for c in row
        if isinstance(c.value, str) and c.value.startswith("=")
    }


@pytest.mark.parametrize("inventory", [INV10, INV7], ids=["thong_ke_T10", "thong_ke_T7"])
def test_real_export_keeps_gpu_qhdc_formulas(
    new_database: DbFactory, inventory: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    if not (T10.exists() and inventory.exists()):
        pytest.skip(
            f"thiếu dữ liệu thật trong samples/: {', '.join(f.name for f in (T10, inventory) if not f.exists())}"
        )
    if not has_sheet(inventory, "GPU QHDC"):
        pytest.skip(f"{inventory.name} không có sheet 'GPU QHDC'")
    for c in _client(new_database, tmp_path_factory.mktemp("exp"), [T10, inventory], links=True):
        r = c.get("/api/v1/alerts/export.xlsx", params=PERIOD)
        assert r.status_code == 200, r.text
        before, after = _formulas(inventory, "GPU QHDC"), _formulas(r.content, "GPU QHDC")
        assert after == before and len(before) > 0  # mọi công thức giữ nguyên (fullCalcOnLoad để Excel tự tính lại)
        if inventory == INV10:
            assert len(after) == 280  # CONTEXT §5
