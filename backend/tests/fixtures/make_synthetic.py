"""Sinh fixture TỔNG HỢP (IP giả 192.0.2.x – dải TEST-NET) cho cả 2 schema VTNet + inventory.
Dùng cho CI khi không có dữ liệu thật trong samples/. Chạy:  python tests/fixtures/make_synthetic.py

Thiết kế 6 server × 5 ngày (2026-10-01..05) với kết quả biết trước ở ngưỡng T=40:
  .1  gpu 80 / mem 85            -> safe     (high_load)
  .2  gpu 50 / mem 60            -> safe     (healthy)
  .3  gpu  5 / mem 90            -> warning  (memory_bound)
  .4  gpu 60 / mem 20            -> warning  (compute_bound)
  .5  gpu  2 / mem  3            -> danger   (idle)  + VTNet THẤP TẢI
  .6  gpu [0,0,0,0,100]/mem 30   -> danger   (bursty_idle, avg gpu 20, peak 100)

Biến thể (cho test import / gpu_core 2.2):
  synthetic_t10_hourly.xlsx : .1 và .5 theo GIỜ (4 mẫu/ngày) — trung bình ngày giữ đúng như bản theo ngày
  synthetic_t10_units.xlsx  : thêm 3 dòng đơn vị VAI (phải bị bỏ) + 1 dòng don_vi rỗng (giữ)
  synthetic_inventory_badip.xlsx : thêm 2 dòng IP '192.0.2.16/17' (sai định dạng -> bỏ, không tính là trùng)
  synthetic_inventory_dup.xlsx   : IP 192.0.2.3 xuất hiện 2 lần (phải bị chặn khi import)
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).parent
DAYS = [dt.datetime(2026, 10, d) for d in range(1, 6)]
SERIES = {
    "192.0.2.1": ("4×NVIDIA L40S", [80] * 5, [85] * 5),
    "192.0.2.2": ("2×NVIDIA A30", [50] * 5, [60] * 5),
    "192.0.2.3": ("2×NVIDIA L4", [5] * 5, [90] * 5),
    "192.0.2.4": ("3×NVIDIA A30", [60] * 5, [20] * 5),
    "192.0.2.5": ("1×NVIDIA A30", [2] * 5, [3] * 5),
    "192.0.2.6": ("8×NVIDIA H200", [0, 0, 0, 0, 100], [30] * 5),
}
INVENTORY = [  # ip, gpu_spec, owner, service
    ("192.0.2.1", "4x NVIDIA L40S", "dungha7", "LLM inference"),
    ("192.0.2.2", "\xa02*A30", "dungha7", "OCR"),
    ("192.0.2.3", "2*L4", "kientt6", "Embedding"),
    ("192.0.2.4", "3xNVIDIA  A30", "kientt6", "TTS"),
    ("192.0.2.5", "1*A30", "KienTT6", "Lab test"),  # owner viết hoa -> phải chuẩn hóa
    ("192.0.2.9", "L40S", "dungha7", "Chưa gắn monitor"),  # inventory-only
]  # 192.0.2.6 cố ý KHÔNG có trong inventory -> VTNet-only
INV_HEADER = [
    "STT",
    "Loại server",
    "Cấu hình",
    "CPU",
    "RAM",
    "Disk",
    "HBA",
    "GPU",
    "Serial",
    "IP",
    "Đầu mối sử dụng",
    "Model",
    "Đầu vào hệ thống (CCU, Request...)",
    "Dịch vụ/nghiệp vụ đang chạy",
    'Quản lý bằng?\n(="cụm k8s"  || "Server độc lập")',
    "Tên cụm, ký hiệu để phân biệt các cụm",
]
HOURS = [0, 6, 12, 18]


def _avg(v):
    return sum(v) / len(v)


def make_t10(path: Path, series=None, days=None, hourly_ips=(), extra_rows=(), reclaimed=True):
    """series: {ip: (gpu_type, [gpu theo ngày], [mem theo ngày])}. hourly_ips: IP ghi 4 mẫu/ngày
    (giá trị ±10 quanh giá trị ngày -> trung bình ngày không đổi). extra_rows: dòng raw thêm (host_ip, gpu, mem,
    gpu_type, date_hour, don_vi). Overview = trung bình theo ngày của series."""
    series = SERIES if series is None else series
    days = DAYS if days is None else days
    wb = Workbook()
    ov = wb.active
    ov.title = "VTT_KPI_overview"
    ov.append([None, None, None])
    ov.append([None, None, None])
    ov.append(["Row Labels", "Average of gpu_core (%)", "Average of gpu_mem (%)"])
    for ip, (_, g, m) in series.items():
        ov.append([ip, _avg(g), _avg(m)])
    allg = [x for _, g, _ in series.values() for x in g]
    allm = [x for _, _, m in series.values() for x in m]
    ov.append(["Grand Total", _avg(allg), _avg(allm)])
    raw = wb.create_sheet("server_raw")
    raw.append(["host_ip", "gpu", "mem", "gpu_type", "date_hour", "don_vi"])
    for ip, (t, g, m) in series.items():
        for d, gv, mv in zip(days, g, m):
            if ip in hourly_ips:
                for h, delta in zip(HOURS, [-10, 10, -10, 10]):
                    raw.append([ip, gv + delta if gv >= 10 else gv, mv, t, d + dt.timedelta(hours=h), "VTT"])
            else:
                raw.append([ip, gv, mv, t, d, "VTT"])
    for row in extra_rows:
        raw.append(list(row))
    if reclaimed:
        rc = wb.create_sheet("DS đã thu")
        rc.append(
            [
                "IP",
                "GPU TYPE",
                "Thụhưởngtàinguyên theo QHDC",
                "Owner Instance DCIM",
                "Service Manager (owner tài nguyên hiện tại)",
                "Trạng thái",
            ]
        )
        rc.append(["192.0.2.50", "4*L40s", "VTT", "locnm2", "FREE (thu hồi thấp tải)", "Đã thu hồi"])
    junk = wb.create_sheet("pivot_value")  # sheet phải bị bỏ qua
    junk.append(["Row Labels", "Average of gpu", "Average of mem", "Thấp tải"])
    wb.save(path)


def make_t7(path: Path):
    wb = Workbook()
    ov = wb.active
    ov.title = "VTT_KPI_overview"
    ov.append(["Địa chỉ IP Server", "Average of gpu_util", "Average of gpu_memory"])
    for ip, (_, g, m) in SERIES.items():
        ov.append([ip, _avg(g), _avg(m)])
    raw = wb.create_sheet("VTT_GPU_Server_RAW")
    raw.append(["date", "instance", "gpu_type", "gpu_util", "gpu_memory", "don_vi"])
    for ip, (t, g, m) in SERIES.items():
        for d, gv, mv in zip(DAYS, g, m):
            raw.append([d, ip, t, gv, mv, "VTT"])
    wb.save(path)


def make_inventory(path: Path, rows=None):
    """rows: [(ip, gpu_spec, owner, service)] — mặc định INVENTORY."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Thống kê chi tiết"
    ws.append(INV_HEADER)
    for i, (ip, spec, owner, svc) in enumerate(INVENTORY if rows is None else rows, 1):
        ws.append(
            [
                i,
                "GPU loại 1",
                None,
                64,
                256,
                "2 TB",
                None,
                spec,
                f"SN{i:04d}",
                ip,
                owner,
                "model-x",
                10,
                svc,
                "Server độc lập",
                "Server độc lập",
            ]
        )
    wb.save(path)


