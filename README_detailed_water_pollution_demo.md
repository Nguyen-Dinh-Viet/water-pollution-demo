# Hệ thống demo cảnh báo ô nhiễm nước bằng sensor + camera

## 1. Giới thiệu

Đây là project demo giám sát ô nhiễm nước theo thời gian gần thực, kết hợp **dữ liệu cảm biến**, **ảnh/video hiện trường**, **luật suy diễn 3 tầng**, **worker xử lý bất đồng bộ**, và **dashboard trình diễn**.

Project được thiết kế để phục vụ các mục tiêu sau:

- mô phỏng dữ liệu từ một trạm quan trắc môi trường;
- nhận dữ liệu theo cơ chế **webhook**;
- xử lý dữ liệu cảm biến có thể chứa **null / outlier / spike**;
- kích hoạt phân tích camera khi dữ liệu bất thường;
- hợp nhất kết quả sensor và vision để đưa ra kết luận vận hành;
- lưu lịch sử xử lý, cảnh báo và bằng chứng ảnh;
- hiển thị mọi thứ trên dashboard phục vụ báo cáo/demonstration.

Bản hiện tại của project đang chạy theo mô hình:

- **1 trạm**: `ST001`
- **4 sensor**: `pH`, `COD`, `TSS`, `NH4`
- **timestamp chuẩn UTC**
- **backend**: FastAPI
- **dashboard**: Streamlit
- **database**: PostgreSQL
- **simulator**: FastAPI mô phỏng EnviSoft + camera snapshot / MJPEG / video
- **worker**: tiến trình riêng đọc queue và xử lý event

---

## 2. Bài toán mà project giải quyết

Hệ thống hướng tới một bài toán rất thực tế:

> Khi dữ liệu cảm biến tại trạm quan trắc vượt ngưỡng, hệ thống không nên kết luận ngay là ô nhiễm thật. Thay vào đó, hệ thống cần dùng ảnh/video hiện trường để kiểm tra chéo, từ đó giảm báo động giả và đưa ra kết luận hợp lý hơn.

### Logic vận hành hiện tại

Hệ thống dùng logic 3 tầng:

### Tầng 1 – Sensor rule engine
Đánh giá dữ liệu 4 sensor để phân loại:

- `NORMAL`
- `SUSPECT`
- `ALERT`

### Tầng 2 – Vision engine
Khi sensor bất thường, hệ thống phân tích ROI của ảnh/video để tính:

- `% diện tích vùng màu bất thường`
- `mức độ đậm/đục`
- `mức độ chuyển động`

Kết quả vision được phân loại:

- `NORMAL`
- `ABNORMAL`
- `UNKNOWN`

### Tầng 3 – Fusion engine
Hợp nhất sensor + vision để đưa ra kết luận cuối cùng:

- `NORMAL`
- `CHECK_DEVICE`
- `SUSPICIOUS`
- `VERIFY_CAMERA`
- `CRITICAL_ALERT`

Dashboard đã ánh xạ các trạng thái này sang tiếng Việt để trình diễn dễ hơn.

---

## 3. Chức năng chính của project

### 3.1. Nhận dữ liệu sensor bằng webhook
API backend nhận payload từ simulator hoặc nguồn ngoài qua endpoint:

```text
POST /api/v1/webhooks/envisoft/sensor
```

Dữ liệu được xếp hàng vào bảng `webhook_events_raw`, không xử lý trực tiếp trong request để tránh block API.

### 3.2. Worker xử lý bất đồng bộ
Worker định kỳ đọc event trong queue theo trạng thái:

- `PENDING`
- `PROCESSING`
- `DONE`
- `FAILED`

Khi nhận event, worker sẽ:

1. làm sạch dữ liệu sensor;
2. phát hiện null/outlier/spike;
3. tính trạng thái sensor;
4. nếu cần thì gọi vision engine;
5. hợp nhất kết quả;
6. lưu DB;
7. sinh cảnh báo và bằng chứng.

