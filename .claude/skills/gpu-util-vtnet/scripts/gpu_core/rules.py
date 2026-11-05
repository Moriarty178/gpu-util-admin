# -*- coding: utf-8 -*-
"""Luật phân vùng & nhận xét — NGUỒN CHÂN LÝ, port 1:1 từ skill gpu-util-vtnet.

Luật vùng (1 ngưỡng T, mặc định 40%, so sánh `<=`):
  gpu <= T  VÀ mem <= T  -> danger  ("Nguy hiểm"  - ứng viên thu hồi)
  đúng 1 trong 2 <= T    -> warning ("Cảnh báo"   - cần tối ưu)
  cả hai > T             -> safe    ("An toàn")

Chế độ "áp ngưỡng T cho 1 chỉ số" (`RuleParams.zone_metric`, người dùng chốt 05/11/2026) — CHỈ 2 vùng, bỏ qua chỉ số kia:
  zone_metric="gpu":  gpu <= T -> danger, còn lại -> safe     (không có "Cảnh báo")
  zone_metric="mem":  mem <= T -> danger, còn lại -> safe
  zone_metric="both" (mặc định) = luật 3 vùng ở trên, kết quả y như trước.
"Ngày nguy hiểm" / chuỗi ngày thấp tải đếm theo đúng chế độ đang áp (ngày rơi vào vùng Nguy hiểm).

Luật THẤP TẢI của VTNet (suy luận từ sheet pivot_value file T10, khớp 250/250 server):
  gpu < 10 VÀ mem < 10   -> VTNet gắn "THẤP TẢI" (so sánh `<` chặt)

Các hằng số phụ (ngưỡng VTNet, bursty, tải cao, dữ liệu mỏng) là tham số `RuleParams` (mặc định = hằng số dưới đây)
để app đọc từ cài đặt; gọi không truyền params -> kết quả y như trước.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

DEFAULT_THRESHOLD = 40.0
VTNET_LOW_LOAD_T = 10.0
BURSTY_PEAK = 70.0          # đỉnh util ngày >= 70% mà trung bình <= T  => bursty
HIGH_LOAD = 80.0            # cả 2 >= 80% => tải cao
THIN_COVERAGE = 0.8         # số ngày có dữ liệu / số ngày trong khoảng < 0.8 => dữ liệu mỏng
ZONE_METRICS = ("both", "gpu", "mem")   # chỉ số áp ngưỡng T
ZONE_METRIC_LABEL_VI = {"both": "cả compute và memory", "gpu": "compute", "mem": "memory"}


def check_zone_metric(metric: str) -> str:
    if metric not in ZONE_METRICS:
        raise ValueError(f"zone_metric phải là một trong {ZONE_METRICS}, nhận {metric!r}")
    return metric


@dataclass(frozen=True)
class RuleParams:
    vtnet_low_load_t: float = VTNET_LOW_LOAD_T
    bursty_peak: float = BURSTY_PEAK
    high_load: float = HIGH_LOAD
    thin_coverage: float = THIN_COVERAGE
    zone_metric: str = "both"

    def __post_init__(self) -> None:
        check_zone_metric(self.zone_metric)


DEFAULT_PARAMS = RuleParams()

ZONE_LABEL_VI = {"danger": "Nguy hiểm", "warning": "Cảnh báo", "safe": "An toàn"}
PATTERN_LABEL_VI = {
    "idle": "Idle thật",
    "bursty_idle": "Bursty (ngắt quãng)",
    "memory_bound": "Memory-bound (giữ VRAM, ít tính toán)",
    "compute_bound": "Compute-bound (dư VRAM)",
    "high_load": "Tải cao ổn định",
    "healthy": "Dùng hiệu quả",
}


def _isnum(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def is_danger(gpu, mem, threshold: float = DEFAULT_THRESHOLD, metric: str = "both"):
    """Điều kiện vùng Nguy hiểm — dùng được cho số lẫn pandas Series (đếm ngày nguy hiểm)."""
    if metric == "gpu":
        return gpu <= threshold
    if metric == "mem":
        return mem <= threshold
    check_zone_metric(metric)
    return (gpu <= threshold) & (mem <= threshold)


def classify_zone(gpu: float, mem: float, threshold: float = DEFAULT_THRESHOLD, metric: str = "both") -> str:
    if metric != "both":
        return "danger" if is_danger(gpu, mem, threshold, metric) else "safe"
    lg, lm = gpu <= threshold, mem <= threshold
    if lg and lm:
        return "danger"
    if lg != lm:
        return "warning"
    return "safe"


def zone_rule_text(threshold: float, metric: str = "both") -> str:
    """Mô tả luật vùng đang áp (in lên Excel, slide, giao diện)."""
    T = f"{threshold:g}%"
    if metric == "both":
        return f"util≤{T} & mem≤{T} = Nguy hiểm | đúng 1 chỉ số ≤{T} = Cảnh báo | cả 2 >{T} = An toàn"
    name = ZONE_METRIC_LABEL_VI[check_zone_metric(metric)]
    return f"chỉ xét {name}: {name}≤{T} = Nguy hiểm | {name}>{T} = An toàn (bỏ qua chỉ số còn lại, không có Cảnh báo)"


def classify_pattern(gpu: float, mem: float, threshold: float = DEFAULT_THRESHOLD,
                     peak_gpu: Optional[float] = None, params: RuleParams = DEFAULT_PARAMS) -> str:
    lg, lm = gpu <= threshold, mem <= threshold
    bursty = _isnum(peak_gpu) and peak_gpu >= params.bursty_peak and lg
    if lg and lm:
        return "bursty_idle" if bursty else "idle"
    if lg and not lm:
        return "memory_bound"
    if (not lg) and lm:
        return "compute_bound"
    return "high_load" if (gpu >= params.high_load and mem >= params.high_load) else "healthy"


def vtnet_low_load(gpu: float, mem: float, t: float = VTNET_LOW_LOAD_T) -> bool:
    return gpu < t and mem < t


def assessment_text(gpu: float, mem: float, threshold: float = DEFAULT_THRESHOLD,
                    peak_gpu: Optional[float] = None, coverage: Optional[float] = None,
                    days: Optional[int] = None, days_in_range: Optional[int] = None,
                    params: RuleParams = DEFAULT_PARAMS) -> str:
    """Câu nhận xét tiếng Việt cho 1 server (giữ giọng văn của skill)."""
    T = threshold
    lg = gpu <= T
    bursty = _isnum(peak_gpu) and peak_gpu >= params.bursty_peak and lg
    head = (f"util TB {gpu:.0f}% / VRAM TB {mem:.0f}% (đỉnh util {peak_gpu:.0f}%)"
            if _isnum(peak_gpu) else f"util TB {gpu:.0f}% / VRAM TB {mem:.0f}%")
    p = classify_pattern(gpu, mem, T, peak_gpu, params)
    # memory/compute-bound: "CẢNH BÁO" ở luật cả 2; luật 1 chỉ số → Nguy hiểm hoặc An toàn (ghi rõ chỉ số đang xét)
    zone = classify_zone(gpu, mem, T, params.zone_metric)
    head_zone = ZONE_LABEL_VI[zone].upper()
    if params.zone_metric != "both":
        head_zone += f" (theo {ZONE_METRIC_LABEL_VI[params.zone_metric]})"
    if p == "bursty_idle":
        body = (f"NGUY HIỂM(trung bình) nhưng BURSTY: có đỉnh util {peak_gpu:.0f}% → job chạy ngắt quãng. "
                "Xác minh lịch/cron trước khi thu hồi, đừng cắt vội.")
    elif p == "idle":
        body = "NGUY HIỂM – idle thật: compute+VRAM đều thấp cả kỳ. Ứng viên thu hồi/tái phân bổ NGAY."
    elif p == "memory_bound":
        body = (f"{head_zone} – memory-bound: VRAM {mem:.0f}% (model đã load) nhưng compute chỉ {gpu:.0f}%. "
                "Service chạy nhưng ít request / batch chưa tối ưu → gom model, giảm số card, "
                "hoặc chia card (time-slicing/MPS).")
        if bursty:
            body += f" Có đỉnh util {peak_gpu:.0f}% (bursty) – cân nhắc khi tối ưu."
    elif p == "compute_bound":
        body = (f"{head_zone} – compute-bound: compute {gpu:.0f}% nhưng VRAM {mem:.0f}% thấp (model nhỏ, dư VRAM). "
                "Dồn thêm workload/chia MIG để tăng mật độ.")
    elif p == "high_load":
        body = f"AN TOÀN – tải cao ổn định (compute {gpu:.0f}%, VRAM {mem:.0f}%). Không nén thêm, cân nhắc dư địa."
    else:
        body = f"AN TOÀN – dùng hiệu quả (compute {gpu:.0f}%, VRAM {mem:.0f}%). Giữ nguyên."
    if vtnet_low_load(gpu, mem, params.vtnet_low_load_t):
        body += (f" ⚠ Dưới ngưỡng THẤP TẢI của VTNet (<{params.vtnet_low_load_t:.0f}% cả 2)"
                 " → nguy cơ bị VTNet thu hồi.")
    tail = ""
    if _isnum(coverage) and coverage < params.thin_coverage:
        tail = (f" [Chỉ có {days}/{days_in_range} ngày dữ liệu – dữ liệu mỏng]"
                if days is not None and days_in_range else " [Dữ liệu mỏng]")
    return f"[{head}] {body}{tail}"