FILES = {
    "synthetic_t10.xlsx": lambda p: make_t10(p),
    "synthetic_t7.xlsx": make_t7,
    "synthetic_inventory.xlsx": lambda p: make_inventory(p),
    "synthetic_t10_hourly.xlsx": lambda p: make_t10(p, hourly_ips=("192.0.2.1", "192.0.2.5")),
    "synthetic_t10_units.xlsx": lambda p: make_t10(
        p,
        extra_rows=[
            ("192.0.2.7", 1, 1, "1×NVIDIA L4", DAYS[0], "VAI"),
            ("192.0.2.7", 1, 1, "1×NVIDIA L4", DAYS[1], "VAI"),
            ("192.0.2.8", 1, 1, "1×NVIDIA L4", DAYS[0], "VIC"),
            ("192.0.2.10", 50, 50, "1×NVIDIA L4", DAYS[0], None),
        ],
    ),
    "synthetic_inventory_badip.xlsx": lambda p: make_inventory(
        p, INVENTORY + [("192.0.2.16/17", "8xH200", "kientt6", "HA"), ("192.0.2.16/17", "8xH200", "dungha7", "HA")]
    ),
    "synthetic_inventory_dup.xlsx": lambda p: make_inventory(p, INVENTORY + [("192.0.2.3", "2*L4", "dungha7", "Dup")]),
}


def ensure(force: bool = False) -> list[str]:
    """Sinh các fixture còn thiếu (force=True: sinh lại tất cả)."""
    made = []
    for name, fn in FILES.items():
        p = HERE / name
        if force or not p.exists():
            fn(p)
            made.append(name)
    return made


if __name__ == "__main__":
    ensure(force=True)
    print("OK ->", sorted(p.name for p in HERE.glob("synthetic_*.xlsx")))