### 3.3. Vision engine
Vision engine đang dùng OpenCV để:

- cắt ROI;
- chuyển đổi HSV / grayscale;
- phát hiện vùng tối / đục;
- tính abnormal area %;
- tính turbidity score;
- tính motion score;
- tạo ảnh gốc + ảnh annotated có ROI/BBox.

### 3.4. Dashboard Streamlit
Dashboard cung cấp:

- trạng thái hệ thống;
- card sensor theo event mới nhất;
- kết luận cuối cùng;
- snapshot camera hiện tại;
- ảnh gốc / ảnh AI vision;
- hàng đợi worker;
- dòng sự kiện;
- lịch sử cảnh báo;
- thống kê theo ngày / tháng / quý.

### 3.5. Forecast + NRMSE
Codebase hiện đã có khung cho dự báo sensor và đánh giá:

- `naive_last`
- `moving_avg_3`
- `RMSE`
- `MAE`
- `NRMSE`

NRMSE đang tính theo công thức:

```text
NRMSE = RMSE / (max(y_obs) - min(y_obs))
```

Lưu ý: trong snapshot hiện tại, module forecast đã được thêm file nhưng vẫn còn một số điểm chưa nối hoàn toàn vào runtime. Xem thêm mục **Known issues** ở cuối README.

---

## 4. Kiến trúc tổng thể

```text
[Simulator / EnviSoft giả lập]
        |
        |  webhook POST sensor data
        v
[FastAPI API]
  - nhận webhook
  - xác thực token
  - enqueue raw event
        |
        v
[PostgreSQL]
  - webhook_events_raw
  - sensor_readings
  - vision_results
  - alerts
  - alert_evidences
  - forecast_*
        ^
        |
[Worker]
  - claim event
  - clean sensor
  - rule engine
  - vision engine
  - fusion engine
  - save DB
        |
        v
[Dashboard Streamlit]
  - latest status
  - queue
  - events
  - alerts
  - stats
  - (chuẩn bị cho forecast)
```

---

## 5. Thành phần trong Docker Compose

Project chạy bằng `docker compose` với 5 service chính.

### 5.1. `db`
- image: `postgres:16`
- cổng host: `5432`
- khởi tạo schema từ `db/init.sql`

### 5.2. `api`
- build từ `./backend`
- cổng host: `8000`
- cung cấp REST API cho webhook, latest state, alerts, stats, queue

### 5.3. `worker`
- build từ `worker/Dockerfile`
- poll queue từ DB
- xử lý event độc lập với API

### 5.4. `dashboard`
- build từ `./dashboard`
- cổng host: `8501`
- giao diện trình diễn

### 5.5. `simulator`
- build từ `./simulator`
- cổng host: `8090`
- tạo sensor payload, snapshot, MJPEG stream, video route

---

## 6. Cấu trúc thư mục

```text
water-pollution-demo/
├─ .env
├─ docker-compose.yml
├─ README.md
├─ CHECKLIST_NGHIEM_THU.md
│
├─ db/
│  └─ init.sql
│
├─ backend/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ app/
│     ├─ main.py
│     ├─ core/
│     │  ├─ config.py
│     │  └─ db.py
│     ├─ api/
│     │  └─ forecast.py
│     ├─ schemas/
│     │  └─ webhook.py
│     └─ services/
│        ├─ cleaning_service.py
│        ├─ evaluation_service.py
│        ├─ event_processor.py
│        ├─ forecast_service.py
│        ├─ fusion_engine.py
│        ├─ persistence_service.py
│        ├─ rule_engine.py
│        └─ vision_service.py
│
├─ dashboard/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ streamlit_app.py
│
├─ simulator/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  ├─ envisoft_simulator.py
│  ├─ media/
│  │  ├─ manifest.json
│  │  ├─ normal/
│  │  └─ polluted/
│  └─ mock_data/
│
├─ worker/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ worker.py
│
└─ data/
   ├─ frames/
   └─ annotated/
```

