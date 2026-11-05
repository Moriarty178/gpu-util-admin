# CONTEXT — Bối cảnh nghiệp vụ & dữ liệu (đọc trước khi code)

> Tài liệu nền cho Claude Code. Mọi con số ở đây đã được **chạy lại trên dữ liệu thật** (thư mục `samples/`)
> ngày 03/11/2026. Khi code mâu thuẫn với tài liệu này → dừng lại và hỏi, đừng "sửa cho khớp".

---

## 1. Bài toán trong 5 câu

1. **VTT** (Viettel Telecom) — **TTCN** (Trung tâm Công nghệ) đang dùng ~140 server GPU đặt tại hạ tầng do **VTNet** vận hành.
2. VTNet giám sát tải (CPU/RAM/GPU) và **thu hồi** server tải thấp. Mỗi tháng VTNet gửi 1 file Excel tải GPU theo ngày của từng server (theo IP).
3. TTCN có file **"Thống kê toàn bộ server"** (inventory): server nào, IP nào, **đầu mối** nào quản (dungha7, kientt6), chạy **dịch vụ/model** gì.
4. Việc hiện tại làm thủ công bằng skill `gpu-util-vtnet`: ghép 2 file theo IP → chia vùng An toàn/Cảnh báo/Nguy hiểm theo ngưỡng T% → ghi nhận xét cho từng server để đầu mối xử lý trước khi VTNet thu hồi.
5. **Công cụ cần xây**: web quản trị + CSDL riêng, lưu dữ liệu nhiều tháng, xem biểu đồ tải toàn bộ/từng server theo khoảng ngày bất kỳ, bảng cảnh báo với ngưỡng T chọn trên giao diện.

Người dùng chính: **admin quy hoạch hạ tầng GPU của TTCN** (cầu nối giữa các đội AI và VTNet).
Người dùng phụ [GĐ2]: **các đầu mối** — đăng nhập bằng tài khoản do admin cấp, mặc định chỉ thấy server của mình, có thể ghi giải trình.
**Giai đoạn 1 (đang làm)**: trang quản trị đơn giản chạy thẳng trong Ubuntu/WSL trên máy admin — không Docker, SQLite, không đăng nhập.
**Giai đoạn 2 (sau)**: PostgreSQL + Docker Compose (localhost rồi VM nội bộ), tài khoản & phân quyền đầu mối.
Bối cảnh lớn hơn: TTCN đang chuyển dịch vụ lên nền tảng VTNet (vùng đệm ~47 card L40S, cuốn chiếu) — số liệu tải là căn cứ để
thu hồi card idle, ép các đội không xin vượt chuẩn, và đàm phán SLA với VTNet.

## 2. Thuật ngữ

| Thuật ngữ | Nghĩa |
|---|---|
| Đầu mối (sử dụng) | Người chịu trách nhiệm nhóm server: hiện có `dungha7`, `kientt6` (chuẩn hóa chữ thường) |
| Thấp tải / thu hồi | VTNet gắn cờ server tải thấp → thu hồi về pool ("FREE (thu hồi thấp tải)") |
| `gpu` / `gpu_core` / `gpu_util` | % thời gian SM có kernel chạy (kiểu `DCGM_FI_DEV_GPU_UTIL`) — **không** phải cường độ tính toán; 1 kernel nhỏ vẫn có thể báo cao |
| `mem` / `gpu_mem` / `gpu_memory` | % VRAM đang chiếm |
| Vùng (zone) | An toàn / Cảnh báo / Nguy hiểm theo ngưỡng T (mục 4) |
| Mẫu hình (pattern) | idle, bursty_idle, memory_bound, compute_bound, high_load, healthy (mục 4) |
| Kỳ (period) | Khoảng ngày của 1 file VTNet. Nhãn kỳ = tháng chiếm nhiều ngày nhất |
| QHDC, DCIM | Hệ thống quy hoạch/quản lý tài sản DC của Viettel (chỉ xuất hiện như nhãn cột) |
| VAI, VIC, Ban CNTT | Đơn vị khác dùng chung hạ tầng — **ngoài phạm vi**, chỉ VTT |

