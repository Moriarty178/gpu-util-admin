# -*- coding: utf-8 -*-
"""Đọc & chuẩn hóa file utilization VTNet và file thống kê server TTCN-VTT.

Hỗ trợ 2 schema file VTNet:
  - "t10" (chuẩn hiện hành, từ file HSSD GPU Tháng 10/2026):
        VTT_KPI_overview : header ở dòng 3 -> Row Labels | Average of gpu_core (%) | Average of gpu_mem (%)
                           + dòng "Grand Total"
        server_raw       : host_ip | gpu | mem | gpu_type | date_hour | don_vi
        DS đã thu        : (tùy chọn) danh sách server VTNet đã thu hồi
        HSSD theo ngay VTT : (từ T8, tùy chọn) header dòng 3 -> Ngày | GPU Core % | GPU Memory % | Số server
                           = TB toàn bộ server theo ngày VTNet tự tính (dùng để đối soát, không nhập)
  - "t7"  (cũ, file tháng 7/2026):
        VTT_KPI_overview : header dòng 1 -> Địa chỉ IP Server | Average of gpu_util | Average of gpu_memory
        VTT_GPU_Server_RAW : date | instance | gpu_type | gpu_util | gpu_memory | don_vi

Mọi sheet khác (VAI, VIC, pivot_value, Sheet1, ...) bị bỏ qua khi import,
nhưng được liệt kê trong `ignored_sheets` để hiển thị cho admin.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# ---------------------------------------------------------------- helpers

def norm_text(s) -> str:
    """Chuẩn hóa chuỗi header/ô: NFC, bỏ NBSP, gộp khoảng trắng, strip."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = unicodedata.normalize("NFC", str(s)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def norm_key(s) -> str:
    return norm_text(s).casefold()


def norm_ip(s) -> str:
    return norm_text(s).replace(" ", "")


def is_ipv4(s) -> bool:
    s = norm_ip(s)
    if not IPV4_RE.match(s):
        return False
    return all(0 <= int(p) <= 255 for p in s.split("."))


_GPU_RE = re.compile(r"^\s*(?:(\d+)\s*[x×*]\s*)?(.+?)\s*$", re.IGNORECASE)


def parse_gpu_spec(spec) -> tuple[Optional[int], Optional[str]]:
    """'4×NVIDIA L40S'->(4,'L40S'); '2*A30'->(2,'A30'); 'L40S'->(None,'L40S');
    '8 x Quadro RTX 6000'/'8xRTX6000'->(8,'RTX 6000'); '3xNVIDIA  A30'->(3,'A30')."""
    s = norm_text(spec)
    if not s:
        return None, None
    m = _GPU_RE.match(s)
    count = int(m.group(1)) if m and m.group(1) else None
    model = (m.group(2) if m else s)
    model = re.sub(r"(?i)\bnvidia\b|\bquadro\b", "", model)
    model = re.sub(r"\s+", " ", model).strip().upper()
    model = re.sub(r"^RTX\s*(\d+)", r"RTX \1", model)          # RTX6000 -> RTX 6000
    model = model.replace("L40 S", "L40S")
    return count, (model or None)


# ---------------------------------------------------------------- VTNet workbook

OV_ALIASES = {
    "ip": ["địa chỉ ip server", "row labels", "ip os", "ip", "host_ip", "instance"],  # "IP OS": file T8, T9
    "gpu": ["average of gpu_util", "average of gpu_core (%)", "average of gpu (%)", "average of gpu", "gpu_util", "gpu"],
    "mem": ["average of gpu_memory", "average of gpu_mem (%)", "average of mem (%)", "average of mem", "gpu_memory", "mem"],
}
RAW_ALIASES = {
    "ip": ["host_ip", "instance", "ip"],
    "ts": ["date_hour", "date", "ts", "datetime"],
    "gpu": ["gpu", "gpu_util", "gpu_core"],
    "mem": ["mem", "gpu_memory", "gpu_mem"],
    "gpu_type": ["gpu_type"],
    "don_vi": ["don_vi", "đơn vị"],
}
DAILY_ALIASES = {
    "day": ["ngày", "ngay", "date"],
    "gpu": ["gpu core %", "gpu core (%)", "gpu %"],
    "mem": ["gpu memory %", "gpu memory (%)", "mem %"],
    "n_servers": ["số server", "so server"],
}
RAW_STANDARD_COLUMNS = ["ip", "ts", "gpu", "mem", "gpu_type", "don_vi"]  # 6 cột server_raw chuẩn (T7–T10)
RECLAIM_ALIASES = {
    "ip": ["ip"],
    "gpu_type": ["gpu type", "gpu_type"],
    "beneficiary": ["thụhưởngtàinguyên theo qhdc", "thụ hưởng tài nguyên theo qhdc"],
    "owner_dcim": ["owner instance dcim"],
    "service_manager": ["service manager (owner tài nguyên hiện tại)"],
    "status": ["trạng thái"],
}