---

## 7. Ý nghĩa của từng file chính

## 7.1. `backend/app/main.py`
Đây là file entry point của backend. Hiện file này đảm nhiệm:

- tạo app FastAPI;
- mount static `/files` để phục vụ ảnh evidence;
- cung cấp endpoint health;
- cung cấp endpoint webhook ingest;
- trả dữ liệu `latest`, `history`, `events`, `alerts`, `stats`, `queue`;
- cung cấp route trigger mock scenario.

## 7.2. `backend/app/services/cleaning_service.py`
Xử lý làm sạch dữ liệu sensor trước khi đưa vào rule engine.

Nhiệm vụ chính:
- nhận biết `null`;
- đánh dấu outlier theo domain rule;
- đánh dấu spike theo biến động lịch sử.

## 7.3. `backend/app/services/rule_engine.py`
Đánh giá dữ liệu sensor so với threshold trong DB để kết luận trạng thái tầng 1.

## 7.4. `backend/app/services/vision_service.py`
Phân tích ảnh/video:
- đọc frame từ snapshot/camera/mock;
- tính abnormal area, turbidity, motion;
- trích bbox;
- lưu ảnh gốc và annotated vào `/app/data`.

## 7.5. `backend/app/services/fusion_engine.py`
Hợp nhất sensor + vision để đưa ra kết luận cuối cùng và gợi ý thao tác cho người vận hành.

## 7.6. `backend/app/services/event_processor.py`
Đây là lõi xử lý của worker. Flow hiện tại:

1. lấy station config;
2. reset output cũ của event;
3. clean sensor;
4. save sensor readings;
5. evaluate sensor state;
6. nếu cần thì gọi vision;
7. save vision;
8. fuse;
9. save alert.

## 7.7. `backend/app/services/persistence_service.py`
Bao gồm các hàm thao tác DB như:
- enqueue event;
- claim event;
- mark done / failed;
- save readings;
- save vision;
- save alert;
- fetch thresholds / station;
- health summary.

## 7.8. `worker/worker.py`
Tiến trình poll queue từ DB theo chu kỳ `WORKER_POLL_SECONDS`, rồi gọi `process_event_payload()`.

## 7.9. `simulator/envisoft_simulator.py`
Simulator đóng vai trò vừa là nguồn webhook, vừa là nguồn camera mô phỏng.

Hiện file này đã có:
- scene `clear` và `polluted`;
- snapshot route;
- MJPEG stream route;
- route phát video;
- các scenario sensor: `normal`, `sensor_fault`, `real_pollution`, `null_outlier`;
- khung load `manifest.json`.

## 7.10. `dashboard/streamlit_app.py`
Dashboard trình diễn. Luồng hiện tại:

- gọi `/health`;
- gọi `/latest`;
- gọi `/history`;
- gọi `/alerts`;
- gọi `/events`;
- gọi `/queue`;
- render theo tab.

## 7.11. `db/init.sql`
Khởi tạo toàn bộ schema và seed station/sensor mặc định.

---

## 8. Biến môi trường

File `.env` hiện tại của project:

```env
APP_ENV=dev
API_HOST=0.0.0.0
API_PORT=8000
DATABASE_URL=postgresql://waterdemo:waterdemo_pass@db:5432/waterdemo
ADMIN_API_KEY=demo_admin_key_2026
WEBHOOK_TOKEN=envisoft_webhook_st001_2026
DEFAULT_TIMEZONE=UTC
FRAME_STORAGE_PATH=/app/data/frames
ANNOTATED_STORAGE_PATH=/app/data/annotated
DEFAULT_CAMERA_URL=http://simulator:8090/camera/clear/stream.mjpg
DEFAULT_SNAPSHOT_URL=http://simulator:8090/camera/clear/snapshot.jpg
STREAMLIT_BACKEND_URL=http://api:8000
SIMULATOR_TARGET_WEBHOOK=http://api:8000/api/v1/webhooks/envisoft/sensor
WORKER_POLL_SECONDS=1.0
WORKER_NAME=worker-main
```

