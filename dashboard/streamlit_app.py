import base64
import io
import math
import os
import struct
import time
import wave
from typing import Any, Dict, List

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

BACKEND_URL = os.getenv("STREAMLIT_BACKEND_URL", "http://api:8000")
API_KEY = os.getenv("ADMIN_API_KEY", "demo_admin_key_2026")
STATION_CODE = "ST001"

STATUS_LABELS = {
    "NORMAL": ("🟢", "Bình thường"),
    "CHECK_DEVICE": ("🟡", "Cần kiểm tra thiết bị"),
    "SUSPICIOUS": ("🟡", "Cảnh báo nghi ngờ"),
    "VERIFY_CAMERA": ("🟡", "Cần xác minh camera"),
    "CRITICAL_ALERT": ("🔴", "Cảnh báo nguy cấp"),
}

SOUND_ALERT_STATES = {"CRITICAL_ALERT", "CHECK_DEVICE", "SUSPICIOUS"}


st.set_page_config(
    page_title="Water Pollution Demo",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1500px;
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    h1 {
        font-size: 2.15rem !important;
        line-height: 1.15 !important;
        margin-bottom: 0.15rem !important;
    }
    h2 {
        font-size: 1.45rem !important;
        margin-top: 0.45rem !important;
    }
    h3 {
        font-size: 1.15rem !important;
    }
    p, li, div[data-testid="stMarkdownContainer"] p {
        font-size: 0.95rem !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.55rem !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.92rem !important;
    }
    .small-note {
        font-size: 0.86rem;
        color: #666;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Hệ thống cảnh báo ô nhiễm nước – Demo 5★")
st.caption("Webhook UTC • 04 sensor • worker tách riêng • camera snapshot/MJPEG • fusion decision • lưu vết bằng chứng")


def build_alarm_wav_bytes(
    duration_sec: float = 0.9,
    freq: float = 880.0,
    volume: float = 0.45,
    sample_rate: int = 44100,
) -> bytes:
    buffer = io.BytesIO()
    n_samples = int(duration_sec * sample_rate)

    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        frames = bytearray()
        for i in range(n_samples):
            value = int(volume * 32767 * math.sin(2 * math.pi * freq * i / sample_rate))
            frames.extend(struct.pack("<h", value))
        wav_file.writeframes(bytes(frames))

    return buffer.getvalue()


def play_alarm_if_needed(alert: Dict[str, Any] | None) -> None:
    if not alert:
        return

    alert_id = alert.get("id")
    final_state = alert.get("final_state")

    if final_state not in SOUND_ALERT_STATES:
        return

    last_played_id = st.session_state.get("last_played_alert_id")
    if last_played_id == alert_id:
        return

    audio_bytes = build_alarm_wav_bytes()
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    components.html(
        f"""
        <audio autoplay>
            <source src="data:audio/wav;base64,{audio_b64}" type="audio/wav">
        </audio>
        """,
        height=0,
    )

    st.session_state["last_played_alert_id"] = alert_id


def request_json(
    path: str,
    method: str = "GET",
    require_api_key: bool = True,
    timeout: int = 30,
) -> Dict[str, Any] | List[Dict[str, Any]]:
    headers = {"X-API-Key": API_KEY} if require_api_key else {}
    url = path if path.startswith("http") else f"{BACKEND_URL}{path}"
    resp = requests.request(method, url, headers=headers, timeout=timeout)
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


def show_backend_image(path: str, caption: str, use_container_width: bool = True) -> None:
    content = get_image_bytes(path)
    if content:
        st.image(content, caption=caption, use_container_width=use_container_width)
    else:
        st.warning(f"Không tải được hình ảnh: {caption}")


def trigger_scenario(path: str) -> None:
    response = request_json(path, method="POST")
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    event_id = response.get("event_id") or body.get("event_id") or "N/A"
    st.toast(f"Đã xếp hàng event {event_id}")
    time.sleep(1.0)
    st.rerun()


def format_number(value: Any) -> str:
    if value is None:
        return "NULL"
    try:
        number = float(value)
    except Exception:
        return str(value)

    if abs(number) >= 1000:
        return f"{number:,.0f}"
    if abs(number) >= 100:
        return f"{number:.1f}"
    if abs(number) >= 10:
        return f"{number:.2f}"
    return f"{number:.3f}"


def find_exceeded_sensors(sensors: List[Dict[str, Any]], thresholds: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    exceeded: List[Dict[str, Any]] = []

    for sensor in sensors or []:
        code = sensor.get("sensor_code")
        value = sensor.get("value")
        unit = sensor.get("unit") or ""

        if not code or value is None:
            continue

        threshold = thresholds.get(code, {}) or {}
        min_th = threshold.get("min_threshold")
        max_th = threshold.get("max_threshold")

        if code == "ph":
            if min_th is not None and value < min_th:
                exceeded.append(
                    {
                        "sensor_code": code.upper(),
                        "value": f"{format_number(value)} {unit}".strip(),
                        "threshold": f">= {min_th}",
                        "reason": f"Thấp hơn ngưỡng ({value} < {min_th})",
                    }
                )
            elif max_th is not None and value > max_th:
                exceeded.append(
                    {
                        "sensor_code": code.upper(),
                        "value": f"{format_number(value)} {unit}".strip(),
                        "threshold": f"<= {max_th}",
                        "reason": f"Cao hơn ngưỡng ({value} > {max_th})",
                    }
                )
        else:
            if min_th is not None and value < min_th:
                exceeded.append(
                    {
                        "sensor_code": code.upper(),
                        "value": f"{format_number(value)} {unit}".strip(),
                        "threshold": f">= {min_th}",
                        "reason": f"Thấp hơn ngưỡng ({value} < {min_th})",
                    }
                )
            elif max_th is not None and value > max_th:
                exceeded.append(
                    {
                        "sensor_code": code.upper(),
                        "value": f"{format_number(value)} {unit}".strip(),
                        "threshold": f"<= {max_th}",
                        "reason": f"Vượt ngưỡng ({value} > {max_th})",
                    }
                )

    return exceeded


def build_sensor_warning_text(exceeded: List[Dict[str, Any]]) -> str:
    if not exceeded:
        return "Không có chỉ số nào vượt ngưỡng."
    return " | ".join(f"{item['sensor_code']}: {item['reason']}" for item in exceeded)


def render_status_banner(status_label: str) -> None:
    if status_label == "CRITICAL_ALERT":
        st.error("🔴 CẢNH BÁO Ô NHIỄM: Có chỉ số vượt ngưỡng. Kiểm tra ngay camera và hiện trường.")
    elif status_label == "CHECK_DEVICE":
        st.warning("🟡 CẢNH BÁO THIẾT BỊ: Dữ liệu sensor bất thường, cần kiểm tra đầu đo.")
    elif status_label == "SUSPICIOUS":
        st.warning("🟡 CẢNH BÁO NGHI NGỜ: AI camera phát hiện bất thường, cần xác minh thêm.")
    elif status_label == "VERIFY_CAMERA":
        st.warning("🟡 CẦN XÁC MINH CAMERA: Chưa đủ dữ liệu hình ảnh để kết luận.")
    else:
        st.success("🟢 HỆ THỐNG ĐANG ỔN ĐỊNH")


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

    sound_enabled = st.toggle("Bật âm thanh cảnh báo", value=True)
    auto_refresh = st.toggle("Tự làm mới mỗi 5 giây", value=False)

    if st.button("Làm mới ngay", use_container_width=True):
        st.rerun()


try:
    health = request_json("/health", require_api_key=False, timeout=10)
    latest = request_json(f"/api/v1/stations/{STATION_CODE}/latest")
    history = request_json(f"/api/v1/stations/{STATION_CODE}/history?limit=120")
    alerts = request_json(f"/api/v1/stations/{STATION_CODE}/alerts?limit=12")
    events = request_json(f"/api/v1/stations/{STATION_CODE}/events?limit=12")
    queue = request_json(f"/api/v1/stations/{STATION_CODE}/queue?limit=12")
except Exception as exc:
    st.error(f"Không tải được dữ liệu từ backend: {exc}")
    st.stop()

station = latest.get("station", {})
alert = latest.get("latest_alert")
vision = latest.get("latest_vision") or {}
thresholds = latest.get("thresholds", {}) or {}
health_summary = latest.get("health_summary", {}) or {}
sensors = latest.get("sensors", []) or []

if sound_enabled:
    play_alarm_if_needed(alert)

status_label = (alert or {}).get("final_state", "NORMAL")
status_icon, status_text = STATUS_LABELS.get(status_label, ("⚪", status_label))

row1 = st.columns([1.55, 1.05, 0.85, 0.85, 0.85])
row1[0].success(
    f"Backend: {health.get('backend', 'UNKNOWN')} | "
    f"CSDL: {health.get('database', 'UNKNOWN')} | "
    f"Worker: Tách riêng\n\n"
    f"Hàng đợi chờ: {(health.get('queue') or {}).get('pending', 0)} | "
    f"Hàng đợi lỗi: {(health.get('queue') or {}).get('failed', 0)}"
)
row1[1].metric("Trạng thái", f"{status_icon} {status_text}")
row1[2].metric("Webhook", int(health_summary.get("total_webhooks") or 0))
row1[3].metric("Đang chờ", int(health_summary.get("pending_webhooks") or 0))
row1[4].metric("Cảnh báo", int(health_summary.get("total_alerts") or 0))

render_status_banner(status_label)

left, right = st.columns([1.22, 1])

with left:
    st.subheader(f"Trạm {station.get('station_name', 'N/A')} ({station.get('station_code', STATION_CODE)})")
    st.markdown(
        (
            f"<div class='small-note'>Múi giờ: {station.get('timezone', 'UTC')} • "
            f"Camera mô phỏng nội bộ đang hoạt động • "
            f"Ảnh chụp hiện tại được lấy qua backend proxy</div>"
        ),
        unsafe_allow_html=True,
    )

    exceeded_sensors = find_exceeded_sensors(sensors, thresholds)
    sensor_warning_text = build_sensor_warning_text(exceeded_sensors)

    if sensors:
        metric_cols = st.columns(len(sensors))
        for idx, sensor in enumerate(sensors):
            code = (sensor.get("sensor_code") or "").upper()
            value = format_number(sensor.get("value"))
            unit = sensor.get("unit") or ""

            flags: List[str] = []
            if sensor.get("is_null"):
                flags.append("null")
            if sensor.get("is_outlier"):
                flags.append("outlier")
            if sensor.get("is_spike"):
                flags.append("spike")

            threshold = thresholds.get((sensor.get("sensor_code") or "").lower(), {}) or {}
            help_text = ", ".join(flags) if flags else (sensor.get("quality") or "unknown")
            th_text = f"min={threshold.get('min_threshold')} | max={threshold.get('max_threshold')}"

            with metric_cols[idx]:
                st.metric(
                    code,
                    f"{value} {unit}".strip(),
                    help=f"{help_text} | {th_text}",
                )

    if alert:
        st.markdown(f"### Kết luận hiện tại: {status_icon} {status_text}")
        st.write(alert.get("explain_text", "Không có mô tả cảnh báo."))
        if alert.get("operator_hint"):
            st.caption(f"Gợi ý xử lý: {alert.get('operator_hint')}")
    else:
        st.markdown("### Kết luận hiện tại: 🟢 Bình thường")
        st.write("Chưa phát sinh cảnh báo, hệ thống đang ở chế độ giám sát thông thường.")

    if exceeded_sensors:
        st.error("Chỉ số vượt ngưỡng ô nhiễm: " + sensor_warning_text)
        st.dataframe(pd.DataFrame(exceeded_sensors), use_container_width=True, hide_index=True)

    if history:
        df = pd.DataFrame(history)
        if not df.empty and {"timestamp_utc", "sensor_code", "value"}.issubset(df.columns):
            df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], errors="coerce")
            chart_df = (
                df.pivot_table(
                    index="timestamp_utc",
                    columns="sensor_code",
                    values="value",
                    aggfunc="last",
                )
                .sort_index()
            )

            st.subheader("Xu hướng sensor gần đây")
            if not chart_df.empty:
                available_cols = list(chart_df.columns)
                default_cols = available_cols[:1] if available_cols else []
                selected_cols = st.multiselect(
                    "Chọn sensor hiển thị",
                    options=available_cols,
                    default=default_cols,
                    key="trend_sensor_cols",
                )
                if selected_cols:
                    st.line_chart(chart_df[selected_cols], use_container_width=True)
                else:
                    st.info("Hãy chọn ít nhất 1 sensor để hiển thị biểu đồ.")

with right:
    st.subheader("Nguồn camera / AI Vision")
    live_tabs = st.tabs(["Ảnh hiện tại", "Bằng chứng AI"])

    with live_tabs[0]:
        show_backend_image(
            f"/api/v1/stations/{STATION_CODE}/camera/current.jpg",
            "Ảnh camera hiện tại dùng để giám sát và hỗ trợ AI đánh giá ô nhiễm",
        )

    with live_tabs[1]:
        if vision.get("annotated_frame_url"):
            ai_state = vision.get("vision_state", "UNKNOWN")

            if ai_state == "ABNORMAL":
                st.error("AI camera dự đoán: Có dấu hiệu ô nhiễm")
            elif ai_state == "NORMAL":
                st.success("AI camera dự đoán: Chưa phát hiện ô nhiễm rõ")
            else:
                st.warning("AI camera dự đoán: Chưa đủ dữ liệu để kết luận")

            image_tabs = st.tabs(["Ảnh khoanh vùng", "Ảnh gốc"])
            with image_tabs[0]:
                show_backend_image(vision["annotated_frame_url"], "Bằng chứng đã khoanh ROI/BBox")
            with image_tabs[1]:
                raw_frame_url = vision.get("raw_frame_url")
                if raw_frame_url:
                    show_backend_image(raw_frame_url, "Frame gốc")
                else:
                    st.info("Chưa có ảnh gốc.")

            bbox_items = vision.get("bbox_json") or vision.get("bbox_list") or []

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("% vùng bất thường", vision.get("abnormal_area_percent", 0))
            c2.metric("Mức độ đậm/đục", vision.get("turbidity_score", 0))
            c3.metric("Mức độ chuyển động", vision.get("motion_score", 0))
            c4.metric("Số bbox", len(bbox_items))
        else:
            st.info("Chưa có kết quả AI vision. Hãy chạy kịch bản 1 hoặc 2 để kích hoạt phân tích camera.")

        media_meta = vision.get("media_meta") or {}
        if media_meta:
            st.caption(f"Nguồn: {media_meta.get('source', 'N/A')}")
            st.caption(f"Tiêu đề: {media_meta.get('title', 'N/A')}")
            st.caption(f"Giấy phép: {media_meta.get('license', 'N/A')}")

st.divider()

queue_tab, event_tab, alert_tab, stats_tab, forecast_tab = st.tabs(
    ["Hàng đợi worker", "Dòng sự kiện", "Lịch sử cảnh báo", "Thống kê", "Dự báo & NRMSE"]
)

with queue_tab:
    st.subheader("Hàng đợi xử lý")
    if queue:
        df_q = pd.DataFrame(queue)
        rename_map = {
            "event_id": "Mã event",
            "received_at": "Thời điểm nhận",
            "processing_status": "Trạng thái xử lý",
            "processing_started_at": "Bắt đầu xử lý",
            "processed_at": "Xử lý xong",
            "processing_worker": "Worker",
            "process_message": "Ghi chú",
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
                top[0].write(f"**{item.get('event_id', 'N/A')}**")
                top[1].write(f"UTC: {item.get('timestamp_utc', 'N/A')}")

                event_alert = item.get("alert") or {}
                state_key = event_alert.get("final_state") or "NORMAL"
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
                        show_backend_image(vision_block["annotated_frame_url"], "Ảnh AI vision")
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
                    icon, label = STATUS_LABELS.get(item.get("final_state", "NORMAL"), ("⚪", item.get("final_state", "UNKNOWN")))
                    st.write(f"**{icon} {label}** – {item.get('timestamp_utc', 'N/A')}")
                    st.write(item.get("explain_text", "Không có mô tả cảnh báo."))
                    st.caption(
                        f"Sensor={item.get('sensor_state', 'N/A')} | "
                        f"Vision={item.get('vision_state', 'N/A')} | "
                        f"Đã xác nhận={item.get('acknowledged', False)}"
                    )

                    if not item.get("acknowledged", False):
                        if st.button(f"Xác nhận cảnh báo #{item.get('id')}", key=f"ack_{item.get('id')}"):
                            request_json(f"/api/v1/stations/{STATION_CODE}/ack-alert/{item.get('id')}", method="POST")
                            st.rerun()

                with c2:
                    img_cols = st.columns(2)
                    with img_cols[0]:
                        if item.get("raw_frame_url"):
                            show_backend_image(item["raw_frame_url"], "Gốc")
                    with img_cols[1]:
                        if item.get("annotated_frame_url"):
                            show_backend_image(item["annotated_frame_url"], "Khoanh vùng")
    else:
        st.info("Chưa có cảnh báo nào.")

with stats_tab:
    group_by = st.radio("Gom theo", ["day", "month", "quarter"], horizontal=True)
    stats = request_json(f"/api/v1/stations/{STATION_CODE}/stats?group_by={group_by}")

    if stats:
        stats_df = pd.DataFrame(stats)
        stats_df["bucket"] = pd.to_datetime(stats_df["bucket"], errors="coerce")

        pivot_df = (
            stats_df.pivot_table(
                index="bucket",
                columns="final_state",
                values="total",
                aggfunc="sum",
            )
            .fillna(0)
            .sort_index()
        )

        st.bar_chart(pivot_df, use_container_width=True)
        st.dataframe(
            stats_df.rename(
                columns={
                    "bucket": "Mốc thời gian",
                    "final_state": "Trạng thái",
                    "total": "Số lượng",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Chưa đủ dữ liệu thống kê.")

with forecast_tab:
    st.subheader("Dự báo ngắn hạn và đánh giá NRMSE")

    sensor_code = st.selectbox("Chọn sensor", ["cod", "tss", "nh4", "ph"], key="forecast_sensor")
    model_name = st.selectbox("Chọn mô hình", ["naive_last", "moving_avg_3"], key="forecast_model")

    if st.button("Chạy forecast"):
        try:
            forecast_data = request_json(
                f"/api/v1/forecast/run?station_code={STATION_CODE}&sensor_code={sensor_code}&model_name={model_name}"
            )
            metrics = forecast_data.get("metrics", {})
            series = forecast_data.get("series", {})

            c1, c2, c3 = st.columns(3)
            c1.metric("RMSE", f"{metrics['rmse']:.4f}" if metrics.get("rmse") is not None else "N/A")
            c2.metric("MAE", f"{metrics['mae']:.4f}" if metrics.get("mae") is not None else "N/A")
            c3.metric("NRMSE", f"{metrics['nrmse']:.4f}" if metrics.get("nrmse") is not None else "N/A")

            nrmse_value = metrics.get("nrmse")
            if nrmse_value is not None and nrmse_value > 0.25:
                st.warning("NRMSE đang khá cao, dự báo còn sai lệch đáng kể.")
            elif nrmse_value is not None:
                st.success("NRMSE ở mức chấp nhận được cho demo hiện tại.")

            df_fc = pd.DataFrame(
                {
                    "timestamp_utc": series.get("timestamps", []),
                    "observed": series.get("y_obs", []),
                    "forecast": series.get("y_fore", []),
                }
            )

            if not df_fc.empty:
                st.line_chart(
                    df_fc.set_index("timestamp_utc")[["observed", "forecast"]],
                    use_container_width=True,
                )
                st.dataframe(df_fc, use_container_width=True, hide_index=True)
            else:
                st.info("Forecast chạy xong nhưng chưa có đủ điểm để hiển thị.")
        except Exception as exc:
            st.error(f"Không chạy được forecast: {exc}")

st.caption(f"Lần làm mới cuối (UTC): {pd.Timestamp.utcnow()}")

if auto_refresh:
    time.sleep(5)
    st.rerun()