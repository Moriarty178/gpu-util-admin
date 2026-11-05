"""G2-M1 — phát lại lô GĐ1 (SQLite) sang CSDL mới (ADR-9). Nguồn luôn SQLite; đích = SQLite và PostgreSQL (TEST_PG_URL).

Kiểm: (1) fixture tổng hợp đủ trạng thái lô (committed, rolled_back, nhập lại file đã hoàn tác, failed, discarded)
→ `verify()` khớp + API đích = API nguồn; (2) dữ liệu thật T10 → golden độc lập của test_analytics_real chạy trên đích.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import test_analytics_real as real
from conftest import FIX, DbFactory, add_user, app_client, make_settings
from fastapi.testclient import TestClient
from realdata import INV7, T10, needs
from sqlalchemy import Engine, delete, update
from sqlalchemy.orm import Session
from test_import_api import commit, edited_t10, effective, staged, up

from app.config import Settings
from app.db.migrate import upgrade
from app.db.models import AppSetting, ImportBatch, IpLink
from app.db.seed import seed
from app.db.session import make_engine
from app.tools.replay import NOTE_PREFIX, ReplayError, main, replay, verify


@pytest.fixture
def src_settings(tmp_path: Path) -> Settings:
    return make_settings(f"sqlite:///{(tmp_path / 'src' / 'app.db').as_posix()}", tmp_path / "src")


@pytest.fixture
def src_engine(src_settings: Settings) -> Iterator[Engine]:
    eng = make_engine(src_settings.database_url)
    upgrade(eng)
    seed(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def dst_settings(new_database: DbFactory, tmp_path: Path) -> Settings:
    (tmp_path / "dst").mkdir()
    return make_settings(new_database(tmp_path / "dst"), tmp_path / "dst")


@pytest.fixture
def dst_engine(dst_settings: Settings) -> Iterator[Engine]:
    eng = make_engine(dst_settings.database_url)
    yield eng
    eng.dispose()


def build_source(c: TestClient, src_engine: Engine, tmp_path: Path) -> None:
    """#1 T10 · #2 T10 sửa 1 giá trị → hoàn tác · #3 thống kê · #4 lỗi (IP trùng) · #5 T7 hủy · #6 nhập lại file #2."""
    commit(c, staged(c, FIX / "synthetic_t10.xlsx")["id"])
    edited = edited_t10(tmp_path, "192.0.2.1", 1, 81)
    b2 = commit(c, staged(c, edited)["id"])
    assert c.post(f"/api/v1/imports/{b2['id']}/rollback").status_code == 200
    commit(c, staged(c, FIX / "synthetic_inventory.xlsx")["id"])
    assert up(c, FIX / "synthetic_inventory_dup.xlsx").status_code == 422
    b5 = staged(c, FIX / "synthetic_t7.xlsx")
    assert c.post(f"/api/v1/imports/{b5['id']}/discard").status_code == 200
    commit(c, staged(c, edited)["id"])
    with Session(src_engine) as s, s.begin():  # admin đã sửa liên kết & cài đặt (đích phải giống, không lấy bản seed)
        s.execute(delete(IpLink).where(IpLink.inventory_ip == "10.207.188.1"))
        s.execute(update(IpLink).where(IpLink.inventory_ip == "10.207.188.2").values(pair_confirmed=True))
        s.execute(update(AppSetting).where(AppSetting.key == "bursty_peak").values(value=70))


def api_view(c: TestClient) -> dict[str, Any]:
    q = {"start": "2026-10-01", "end": "2026-10-05"}
    alerts = c.get("/api/v1/alerts", params={**q, "threshold": 40, "page_size": 500}).json()
    return {
        "fleet": c.get("/api/v1/fleet/timeseries", params=q).json()["points"],
        "summary": {k: v for k, v in c.get("/api/v1/fleet/summary", params=q).json().items() if k != "params"},
        "alerts": (alerts["items"], alerts["matrix"], alerts["pattern_counts"]),
        "servers": c.get("/api/v1/servers", params=q).json()["items"],
        "settings": c.get("/api/v1/meta").json()["settings"],
    }