### Giải thích nhanh
- `DATABASE_URL`: chuỗi kết nối PostgreSQL nội bộ Docker
- `ADMIN_API_KEY`: dùng cho các route admin / mock trigger / acknowledge
- `WEBHOOK_TOKEN`: token mà simulator dùng để đẩy sensor webhook
- `DEFAULT_CAMERA_URL`, `DEFAULT_SNAPSHOT_URL`: fallback camera source
- `STREAMLIT_BACKEND_URL`: dashboard gọi backend qua hostname Docker `api`
- `SIMULATOR_TARGET_WEBHOOK`: simulator đẩy về backend
- `WORKER_POLL_SECONDS`: chu kỳ worker quét queue

---

## 9. Schema dữ liệu chính trong PostgreSQL

### 9.1. `stations`
Lưu cấu hình trạm:
- station code/name
- timezone
- camera_url
- snapshot_url
- ROI (`roi_x`, `roi_y`, `roi_w`, `roi_h`)

### 9.2. `station_sensors`
Lưu 4 sensor của trạm và threshold tương ứng.

### 9.3. `webhook_events_raw`
Lưu raw payload và trạng thái xử lý queue.

### 9.4. `sensor_readings`
Lưu từng sensor reading sau khi clean.

### 9.5. `vision_results`
Lưu kết quả vision theo event:
- abnormal area
- turbidity
- motion
- bbox JSON
- đường dẫn ảnh raw/annotated

### 9.6. `alerts`
Lưu kết luận cuối cùng của event.

### 9.7. `alert_evidences`
Lưu bằng chứng ảnh gắn với từng alert.

### 9.8. `forecast_runs`, `forecast_predictions`, `forecast_metrics`
Khung lưu trữ cho bài toán dự báo và chỉ số đánh giá.

---

## 10. Các sensor và threshold mặc định

Project seed sẵn một trạm `ST001` với 4 sensor:

| Sensor | Ý nghĩa | Ngưỡng mặc định |
|---|---|---|
| `ph`  | độ pH | 5.5 – 9.0 |
| `cod` | Chemical Oxygen Demand | max 75.0 mg/L |
| `tss` | Total Suspended Solids | max 100.0 mg/L |
| `nh4` | Amoni | max 10.0 mg/L |

---

## 11. Media thật và mock

Project hiện có 2 nhóm media:

### 11.1. `simulator/mock_data/`
Dùng cho các snapshot/video mock cũ.

### 11.2. `simulator/media/`
Là nơi bắt đầu chứa media thật hơn, chia thành:
- `normal/`
- `polluted/`
- `manifest.json`

`manifest.json` dùng để gắn metadata cho từng file:
- nguồn (`source`)
- tiêu đề (`title`)
- license
- scenario

Lưu ý: trong snapshot code hiện tại, simulator đã bắt đầu load `manifest.json`, nhưng chưa chuyển hẳn sang dùng `simulator/media/` trong toàn bộ pipeline.

---

## 12. Cách chạy project

## 12.1. Điều kiện
Máy cần có:
- Docker
- Docker Compose plugin

## 12.2. Chạy từ đầu
Tại thư mục gốc project:

```bash
docker compose down -v --remove-orphans
docker compose up --build
```

### Vì sao nên dùng `down -v`
Do project dùng `db/init.sql` để tạo schema, nên nếu bạn đã thay đổi schema mà không xóa volume cũ thì DB sẽ không khởi tạo lại đúng.

## 12.3. Địa chỉ sau khi chạy
- API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8501`
- Simulator: `http://localhost:8090`

---

## 13. Luồng chạy end-to-end

### Bước 1
Simulator sinh một payload sensor.

### Bước 2
Payload được gửi tới backend bằng webhook.

### Bước 3
Backend xác thực token và lưu raw event vào `webhook_events_raw` với trạng thái `PENDING`.

