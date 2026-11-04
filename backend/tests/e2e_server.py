"""Server cho E2E Playwright (G2-M4): CSDL tạm mới mỗi lần (dữ liệu tổng hợp 2 kỳ như test_g2m3) + admin, phục vụ
frontend/dist tại 127.0.0.1:<cổng>. KHÔNG dùng data/ thật. Mật khẩu admin = TEST_PASSWORD của conftest (chỉ cho test).

Chạy (playwright.config.ts gọi): uv run --directory backend python tests/e2e_server.py 8765
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import uvicorn
from conftest import FIX, TEST_TODAY, add_user, app_client, make_settings, make_synthetic
from test_g2m3 import INV_ROWS, NOV, NOV_DAYS, upload

from app.config import ROOT_DIR
from app.db.migrate import upgrade
from app.db.seed import seed
from app.db.session import make_engine
from app.main import create_app
from app.services import import_checks


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    import_checks.today = lambda: TEST_TODAY  # type: ignore[assignment]  # dữ liệu tổng hợp tới 05/11/2026
    root = Path(tempfile.mkdtemp(prefix="gpu-e2e-"))
    st = make_settings(f"sqlite:///{(root / 'app.db').as_posix()}", root)
    st = st.model_copy(update={"frontend_dist": ROOT_DIR / "frontend" / "dist"})
    eng = make_engine(st.database_url)
    upgrade(eng)
    seed(eng)
    eng.dispose()
    make_synthetic.ensure()
    inv = root / "Thong_ke_tong_hop.xlsx"
    make_synthetic.make_inventory(inv, INV_ROWS)
    nov = root / "HSSD_GPU_tong_hop_T11.xlsx"
    make_synthetic.make_t10(nov, series=NOV, days=NOV_DAYS, reclaimed=False)
    add_user(st.database_url)  # admin, đã đổi mật khẩu
    with app_client(st) as c:
        upload(c, FIX / "synthetic_t10.xlsx")
        upload(c, inv)
        upload(c, nov)
    try:
        uvicorn.run(create_app(st), host="127.0.0.1", port=port, log_level="warning")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