## 3. Định dạng file VTNet

### 3.1 Schema `t10` — CHUẨN HIỆN HÀNH (file `HSSD GPU Thang 10 2026 - VTT.xlsx`)

| Sheet | Dùng? | Cấu trúc |
|---|---|---|
| `server_raw` | **Nhập** | Header dòng 1: `host_ip, gpu, mem, gpu_type, date_hour, don_vi`. 2.930 dòng, 92 IP, 32 ngày **01/10 → 01/11** (có ngày tràn 01/11). `date_hour` hiện luôn 00:00 (mẫu theo ngày) nhưng tên cột gợi ý VTNet có thể gửi theo giờ |
| `VTT_KPI_overview` | **Đối soát** | 2 dòng trống, header ở **dòng 3**: `Row Labels, Average of gpu_core (%), Average of gpu_mem (%)`; 92 dòng IP + dòng `Grand Total` |
| `DS đã thu` | **Nhập (tùy chọn)** | `IP, GPU TYPE, Thụhưởngtàinguyên theo QHDC, Owner Instance DCIM, Service Manager (owner tài nguyên hiện tại), Trạng thái` — 30 server đã bị thu hồi |
| `HSSD theo ngay VTT` | Đối soát (golden) | Header dòng 3: `Ngày, GPU Core %, GPU Memory %, Số server` — tải TB toàn bộ server theo ngày, VTNet tự tính |
| `pivot_value`, `Sheet1` | Bỏ qua | 250 IP **mọi đơn vị**, 1 kỳ 31 ngày **khác** T10 (không rõ tháng), cột `Thấp tải` = BÌNH THƯỜNG/THẤP TẢI |
| `VAI`, `VIC`, `VTNet ` | Bỏ qua | Đơn vị khác, đang lỗi `#REF!` |

### 3.2 Schema `t7` — CŨ (file `HSSD_GPU_Daily_VTT_thang7.xlsx`)
`VTT_KPI_overview` header dòng 1: `Địa chỉ IP Server, Average of gpu_util, Average of gpu_memory` (+ dòng Grand Total).
`VTT_GPU_Server_RAW`: `date, instance, gpu_type, gpu_util, gpu_memory, don_vi`. 2.627 dòng, 88 IP, 01/07 → 30/07.
Vẫn phải nhập được (dữ liệu lịch sử).

### 3.3 Đã kiểm chứng (đây là định nghĩa CHUẨN, có test)

| Phát hiện | Kết quả kiểm |
|---|---|
| `VTT_KPI_overview` = **trung bình các mẫu ngày** của từng IP trên **toàn kỳ file** (kể cả ngày tràn 01/11) | lệch 0 (T10, T7). Nếu bỏ 01/11 → lệch tới 3,1 điểm % |
| `Grand Total` = trung bình **tất cả dòng raw** (trọng số theo số mẫu) | T10: 38,7377 / 72,3138 |
| `HSSD theo ngay VTT` = **trung bình đơn giản qua các server có số liệu trong ngày** | lệch ~1e-14, `Số server` khớp từng ngày (90–91) |
| Luật **THẤP TẢI** của VTNet = `gpu < 10 VÀ mem < 10` (trung bình kỳ) | khớp **250/250** dòng `pivot_value`. Ngưỡng 5/15/20 hay luật OR đều sai |
| Trung bình có trọng số theo số card khác hẳn | T10 tháng 10: theo server 38,9% vs theo card 44,8% (server 8×H200 tải cao kéo lên) |
| Server bị thu hồi biến mất khỏi raw | 0/30 IP trong `DS đã thu` còn xuất hiện trong `server_raw` T10 |