### Bước 4
Worker claim event, chuyển trạng thái `PROCESSING`.

### Bước 5
Worker clean sensor data và lưu `sensor_readings`.

### Bước 6
Rule engine xác định `sensor_state`.

### Bước 7
Nếu sensor bất thường, worker gọi vision engine để phân tích ảnh/video.

### Bước 8
Vision result được lưu vào `vision_results`.

### Bước 9
Fusion engine sinh `final_state` và lưu `alerts`, `alert_evidences`.

### Bước 10
Dashboard hiển thị kết quả mới nhất.

---

## 14. API chính hiện có

## 14.1. Health
```http
GET /health
```

## 14.2. Danh sách trạm
```http
GET /api/v1/stations
```

## 14.3. Cấu hình trạm
```http
GET /api/v1/config/stations/{station_code}
Header: X-API-Key
```

## 14.4. Webhook sensor
```http
POST /api/v1/webhooks/envisoft/sensor
Header: X-Webhook-Token
```

## 14.5. Dữ liệu mới nhất của trạm
```http
GET /api/v1/stations/{station_code}/latest
```

## 14.6. Lịch sử readings
```http
GET /api/v1/stations/{station_code}/history
```

## 14.7. Danh sách event
```http
GET /api/v1/stations/{station_code}/events
```

## 14.8. Lịch sử alert
```http
GET /api/v1/stations/{station_code}/alerts
```

## 14.9. Thống kê alert
```http
GET /api/v1/stations/{station_code}/stats?group_by=day|month|quarter
```

## 14.10. Acknowledge alert
```http
POST /api/v1/stations/{station_code}/ack-alert/{alert_id}
Header: X-API-Key
```

## 14.11. Queue trạng thái worker
```http
GET /api/v1/stations/{station_code}/queue
```

## 14.12. Snapshot camera hiện tại
```http
GET /api/v1/stations/{station_code}/camera/current.jpg
```

## 14.13. Trigger mock scenario
```http
POST /api/v1/stations/{station_code}/mock/normal
POST /api/v1/stations/{station_code}/mock/scenario-1
POST /api/v1/stations/{station_code}/mock/scenario-2
POST /api/v1/stations/{station_code}/mock/scenario-3
Header: X-API-Key
```

## 14.14. Forecast route
Codebase hiện đã có route forecast trong file riêng, nhưng cần nối hoàn chỉnh vào `main.py` để dùng ổn định trong runtime. Xem mục **Known issues**.

---

## 15. Kịch bản demo hiện có

### 15.1. `normal`
Mô phỏng dữ liệu bình thường, camera sạch.

Kỳ vọng:
- không có cảnh báo nghiêm trọng;
- dashboard hiển thị trạng thái bình thường.

### 15.2. `scenario-1` – lỗi cảm biến
Mô phỏng COD tăng cao nhưng hình ảnh không bất thường rõ.

Kỳ vọng:
- `CHECK_DEVICE`
- hệ thống nghiêng về kiểm tra thiết bị / sensor.

### 15.3. `scenario-2` – ô nhiễm thật
Mô phỏng nhiều sensor vượt ngưỡng và camera polluted.

Kỳ vọng:
- `CRITICAL_ALERT`
- có ảnh evidence, BBox và explain text.

### 15.4. `scenario-3` – null / outlier
Mô phỏng một sensor null và một sensor outlier.

Kỳ vọng:
- hệ thống không crash;
- kết luận thận trọng, ưu tiên kiểm tra thiết bị hoặc xác minh thêm.

---

## 16. Dashboard hiện hiển thị gì

### 16.1. Sidebar
- nút nạp trạng thái bình thường;
- nút chạy 3 kịch bản mock;
- toggle tự làm mới.

### 16.2. Hàng trạng thái tổng quan
- Backend / DB / worker
- queue pending / failed
- trạng thái hiện tại
- tổng webhook / pending / alerts

