# CHECKLIST NGHIỆM THU CUỐI – DEMO CẢNH BÁO Ô NHIỄM NƯỚC

## A. Hạ tầng và Docker

| STT | Hạng mục | Kết quả mong đợi | Đạt/Không |
|---|---|---|---|
| 1 | `docker compose up --build` chạy thành công | 5 service lên đầy đủ | |
| 2 | PostgreSQL healthy | Container `db` healthy | |
| 3 | API sẵn sàng | Truy cập `/health` trả về `backend=UP` | |
| 4 | Worker sẵn sàng | `/health` hiển thị `SEPARATE_WORKER` | |
| 5 | Simulator sẵn sàng | Mở được `http://localhost:8090/` | |
| 6 | Dashboard sẵn sàng | Mở được `http://localhost:8501/` | |

## B. Webhook và hàng đợi

| STT | Hạng mục | Kết quả mong đợi | Đạt/Không |
|---|---|---|---|
| 1 | Gửi webhook bình thường | API trả `queued=true` | |
| 2 | Worker nhận event | Hàng đợi chuyển `PENDING -> PROCESSING -> DONE` | |
| 3 | Event lỗi được ghi nhận | Nếu lỗi, trạng thái `FAILED` có message | |
| 4 | Xử lý idempotent | Cùng `event_id` không tạo trùng dữ liệu | |

## C. Sensor và làm sạch dữ liệu

| STT | Hạng mục | Kết quả mong đợi | Đạt/Không |
|---|---|---|---|
| 1 | Đủ 04 sensor | pH, COD, TSS, NH4 | |
| 2 | Timestamp UTC | Bản ghi lưu UTC | |
| 3 | Xử lý null | Sensor `null` không gây crash | |
| 4 | Xử lý outlier | Giá trị vô lý được gắn cờ `outlier` | |
| 5 | Xử lý spike | Biến động đột ngột được gắn cờ `spike` | |

## D. Camera / Video source

| STT | Hạng mục | Kết quả mong đợi | Đạt/Không |
|---|---|---|---|
| 1 | Snapshot HTTP hoạt động | Mở được `/camera/clear/snapshot.jpg` | |
| 2 | MJPEG stream hoạt động | Mở được `/camera/clear/stream.mjpg` | |
| 3 | Video MP4 mock hoạt động | Mở được `/camera/clear/video.mp4` | |
| 4 | Scene polluted hoạt động | Mở được snapshot/stream polluted | |

## E. AI Vision

| STT | Hạng mục | Kết quả mong đợi | Đạt/Không |
|---|---|---|---|
| 1 | ROI hợp lệ | Ảnh evidence có khung ROI | |
| 2 | Tính % vùng bất thường | Có chỉ số `abnormal_area_percent` | |
| 3 | Tính độ đậm/đục | Có `turbidity_score` | |
| 4 | Tính mức chuyển động | Có `motion_score` | |
| 5 | Có BBox | Ảnh polluted có vùng khoanh đỏ | |

## F. Fusion logic 3 tầng

| STT | Tình huống | Kết quả mong đợi | Đạt/Không |
|---|---|---|---|
| 1 | Bình thường | `NORMAL` | |
| 2 | Sensor bất thường + camera bình thường | `CHECK_DEVICE` | |
| 3 | Sensor bất thường + camera bất thường | `CRITICAL_ALERT` | |
| 4 | Null/outlier + camera bình thường | `CHECK_DEVICE` hoặc `VERIFY_CAMERA` hợp lý | |

## G. Dashboard trình diễn

| STT | Hạng mục | Kết quả mong đợi | Đạt/Không |
|---|---|---|---|
| 1 | Hiển thị trạng thái hệ thống | Có backend, DB, worker, queue | |
| 2 | Hiển thị 04 sensor | Có metric card từng sensor | |
| 3 | Hiển thị live snapshot | Có ảnh hiện tại từ camera simulator | |
| 4 | Hiển thị evidence | Có ảnh gốc + ảnh khoanh vùng | |
| 5 | Hiển thị hàng đợi worker | Có bảng queue | |
| 6 | Hiển thị lịch sử cảnh báo | Có explain text và acknowledge | |
| 7 | Hiển thị thống kê | Có day/month/quarter | |

## H. Kịch bản demo cuối

| STT | Kịch bản | Kết quả mong đợi | Đạt/Không |
|---|---|---|---|
| 1 | Nạp trạng thái bình thường | Dashboard xanh | |
| 2 | Kịch bản 1 – lỗi cảm biến | Dashboard vàng, `CHECK_DEVICE` | |
| 3 | Kịch bản 2 – ô nhiễm thật | Dashboard đỏ, `CRITICAL_ALERT` | |
| 4 | Kịch bản 3 – null/outlier | Hệ thống không crash, cảnh báo hợp lý | |

## I. Hồ sơ trình diễn nên chuẩn bị kèm

- 01 file ZIP mã nguồn Step 3
- 01 slide 5–7 phút
- 01 checklist nghiệm thu đã tích
- 01 kịch bản demo ngắn theo thứ tự: bình thường → lỗi cảm biến → ô nhiễm thật
- 01 phương án fallback nếu camera thật không kết nối được: dùng simulator snapshot/stream/video
