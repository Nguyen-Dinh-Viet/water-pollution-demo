import os
import time
from typing import Any, Dict

import pandas as pd
import requests
import streamlit as st

BACKEND_URL = os.getenv("STREAMLIT_BACKEND_URL", "http://api:8000")
API_KEY = os.getenv("ADMIN_API_KEY", "demo_admin_key_2026")
STATION_CODE = "ST001"

st.set_page_config(page_title="Water Pollution Demo", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    .block-container {max-width: 1500px; padding-top: 1.0rem; padding-bottom: 1rem;}
    h1 {font-size: 2.2rem !important; line-height: 1.15 !important; margin-bottom: 0.2rem !important;}
    h2 {font-size: 1.5rem !important; margin-top: 0.6rem !important;}
    h3 {font-size: 1.2rem !important;}
    p, li, div[data-testid="stMarkdownContainer"] p {font-size: 0.96rem !important;}
    div[data-testid="stMetricValue"] {font-size: 1.65rem !important;}
    div[data-testid="stMetricLabel"] {font-size: 0.95rem !important;}
    .small-note {font-size: 0.86rem; color: #666;}
    @media (min-width: 1200px) {
        .stApp {zoom: 0.92;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Hệ thống cảnh báo ô nhiễm nước – Demo 5★")
st.caption("Webhook UTC • 04 sensor • worker tách riêng • camera snapshot/MJPEG • fusion decision • lưu vết bằng chứng")

STATUS_LABELS = {
    "NORMAL": ("🟢", "Bình thường"),
    "CHECK_DEVICE": ("🟡", "Cần kiểm tra thiết bị"),
    "SUSPICIOUS": ("🟡", "Cảnh báo nghi ngờ"),
    "VERIFY_CAMERA": ("🟡", "Cần xác minh camera"),
    "CRITICAL_ALERT": ("🔴", "Cảnh báo nguy cấp"),
}


def get_json(path: str, method: str = "GET") -> Dict[str, Any] | list[dict]:
    headers = {"X-API-Key": API_KEY}
    url = f"{BACKEND_URL}{path}"
    resp = requests.request(method, url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_image_bytes(path: str) -> bytes | None:
    url = path if path.startswith("http") else f"{BACKEND_URL}{path}"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def show_backend_image(path: str, caption: str, use_container_width: bool = True):
    content = get_image_bytes(path)
    if content:
        st.image(content, caption=caption, use_container_width=use_container_width)
    else:
        st.warning(f"Không tải được hình ảnh: {caption}")


def trigger_scenario(path: str):
    response = get_json(path, method="POST")
    st.toast(f"Đã xếp hàng event {response.get('event_id', '') or response.get('body', {}).get('event_id', '')}")
    time.sleep(1.2)
    st.rerun()


with st.sidebar:
    st.subheader("Điều khiển demo")
    if st.button("Nạp trạng thái bình thường", use_container_width=True):
        trigger_scenario(f"/api/v1/stations/{STATION_CODE}/mock/normal")
    if st.button("Kịch bản 1 – lỗi cảm biến", use_container_width=True):
        trigger_scenario(f"/api/v1/stations/{STATION_CODE}/mock/scenario-1")
    if st.button("Kịch bản 2 – ô nhiễm thật", use_container_width=True):
        trigger_scenario(f"/api/v1/stations/{STATION_CODE}/mock/scenario-2")
    if st.button("Kịch bản 3 – null/outlier", use_container_width=True):
        trigger_scenario(f"/api/v1/stations/{STATION_CODE}/mock/scenario-3")
    st.divider()
    auto_refresh = st.toggle("Tự làm mới mỗi 5 giây", value=False)
    if st.button("Làm mới ngay", use_container_width=True):
        st.rerun()

health = requests.get(f"{BACKEND_URL}/health", timeout=10).json()
latest = get_json(f"/api/v1/stations/{STATION_CODE}/latest")
history = get_json(f"/api/v1/stations/{STATION_CODE}/history?limit=120")
alerts = get_json(f"/api/v1/stations/{STATION_CODE}/alerts?limit=12")
events = get_json(f"/api/v1/stations/{STATION_CODE}/events?limit=12")
queue = get_json(f"/api/v1/stations/{STATION_CODE}/queue?limit=12")

station = latest["station"]
alert = latest.get("latest_alert")
vision = latest.get("latest_vision")
thresholds = latest.get("thresholds", {})
health_summary = latest.get("health_summary", {})

status_label = (alert or {}).get("final_state", "NORMAL")
status_icon, status_text = STATUS_LABELS.get(status_label, ("⚪", status_label))

row1 = st.columns([1.55, 1.05, 0.85, 0.85, 0.85])
row1[0].success(
    f"Backend: {health['backend']} | CSDL: {health['database']} | Worker: Tách riêng\n\n"
    f"Hàng đợi chờ: {health['queue']['pending']} | Hàng đợi lỗi: {health['queue']['failed']}"
)
row1[1].metric("Trạng thái", f"{status_icon} {status_text}")
row1[2].metric("Webhook", int(health_summary.get("total_webhooks") or 0))
row1[3].metric("Đang chờ", int(health_summary.get("pending_webhooks") or 0))
row1[4].metric("Cảnh báo", int(health_summary.get("total_alerts") or 0))

left, right = st.columns([1.22, 1])
with left:
    st.subheader(f"Trạm {station['station_name']} ({station['station_code']})")
    st.markdown(
        f"<div class='small-note'>Múi giờ: {station['timezone']} • Camera mô phỏng nội bộ đang hoạt động • Ảnh chụp hiện tại được lấy qua backend proxy</div>",
        unsafe_allow_html=True,
    )
    sensors = latest.get("sensors", [])
    if sensors:
        metric_cols = st.columns(len(sensors))
        for idx, sensor in enumerate(sensors):
            code = sensor["sensor_code"]
            value = "NULL" if sensor["value"] is None else sensor["value"]
            flags = []
            if sensor["is_null"]:
                flags.append("null")
            if sensor["is_outlier"]:
                flags.append("outlier")
            if sensor["is_spike"]:
                flags.append("spike")
            threshold = thresholds.get(code, {})
            th_text = f"min={threshold.get('min_threshold')} max={threshold.get('max_threshold')}"
            help_text = ", ".join(flags) if flags else sensor["quality"]
            with metric_cols[idx]:
                st.metric(code.upper(), f"{value} {sensor['unit'] or ''}", help=f"{help_text} | {th_text}")

    if alert:
        st.markdown(f"### Kết luận hiện tại: {status_icon} {status_text}")
        st.write(alert["explain_text"])
    else:
        st.markdown("### Kết luận hiện tại: 🟢 Bình thường")
        st.write("Chưa phát sinh cảnh báo, hệ thống đang ở chế độ giám sát thông thường.")

    if history:
        df = pd.DataFrame(history)
        if not df.empty:
            df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
            chart_df = df.pivot_table(index="timestamp_utc", columns="sensor_code", values="value", aggfunc="last").sort_index()
            st.subheader("Xu hướng sensor gần đây")
            if not chart_df.empty:
                st.line_chart(chart_df, use_container_width=True)

with right:
    st.subheader("Nguồn camera / AI Vision")
    live_tabs = st.tabs(["Ảnh hiện tại", "Bằng chứng AI"])
    with live_tabs[0]:
        show_backend_image(f"/api/v1/stations/{STATION_CODE}/camera/current.jpg", "Ảnh snapshot hiện tại từ camera mô phỏng")
    with live_tabs[1]:
        if vision and vision.get("annotated_frame_url"):
            image_tabs = st.tabs(["Ảnh khoanh vùng", "Ảnh gốc"])
            with image_tabs[0]:
                show_backend_image(vision['annotated_frame_url'], "Bằng chứng đã khoanh ROI/BBox")
            with image_tabs[1]:
                show_backend_image(vision['raw_frame_url'], "Frame gốc")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("% vùng bất thường", vision.get("abnormal_area_percent", 0))
            c2.metric("Mức độ đậm/đục", vision.get("turbidity_score", 0))
            c3.metric("Mức độ chuyển động", vision.get("motion_score", 0))
            c4.metric("Số bbox", len(vision.get("bbox_json") or []))
            media_meta = vision.get("media_meta") or {}
            if media_meta:
                st.caption(f"Nguồn: {media_meta.get('source', 'N/A')}")
                st.caption(f"Tiêu đề: {media_meta.get('title', 'N/A')}")
                st.caption(f"Giấy phép: {media_meta.get('license', 'N/A')}")
        else:
            st.info("Chưa có kết quả AI vision. Hãy chạy kịch bản 1 hoặc 2 để kích hoạt phân tích camera.")

st.divider()

queue_tab, event_tab, alert_tab, stats_tab, forecast_tab = st.tabs(
    ["Hàng đợi worker", "Dòng sự kiện", "Lịch sử cảnh báo", "Thống kê", "Dự báo & NRMSE"]
)

with queue_tab:
    st.subheader("Hàng đợi xử lý")
    if queue:
        df_q = pd.DataFrame(queue)
        rename_map = {
            'event_id': 'Mã event', 'received_at': 'Thời điểm nhận', 'processing_status': 'Trạng thái xử lý',
            'processing_started_at': 'Bắt đầu xử lý', 'processed_at': 'Xử lý xong', 'processing_worker': 'Worker',
            'process_message': 'Ghi chú'
        }
        df_q = df_q.rename(columns=rename_map)
        st.dataframe(df_q, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có bản ghi webhook nào.")

with event_tab:
    st.subheader("Các event gần nhất")
    if events:
        for item in events:
            with st.container(border=True):
                top = st.columns([1.4, 1, 1])
                top[0].write(f"**{item['event_id']}**")
                top[1].write(f"UTC: {item['timestamp_utc']}")
                state_key = ((item.get("alert") or {}).get("final_state") or "NORMAL")
                icon, label = STATUS_LABELS.get(state_key, ("⚪", state_key))
                top[2].write(f"Trạng thái: **{icon} {label}**")

                sensor_rows = []
                for code, detail in sorted((item.get("sensors") or {}).items()):
                    sensor_rows.append(
                        {
                            "Sensor": code,
                            "Giá trị": detail.get("value"),
                            "Chất lượng": detail.get("quality"),
                            "Null": detail.get("is_null"),
                            "Outlier": detail.get("is_outlier"),
                            "Spike": detail.get("is_spike"),
                        }
                    )
                cols = st.columns([1.15, 1])
                with cols[0]:
                    if sensor_rows:
                        st.dataframe(pd.DataFrame(sensor_rows), use_container_width=True, hide_index=True)
                with cols[1]:
                    vision_block = item.get("vision") or {}
                    if vision_block.get("annotated_frame_url"):
                        show_backend_image(vision_block['annotated_frame_url'], 'Ảnh AI vision')
                        st.caption(
                            f"Vùng bất thường={vision_block.get('abnormal_area_percent', 0)}% | "
                            f"Đậm/đục={vision_block.get('turbidity_score', 0)} | "
                            f"Chuyển động={vision_block.get('motion_score', 0)}"
                        )
                    else:
                        st.caption("Event này không kích hoạt vision hoặc chưa được worker xử lý xong.")
                    media_meta = vision_block.get("media_meta") or {}
                    if media_meta:
                        st.caption(
                            f"Nguồn={media_meta.get('source', 'N/A')} | "
                            f"Tiêu đề={media_meta.get('title', 'N/A')} | "
                            f"Giấy phép={media_meta.get('license', 'N/A')}"
                        )
    else:       
        st.info("Chưa có event nào.")

with alert_tab:
    st.subheader("Lịch sử cảnh báo và ảnh bằng chứng")
    if alerts:
        for item in alerts:
            with st.container(border=True):
                c1, c2 = st.columns([1.7, 1])
                with c1:
                    icon, label = STATUS_LABELS.get(item['final_state'], ('⚪', item['final_state']))
                    st.write(f"**{icon} {label}** – {item['timestamp_utc']}")
                    st.write(item["explain_text"])
                    st.caption(f"Sensor={item['sensor_state']} | Vision={item['vision_state']} | Đã xác nhận={item['acknowledged']}")
                    if not item["acknowledged"]:
                        if st.button(f"Xác nhận cảnh báo #{item['id']}", key=f"ack_{item['id']}"):
                            get_json(f"/api/v1/stations/{STATION_CODE}/ack-alert/{item['id']}", method="POST")
                            st.rerun()
                with c2:
                    img_cols = st.columns(2)
                    with img_cols[0]:
                        if item.get("raw_frame_url"):
                            show_backend_image(item['raw_frame_url'], 'Gốc')
                    with img_cols[1]:
                        if item.get("annotated_frame_url"):
                            show_backend_image(item['annotated_frame_url'], 'Khoanh vùng')
    else:
        st.info("Chưa có cảnh báo nào.")

with stats_tab:
    group_by = st.radio("Gom theo", ["day", "month", "quarter"], horizontal=True)
    stats = get_json(f"/api/v1/stations/{STATION_CODE}/stats?group_by={group_by}")
    if stats:
        stats_df = pd.DataFrame(stats)
        stats_df["bucket"] = pd.to_datetime(stats_df["bucket"])
        pivot_df = stats_df.pivot_table(index="bucket", columns="final_state", values="total", aggfunc="sum").fillna(0).sort_index()
        st.bar_chart(pivot_df, use_container_width=True)
        st.dataframe(stats_df.rename(columns={"bucket": "Mốc thời gian", "final_state": "Trạng thái", "total": "Số lượng"}), use_container_width=True, hide_index=True)
    else:
        st.info("Chưa đủ dữ liệu thống kê.")

with forecast_tab:
    st.subheader("Dự báo ngắn hạn và đánh giá NRMSE")

    sensor_code = st.selectbox("Chọn sensor", ["cod", "tss", "nh4", "ph"])
    model_name = st.selectbox("Chọn mô hình", ["naive_last", "moving_avg_3"])

    if st.button("Chạy forecast"):
        try:
            forecast_data = get_json(
                f"/api/v1/forecast/run?station_code={STATION_CODE}&sensor_code={sensor_code}&model_name={model_name}"
            )
            metrics = forecast_data["metrics"]
            series = forecast_data["series"]

            c1, c2, c3 = st.columns(3)
            c1.metric("RMSE", f"{metrics['rmse']:.4f}" if metrics["rmse"] is not None else "N/A")
            c2.metric("MAE", f"{metrics['mae']:.4f}" if metrics["mae"] is not None else "N/A")
            c3.metric("NRMSE", f"{metrics['nrmse']:.4f}" if metrics["nrmse"] is not None else "N/A")

            df_fc = pd.DataFrame({
                "timestamp_utc": series["timestamps"],
                "observed": series["y_obs"],
                "forecast": series["y_fore"]
            })

            if not df_fc.empty:
                st.line_chart(df_fc.set_index("timestamp_utc")[["observed", "forecast"]], use_container_width=True)
                st.dataframe(df_fc, use_container_width=True, hide_index=True)
            else:
                st.info("Forecast chạy xong nhưng chưa có đủ điểm để hiển thị.")
        except Exception as exc:
            st.error(f"Không chạy được forecast: {exc}")

st.caption(f"Lần làm mới cuối (UTC): {pd.Timestamp.utcnow()}")

if auto_refresh:
    time.sleep(5)
    st.rerun()