`gpu_type` có nhiều kiểu viết: `4×NVIDIA L40S`, `8 x Quadro RTX 6000`, `2×NVIDIA A30` → chuẩn hóa về (số card, model) bằng `gpu_core.parse_gpu_spec`.

## 4. Luật nghiệp vụ (nguồn chân lý: `backend/gpu_core/rules.py`)

**Vùng** — 1 ngưỡng T (mặc định 40, chỉnh được trên UI), so sánh `<=`:

```
gpu_avg <= T  VÀ mem_avg <= T   → Nguy hiểm  (danger)   ứng viên thu hồi
đúng 1 trong 2 <= T             → Cảnh báo   (warning)  cần tối ưu
cả hai > T                      → An toàn    (safe)
```

**Tùy chọn "Áp T cho"** (cài đặt `zone_metric`, chọn tạm được khi xem — người dùng chốt 05/11/2026, PLAN §14.9). Mặc định
`both` = luật trên. `gpu` / `mem` = chỉ xét 1 chỉ số, **2 vùng**, bỏ qua hẳn chỉ số kia:

```
chỉ số đã chọn <= T  → Nguy hiểm      chỉ số đã chọn > T → An toàn      (không có Cảnh báo)
vd compute 15 / memory 75, T = 40:  both → Cảnh báo · gpu → Nguy hiểm · mem → An toàn
```
Mẫu hình (bảng dưới) vẫn mô tả theo cả 2 chỉ số; ngày nguy hiểm / streak đếm theo chế độ đang áp.

**Mẫu hình** (dùng `gpu_peak` = max mẫu ngày trong khoảng):

| pattern | Điều kiện | Ý nghĩa / khuyến nghị |
|---|---|---|
| `idle` | danger, peak < 70 | Idle thật → thu hồi/tái phân bổ ngay |
| `bursty_idle` | danger, peak ≥ 70 | Job ngắt quãng → xác minh lịch/cron trước khi cắt |
| `memory_bound` | gpu ≤ T, mem > T | Model load sẵn ngồi chờ → gom model, giảm card, chia card (time-slicing/MPS) |
| `compute_bound` | gpu > T, mem ≤ T | Model nhỏ dư VRAM → dồn workload, chia MIG |
| `high_load` | safe, cả 2 ≥ 80 | Tải cao, không nén thêm |
| `healthy` | safe còn lại | Dùng hiệu quả |

**Cờ VTNet**: `vtnet_low_load = gpu_avg < 10 AND mem_avg < 10` (so sánh `<` chặt) — hiển thị **song song** với vùng T,
vì đây mới là luật VTNet thực sự dùng để thu hồi (suy luận, chưa được VTNet xác nhận chính thức).

**Dữ liệu mỏng**: `coverage = số ngày có mẫu / số ngày trong khoảng < 0.8`.
**Streak thấp tải**: số ngày liên tiếp gần nhất (tính từ ngày cuối có dữ liệu) mà gpu ≤ T và mem ≤ T (chế độ 1 chỉ số: chỉ số đó ≤ T).

Hạn chế phải luôn hiển thị: file chỉ có GPU, **không có CPU/RAM** → chỉ là xấp xỉ luật thu hồi của VTNet.

## 5. File thống kê server (inventory) — `Thong_ke_toan_bo_server_TTCN_VTT.xlsx`

- Sheet dùng: **`Thống kê chi tiết`**, header dòng 1, **16 cột** (bản tháng 7 có 17 — cột cuối "Đánh giá..." đã bị bỏ):
  `STT, Loại server, Cấu hình, CPU, RAM, Disk, HBA, GPU, Serial, IP, Đầu mối sử dụng, Model,
  Đầu vào hệ thống (CCU, Request...), Dịch vụ/nghiệp vụ đang chạy, Quản lý bằng? (="cụm k8s" || "Server độc lập"),
  Tên cụm, ký hiệu để phân biệt các cụm`.
  → **Tìm cột theo tên header, không theo vị trí** (`gpu_core.parsing.read_inventory`).
