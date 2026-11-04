"""Test luồng nhập dữ liệu G1-M1 (PLAN §5) trên fixture tổng hợp — kết quả biết trước, SQLite tạm mỗi test."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any

import openpyxl
from conftest import FIX, app_client, make_synthetic
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, text, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.migrate import downgrade, is_migrated, upgrade
from app.db.models import AppSetting, ImportBatch
from app.db.seed import seed
from app.services.import_service import effective_samples

T10 = FIX / "synthetic_t10.xlsx"


def up(client: TestClient, path: Path, name: str | None = None) -> Any:
    with path.open("rb") as f:
        return client.post("/api/v1/imports", files={"file": (name or path.name, f, "application/octet-stream")})


def staged(client: TestClient, path: Path) -> dict[str, Any]:
    r = up(client, path)
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    assert body["status"] == "staged"
    return body


def commit(client: TestClient, batch_id: int) -> dict[str, Any]:
    r = client.post(f"/api/v1/imports/{batch_id}/commit", json={"acknowledge": True})
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def effective(engine: Engine) -> Any:
    with Session(engine) as s:
        return effective_samples(s, "2026-09-01", "2026-12-31")


def edited_t10(tmp_path: Path, ip: str, day: int, gpu: float) -> Path:
    """Bản sao file T10 tổng hợp, sửa đúng 1 giá trị gpu."""
    wb = openpyxl.load_workbook(T10)
    ws = wb["server_raw"]
    for row in ws.iter_rows(min_row=2):
        if row[0].value == ip and row[4].value == dt.datetime(2026, 10, day):
            row[1].value = gpu
    out = tmp_path / "t10_edited.xlsx"
    wb.save(out)
    return out


# ------------------------------------------------------------------ VTNet


def test_upload_t10_staged_then_commit(client: TestClient, engine: Engine, settings: Settings) -> None:
    b = staged(client, T10)
    assert (b["kind"], b["schema_version"], b["kind_label"]) == ("vtnet_util", "t10", "File tải VTNet")
    assert (b["period_start"], b["period_end"], b["period_label"]) == ("2026-10-01", "2026-10-05", "2026-10")
    sm, v = b["summary"], b["validation"]
    assert (sm["rows"], sm["n_ips"], sm["days"], sm["granularity"], sm["reclaimed"]) == (30, 6, 5, "day", 1)
    assert sm["gpu_models"]["A30"] == {"servers": 3, "cards": 6} and sm["gpu_models"]["H200"]["cards"] == 8
    assert (sm["prev_batch_id"], sm["overlap_samples"], sm["replaced"]) == (None, 0, 0)
    assert v["overview"]["ok"] is True and "pivot_value" in v["ignored_sheets"]
    sha = hashlib.sha256(T10.read_bytes()).hexdigest()
    assert (settings.upload_path / f"{sha}.xlsx").read_bytes() == T10.read_bytes()  # file gốc được giữ
    assert effective(engine).empty  # staged chưa ảnh hưởng số liệu

    c = commit(client, b["id"])
    assert c["status"] == "committed" and c["committed_by"] == "admin"
    eff = effective(engine)
    assert len(eff) == 30 and set(eff["batch_id"]) == {b["id"]}
    with engine.connect() as conn:
        rc = conn.execute(text("SELECT ip, first_seen FROM reclaim_current")).all()
        assert [(r[0], str(r[1])) for r in rc] == [("192.0.2.50", "2026-10-01")]
        assert conn.execute(text("SELECT count(*) FROM vtnet_overview")).scalar() == 6


def test_upload_t7_schema(client: TestClient) -> None:
    b = staged(client, FIX / "synthetic_t7.xlsx")
    assert b["schema_version"] == "t7" and b["summary"]["rows"] == 30 and b["summary"]["reclaimed"] is None
    assert b["validation"]["overview"]["ok"] is True


def test_duplicate_committed_file_is_409(client: TestClient) -> None:
    b = staged(client, T10)
    commit(client, b["id"])
    r = up(client, T10, "ten-khac.xlsx")  # cùng nội dung, khác tên → vẫn là trùng (sha256)
    assert r.status_code == 409 and f"lô #{b['id']}" in r.json()["detail"]


def test_two_staged_same_file_second_commit_409(client: TestClient) -> None:
    a, b = staged(client, T10), staged(client, T10)
    commit(client, a["id"])
    r = client.post(f"/api/v1/imports/{b['id']}/commit", json={"acknowledge": True})
    assert r.status_code == 409 and f"lô #{a['id']}" in r.json()["detail"]


def test_reimport_one_changed_value_then_rollback_restores(client: TestClient, engine: Engine, tmp_path: Path) -> None:
    first = staged(client, T10)
    commit(client, first["id"])
    second = staged(client, edited_t10(tmp_path, "192.0.2.1", 1, 81))
    sm = second["summary"]
    assert (sm["prev_batch_id"], sm["overlap_samples"], sm["replaced"]) == (first["id"], 30, 1)
    assert sm["overlap_days"] == [f"2026-10-0{d}" for d in range(1, 6)]
    assert (sm["new_ips"], sm["gone_ips"]) == ([], [])

    def gpu_at(ip: str, day: int) -> float:
        eff = effective(engine)
        row = eff[(eff["ip"] == ip) & (eff["ts"] == dt.datetime(2026, 10, day))]
        assert len(row) == 1
        return float(row["gpu"].iloc[0])

    assert gpu_at("192.0.2.1", 1) == 80  # staged chưa thay
    commit(client, second["id"])
    assert gpu_at("192.0.2.1", 1) == 81 and len(effective(engine)) == 30  # lô mới nhất thắng, không đếm trùng
    r = client.post(f"/api/v1/imports/{second['id']}/rollback")
    assert r.status_code == 200 and r.json()["status"] == "rolled_back"
    assert gpu_at("192.0.2.1", 1) == 80  # giá trị cũ "sống lại"
    third = staged(client, edited_t10(tmp_path, "192.0.2.1", 1, 81))  # nhập lại file đã hoàn tác: được phép
    commit(client, third["id"])
    assert gpu_at("192.0.2.1", 1) == 81


def test_new_and_gone_ips(client: TestClient, tmp_path: Path) -> None:
    commit(client, staged(client, T10)["id"])
    series = {k: v for k, v in make_synthetic.SERIES.items() if k != "192.0.2.6"}
    series["192.0.2.7"] = ("1×NVIDIA L4", [30] * 5, [30] * 5)
    p = tmp_path / "t11.xlsx"
    make_synthetic.make_t10(p, series=series, days=[dt.datetime(2026, 11, d) for d in range(1, 6)])
    sm = staged(client, p)["summary"]
    assert (sm["new_ips"], sm["gone_ips"], sm["overlap_samples"]) == (["192.0.2.7"], ["192.0.2.6"], 0)


def test_hourly_file_imported_with_warning(client: TestClient, engine: Engine) -> None:
    b = staged(client, FIX / "synthetic_t10_hourly.xlsx")
    assert b["summary"]["granularity"] == "hour" and b["summary"]["rows"] == 60 and b["summary"]["days"] == 5
    assert any("GIỜ" in w for w in b["validation"]["warnings"])
    commit(client, b["id"])
    assert len(effective(engine)) == 60  # lưu nguyên mẫu giờ; gom ngày khi tính (gpu_core.to_daily)


def test_other_units_dropped_with_warning(client: TestClient) -> None:
    b = staged(client, FIX / "synthetic_t10_units.xlsx")
    assert b["summary"]["rows"] == 31 and b["summary"]["n_ips"] == 7
    assert any("đơn vị khác VTT" in w for w in b["validation"]["warnings"])


# ------------------------------------------------------------------ thống kê (inventory)


def test_inventory_snapshots(client: TestClient, engine: Engine) -> None:
    a = staged(client, FIX / "synthetic_inventory.xlsx")
    assert (a["kind"], a["schema_version"]) == ("inventory", "inventory_v1")
    assert a["summary"]["rows"] == 6 and a["summary"]["by_owner"] == {"dungha7": 3, "kientt6": 3}
    assert a["summary"]["linked_ips"] == 0
    commit(client, a["id"])
    with engine.connect() as conn:
        row = conn.execute(text("SELECT owner, gpu_count, gpu_model FROM inventory_current WHERE ip='192.0.2.2'")).one()
        assert tuple(row) == ("dungha7", 2, "A30")  # NBSP đã bỏ
        assert conn.execute(text("SELECT gpu_count FROM inventory_current WHERE ip='192.0.2.9'")).scalar() is None

    b = staged(client, FIX / "synthetic_inventory_badip.xlsx")  # Q13: IP lỗi bỏ trước → không bị coi là trùng
    assert b["summary"]["rows"] == 6 and (b["summary"]["added_ips"], b["summary"]["removed_ips"]) == ([], [])
    assert [x["excel_row"] for x in b["validation"]["invalid_ip_rows"]] == [8, 9]
    commit(client, b["id"])
    with engine.connect() as conn:
        assert set(conn.execute(text("SELECT DISTINCT batch_id FROM inventory_current")).scalars()) == {b["id"]}


def test_inventory_duplicate_ip_is_blocked(client: TestClient) -> None:
    r = up(client, FIX / "synthetic_inventory_dup.xlsx")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "IP trùng" in detail and "192.0.2.3 (dòng Excel 4, 8)" in detail
    batches = client.get("/api/v1/imports").json()["items"]
    assert batches[0]["status"] == "failed" and "IP trùng" in batches[0]["validation"]["error"]


def test_inventory_missing_owner_column_is_blocked(client: TestClient, tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Thống kê chi tiết"
    ws.append(["STT", "IP", "GPU"])
    ws.append([1, "192.0.2.1", "2*A30"])
    p = tmp_path / "no_owner.xlsx"
    wb.save(p)
    r = up(client, p)
    assert r.status_code == 422 and "Đầu mối sử dụng" in r.json()["detail"]


# ------------------------------------------------------------------ kiểm tra file


def test_rejects_non_xlsx_unknown_and_corrupt(client: TestClient, tmp_path: Path) -> None:
    assert up(client, T10, "data.csv").status_code == 422
    bad = tmp_path / "hong.xlsx"
    bad.write_bytes(b"khong phai excel")
    r = up(client, bad)
    assert r.status_code == 422 and "Không đọc được" in r.json()["detail"]
    wb = openpyxl.Workbook()
    wb.active.title = "Foo"  # type: ignore[union-attr]
    other = tmp_path / "khac.xlsx"
    wb.save(other)
    r = up(client, other)
    assert r.status_code == 422 and "Không nhận diện" in r.json()["detail"] and "Foo" in r.json()["detail"]


def test_upload_size_limit_413(client: TestClient, engine: Engine) -> None:
    with Session(engine) as s, s.begin():
        s.execute(update(AppSetting).where(AppSetting.key == "max_upload_mb").values(value=0.001))
    r = up(client, T10)
    assert r.status_code == 413 and "MB" in r.json()["detail"]


# ------------------------------------------------------------------ trạng thái lô


def test_state_transitions(client: TestClient, engine: Engine) -> None:
    b = staged(client, T10)
    i = b["id"]
    assert client.post(f"/api/v1/imports/{i}/rollback").status_code == 409  # chưa committed
    r = client.post(f"/api/v1/imports/{i}/discard")
    assert r.status_code == 200 and r.json()["status"] == "discarded"
    with engine.connect() as conn:  # lô bị hủy không để lại mẫu
        assert conn.execute(text("SELECT count(*) FROM util_sample")).scalar() == 0
    assert client.post(f"/api/v1/imports/{i}/commit", json={"acknowledge": True}).status_code == 409
    assert client.get("/api/v1/imports/999").status_code == 404
    c = staged(client, T10)
    commit(client, c["id"])
    r = client.post(f"/api/v1/imports/{c['id']}/commit", json={"acknowledge": True})
    assert r.status_code == 409 and "đã nhập" in r.json()["detail"]
    assert client.post(f"/api/v1/imports/{c['id']}/discard").status_code == 409
    items = client.get("/api/v1/imports").json()["items"]
    assert [x["status"] for x in items] == ["committed", "discarded"]


def test_download_original_file(client: TestClient) -> None:
    b = staged(client, T10)
    r = client.get(f"/api/v1/imports/{b['id']}/file")
    assert r.status_code == 200 and r.content == T10.read_bytes()
    assert "synthetic_t10.xlsx" in r.headers["content-disposition"]


def test_stale_staged_discarded_on_startup(client: TestClient, engine: Engine, settings: Settings) -> None:
    b = staged(client, T10)
    with Session(engine) as s, s.begin():
        old = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(hours=25)
        s.execute(update(ImportBatch).where(ImportBatch.id == b["id"]).values(uploaded_at=old))
    with app_client(settings) as c2:  # khởi động lại app
        assert c2.get(f"/api/v1/imports/{b['id']}").json()["status"] == "discarded"


# ------------------------------------------------------------------ migration & seed


def test_seed_is_idempotent(engine: Engine) -> None:
    assert seed(engine) == {"settings_added": 0, "links_added": 0, "links_skipped": 9}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ip_link")).scalar() == 9
        assert conn.execute(text("SELECT count(*) FROM app_setting")).scalar() == 6
        assert conn.execute(text("SELECT count(*) FROM ip_link WHERE pair_confirmed")).scalar() == 0
        row = conn.execute(text("SELECT vtnet_ip, created_by FROM ip_link WHERE inventory_ip='10.207.188.1'")).one()
        assert tuple(row) == ("10.205.36.51", "seed")


def test_downgrade_base_and_upgrade_again(engine: Engine) -> None:
    downgrade(engine)
    assert not is_migrated(engine)
    insp = inspect(engine)
    assert set(insp.get_table_names()) | set(insp.get_view_names()) == {"alembic_version"}
    upgrade(engine)
    assert is_migrated(engine)
