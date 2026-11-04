"""Test lõi gpu_core.
- Nhóm SYNTHETIC: luôn chạy (CI), dùng fixture IP giả trong tests/fixtures.
- Nhóm REAL: chạy khi có dữ liệu thật trong ../samples (bị .gitignore). Golden lấy từ nguồn ĐỘC LẬP:
  sheet VTNet tự tính (VTT_KPI_overview, 'HSSD theo ngay VTT') và kết quả skill v1 tháng 7 (15/44/18).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest

import gpu_core as g

warnings.filterwarnings("ignore", category=UserWarning)
FIX = Path(__file__).parent / "fixtures"
SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _sample(*names: str) -> Path:
    """File thật đầu tiên tồn tại trong samples/ (chấp nhận vài cách đặt tên)."""
    return next((SAMPLES / n for n in names if (SAMPLES / n).exists()), SAMPLES / names[0])


T10 = _sample("HSSD_GPU_Thang_10_2026_-_VTT.xlsx", "HSSD_GPU_Thang_10_2026_VTT.xlsx")
T7 = _sample("HSSD GPU Thang 7 2026 - VTT.xlsx", "HSSD_GPU_Daily_VTT_thang7.xlsx")
T8 = _sample("HSSD GPU Thang 8 2026 - VTT.xlsx")
T9 = _sample("HSSD GPU Thang 9 2026 - VTT.xlsx")
# Thống kê toàn bộ server VTT (1 file, người dùng chốt 03/11/2026): 134 dòng / 129 IP hợp lệ — khớp golden T7 (skill v1).
INV7 = _sample("Thong_ke_toan_bo_server_TTCN_VTT.xlsx", "Thong_ke_toan_bo_server_TTCN_VTT_thang7.xlsx")
# Bản 137 dòng dùng khi lập golden "thống kê T10" (CONTEXT §7) — chưa có → các test đó tự skip.
INV10 = _sample("Thong_ke_toan_bo_server_TTCN_VTT_ban137.xlsx")


def needs(*files: Path):
    """Skip khi THIẾU đúng file test cần (không skip/fail lẫn lộn khi chỉ có 1 phần samples/)."""
    missing = [f.name for f in files if not f.exists()]
    return pytest.mark.skipif(bool(missing), reason=f"thiếu dữ liệu thật trong samples/: {', '.join(missing)}")


def _has_sheet(path: Path, sheet: str) -> bool:
    """Kiểm tra sheet có trong file — độc lập với parser (để không che lỗi parser)."""
    import openpyxl

    names = openpyxl.load_workbook(path, read_only=True).sheetnames
    return any(g.norm_text(n).casefold() == sheet.casefold() for n in names)


# ------------------------------------------------------------------ rules


@pytest.mark.parametrize(
    "gpu,mem,zone",
    [
        (40, 40, "danger"),
        (40.01, 40, "warning"),
        (40, 40.01, "warning"),
        (40.01, 40.01, "safe"),
        (0, 0, "danger"),
        (100, 100, "safe"),
    ],
)
def test_zone_boundaries(gpu, mem, zone):
    assert g.classify_zone(gpu, mem, 40) == zone


def test_threshold_is_parameter():
    assert g.classify_zone(45, 45, 40) == "safe"
    assert g.classify_zone(45, 45, 50) == "danger"


def test_vtnet_low_load_is_strict():
    assert g.vtnet_low_load(9.99, 9.99)
    assert not g.vtnet_low_load(10, 5)
    assert not g.vtnet_low_load(5, 10)


@pytest.mark.parametrize(
    "gpu,mem,peak,pattern",
    [
        (5, 5, 20, "idle"),
        (5, 5, 70, "bursty_idle"),
        (5, 90, 10, "memory_bound"),
        (60, 20, 70, "compute_bound"),
        (85, 85, 100, "high_load"),
        (50, 60, 80, "healthy"),
    ],
)
def test_patterns(gpu, mem, peak, pattern):
    assert g.classify_pattern(gpu, mem, 40, peak) == pattern


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("4×NVIDIA L40S", (4, "L40S")),
        ("\xa02*A30", (2, "A30")),
        ("L40S", (None, "L40S")),
        ("8 x Quadro RTX 6000", (8, "RTX 6000")),
        ("8xRTX6000", (8, "RTX 6000")),
        ("3xNVIDIA  A30", (3, "A30")),
        ("2x NVIDIA L40", (2, "L40")),
        ("8×NVIDIA H200", (8, "H200")),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_gpu_spec(spec, expected):
    assert g.parse_gpu_spec(spec) == expected


# ------------------------------------------------------------------ synthetic


# fixture tổng hợp được sinh trong conftest.py (session, autouse)

EXPECTED_SYN = {
    "192.0.2.1": ("safe", "high_load"),
    "192.0.2.2": ("safe", "healthy"),
    "192.0.2.3": ("warning", "memory_bound"),
    "192.0.2.4": ("warning", "compute_bound"),
    "192.0.2.5": ("danger", "idle"),
    "192.0.2.6": ("danger", "bursty_idle"),
}


@pytest.mark.parametrize("fname,schema", [("synthetic_t10.xlsx", "t10"), ("synthetic_t7.xlsx", "t7")])
def test_synthetic_both_schemas(fname, schema):
    wb = g.read_vtnet_workbook(FIX / fname)
    assert wb.schema == schema
    assert wb.raw["ip"].nunique() == 6 and len(wb.raw) == 30
    assert g.validate_overview(wb.raw, wb.overview)["ok"]
    st = g.server_stats(wb.raw, "2026-10-01", "2026-10-05", 40).set_index("ip")
    for ip, (zone, pattern) in EXPECTED_SYN.items():
        assert (st.loc[ip, "zone"], st.loc[ip, "pattern"]) == (zone, pattern), ip
    assert st["vtnet_low_load"].sum() == 1 and st.loc["192.0.2.5", "vtnet_low_load"]
    assert st.loc["192.0.2.6", "gpu_peak"] == 100 and st.loc["192.0.2.6", "gpu_avg"] == 20


def test_synthetic_t10_extras():
    wb = g.read_vtnet_workbook(FIX / "synthetic_t10.xlsx")
    assert wb.overview_total is not None
    assert "pivot_value" in wb.ignored_sheets
    assert list(wb.reclaimed["ip"]) == ["192.0.2.50"]


def test_synthetic_inventory_and_matrix():
    inv = g.read_inventory(FIX / "synthetic_inventory.xlsx")
    assert inv.loc[inv.ip == "192.0.2.5", "owner"].item() == "kientt6"  # đã casefold
    assert inv.loc[inv.ip == "192.0.2.2", "gpu_count"].item() == 2  # NBSP đã bỏ
    wb = g.read_vtnet_workbook(FIX / "synthetic_t10.xlsx")
    st = g.server_stats(wb.raw, "2026-10-01", "2026-10-05", 40)
    mtx = g.zone_owner_matrix(st, inv)
    assert mtx.loc["Tổng", "Tổng"] == 5  # .6 không có inventory
    assert set(st.ip) - set(inv.ip) == {"192.0.2.6"}  # VTNet-only
    assert set(inv.ip) - set(st.ip) == {"192.0.2.9"}  # inventory-only


@pytest.mark.parametrize(
    "reader,fname",
    [(g.read_vtnet_workbook, "synthetic_t10.xlsx"), (g.read_inventory, "synthetic_inventory.xlsx")],
)
def test_readers_close_file(reader, fname, tmp_path):
    """Đọc xong phải đóng file ngay (không chờ gc): trên Windows file còn mở thì không xóa/ghi đè được."""
    import gc
    import shutil

    p = tmp_path / fname
    shutil.copy(FIX / fname, p)
    gc.disable()
    try:
        reader(p)
        p.unlink()  # PermissionError trên Windows nếu còn giữ handle
    finally:
        gc.enable()
    assert not p.exists()


def test_fleet_daily_definition():
    wb = g.read_vtnet_workbook(FIX / "synthetic_t10.xlsx")
    fd = g.fleet_daily(wb.raw, "2026-10-01", "2026-10-05")
    day5 = fd.iloc[-1]
    assert day5["n_servers"] == 6
    assert day5["gpu"] == pytest.approx((80 + 50 + 5 + 60 + 2 + 100) / 6)


def test_low_load_streak_and_range_clip():
    wb = g.read_vtnet_workbook(FIX / "synthetic_t10.xlsx")
    st = g.server_stats(wb.raw, "2026-10-01", "2026-10-04", 40).set_index("ip")
    assert st.loc["192.0.2.6", "gpu_peak"] == 0  # ngày 5 (100%) nằm ngoài khoảng
    assert st.loc["192.0.2.6", "low_streak"] == 4


# ------------------------------------------------------------------ real data (golden độc lập)


@needs(T10)
def test_real_t10_overview_matches_raw():
    wb = g.read_vtnet_workbook(T10)
    assert wb.schema == "t10" and wb.raw["ip"].nunique() == 92 and len(wb.raw) == 2930
    v = g.validate_overview(wb.raw, wb.overview)
    assert v["ok"] and v["max_abs_diff_gpu"] < 1e-9
    assert wb.overview_total == pytest.approx((wb.raw.gpu.mean(), wb.raw.mem.mean()))
    assert wb.dominant_month == "2026-10"  # dù file có ngày tràn 2026-11-01


@needs(T10)
def test_real_t10_reclaimed_sheet():
    if not _has_sheet(T10, "DS đã thu"):
        pytest.skip(f"{T10.name} không có sheet 'DS đã thu' (file gốc VTNet T10 có 30 server đã thu hồi)")
    wb = g.read_vtnet_workbook(T10)
    assert wb.reclaimed is not None and len(wb.reclaimed) == 30


@needs(T10)
def test_real_t10_fleet_matches_vtnet_daily_sheet():
    wb = g.read_vtnet_workbook(T10)
    fd = g.fleet_daily(wb.raw, "2026-10-01", "2026-10-31")
    ref = pd.read_excel(T10, sheet_name="HSSD theo ngay VTT", header=2).dropna(subset=["GPU Core %"])
    j = fd.merge(ref, left_on="day", right_on="Ngày")
    assert len(j) == 31
    assert (j["gpu"] - j["GPU Core %"]).abs().max() < 1e-9
    assert (j["mem"] - j["GPU Memory %"]).abs().max() < 1e-9
    assert (j["n_servers"] == j["Số server"]).all()


@needs(T7, INV7)
def test_real_t7_reproduces_skill_v1():
    wb = g.read_vtnet_workbook(T7)
    inv = g.read_inventory(INV7)
    st = g.server_stats(wb.raw, threshold=40)
    mtx = g.zone_owner_matrix(st, inv)
    assert mtx.loc["safe"].to_dict() == {"dungha7": 8, "kientt6": 7, "Tổng": 15}
    assert mtx.loc["warning"].to_dict() == {"dungha7": 21, "kientt6": 23, "Tổng": 44}
    assert mtx.loc["danger"].to_dict() == {"dungha7": 14, "kientt6": 4, "Tổng": 18}


@needs(T10, INV10)
def test_real_t10_golden_matrix():
    wb = g.read_vtnet_workbook(T10)
    inv = g.read_inventory(INV10)
    assert len(inv) == 137
    st = g.server_stats(wb.raw, "2026-10-01", "2026-11-01", 40)
    assert st["zone"].value_counts().to_dict() == {"warning": 46, "safe": 35, "danger": 11}
    mtx = g.zone_owner_matrix(st, inv)
    assert mtx.loc["safe"].to_dict() == {"dungha7": 18, "kientt6": 15, "Tổng": 33}
    assert mtx.loc["warning"].to_dict() == {"dungha7": 18, "kientt6": 20, "Tổng": 38}
    assert mtx.loc["danger"].to_dict() == {"dungha7": 5, "kientt6": 4, "Tổng": 9}
    assert len(set(st.ip) - set(inv.ip)) == 12 and len(set(inv.ip) - set(st.ip)) == 57


# ------------------------------------------------------------------ export (định dạng skill)


def test_export_assessed_inventory(tmp_path):
    import openpyxl

    from gpu_core.export import ASSESS_HEADER, SUMMARY_SHEET, write_assessed_inventory

    wb = g.read_vtnet_workbook(FIX / "synthetic_t10.xlsx")
    inv = g.read_inventory(FIX / "synthetic_inventory.xlsx")
    st = g.server_stats(wb.raw, "2026-10-01", "2026-10-05", 40)
    out = tmp_path / "kq.xlsx"
    res = write_assessed_inventory(
        FIX / "synthetic_inventory.xlsx", out, st, inv, 40, "2026-10-01", "2026-10-05", reclaimed=wb.reclaimed
    )
    assert res["matched"] == 5
    x = openpyxl.load_workbook(out)
    assert x.sheetnames[0] == SUMMARY_SHEET
    ws = x["Thống kê chi tiết"]
    assert ws.cell(1, 17).value == ASSESS_HEADER  # inventory 16 cột -> thêm ở cột 17
    zones = {ws.cell(r, 10).value: ws.cell(r, 18).value for r in range(2, ws.max_row + 1)}
    assert zones["192.0.2.5"] == "Nguy hiểm" and zones["192.0.2.9"] == "Chưa có dữ liệu VTNet"
    # IP liên kết: inventory .9 <-> VTNet .6 -> .6 được map
    out2 = tmp_path / "kq2.xlsx"
    res2 = write_assessed_inventory(
        FIX / "synthetic_inventory.xlsx",
        out2,
        st,
        inv,
        40,
        "2026-10-01",
        "2026-10-05",
        ip_links={"192.0.2.9": "192.0.2.6"},
    )
    assert res2["matched"] == 6


# ------------------------------------------------------------------ liên kết IP

SEED_LINKS = Path(__file__).resolve().parents[1] / "seeds" / "ip_links.csv"


def test_load_ip_links_seed():
    df = g.load_ip_links(SEED_LINKS)
    assert len(df) == 9 and not df["pair_confirmed"].any()
    assert df.iloc[0]["inventory_ip"] == "10.207.188.1" and df.iloc[0]["vtnet_ip"] == "10.205.36.51"


def test_load_ip_links_rejects_duplicates(tmp_path):
    p = tmp_path / "l.csv"
    p.write_text("inventory_ip,vtnet_ip\n192.0.2.9,192.0.2.6\n192.0.2.8,192.0.2.6\n", encoding="utf-8")
    with pytest.raises(ValueError):
        g.load_ip_links(p)


def test_apply_ip_links_and_conflict():
    inv = g.read_inventory(FIX / "synthetic_inventory.xlsx")
    eff = g.apply_ip_links(inv, {"192.0.2.9": "192.0.2.6"})
    row = eff[eff.inventory_ip == "192.0.2.9"].iloc[0]
    assert row["ip"] == "192.0.2.6" and row["ip_linked"]
    with pytest.raises(ValueError):  # trỏ vào IP đã có dòng thống kê khác
        g.apply_ip_links(inv, {"192.0.2.9": "192.0.2.1"})


@needs(T10, INV10)
def test_real_t10_golden_with_rtx6000_links():
    wb = g.read_vtnet_workbook(T10)
    inv = g.apply_ip_links(g.read_inventory(INV10), g.load_ip_links(SEED_LINKS))
    st = g.server_stats(wb.raw, "2026-10-01", "2026-11-01", 40)
    mtx = g.zone_owner_matrix(st, inv)
    assert mtx.loc["safe"].to_dict() == {"dungha7": 18, "kientt6": 16, "Tổng": 34}
    assert mtx.loc["warning"].to_dict() == {"dungha7": 18, "kientt6": 27, "Tổng": 45}
    assert mtx.loc["danger"].to_dict() == {"dungha7": 5, "kientt6": 5, "Tổng": 10}
    assert sorted(set(st.ip) - set(inv.ip)) == ["10.221.122.33", "10.221.155.36", "10.221.155.37"]
    inv_only = set(inv.loc[~inv.ip.isin(st.ip), "inventory_ip"])
    assert len(inv_only) == 48 and len(inv_only & set(wb.reclaimed.ip)) == 13


# ------------------------------------------------------------------ gpu_core 2.2 (Q13, Q15)


def test_don_vi_other_units_dropped():
    wb = g.read_vtnet_workbook(FIX / "synthetic_t10_units.xlsx")
    assert set(wb.raw["ip"]) == {f"192.0.2.{i}" for i in (1, 2, 3, 4, 5, 6, 10)}  # VAI/VIC bỏ, don_vi rỗng giữ
    assert len(wb.raw) == 31
    assert any("đơn vị khác VTT" in w and "3 dòng" in w for w in wb.warnings)


def test_hourly_is_aggregated_to_daily():
    wb = g.read_vtnet_workbook(FIX / "synthetic_t10_hourly.xlsx")
    assert len(wb.raw) == 2 * 5 * 4 + 4 * 5  # .1, .5 theo giờ; còn lại theo ngày
    assert any("GIỜ" in w for w in wb.warnings)
    daily = g.to_daily(wb.raw)
    assert len(daily) == 30 and (daily["ts"] == daily["ts"].dt.normalize()).all()
    st = g.server_stats(wb.raw, "2026-10-01", "2026-10-05", 40).set_index("ip")
    # Kết quả biết trước (= bản theo ngày): .1 gpu 80 (đỉnh ngày 80, không phải đỉnh giờ 90), 5/5 ngày
    assert st.loc["192.0.2.1", "gpu_avg"] == 80 and st.loc["192.0.2.1", "gpu_peak"] == 80
    assert st.loc["192.0.2.1", "days"] == 5 and st.loc["192.0.2.5", "danger_days"] == 5
    for ip, (zone, pattern) in EXPECTED_SYN.items():
        assert (st.loc[ip, "zone"], st.loc[ip, "pattern"]) == (zone, pattern), ip
    fd = g.fleet_daily(wb.raw, "2026-10-01", "2026-10-05")
    assert len(fd) == 5 and fd.iloc[0]["gpu"] == pytest.approx((80 + 50 + 5 + 60 + 2 + 0) / 6)


def test_to_daily_keeps_daily_data_unchanged():
    wb = g.read_vtnet_workbook(FIX / "synthetic_t10.xlsx")
    pd.testing.assert_frame_equal(g.to_daily(wb.raw), wb.raw)


def test_read_inventory_drops_invalid_ip_before_duplicate_check():
    inv = g.read_inventory(FIX / "synthetic_inventory_badip.xlsx")
    assert len(inv) == 6 and inv["ip"].is_unique
    assert inv.attrs["invalid_ip_rows"] == [
        {"excel_row": 8, "ip": "192.0.2.16/17"},
        {"excel_row": 9, "ip": "192.0.2.16/17"},
    ]
    assert "dòng Excel 8, 9" in inv.attrs["warnings"][0]
    g.apply_ip_links(inv, {"192.0.2.9": "192.0.2.6"})  # không còn báo trùng giả


# ------------------------------------------------------------------ gpu_core 2.3: RuleParams


def test_rule_params_default_is_unchanged():
    wb = g.read_vtnet_workbook(FIX / "synthetic_t10.xlsx")
    a = g.server_stats(wb.raw, "2026-10-01", "2026-10-05", 40)
    b = g.server_stats(wb.raw, "2026-10-01", "2026-10-05", 40, params=g.RuleParams())
    pd.testing.assert_frame_equal(a, b)


def test_rule_params_change_results():
    wb = g.read_vtnet_workbook(FIX / "synthetic_t10.xlsx")
    p = g.RuleParams(vtnet_low_load_t=25, bursty_peak=101, high_load=90, thin_coverage=1.01)
    st = g.server_stats(wb.raw, "2026-10-01", "2026-10-05", 40, params=p).set_index("ip")
    assert st.loc["192.0.2.6", "pattern"] == "idle"  # đỉnh 100 < 101 → không còn bursty
    assert st.loc["192.0.2.1", "pattern"] == "healthy"  # 80/85 < 90 → không còn high_load
    assert sorted(st.index[st["vtnet_low_load"]]) == ["192.0.2.5"]  # .6 gpu 20 ≥ 25? không: 20<25 nhưng mem 30 ≥ 25
    assert st["thin_data"].all() and "<25% cả 2" in st.loc["192.0.2.5", "assessment"]
    assert g.classify_pattern(5, 5, 40, 75, g.RuleParams(bursty_peak=80)) == "idle"


def test_compare_periods_movements():
    """Chuyển vùng giữa 2 kỳ: tốt hơn = improved, xấu hơn = worsened, chỉ có ở kỳ sau = new, chỉ ở kỳ trước = gone."""
    prev = pd.DataFrame({"ip": ["a", "b", "c", "e"], "zone": ["safe", "warning", "danger", "warning"],
                         "gpu_avg": [50.0, 30.0, 5.0, 20.0], "mem_avg": [60.0, 50.0, 5.0, 60.0]})  # fmt: skip
    cur = pd.DataFrame({"ip": ["a", "b", "d", "e"], "zone": ["danger", "safe", "warning", "warning"],
                        "gpu_avg": [10.0, 70.0, 20.0, 25.0], "mem_avg": [10.0, 80.0, 60.0, 65.0]})  # fmt: skip
    j = g.compare_periods(prev, cur).set_index("ip")
    assert j["movement"].to_dict() == {"a": "worsened", "b": "improved", "c": "gone", "d": "new", "e": "same"}
    assert j.loc["a", "d_gpu"] == -40 and j.loc["b", "d_mem"] == 30
    assert pd.isna(j.loc["c", "zone_cur"]) and pd.isna(j.loc["d", "zone_prev"])


def test_overview_header_variant_t8(tmp_path):
    """File VTNet T8/T9: sheet VTT_KPI_overview dùng tiêu đề 'IP OS', 'Average of gpu (%)', 'Average of mem (%)'."""
    import openpyxl

    p = tmp_path / "t8.xlsx"
    from conftest import make_synthetic

    make_synthetic.make_t10(p)
    wb = openpyxl.load_workbook(p)
    ws = wb["VTT_KPI_overview"]
    for col, h in enumerate(["IP OS", "Average of gpu (%)", "Average of mem (%)"], 1):
        ws.cell(3, col, h)
    wb.save(p)
    out = g.read_vtnet_workbook(p)
    assert out.overview is not None and len(out.overview) == 6
    assert g.validate_overview(out.raw, out.overview)["ok"]


# ---------------------------------------------------------------- 2.4: sheet 'HSSD theo ngay VTT' + cột chuẩn


def _raw(rows):
    return pd.DataFrame(rows, columns=["ip", "ts", "gpu", "mem"]).assign(ts=lambda d: pd.to_datetime(d["ts"]))


def test_validate_daily_synthetic():
    raw = _raw([("10.0.0.1", "2026-10-01", 10, 20), ("10.0.0.2", "2026-10-01", 30, 40),
                ("10.0.0.1", "2026-10-02", 50, 60), ("10.0.0.1", "2026-11-01", 1, 1)])  # fmt: skip
    # TB tính tay: 01/10 = (10+30)/2, (20+40)/2, 2 server; 02/10 = 50/60, 1 server; 01/11 chỉ có trong raw
    good = pd.DataFrame({"day": pd.to_datetime(["2026-10-01", "2026-10-02"]), "gpu": [20.0, 50.0],
                         "mem": [30.0, 60.0], "n_servers": [2, 1]})  # fmt: skip
    v = g.validate_daily(raw, good)
    assert v["ok"] and v["n_common"] == 2 and v["only_raw"] == ["2026-11-01"] and v["mismatched_days"] == []
    bad = good.copy()
    bad.loc[1, "gpu"] = 50.5  # lệch 0,5 điểm
    bad.loc[0, "n_servers"] = 3  # khác số server
    bad = pd.concat([bad, pd.DataFrame({"day": pd.to_datetime(["2026-10-03"]), "gpu": [1.0], "mem": [1.0],
                                        "n_servers": [1]})])  # fmt: skip
    v = g.validate_daily(raw, bad)
    assert not v["ok"] and v["mismatched_days"] == ["2026-10-01", "2026-10-02"] and v["only_sheet"] == ["2026-10-03"]
    assert v["max_abs_diff_gpu"] == pytest.approx(0.5)


def test_missing_standard_columns_and_daily_sheet(tmp_path):
    import openpyxl

    wb = openpyxl.load_workbook(FIX / "synthetic_t10.xlsx")
    ws = wb["server_raw"]
    ws.delete_cols([c.value for c in ws[1]].index("don_vi") + 1)
    dl = wb.create_sheet("HSSD theo ngay VTT")
    dl.append(["HSSD GPU THEO NGÀY - CỦA VTT"])
    dl.append([])
    dl.append(["Ngày", "GPU Core %", "GPU Memory %", "Số server"])
    dl.append([pd.Timestamp("2026-10-01").to_pydatetime(), 1.5, 2.5, 6])
    p = tmp_path / "x.xlsx"
    wb.save(p)
    w = g.read_vtnet_workbook(p)
    assert w.missing_columns == ["don_vi"] and w.sheet_names["daily"] == "HSSD theo ngay VTT"
    assert w.daily.to_dict("records") == [{"day": pd.Timestamp("2026-10-01"), "gpu": 1.5, "mem": 2.5, "n_servers": 6}]
    assert "HSSD theo ngay VTT" not in w.ignored_sheets
    assert g.read_vtnet_workbook(FIX / "synthetic_t10.xlsx").missing_columns == []


@pytest.mark.parametrize("path,n_days,only_raw", [(T8, 31, []), (T9, 30, []), (T10, 31, ["2026-11-01"])],
                         ids=["T8", "T9", "T10"])  # fmt: skip
def test_real_daily_sheet_matches(path, n_days, only_raw):
    """Golden độc lập = sheet VTNet 'HSSD theo ngay VTT' (T8, T9, T10): khớp từng ngày cả GPU, VRAM, số server."""
    if not _has_sheet(path, "HSSD theo ngay VTT"):
        pytest.skip(f"thiếu dữ liệu thật trong samples/: {path.name}")
    wb = g.read_vtnet_workbook(path)
    ref = pd.read_excel(path, sheet_name="HSSD theo ngay VTT", header=2).dropna(subset=["GPU Core %"])
    assert len(wb.daily) == len(ref) == n_days
    v = g.validate_daily(wb.raw, wb.daily)
    assert v["ok"] and v["n_common"] == n_days and v["only_raw"] == only_raw
    assert v["max_abs_diff_gpu"] < 1e-9 and v["max_abs_diff_mem"] < 1e-9
    assert wb.missing_columns == []