- Sheet `GPU QHDC` có ~280 công thức → khi xuất file phải giữ nguyên (đã xử lý bằng `fullCalcOnLoad`).
- 137 dòng, 137 IP duy nhất, không IP trống. Đầu mối: kientt6 80, dungha7 57.
- Cột GPU viết lộn xộn: `4x NVIDIA L40S`, `2*L4`, ` 2*A30` (có NBSP), `3xNVIDIA  A30`, `8xRTX6000`, `L40S` (thiếu số lượng).
- `Quản lý bằng`: cụm k8s 98 / Server độc lập 39. `Tên cụm`: 1, 2, 3, 4, 5, "Server độc lập".
- STT bị trùng (132, 133) → **không dùng STT làm khóa**; khóa là IP.

## 6. Kết quả ánh xạ & chất lượng dữ liệu (T10 + inventory mới)

```
                         KHÔNG liên kết IP                     CÓ 9 liên kết RTX6000 (mặc định sau seed)
Inventory 137 IP ──┬── 80 khớp VTNet                      ┬── 89 khớp VTNet (9 qua liên kết)
                   └── 57 không có tải                     └── 48 không có tải ──┬── 13 nằm trong "DS đã thu"
                                                                                 └── 35 chưa rõ (chưa monitor / đã trả / non-GPU?)
VTNet  92 IP ──────┬── 80 khớp                             ┬── 89 khớp
                   └── 12 thiếu trong inventory            └──  3 thiếu trong inventory
```

Các trường hợp cụ thể phải hỗ trợ trên UI (màn "Đối soát"):

1. **Đổi IP — ĐÃ XÁC NHẬN (03/11/2026)**: inventory `10.207.188.1–9` (9 server 8×RTX6000, kientt6) **chính là** 9 server VTNet
   đo ở `10.205.36.51–59` (8×Quadro RTX 6000). Người dùng chốt ghép theo **IP tăng dần** (`.188.1↔.36.51` … `.188.9↔.36.59`),
   seed `backend/seeds/ip_links.csv` với `pair_confirmed=false`: **từng cặp chưa được kiểm thực tế**. Ảnh hưởng: dịch vụ gán cho từng máy
   (`.188.1–4` Callbot "Xử lý voice", `.5–7` GSCG "Nhận diện cảm xúc", `.8–9` Video bot/OCR) có thể lệch cặp;
   **không** ảnh hưởng tổng hợp theo đầu mối (cả 9 là kientt6). Tải 9 máy (theo IP VTNet): 1 Nguy hiểm (`.51` idle 0/35,6%),
   7 Cảnh báo (memory-bound), 1 An toàn (`.54`).
2. **VTNet-only còn lại**: `10.221.122.33` (3×L4, tải 0/6% → dưới ngưỡng VTNet), `10.221.155.36`, `10.221.155.37` (4×L40S) — thiếu từ tháng 7.
3. **Lệch số card** inventory vs VTNet: `2*L4` nhưng VTNet `3×L4` (5 server `10.221.58.45–49`), `3*L40` vs `6×L40` (`10.221.58.75`),
   `3*A30` vs `1×A30` (`10.207.163.82`), `L40S` không ghi số lượng vs `4×` (`10.221.155.19`) — 8 server; 9 máy RTX6000 khớp (8 = 8).
   → Số card lấy theo VTNet `gpu_type`, inventory là dự phòng; hiển thị cờ lệch.
4. **Đã thu hồi nhưng inventory còn**: 13 IP — dungha7: `10.221.58.58`, `10.221.58.59`, `10.221.155.10`;
   kientt6: `10.221.58.56`, `10.221.155.54–63` (trừ `.58`; 8 server "video face Streaming" + `.63`).
   → Server đã thu hồi phải có trạng thái riêng, không bị tính là "thiếu monitor".

## 7. Số tham chiếu (golden) — test phải khớp

Ngưỡng T = 40, khoảng = toàn kỳ file.