OVERVIEW_SHEET_NAMES = ["vtt_kpi_overview"]
RAW_SHEET_NAMES = ["server_raw", "vtt_gpu_server_raw"]
RECLAIM_SHEET_NAMES = ["ds đã thu"]
DAILY_SHEET_NAMES = ["hssd theo ngay vtt", "hssd theo ngày vtt"]


@dataclass
class VtnetWorkbook:
    schema: str                                   # "t10" | "t7"
    raw: pd.DataFrame                             # ip, ts, gpu, mem, gpu_type, don_vi
    overview: Optional[pd.DataFrame]              # ip, gpu, mem  (trung bình VTNet tự tính)
    overview_total: Optional[tuple[float, float]] # dòng Grand Total nếu có
    reclaimed: Optional[pd.DataFrame]             # ip, gpu_type, beneficiary, owner_dcim, service_manager, status
    daily: Optional[pd.DataFrame] = None          # day, gpu, mem, n_servers (sheet 'HSSD theo ngay VTT')
    missing_columns: list = field(default_factory=list)  # cột chuẩn tùy chọn của server_raw không có trong file
    sheet_names: dict = field(default_factory=dict)
    ignored_sheets: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def period(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.raw["ts"].min(), self.raw["ts"].max()

    @property
    def dominant_month(self) -> str:
        """Tháng chiếm nhiều ngày nhất ('YYYY-MM'). File T10 chứa cả ngày tràn 01/11 -> vẫn là '2026-10'."""
        days = self.raw["ts"].dt.normalize().drop_duplicates()
        return days.dt.strftime("%Y-%m").value_counts().idxmax()


def _find_sheet(xl: pd.ExcelFile, wanted: list[str]) -> Optional[str]:
    by_key = {norm_key(s): s for s in xl.sheet_names}
    for w in wanted:
        if w in by_key:
            return by_key[w]
    return None


def _locate_header(df_noheader: pd.DataFrame, aliases: dict, scan_rows: int = 10) -> int:
    """Trả về chỉ số dòng header: dòng đầu tiên có >=2 ô khớp alias."""
    flat = {a for names in aliases.values() for a in names}
    for i in range(min(scan_rows, len(df_noheader))):
        hits = sum(1 for v in df_noheader.iloc[i].tolist() if norm_key(v) in flat)
        if hits >= 2:
            return i
    raise ValueError(f"Không tìm thấy dòng header (cần >=2 cột trong {sorted(flat)})")


def _read_table(xl: pd.ExcelFile, sheet: str, aliases: dict, required: list[str]) -> pd.DataFrame:
    probe = pd.read_excel(xl, sheet_name=sheet, header=None, nrows=12)
    h = _locate_header(probe, aliases)
    df = pd.read_excel(xl, sheet_name=sheet, header=h)
    colmap = {}
    keys = {norm_key(c): c for c in df.columns}
    for logical, names in aliases.items():
        for n in names:
            if n in keys:
                colmap[keys[n]] = logical
                break
    missing = [r for r in required if r not in colmap.values()]
    if missing:
        raise ValueError(f"Sheet '{sheet}': thiếu cột {missing}. Có: {list(df.columns)}")
    return df.rename(columns=colmap)[list(colmap.values())]


def read_vtnet_workbook(path) -> VtnetWorkbook:
    with pd.ExcelFile(path) as xl:  # đóng file ngay khi đọc xong (Windows: file còn mở thì không xóa/ghi đè được)
        return _read_vtnet_xl(xl)


def _read_vtnet_xl(xl: pd.ExcelFile) -> VtnetWorkbook:
    warnings: list[str] = []

    raw_sheet = _find_sheet(xl, RAW_SHEET_NAMES)
    if not raw_sheet:
        raise ValueError(f"Không thấy sheet dữ liệu thô {RAW_SHEET_NAMES}. Có: {xl.sheet_names}")
    raw = _read_table(xl, raw_sheet, RAW_ALIASES, ["ip", "ts", "gpu", "mem"])
    missing_columns = [c for c in RAW_STANDARD_COLUMNS if c not in raw.columns]
    raw_cols_original = {norm_key(c) for c in pd.read_excel(xl, sheet_name=raw_sheet, nrows=0).columns}
    schema = "t10" if "host_ip" in raw_cols_original else "t7"

    raw["ip"] = raw["ip"].map(norm_ip)
    bad_ip = ~raw["ip"].map(is_ipv4)
    if bad_ip.any():
        warnings.append(f"Bỏ {int(bad_ip.sum())} dòng raw có IP không hợp lệ: {sorted(raw.loc[bad_ip,'ip'].unique())[:5]}")
        raw = raw[~bad_ip]
    raw["ts"] = pd.to_datetime(raw["ts"], errors="coerce")
    for c in ("gpu", "mem"):
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    bad = raw[["ts", "gpu", "mem"]].isna().any(axis=1)
    if bad.any():
        warnings.append(f"Bỏ {int(bad.sum())} dòng raw thiếu ngày/giá trị.")
        raw = raw[~bad]
    oor = (raw["gpu"].lt(0) | raw["gpu"].gt(100) | raw["mem"].lt(0) | raw["mem"].gt(100))
    if oor.any():
        warnings.append(f"{int(oor.sum())} dòng có giá trị ngoài [0,100] (giữ nguyên, cần kiểm tra).")
    for c in ("gpu_type", "don_vi"):
        if c not in raw.columns:
            raw[c] = None
        raw[c] = raw[c].map(lambda v: norm_text(v) or None)
    other_unit = raw["don_vi"].map(lambda v: isinstance(v, str) and v.casefold() != "vtt")
    if other_unit.any():                       # chỉ nhập VTT (hoặc để trống) — PLAN §5.4
        units = sorted(raw.loc[other_unit, "don_vi"].unique())
        warnings.append(f"Bỏ {int(other_unit.sum())} dòng raw của đơn vị khác VTT: {units[:5]}")
        raw = raw[~other_unit]
    dup = raw.duplicated(["ip", "ts"], keep="last")
    if dup.any():
        warnings.append(f"{int(dup.sum())} dòng trùng (ip, thời điểm) — giữ dòng cuối.")
        raw = raw[~dup]
    if (raw["ts"].dt.hour != 0).any() or (raw["ts"].dt.minute != 0).any():
        warnings.append("Dữ liệu có giờ khác 00:00 → granularity theo GIỜ (không phải ngày).")
    raw = raw.sort_values(["ip", "ts"]).reset_index(drop=True)

    overview = overview_total = None
    ov_sheet = _find_sheet(xl, OVERVIEW_SHEET_NAMES)
    if ov_sheet:
        ov = _read_table(xl, ov_sheet, OV_ALIASES, ["ip", "gpu", "mem"])
        lab = ov["ip"].map(norm_text)
        tot = ov[lab.str.casefold() == "grand total"]
        if len(tot):
            overview_total = (float(tot["gpu"].iloc[0]), float(tot["mem"].iloc[0]))
        ov = ov[lab.map(is_ipv4)].copy()
        ov["ip"] = ov["ip"].map(norm_ip)
        ov["gpu"] = pd.to_numeric(ov["gpu"], errors="coerce")
        ov["mem"] = pd.to_numeric(ov["mem"], errors="coerce")
        overview = ov.reset_index(drop=True)
    else:
        warnings.append("Không có sheet VTT_KPI_overview → bỏ qua đối soát trung bình.")

    reclaimed = None
    rc_sheet = _find_sheet(xl, RECLAIM_SHEET_NAMES)
    if rc_sheet:
        rc = _read_table(xl, rc_sheet, RECLAIM_ALIASES, ["ip"])
        rc["ip"] = rc["ip"].map(norm_ip)
        rc = rc[rc["ip"].map(is_ipv4)]
        for c in RECLAIM_ALIASES:
            if c not in rc.columns:
                rc[c] = None
            elif c != "ip":
                rc[c] = rc[c].map(lambda v: norm_text(v) or None)
        reclaimed = rc[list(RECLAIM_ALIASES)].reset_index(drop=True)

    daily = None
    dl_sheet = _find_sheet(xl, DAILY_SHEET_NAMES)
    if dl_sheet:  # sheet phụ: sai cấu trúc thì chỉ ghi chú, không chặn nhập
        try:
            dl = _read_table(xl, dl_sheet, DAILY_ALIASES, ["day", "gpu", "mem"])
        except ValueError as exc:
            warnings.append(f"Bỏ qua đối soát theo ngày: {exc}")
        else:
            dl["day"] = pd.to_datetime(dl["day"], errors="coerce").dt.normalize()
            for c in ("gpu", "mem", "n_servers"):
                if c in dl.columns:
                    dl[c] = pd.to_numeric(dl[c], errors="coerce")
                else:
                    dl[c] = float("nan")
            daily = dl.dropna(subset=["day", "gpu", "mem"])[list(DAILY_ALIASES)].reset_index(drop=True)

    used = {raw_sheet, ov_sheet, rc_sheet, dl_sheet} - {None}
    return VtnetWorkbook(
        schema=schema, raw=raw, overview=overview, overview_total=overview_total,
        reclaimed=reclaimed, daily=daily, missing_columns=missing_columns,
        sheet_names={"raw": raw_sheet, "overview": ov_sheet, "reclaimed": rc_sheet, "daily": dl_sheet},
        ignored_sheets=[s for s in xl.sheet_names if s not in used],
        warnings=warnings,
    )


# ---------------------------------------------------------------- Inventory workbook

INVENTORY_SHEET = "Thống kê chi tiết"
# header (đã norm_key) -> khóa logic. So khớp "bắt đầu bằng" để chịu được header dài/xuống dòng.
INV_PREFIX = [
    ("stt", "stt"), ("loại server", "server_class"), ("cấu hình", "config"), ("cpu", "cpu"),
    ("ram", "ram"), ("disk", "disk"), ("hba", "hba"), ("gpu", "gpu_spec"), ("serial", "serial"),
    ("ip", "ip"), ("đầu mối", "owner"), ("model", "model"), ("đầu vào hệ thống", "input_load"),
    ("dịch vụ", "service"), ("quản lý bằng", "managed_by"), ("tên cụm", "cluster"),
    ("đánh giá", "assessment"),
]


def _inv_key(header) -> Optional[str]:
    k = norm_key(header)
    for prefix, key in INV_PREFIX:
        if k == prefix or (len(prefix) > 3 and k.startswith(prefix)):
            return key
    return None


def load_ip_links(path) -> pd.DataFrame:
    """CSV liên kết IP: inventory_ip, vtnet_ip, pair_confirmed (true/false), reason.
    Dùng khi cùng 1 máy có IP khác nhau giữa file thống kê và VTNet (vd 9 server RTX6000)."""
    df = pd.read_csv(path, dtype=str).fillna("")
    for c in ("inventory_ip", "vtnet_ip"):
        df[c] = df[c].map(norm_ip)
        bad = ~df[c].map(is_ipv4)
        if bad.any():
            raise ValueError(f"ip_links: {c} không hợp lệ: {df.loc[bad, c].tolist()}")
    if "pair_confirmed" not in df.columns:
        df["pair_confirmed"] = "false"
    df["pair_confirmed"] = df["pair_confirmed"].str.strip().str.casefold().isin(["true", "1", "yes", "có"])
    for c in ("inventory_ip", "vtnet_ip"):
        dup = df[c][df[c].duplicated()]
        if len(dup):
            raise ValueError(f"ip_links: {c} bị trùng: {sorted(dup.unique())}")
    return df


def links_dict(links) -> dict:
    if links is None:
        return {}
    if isinstance(links, dict):
        return links
    return dict(zip(links["inventory_ip"], links["vtnet_ip"]))


def apply_ip_links(inv: pd.DataFrame, links) -> pd.DataFrame:
    """Trả inventory với cột `ip` = IP phía VTNet (effective) và `inventory_ip` = IP gốc trong file thống kê.
    Báo lỗi nếu IP đích trùng với IP của một dòng inventory khác (2 dòng cùng trỏ 1 máy)."""
    m = links_dict(links)
    out = inv.copy()
    out["inventory_ip"] = out["ip"]
    out["ip"] = out["ip"].map(lambda v: m.get(v, v))
    out["ip_linked"] = out["ip"] != out["inventory_ip"]
    dup = out["ip"][out["ip"].duplicated()]
    if len(dup):
        raise ValueError(f"Liên kết IP gây trùng với dòng thống kê khác: {sorted(dup.unique())}")
    out.attrs.update(inv.attrs)
    return out


def read_inventory(path, sheet: str = INVENTORY_SHEET) -> pd.DataFrame:
    """Đọc sheet 'Thống kê chi tiết' -> DataFrame với cột logic + excel_row (số dòng Excel gốc)."""
    with pd.ExcelFile(path) as xl:  # đóng file ngay khi đọc xong
        target = _find_sheet(xl, [norm_key(sheet)])
        if not target:
            raise ValueError(f"Không thấy sheet '{sheet}'. Có: {xl.sheet_names}")
        df = pd.read_excel(xl, sheet_name=target, header=0, dtype=object)
    rename, extra = {}, []
    for c in df.columns:
        key = _inv_key(c)
        if key and key not in rename.values():
            rename[c] = key
        elif not str(c).startswith("Unnamed"):
            extra.append(c)
    if "ip" not in rename.values():
        raise ValueError(f"Sheet '{target}' không có cột IP. Header: {list(df.columns)}")
    df["excel_row"] = df.index + 2
    df = df.rename(columns=rename)
    df = df[df["ip"].map(lambda v: norm_text(v) != "")].copy()
    for c in df.columns:
        if c not in ("excel_row",):
            df[c] = df[c].map(lambda v: norm_text(v) or None)
    df["ip"] = df["ip"].map(norm_ip)
    # IP sai định dạng (vd '10.29.95.16/17') -> bỏ + ghi lại dòng Excel. Bỏ TRƯỚC khi kiểm trùng IP (Q13).
    bad = ~df["ip"].map(is_ipv4)
    invalid = [{"excel_row": int(r), "ip": ip} for r, ip in zip(df.loc[bad, "excel_row"], df.loc[bad, "ip"])]
    df = df[~bad].copy()
    if "owner" in df.columns:
        df["owner"] = df["owner"].map(lambda v: v.casefold() if v else None)
    spec = df["gpu_spec"] if "gpu_spec" in df.columns else pd.Series([None] * len(df), index=df.index)
    parsed = spec.map(parse_gpu_spec)
    df["gpu_count"] = parsed.map(lambda t: t[0]).astype("Int64")      # số nguyên, thiếu = <NA>
    df["gpu_model"] = parsed.map(lambda t: t[1])
    df.attrs["extra_columns"] = extra
    df.attrs["sheet"] = target
    df.attrs["invalid_ip_rows"] = invalid
    df.attrs["warnings"] = ([f"Bỏ {len(invalid)} dòng có IP không hợp lệ (dòng Excel "
                             f"{', '.join(str(x['excel_row']) for x in invalid)}): "
                             f"{sorted({x['ip'] for x in invalid})}"] if invalid else [])
    return df.reset_index(drop=True)
