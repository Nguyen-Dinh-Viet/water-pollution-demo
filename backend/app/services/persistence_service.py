from __future__ import annotations

from typing import Any, Dict, List

from psycopg2.extras import Json

from app.core.db import get_conn


PROCESSING_STATES = {"PENDING", "PROCESSING", "DONE", "FAILED"}


def fetch_station(station_code: str) -> Dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM stations WHERE station_code = %s", (station_code,))
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_thresholds(station_code: str) -> Dict[str, Dict[str, Any]]:
    sql = """
        SELECT ss.sensor_code, ss.sensor_name, ss.min_threshold, ss.max_threshold, ss.unit
        FROM station_sensors ss
        JOIN stations s ON s.id = ss.station_id
        WHERE s.station_code = %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (station_code,))
            rows = cur.fetchall()
            return {row["sensor_code"]: dict(row) for row in rows}


def enqueue_raw_event(payload: dict) -> Dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO webhook_events_raw (
                    event_id, source, station_code, payload, processed,
                    processing_status, process_message
                )
                VALUES (%s, %s, %s, %s, FALSE, 'PENDING', 'Queued by webhook')
                ON CONFLICT (event_id) DO UPDATE SET
                    payload = EXCLUDED.payload,
                    process_message = 'Duplicate webhook payload refreshed',
                    source = EXCLUDED.source,
                    processed = FALSE,
                    processing_status = 'PENDING',
                    processing_started_at = NULL,
                    processed_at = NULL
                RETURNING id, event_id, station_code, processing_status, received_at
                """,
                (payload["event_id"], payload["source"], payload["station_code"], Json(payload)),
            )
            row = cur.fetchone()
            return dict(row)


def claim_next_event(worker_name: str) -> Dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH picked AS (
                    SELECT id
                    FROM webhook_events_raw
                    WHERE processed = FALSE
                      AND processing_status IN ('PENDING', 'FAILED')
                    ORDER BY received_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE webhook_events_raw w
                SET processing_status = 'PROCESSING',
                    processing_started_at = NOW(),
                    processing_worker = %s,
                    process_message = 'Worker picked event'
                FROM picked
                WHERE w.id = picked.id
                RETURNING w.*
                """,
                (worker_name,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def mark_event_done(event_id: str, message: str = "Processed successfully") -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE webhook_events_raw
                SET processed = TRUE,
                    processing_status = 'DONE',
                    processed_at = NOW(),
                    process_message = %s
                WHERE event_id = %s
                """,
                (message, event_id),
            )


def mark_event_failed(event_id: str, message: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE webhook_events_raw
                SET processed = FALSE,
                    processing_status = 'FAILED',
                    process_message = %s
                WHERE event_id = %s
                """,
                (message[:1000], event_id),
            )


def reset_event_outputs(event_id: str, station_code: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM alerts WHERE event_id = %s AND station_code = %s", (event_id, station_code))
            alert_ids = [row["id"] for row in cur.fetchall()]
            if alert_ids:
                cur.execute("DELETE FROM alert_evidences WHERE alert_id = ANY(%s)", (alert_ids,))
            cur.execute("DELETE FROM alerts WHERE event_id = %s AND station_code = %s", (event_id, station_code))
            cur.execute("DELETE FROM vision_results WHERE event_id = %s AND station_code = %s", (event_id, station_code))
            cur.execute("DELETE FROM sensor_readings WHERE event_id = %s AND station_code = %s", (event_id, station_code))




def update_station_camera_sources(station_code: str, camera_url: str | None, snapshot_url: str | None) -> None:
    if not camera_url and not snapshot_url:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE stations
                SET camera_url = COALESCE(%s, camera_url),
                    snapshot_url = COALESCE(%s, snapshot_url)
                WHERE station_code = %s
                """,
                (camera_url, snapshot_url, station_code),
            )