### 16.3. Panel trái
- thông tin trạm
- 4 sensor gần nhất
- kết luận hiện tại
- biểu đồ xu hướng sensor gần đây

### 16.4. Panel phải
- ảnh snapshot hiện tại
- ảnh AI vision (annotated + raw)
- abnormal area
- turbidity
- motion
- bbox count

### 16.5. Tabs bên dưới
- Hàng đợi worker
- Dòng sự kiện
- Lịch sử cảnh báo
- Thống kê

Lưu ý: tab **Dự báo & NRMSE** chưa được render trong snapshot hiện tại, dù code backend forecast đã bắt đầu xuất hiện.

---

## 17. Forecast và NRMSE

## 17.1. File đã có
- `backend/app/services/forecast_service.py`
- `backend/app/services/evaluation_service.py`
- `backend/app/api/forecast.py`
- bảng `forecast_*` trong `db/init.sql`

## 17.2. Các baseline model
### `naive_last`
Dự báo điểm kế tiếp bằng giá trị cuối cùng của chuỗi lịch sử.

### `moving_avg_3`
Dự báo bằng trung bình 3 điểm gần nhất.

## 17.3. Các metric
- RMSE
- MAE
- NRMSE

## 17.4. Công thức NRMSE
```text
NRMSE = RMSE / (max(y_obs) - min(y_obs))
```

## 17.5. Trạng thái hiện tại
Khối forecast đang ở mức **đã có service + schema + route file**, nhưng chưa được nối hoàn chỉnh vào app runtime. Xem mục **Known issues** để sửa triệt để.

---

## 18. Các lệnh hữu ích khi vận hành

## 18.1. Xem log tất cả service
```bash
docker compose logs -f
```

## 18.2. Xem riêng backend
```bash
docker compose logs -f api
```

## 18.3. Xem riêng worker
```bash
docker compose logs -f worker
```

## 18.4. Xem riêng dashboard
```bash
docker compose logs -f dashboard
```

## 18.5. Xem riêng simulator
```bash
docker compose logs -f simulator
```

## 18.6. Build sạch lại toàn bộ
```bash
docker compose down -v --remove-orphans
docker compose build --no-cache
docker compose up
```

---

## 19. Troubleshooting thường gặp

### 19.1. API lên nhưng dashboard không hiện ảnh
Nguyên nhân hay gặp:
- cache trình duyệt;
- simulator chưa lên;
- worker chưa xử lý event;
- snapshot URL nội bộ chưa đọc được.

Cách xử lý:
- hard refresh trình duyệt;
- kiểm tra `http://localhost:8090`;
- kiểm tra `docker compose logs -f simulator`;
- chạy lại scenario.

### 19.2. Forecast route không thấy trong `/docs`
Nguyên nhân hay gặp:
- chưa `include_router` trong `main.py`.

### 19.3. SQL lỗi khi lưu forecast
Nguyên nhân hay gặp:
- schema `forecast_runs` không khớp với code insert;
- DB volume cũ chưa reset.

### 19.4. Media thật không được worker đọc
Nguyên nhân hay gặp:
- chưa mount `./simulator/media:/app/media` trong `docker-compose.yml`.

### 19.5. Vision vẫn dùng ảnh mock cũ
Nguyên nhân hay gặp:
- simulator chưa chuyển toàn bộ từ `mock_data` sang `media/`;
- `event_processor.py` chưa truyền `media_file/media_meta` sang `vision_service.py`.

---

## 20. Tình trạng hiện tại của snapshot mã nguồn này

README này được viết dựa trên **snapshot project hiện tại**, nên dưới đây là các điểm cần biết để tránh hiểu nhầm.

### 20.1. Những phần đã ổn
- Docker compose và các service chính đã có đủ;
- backend, worker, dashboard, simulator, DB đều đã hiện diện;
- queue xử lý bất đồng bộ đã có;
- mock scenarios đã có;
- vision pipeline cơ bản đã có;
- dashboard core đã chạy được;
- forecast service và evaluation service đã bắt đầu được thêm vào.

