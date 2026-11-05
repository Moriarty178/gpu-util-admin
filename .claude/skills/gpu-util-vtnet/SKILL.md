---
name: gpu-util-vtnet
description: Đánh giá tải GPU từ file utilization VTNet (format T10 server_raw hoặc T7 cũ): map IP sang thống kê server TTCN-VTT, phân vùng an toàn/cảnh báo/nguy hiểm theo ngưỡng T, ghi nhận xét, so sánh kỳ.
---

# gpu-util-vtnet v2 — Đánh giá tải GPU VTNet (TTCN-VTT)

Một lệnh: ánh xạ IP → phân vùng → nhận xét từng server → tổng hợp theo đầu mối → xuất file thống kê đã gắn đánh giá.
Logic nằm trong `scripts/gpu_core/` — **bản sao** của `backend/gpu_core` trong project `gpu-util-admin`
(nguồn chân lý là backend; đồng bộ bằng `scripts/sync_skill.sh`). Không sửa logic trực tiếp ở đây.

## Khi nào dùng
Người dùng đưa file utilization VTNet + file `Thong_ke_toan_bo_server_TTCN_VTT.xlsx` và muốn: phân vùng tải,
danh sách server nguy cơ thu hồi, cập nhật cột đánh giá, so sánh với kỳ trước, hoặc kiểm tra nhanh một file
VTNet mới trước khi nhập vào công cụ quản trị. Không dùng cho file không có số liệu gpu/mem theo IP.

## Định dạng đầu vào (tự nhận diện)
| Schema | Sheet thô | Cột thô | Sheet overview |
|---|---|---|---|
| **t10** (chuẩn hiện hành) | `server_raw` | host_ip, gpu, mem, gpu_type, date_hour, don_vi | `VTT_KPI_overview`, header ở **dòng 3**: Row Labels, Average of gpu_core (%), Average of gpu_mem (%), có dòng Grand Total |
| **t7** (cũ) | `VTT_GPU_Server_RAW` | date, instance, gpu_type, gpu_util, gpu_memory, don_vi | `VTT_KPI_overview` header dòng 1 |

Sheet `DS đã thu` (nếu có) = server VTNet đã thu hồi. Sheet `HSSD theo ngay VTT` (từ T8) = TB toàn bộ server theo ngày
VTNet tự tính → `wb.daily`, đối soát bằng `gpu_core.validate_daily(wb.raw, wb.daily)` (không nhập). Các sheet khác
(VAI, VIC, pivot_value, Sheet1) bị bỏ qua. `wb.missing_columns` = cột chuẩn của sheet thô mà file thiếu (vd `don_vi`).
File thống kê: sheet `Thống kê chi tiết`, cột tìm theo **tên header** (IP, Đầu mối sử dụng, Dịch vụ/nghiệp vụ...).
Nếu chưa có cột "Đánh giá..." thì thêm vào cuối.

## Cách chạy
Xác định thư mục của skill này (`<SKILL_DIR>`; trong project là `.claude/skills/gpu-util-vtnet`, trên claude.ai
là thư mục skill được mount). Chạy:

```bash
python <SKILL_DIR>/scripts/analyze_gpu_util.py \
  --vtnet <file_VTNet.xlsx> --inventory <Thong_ke_toan_bo_server_TTCN_VTT.xlsx> \
  --out <KetQua.xlsx> [--threshold 40] [--start YYYY-MM-DD --end YYYY-MM-DD] [--history gpu_util_history.csv] \
  [--ip-links ip_links.csv]
```
- `--ip-links`: CSV `inventory_ip,vtnet_ip,pair_confirmed,reason` cho máy có IP khác nhau giữa thống kê và VTNet.
  Trong project dùng `backend/seeds/ip_links.csv` (9 server RTX6000 `10.207.188.1–9` ↔ `10.205.36.51–59`, đã xác nhận
  cùng máy; thứ tự từng cặp chưa xác nhận). Trên claude.ai: nhắc người dùng upload file này nếu có.
- `--threshold` mặc định 40. `--start/--end` mặc định = toàn bộ kỳ trong file (T10 có cả ngày tràn 01 tháng sau —
  khớp tuyệt đối với `VTT_KPI_overview`). Nhãn kỳ = tháng chiếm nhiều ngày nhất.
- `--history`: CSV snapshot theo kỳ để so sánh (trên claude.ai file không tự lưu giữa các chat → người dùng tải về và upload lại).
- Trên claude.ai: đầu vào ở `/mnt/user-data/uploads/`, ghi ra `/mnt/user-data/outputs/`, rồi gửi file kết quả cho người dùng.
- Phụ thuộc: `pandas`, `openpyxl`.

## Luật (không tự ý đổi)
- Vùng, 1 ngưỡng T, so sánh `<=`: gpu≤T **và** mem≤T → **Nguy hiểm**; đúng 1 trong 2 ≤T → **Cảnh báo**; cả 2 >T → **An toàn**.
  Tùy chọn `--zone-metric gpu|mem`: chỉ xét 1 chỉ số → 2 vùng (chỉ số đó ≤T → **Nguy hiểm**, còn lại → **An toàn**,
  không có Cảnh báo); ngày nguy hiểm/chuỗi ngày đếm theo cùng chế độ. Mặc định `both` = luật 3 vùng.
- Mẫu hình: idle / bursty_idle (TB ≤T nhưng đỉnh ngày ≥70%) / memory_bound / compute_bound / high_load (cả 2 ≥80%) / healthy.
- Cờ **THẤP TẢI VTNet**: gpu<10 **và** mem<10 (so sánh `<`), suy luận từ sheet `pivot_value` file T10 — khớp 250/250 server.
- Dữ liệu mỏng: số ngày có số liệu / số ngày trong khoảng < 0.8.
- `gpu` = % SM có kernel chạy (không phải cường độ tính toán) → luôn đọc kèm `mem` (VRAM).

## Đầu ra
1. `Thống kê chi tiết`: cột Đánh giá + 6 cột phụ (Vùng tô màu, util TB, VRAM TB, đỉnh util, số ngày, cờ VTNet).
2. Sheet `Đánh giá tải VTNet` (đầu file): vùng×đầu mối, mẫu hình, so sánh kỳ trước, lỗ hổng ánh xạ, danh sách đã thu hồi.
Các sheet/công thức khác giữ nguyên (đặt fullCalcOnLoad để Excel tự tính lại).

## Luôn nói với người dùng
- File chỉ có GPU, không có CPU/RAM → kết quả là xấp xỉ luật thu hồi của VTNet.
- Số IP lệch 2 chiều (VTNet-only / inventory-only, bao nhiêu đã bị thu hồi) — để họ cập nhật file thống kê.
- Cảnh báo dữ liệu (dòng bị bỏ, giá trị ngoài 0–100, dữ liệu theo giờ).

## Số tham chiếu để tự kiểm (ngưỡng 40, toàn kỳ file)
- T7 + thống kê T7: map 77 → An toàn 15 / Cảnh báo 44 / Nguy hiểm 18.
- T10 + thống kê T10: map 80 → An toàn 33 / Cảnh báo 38 / Nguy hiểm 9; VTNet-only 12; inventory-only 57.
- T10 + thống kê T10 + `--ip-links` 9 RTX6000: map 89 → 34 / 45 / 10; VTNet-only 3; inventory-only 48 (13 đã thu hồi).