| Bộ dữ liệu | Server VTNet | Vùng (mọi server VTNet) | Ma trận server map được (An toàn / Cảnh báo / Nguy hiểm) |
|---|---|---|---|
| T7 + inventory T7 | 88 | 21 / 48 / 19 | **77**: dungha7 8/21/14, kientt6 7/23/4 → **15 / 44 / 18** (= kết quả skill v1) |
| T10 + inventory T10, không liên kết | 92 | 35 / 46 / 11 | **80**: dungha7 18/18/5, kientt6 15/20/4 → **33 / 38 / 9** |
| **T10 + inventory T10 + 9 liên kết RTX6000** (trạng thái mặc định của công cụ) | 92 | 35 / 46 / 11 | **89**: dungha7 18/18/5, kientt6 16/27/5 → **34 / 45 / 10**; chưa map 1/1/1 |

Thêm cho T10: mẫu hình (92 server) memory_bound 46, healthy 18, high_load 17, idle 7, bursty_idle 4; dưới ngưỡng VTNet: 1
(`10.221.122.33`); dữ liệu mỏng: 1 (`10.254.135.34`, 21/32 ngày). T10 ngưỡng 30, khoảng 01/10–31/10 trên server map được:
không liên kết 36 / 38 / 6 (80), có liên kết 40 / 43 / 6 (89). Lệch số card inventory ↔ VTNet: 8 server (7 khác số + 1 thiếu số).
Phạm vi đầu mối (có liên kết): kientt6 = 48 server (16/27/5), dungha7 = 41 server (18/18/5).
Biểu đồ tải toàn bộ 01/10–31/10 phải khớp sheet `HSSD theo ngay VTT` (31 điểm, vd 01/10 = 34,761% GPU / 70,878% VRAM, 91 server).
File T8 (31 ngày, 01/08 = 19,291% / 63,805%, 95 server) và T9 (30 ngày, 01/09 = 38,344% / 72,342%, 92 server) cũng khớp sheet này
~1e-14 — dùng làm đối soát khi nhập (`gpu_core.validate_daily`, cảnh báo `daily_mismatch`).

Xu hướng T7 → T10 (chỉ để định hướng UI so sánh kỳ): TB gpu 22,3% → 38,8%; nguy hiểm 19 → 11 server (54 → 37 card);
20 server cải thiện, 5 xấu đi, 9 mới, 5 biến mất.

**Dữ liệu mẫu hiện có (người dùng chốt 03/11/2026)** — `samples/`:
- VTNet T7, T8, T9, T10 (`HSSD GPU Thang 7|8|9 2026 - VTT.xlsx`, `HSSD_GPU_Thang_10_2026_VTT.xlsx`); cả 4 theo định dạng `server_raw`.
  T8/T9: sheet overview tiêu đề `IP OS`, `Average of gpu (%)`, `Average of mem (%)` (gpu_core 2.3 đã nhận). Golden T8/T9 = TB tự tính
  khớp `VTT_KPI_overview` của VTNet. File T10 hiện có **không có** sheet `DS đã thu`.
- **1 file thống kê toàn bộ server VTT** `Thong_ke_toan_bo_server_TTCN_VTT.xlsx`: 134 dòng (129 IP hợp lệ + 5 IP sai định dạng dòng
  131–135), kientt6 74 / dungha7 55, sheet `GPU QHDC` + `Thống kê chi tiết` — chính là bản dùng cho golden T7 (15/44/18 ✓).
  Golden "thống kê T10" ở bảng trên (137 dòng: 34/45/10, kientt6 48, 137 = 89/13/35, 280 công thức) cần **bản 137 dòng**, đặt tên
  `Thong_ke_toan_bo_server_TTCN_VTT_ban137.xlsx` → khi chưa có, các test đó tự skip. Không sinh golden mới từ code.