def test_replay_all_batch_states(
    src_settings: Settings, src_engine: Engine, dst_settings: Settings, dst_engine: Engine, tmp_path: Path
) -> None:
    with app_client(src_settings) as c:
        build_source(c, src_engine, tmp_path)
        before = api_view(c)
    rep = replay(src_engine, dst_engine, source_uploads=src_settings.upload_path, target_settings=dst_settings)
    assert list(rep.id_map) == [1, 2, 3, 6] and rep.skipped == {"failed": 1, "discarded": 1}
    assert (rep.links, rep.settings, rep.users, rep.users_kept) == (8, 7, 1, [])  # tài khoản admin của nguồn
    assert rep.audit > 0  # nhật ký đăng nhập + nhập lô của nguồn
    assert verify(src_engine, dst_engine) == []

    with Session(dst_engine) as s:
        rows = {b.id: b for b in s.query(ImportBatch)}
        src_rows = {b.id: b for b in Session(src_engine).query(ImportBatch)}
        for a, b in rep.id_map.items():
            x, y = src_rows[a], rows[b]
            assert (y.status, y.file_sha256, y.committed_at, y.rolled_back_at, y.uploaded_at) == (
                x.status, x.file_sha256, x.committed_at, x.rolled_back_at, x.uploaded_at,
            )  # fmt: skip
            assert y.note is not None and y.note.startswith(f"{NOTE_PREFIX}{a}")
            assert (dst_settings.upload_path / f"{y.file_sha256}.xlsx").is_file()  # file gốc có ở phía đích
    eff = effective(dst_engine)
    row = eff[(eff["ip"] == "192.0.2.1") & (eff["ts"] == dt.datetime(2026, 10, 1))]
    assert float(row["gpu"].iloc[0]) == 81  # lô #6 (nhập lại file đã hoàn tác) thắng

    with app_client(dst_settings) as c:
        assert api_view(c) == before  # số trên API đích = nguồn

    with pytest.raises(ReplayError, match="đã có lô import"):
        replay(src_engine, dst_engine, source_uploads=src_settings.upload_path, target_settings=dst_settings)


def test_replay_detects_missing_or_changed_file(
    src_settings: Settings, src_engine: Engine, dst_settings: Settings, dst_engine: Engine, tmp_path: Path
) -> None:
    with app_client(src_settings) as c:
        b = commit(c, staged(c, FIX / "synthetic_t10.xlsx")["id"])
    stored = src_settings.upload_path / f"{b['file_sha256']}.xlsx"
    stored.write_bytes(stored.read_bytes() + b"x")
    with pytest.raises(ReplayError, match="không khớp sha256"):
        replay(src_engine, dst_engine, source_uploads=src_settings.upload_path, target_settings=dst_settings)
    stored.unlink()
    with Session(src_engine) as s, s.begin():
        s.execute(update(ImportBatch).values(file_path="khong/co.xlsx"))
    with pytest.raises(ReplayError, match="Thiếu file gốc"):
        replay(src_engine, dst_engine, source_uploads=src_settings.upload_path, target_settings=dst_settings)


def test_verify_reports_difference(src_settings: Settings, src_engine: Engine, dst_settings: Settings) -> None:
    dst = make_engine(dst_settings.database_url)
    upgrade(dst)
    seed(dst)
    with app_client(src_settings) as c:
        commit(c, staged(c, FIX / "synthetic_t10.xlsx")["id"])
    diffs = verify(src_engine, dst)
    dst.dispose()
    assert any(d.startswith("util_effective") for d in diffs) and any(d.startswith("số lô") for d in diffs)


def test_cli(
    src_settings: Settings, src_engine: Engine, dst_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    with app_client(src_settings) as c:
        commit(c, staged(c, FIX / "synthetic_t10.xlsx")["id"])
    add_user(src_settings.database_url, "kientt6", "owner", owner_key="kientt6")
    dst = make_engine(dst_settings.database_url)
    upgrade(dst)
    dst.dispose()
    add_user(dst_settings.database_url)  # admin đã tạo ở đích trước khi phát lại (create-admin)
    args = ["--source", src_settings.database_url, "--source-uploads", str(src_settings.upload_path),
            "--target", dst_settings.database_url, "--target-uploads", str(dst_settings.upload_path)]  # fmt: skip
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Đã phát lại 1 lô" in out and "nguồn = đích" in out
    assert "1 tài khoản" in out and "Giữ tài khoản đã có ở đích (không chép đè): admin" in out
    assert main([*args, "--verify-only"]) == 0
    assert main(args) == 1 and "đã có lô import" in capsys.readouterr().err  # không phát lại 2 lần
    assert main(["--source", src_settings.database_url, "--target", src_settings.database_url]) == 2
    assert main(["--source", "sqlite:///khong/co/app.db", "--target", dst_settings.database_url]) == 2
    assert "Không thấy CSDL nguồn" in capsys.readouterr().err


@needs(T10)
def test_replay_real_t10_keeps_golden(
    src_settings: Settings, src_engine: Engine, dst_settings: Settings, dst_engine: Engine
) -> None:
    """Golden độc lập (sheet VTNet 'HSSD theo ngay VTT', CONTEXT §7) chạy lại trên CSDL đích sau khi phát lại."""
    with app_client(src_settings) as c:
        for f in (T10, INV7):
            if f.exists():
                commit(c, staged(c, f)["id"])
    replay(src_engine, dst_engine, source_uploads=src_settings.upload_path, target_settings=dst_settings)
    assert verify(src_engine, dst_engine) == []
    with app_client(dst_settings) as c:
        real.test_fleet_matches_vtnet_daily_sheet(c)
        real.test_alerts_t40_period_all_vtnet_servers(c)
        real.test_alerts_example_item_and_cards(c)
