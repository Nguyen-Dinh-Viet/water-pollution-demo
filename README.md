# Water Pollution Demo – Step 3

Bản Step 3 nâng project lên mức gần hoàn thiện để demo trước hội đồng:

- Worker tách riêng thật sự khỏi API
- Webhook chỉ nhận và xếp hàng, worker xử lý bất đồng bộ
- Camera source thật hơn: snapshot HTTP + MJPEG stream + video MP4 mock
- Dashboard có hàng đợi worker, live snapshot, evidence, lịch sử, thống kê
- Có checklist nghiệm thu cuối trong `CHECKLIST_NGHIEM_THU.md`

## Kiến trúc

- `api`: FastAPI backend
- `worker`: xử lý event riêng
- `dashboard`: Streamlit UI
- `simulator`: EnviSoft webhook simulator + camera snapshot/stream/video
- `db`: PostgreSQL

## Chạy project

```bash
docker compose down -v
docker compose up --build
```

## Địa chỉ

- API: http://localhost:8000
- Dashboard: http://localhost:8501
- Simulator: http://localhost:8090

## Kịch bản demo

1. Bình thường
2. Lỗi cảm biến
3. Ô nhiễm thật
4. Null / outlier

## Điểm nâng cấp chính ở Step 3

### 1. Worker xử lý tách riêng
- Webhook trả về trạng thái `queued`
- Worker đọc từ bảng `webhook_events_raw`
- Có hàng đợi `PENDING / PROCESSING / DONE / FAILED`

### 2. Camera source thật hơn
- Snapshot: `/camera/{scene}/snapshot.jpg`
- MJPEG stream: `/camera/{scene}/stream.mjpg`
- Video MP4: `/camera/{scene}/video.mp4`

### 3. Bằng chứng và truy vết
- Ảnh gốc + ảnh khoanh ROI/BBox
- Explain log trong bảng alert
- Theo dõi hàng đợi worker trong dashboard

## Ghi chú

- Sau khi đổi schema DB, luôn chạy lại với `docker compose down -v`
- Nếu worker chưa xử lý kịp ngay sau khi bấm mock, dashboard sẽ tự hiện event trong vài giây tiếp theo