- Golden T7 → T10 ở trên (20 / 5 / 9 / 5; Nguy hiểm 19 → 11) **đã đạt** với các file này.
- **Chu kỳ tuần** (dự kiến, PLAN §14.8): file tuần giữ nguyên cấu trúc sheet, tuần ISO thứ 2 → CN. File T7 thật dừng ở 30/07 →
  nhập T8 sau T7 báo khoảng trống 1 ngày (31/07); báo cáo tháng 7 vẫn xuất được (30/31 ngày, ghi chú thiếu 31/07). Dữ liệu T7–T10:
  khoảng mặc định 4 tuần = 05/10–01/11 → 10 / 47 / 35 (Nguy hiểm / Cảnh báo / An toàn) — số định hướng, không phải golden.
- Với file thống kê 134 dòng, kỳ T10 có **11 IP VTNet chưa có trong thống kê** (8 server H200 cụm `10.29.95.x` — đều An toàn,
  tải cao — + `10.221.122.33`, `10.221.155.36`, `10.221.155.37`) → map được 81/92, ma trận dungha7 16/18/5, kientt6 10/27/5.
  Chênh với golden bản 137 dòng (89 map, 18/18/5 · 16/27/5) đúng bằng 8 server An toàn → bản 137 dòng nhiều khả năng đã có cụm H200.

## 8. Lịch sử & tài sản sẵn có

- Tháng 7/2026: phân tích thủ công lần đầu → sinh skill `gpu-util-vtnet` v1 (chỉ đọc schema t7, ghi cột 17 cố định, có lỗi
  đếm dòng "Grand Total" như 1 IP → số "VTNet-only" T7 đúng ra là **11**, không phải 12).
- 03/11/2026: skill **v2** = `backend/gpu_core` (đọc t7 + t10, cột theo header, cờ VTNet, danh sách thu hồi, xuất Excel) +
  CLI trong `.claude/skills/gpu-util-vtnet`. Cùng ngày lên **v2.1**: liên kết IP (`load_ip_links`, `apply_ip_links`, CLI `--ip-links`).
  39 test pass (34 chạy mọi nơi + 5 cần dữ liệu thật).
- 03/11/2026 (G1-M1): **v2.2** — parser chỉ nhận `don_vi` VTT/rỗng (bỏ dòng đơn vị khác + cảnh báo); `to_daily` gom mẫu
  theo giờ về ngày trước khi `server_stats`/`fleet_daily` tính (dữ liệu theo ngày: kết quả không đổi);
  `read_inventory` bỏ dòng IP sai định dạng (vd thống kê T7 dòng 131–135 `10.29.95.16/17`) **trước** khi kiểm trùng IP.
- 03/11/2026 (G1-M2): **v2.3** — `RuleParams` (ngưỡng VTNet, bursty, tải cao, dữ liệu mỏng thành tham số, mặc định giữ nguyên);
  `server_stats` / `fleet_daily(weight="gpu")` tính gộp theo nhóm (nhanh ~5–10 lần, đã đối chiếu giống hệt bản cũ trên T10 + fixture).
- `samples/` chứa 4 file thật (VTNet T7, T10; inventory T7, T10) — **dữ liệu nội bộ, không đẩy lên repo công khai**.

## 9. Quyết định đã chốt & điều chưa biết (chi tiết PLAN §13)

Đã chốt 03/11/2026: 9 server RTX6000 là cùng máy (khác IP), ghép theo IP tăng dần, giữ cờ "chưa xác nhận cặp" ·
GĐ1 trang quản trị đơn giản chạy native trong WSL (chưa Docker), GĐ2 Docker Compose + VM · tài khoản riêng của công cụ (không SSO, GĐ2) ·
đầu mối đăng nhập bằng tài khoản admin cấp, mặc định chỉ thấy server của mình (admin mở rộng từng tài khoản).

Chưa biết: VTNet có chuyển sang dữ liệu theo giờ · `pivot_value` là kỳ nào · công thức thu hồi chính thức của VTNet ·
có cần ngưỡng riêng cho GPU và VRAM.