def save_readings(payload: dict, cleaned: List[Dict[str, Any]], timestamp_utc: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for item in cleaned:
                cur.execute(
                    """
                    INSERT INTO sensor_readings (
                        event_id, station_code, sensor_code, value, unit, quality,
                        is_null, is_outlier, is_spike, timestamp_utc
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id, sensor_code) DO UPDATE SET
                        value = EXCLUDED.value,
                        unit = EXCLUDED.unit,
                        quality = EXCLUDED.quality,
                        is_null = EXCLUDED.is_null,
                        is_outlier = EXCLUDED.is_outlier,
                        is_spike = EXCLUDED.is_spike,
                        timestamp_utc = EXCLUDED.timestamp_utc
                    """,
                    (
                        payload["event_id"],
                        payload["station_code"],
                        item["sensor_code"],
                        item["value"],
                        item["unit"],
                        item["quality"],
                        item["is_null"],
                        item["is_outlier"],
                        item["is_spike"],
                        timestamp_utc,
                    ),
                )


def save_vision(payload: dict, timestamp_utc: str, vision_result: Dict[str, Any]) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vision_results (
                    event_id, station_code, frame_timestamp_utc, abnormal_area_percent,
                    turbidity_score, motion_score, vision_state, bbox_json,
                    raw_frame_path, annotated_frame_path, media_file, media_meta
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO UPDATE SET
                    station_code = EXCLUDED.station_code,
                    frame_timestamp_utc = EXCLUDED.frame_timestamp_utc,
                    abnormal_area_percent = EXCLUDED.abnormal_area_percent,
                    turbidity_score = EXCLUDED.turbidity_score,
                    motion_score = EXCLUDED.motion_score,
                    vision_state = EXCLUDED.vision_state,
                    bbox_json = EXCLUDED.bbox_json,
                    media_file = EXCLUDED.media_file,
                    media_meta = EXCLUDED.media_meta,
                    raw_frame_path = EXCLUDED.raw_frame_path,
                    annotated_frame_path = EXCLUDED.annotated_frame_path
                """,
                (
                    payload["event_id"],
                    payload["station_code"],
                    timestamp_utc,
                    vision_result["abnormal_area_percent"],
                    vision_result["turbidity_score"],
                    vision_result["motion_score"],
                    vision_result["vision_state"],
                    Json(vision_result["bbox_list"]),
                    vision_result["raw_frame_path"],
                    vision_result["annotated_frame_path"],
                    vision_result.get("media_file"),
                    Json(vision_result.get("media_meta", {})),
                ),
            )


def save_alert(
    payload: dict,
    timestamp_utc: str,
    sensor_state: str,
    vision_state: str,
    fusion_result: Dict[str, Any],
    vision_result: Dict[str, Any] | None,
) -> int | None:
    if fusion_result["final_state"] == "NORMAL":
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alerts (
                    event_id, station_code, sensor_state, vision_state,
                    final_state, severity, explain_text, timestamp_utc
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO UPDATE SET
                    station_code = EXCLUDED.station_code,
                    sensor_state = EXCLUDED.sensor_state,
                    vision_state = EXCLUDED.vision_state,
                    final_state = EXCLUDED.final_state,
                    severity = EXCLUDED.severity,
                    explain_text = EXCLUDED.explain_text,
                    timestamp_utc = EXCLUDED.timestamp_utc
                RETURNING id
                """,
                (
                    payload["event_id"],
                    payload["station_code"],
                    sensor_state,
                    vision_state,
                    fusion_result["final_state"],
                    fusion_result["severity"],
                    f"{fusion_result['explain_text']} Hướng xử lý: {fusion_result['operator_hint']}",
                    timestamp_utc,
                ),
            )
            alert_id = cur.fetchone()["id"]
            cur.execute("DELETE FROM alert_evidences WHERE alert_id = %s", (alert_id,))
            if vision_result:
                cur.execute(
                    """
                    INSERT INTO alert_evidences (alert_id, evidence_type, file_path, meta)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        alert_id,
                        "annotated_frame",
                        vision_result["annotated_frame_path"],
                        Json(
                            {
                                "abnormal_area_percent": vision_result["abnormal_area_percent"],
                                "turbidity_score": vision_result["turbidity_score"],
                                "motion_score": vision_result["motion_score"],
                                "bbox_count": vision_result["bbox_count"],
                                "roi": vision_result["roi"],
                                "camera_source": vision_result.get("resolved_source") or vision_result.get("source"),
                            }
                        ),
                    ),
                )
            return alert_id


def get_station_health_summary(station_code: str) -> Dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(received_at) AS last_webhook_at,
                       COUNT(*) AS total_webhooks,
                       COUNT(*) FILTER (WHERE processing_status = 'PENDING') AS pending_webhooks,
                       COUNT(*) FILTER (WHERE processing_status = 'FAILED') AS failed_webhooks,
                       MAX(processed_at) AS last_processed_at
                FROM webhook_events_raw
                WHERE station_code = %s
                """,
                (station_code,),
            )
            webhook_row = cur.fetchone() or {}
            cur.execute(
                "SELECT MAX(timestamp_utc) AS last_alert_at, COUNT(*) AS total_alerts FROM alerts WHERE station_code = %s",
                (station_code,),
            )
            alert_row = cur.fetchone() or {}
            cur.execute(
                "SELECT MAX(timestamp_utc) AS last_sensor_at FROM sensor_readings WHERE station_code = %s",
                (station_code,),
            )
            sensor_row = cur.fetchone() or {}
    return {
        "last_webhook_at": webhook_row.get("last_webhook_at"),
        "last_processed_at": webhook_row.get("last_processed_at"),
        "total_webhooks": webhook_row.get("total_webhooks", 0),
        "pending_webhooks": webhook_row.get("pending_webhooks", 0),
        "failed_webhooks": webhook_row.get("failed_webhooks", 0),
        "last_alert_at": alert_row.get("last_alert_at"),
        "total_alerts": alert_row.get("total_alerts", 0),
        "last_sensor_at": sensor_row.get("last_sensor_at"),
    }

def save_forecast_result(conn, station_code, sensor_code, model_name, horizon_steps, timestamps, y_obs, y_fore, metrics):
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO forecast_runs (station_code, sensor_code, model_name, horizon_steps)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (station_code, sensor_code, model_name, horizon_steps))

    row = cur.fetchone()
    run_id = row["id"]

    for ts, obs, pred in zip(timestamps, y_obs, y_fore):
        cur.execute("""
            INSERT INTO forecast_predictions (run_id, timestamp_utc, y_obs, y_fore)
            VALUES (%s, %s, %s, %s)
        """, (run_id, ts, obs, pred))

    cur.execute("""
        INSERT INTO forecast_metrics (run_id, rmse, mae, nrmse, n_points)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        run_id,
        metrics.get("rmse"),
        metrics.get("mae"),
        metrics.get("nrmse"),
        metrics.get("n_points")
    ))

    cur.close()
    return run_id