### 20.2. Những phần vẫn còn mismatch trong snapshot hiện tại
1. `backend/app/api/forecast.py` đang là file chuyển tiếp, chưa sạch hoàn toàn.
2. `backend/app/main.py` chưa include router forecast.
3. `forecast_runs` trong `db/init.sql` chưa khớp hoàn toàn với `save_forecast_result()`.
4. `save_forecast_result()` đang lấy `fetchone()[0]`, không khớp kiểu `RealDictCursor`.
5. `simulator/envisoft_simulator.py` đã load `manifest.json` nhưng vẫn còn phụ thuộc `mock_data` ở nhiều route.
6. `docker-compose.yml` chưa mount `simulator/media` cho `api` và `worker`.
7. `schemas/webhook.py` chưa mở rộng field để chở `media_file`, `media_meta`, `video_url`, `scenario`.
8. `event_processor.py` chưa truyền media thật sang vision.
9. `vision_service.py` có `load_frame_from_media()` nhưng chưa được nối vào đường xử lý chính.
10. Dashboard chưa có tab `Dự báo & NRMSE` và chưa hiển thị metadata nguồn media.

### 20.3. Ý nghĩa của mục này
Project **không phải hỏng hoàn toàn**; ngược lại, phần lớn nền tảng đã có. Nhưng snapshot hiện tại là một bản đang ở giữa quá trình nâng cấp Step 4, nên cần thêm một lượt chỉnh đồng bộ để đạt trạng thái hoàn thiện.

---

## 21. Lộ trình hoàn thiện tiếp theo được khuyến nghị

Nếu tiếp tục phát triển project này, thứ tự nên là:

1. sửa xong toàn bộ module forecast;
2. nối router forecast vào backend;
3. hoàn tất chuyển simulator từ `mock_data` sang `media/`;
4. mount `simulator/media` trong compose;
5. mở rộng webhook schema để chở metadata media;
6. nối `event_processor -> vision_service` bằng `media_path`;
7. lưu `media_file/media_meta` trong `vision_results`;
8. hiển thị metadata media trên dashboard;
9. thêm tab `Dự báo & NRMSE` trên dashboard.

---

## 22. Quy trình demo được khuyến nghị

### Pha 1 – Giới thiệu hệ thống
- mở dashboard;
- mô tả 1 trạm, 4 sensor, camera mô phỏng, worker, DB.

### Pha 2 – Bình thường
- bấm “Nạp trạng thái bình thường”;
- chứng minh dashboard ổn định, queue hoạt động, không báo đỏ.

### Pha 3 – Lỗi cảm biến
- bấm “Kịch bản 1 – lỗi cảm biến”;
- giải thích sensor bất thường nhưng camera không quá bất thường;
- kết luận `CHECK_DEVICE`.

### Pha 4 – Ô nhiễm thật
- bấm “Kịch bản 2 – ô nhiễm thật”;
- cho hội đồng xem evidence annotated;
- giải thích abnormal area, turbidity, motion;
- kết luận `CRITICAL_ALERT`.

### Pha 5 – Null/outlier
- bấm “Kịch bản 3 – null/outlier”;
- chứng minh hệ thống không crash, xử lý dữ liệu lỗi có kiểm soát.

---

## 23. Tài liệu kèm theo

- `CHECKLIST_NGHIEM_THU.md`: checklist nghiệm thu trước khi trình diễn.
- `README.md`: tài liệu mô tả tổng thể project.

---

## 24. Gợi ý dùng README này

README này phù hợp cho 3 mục đích:

1. làm tài liệu giới thiệu repo;
2. làm tài liệu handover cho người khác tiếp tục code;
3. làm nền cho slide/demo trước hội đồng.

Nếu bạn đang chuẩn bị trình diễn, nên dùng README này cùng với:
- một checklist nghiệm thu đã tick;
- một kịch bản demo 5–7 phút;
- một danh sách known issues + hướng xử lý nếu được hỏi sâu.

