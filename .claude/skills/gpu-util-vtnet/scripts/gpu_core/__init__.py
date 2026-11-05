# -*- coding: utf-8 -*-
"""gpu_core — logic lõi (parse file VTNet/inventory, luật vùng, phép tính) dùng chung cho
backend FastAPI và skill gpu-util-vtnet. Không phụ thuộc DB/web: chỉ pandas + openpyxl."""
from .parsing import (VtnetWorkbook, apply_ip_links, is_ipv4, links_dict, load_ip_links,  # noqa: F401
                      norm_ip, norm_text, parse_gpu_spec, read_inventory, read_vtnet_workbook)
from .rules import (BURSTY_PEAK, DEFAULT_PARAMS, DEFAULT_THRESHOLD, HIGH_LOAD, PATTERN_LABEL_VI,  # noqa: F401
                    THIN_COVERAGE, VTNET_LOW_LOAD_T, ZONE_LABEL_VI, ZONE_METRIC_LABEL_VI, ZONE_METRICS, RuleParams,
                    assessment_text, check_zone_metric, classify_pattern, classify_zone, is_danger, vtnet_low_load,
                    zone_rule_text)
from .metrics import (compare_periods, days_in_range, fleet_daily, low_load_streak,  # noqa: F401
                      server_stats, to_daily, validate_daily, validate_overview, zone_owner_matrix)

# 2.1: liên kết IP (load_ip_links / apply_ip_links)
# 2.2: chỉ nhập don_vi VTT/rỗng; to_daily gom giờ→ngày (server_stats, fleet_daily); read_inventory bỏ IP sai định dạng
# 2.3: RuleParams — hằng số phụ (VTNet, bursty, tải cao, dữ liệu mỏng) thành tham số, mặc định giữ nguyên
# 2.4: đọc sheet 'HSSD theo ngay VTT' (VtnetWorkbook.daily) + validate_daily; VtnetWorkbook.missing_columns
# 2.5: RuleParams.zone_metric — áp ngưỡng T cho cả 2 chỉ số (mặc định, 3 vùng) hoặc chỉ compute/memory (2 vùng)
__version__ = "2.5.0"
