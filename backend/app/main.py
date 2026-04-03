from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import cv2
import requests
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.db import get_conn
from app.schemas.webhook import SensorWebhookPayload

from app.api.forecast import router as forecast_router

from app.services.persistence_service import (
    enqueue_raw_event,
    fetch_station,
    fetch_thresholds,
    get_station_health_summary,
)

app = FastAPI(title="Water Pollution Demo API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(forecast_router)

Path(settings.frame_storage_path).mkdir(parents=True, exist_ok=True)
Path(settings.annotated_storage_path).mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory="/app/data"), name="files")


def _require_admin_key(header_value: str | None) -> None:
    if header_value != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _require_webhook_token(header_value: str | None) -> None:
    if header_value != settings.webhook_token:
        raise HTTPException(status_code=401, detail="Invalid webhook token")


def _normalize_path_to_url(abs_path: str | None) -> str | None:
    if not abs_path:
        return None
    if abs_path.startswith("/app/data/"):
        return "/files/" + abs_path.replace("/app/data/", "")
    return None


def _fetch_station_or_404(station_code: str) -> Dict[str, Any]:
    station = fetch_station(station_code)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


@app.get("/health")
def health() -> Dict[str, Any]:
    db_ok = True
    queue = {"pending": 0, "failed": 0}
    last_webhook_at = None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT MAX(received_at) AS last_webhook_at,
                           COUNT(*) FILTER (WHERE processing_status = 'PENDING') AS pending,
                           COUNT(*) FILTER (WHERE processing_status = 'FAILED') AS failed
                    FROM webhook_events_raw
                    """
                )
                row = cur.fetchone() or {}
                last_webhook_at = row.get("last_webhook_at")
                queue = {"pending": row.get("pending", 0), "failed": row.get("failed", 0)}
    except Exception:
        db_ok = False
    return {
        "backend": "UP",
        "database": "UP" if db_ok else "DOWN",
        "worker_status": "TÁCH_RIÊNG",
        "camera_status": "SẴN_SÀNG",
        "queue": queue,
        "last_webhook_at": last_webhook_at,
        "time_utc": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/stations")
def list_stations() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT station_code, station_name, timezone, camera_url, snapshot_url FROM stations WHERE is_active = TRUE ORDER BY station_code"
            )
            return [dict(row) for row in cur.fetchall()]


@app.get("/api/v1/config/stations/{station_code}")
def get_station_config(station_code: str, x_api_key: str | None = Header(None)) -> Dict[str, Any]:
    _require_admin_key(x_api_key)
    station = _fetch_station_or_404(station_code)
    thresholds = fetch_thresholds(station_code)
    station["sensors"] = list(thresholds.values())
    return station


@app.post("/api/v1/webhooks/envisoft/sensor")
def ingest_sensor_webhook(payload: SensorWebhookPayload, x_webhook_token: str | None = Header(None)) -> Dict[str, Any]:
    _require_webhook_token(x_webhook_token)
    payload_dict = payload.model_dump()
    queued = enqueue_raw_event(payload_dict)
    return {
        "ok": True,
        "queued": True,
        "event_id": payload.event_id,
        "station_code": payload.station_code,
        "processing_status": queued["processing_status"],
        "message": "Webhook accepted and queued for worker processing.",
    }


@app.get("/api/v1/stations/{station_code}/latest")
def station_latest(station_code: str) -> Dict[str, Any]:
    station = _fetch_station_or_404(station_code)
    thresholds = fetch_thresholds(station_code)
    health_summary = get_station_health_summary(station_code)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_id, timestamp_utc
                FROM sensor_readings
                WHERE station_code = %s
                ORDER BY timestamp_utc DESC, id DESC
                LIMIT 1
                """,
                (station_code,),
            )
            latest_event = cur.fetchone()
            if not latest_event:
                return {
                    "station": station,
                    "thresholds": thresholds,
                    "sensors": [],
                    "latest_alert": None,
                    "latest_vision": None,
                    "health_summary": health_summary,
                }
            event_id = latest_event["event_id"]
            cur.execute(
                """
                SELECT sensor_code, value, unit, quality, is_null, is_outlier, is_spike, timestamp_utc
                FROM sensor_readings
                WHERE station_code = %s AND event_id = %s
                ORDER BY sensor_code
                """,
                (station_code, event_id),
            )
            sensors = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT * FROM vision_results
                WHERE station_code = %s AND event_id = %s
                ORDER BY id DESC LIMIT 1
                """,
                (station_code, event_id),
            )
            vision = cur.fetchone()
            cur.execute(
                """
                SELECT * FROM alerts
                WHERE station_code = %s AND event_id = %s
                ORDER BY id DESC LIMIT 1
                """,
                (station_code, event_id),
            )
            alert = cur.fetchone()

    vision_dict = dict(vision) if vision else None
    if vision_dict:
        vision_dict["raw_frame_url"] = _normalize_path_to_url(vision_dict.get("raw_frame_path"))
        vision_dict["annotated_frame_url"] = _normalize_path_to_url(vision_dict.get("annotated_frame_path"))
    return {
        "station": station,
        "event_id": event_id,
        "thresholds": thresholds,
        "sensors": sensors,
        "latest_alert": dict(alert) if alert else None,
        "latest_vision": vision_dict,
        "health_summary": health_summary,
    }


@app.get("/api/v1/stations/{station_code}/history")
def station_history(station_code: str, limit: int = Query(default=80, ge=1, le=800)) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_id, sensor_code, value, unit, quality, is_null, is_outlier, is_spike, timestamp_utc
                FROM sensor_readings
                WHERE station_code = %s
                ORDER BY timestamp_utc DESC, id DESC
                LIMIT %s
                """,
                (station_code, limit),
            )
            return [dict(row) for row in cur.fetchall()]


@app.get("/api/v1/stations/{station_code}/events")
def station_events(station_code: str, limit: int = Query(default=20, ge=1, le=100)) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT event_id, timestamp_utc
                FROM sensor_readings
                WHERE station_code = %s
                ORDER BY timestamp_utc DESC
                LIMIT %s
                """,
                (station_code, limit),
            )
            base_events = [dict(row) for row in cur.fetchall()]
            if not base_events:
                return []

            event_ids = [item["event_id"] for item in base_events]
            cur.execute(
                """
                SELECT event_id, sensor_code, value, unit, quality, is_null, is_outlier, is_spike
                FROM sensor_readings
                WHERE station_code = %s AND event_id = ANY(%s)
                ORDER BY event_id, sensor_code
                """,
                (station_code, event_ids),
            )
            sensor_rows = cur.fetchall()
            sensor_map: Dict[str, Dict[str, Any]] = {}
            for row in sensor_rows:
                sensor_map.setdefault(row["event_id"], {})[row["sensor_code"]] = {
                    "value": row["value"],
                    "unit": row["unit"],
                    "quality": row["quality"],
                    "is_null": row["is_null"],
                    "is_outlier": row["is_outlier"],
                    "is_spike": row["is_spike"],
                }

            cur.execute(
                """
                SELECT event_id, final_state, severity, explain_text, acknowledged
                FROM alerts
                WHERE station_code = %s AND event_id = ANY(%s)
                """,
                (station_code, event_ids),
            )
            alert_map = {row["event_id"]: dict(row) for row in cur.fetchall()}

            cur.execute(
                """
                SELECT event_id, vision_state, abnormal_area_percent, turbidity_score, motion_score,
                    raw_frame_path, annotated_frame_path, media_file, media_meta
                FROM vision_results
                WHERE station_code = %s AND event_id = ANY(%s)
                """,
                (station_code, event_ids),
            )
            vision_map = {row["event_id"]: dict(row) for row in cur.fetchall()}

    output: List[Dict[str, Any]] = []
    for event in base_events:
        item = {
            **event,
            "sensors": sensor_map.get(event["event_id"], {}),
            "alert": alert_map.get(event["event_id"]),
            "vision": vision_map.get(event["event_id"]),
        }
        vision = item.get("vision")
        if vision:
            vision["raw_frame_url"] = _normalize_path_to_url(vision.get("raw_frame_path"))
            vision["annotated_frame_url"] = _normalize_path_to_url(vision.get("annotated_frame_path"))
        output.append(item)
    return output


@app.get("/api/v1/stations/{station_code}/alerts")
def station_alerts(station_code: str, limit: int = Query(default=20, ge=1, le=100)) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.*, ae.file_path, ae.meta,
                       vr.raw_frame_path, vr.annotated_frame_path
                FROM alerts a
                LEFT JOIN LATERAL (
                    SELECT file_path, meta
                    FROM alert_evidences
                    WHERE alert_id = a.id
                    ORDER BY id DESC LIMIT 1
                ) ae ON TRUE
                LEFT JOIN vision_results vr ON vr.event_id = a.event_id AND vr.station_code = a.station_code
                WHERE a.station_code = %s
                ORDER BY a.timestamp_utc DESC, a.id DESC
                LIMIT %s
                """,
                (station_code, limit),
            )
            rows = []
            for row in cur.fetchall():
                item = dict(row)
                item["evidence_url"] = _normalize_path_to_url(item.pop("file_path", None))
                item["raw_frame_url"] = _normalize_path_to_url(item.pop("raw_frame_path", None))
                item["annotated_frame_url"] = _normalize_path_to_url(item.pop("annotated_frame_path", None))
                rows.append(item)
            return rows


@app.get("/api/v1/stations/{station_code}/stats")
def station_stats(station_code: str, group_by: str = Query(default="day")) -> List[Dict[str, Any]]:
    if group_by not in {"day", "month", "quarter"}:
        raise HTTPException(status_code=400, detail="group_by must be one of day, month, quarter")
    sql = f"""
        SELECT date_trunc('{group_by}', timestamp_utc) AS bucket,
               final_state,
               COUNT(*) AS total
        FROM alerts
        WHERE station_code = %s
        GROUP BY 1, 2
        ORDER BY 1 DESC, 2 ASC
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (station_code,))
            return [dict(row) for row in cur.fetchall()]


@app.post("/api/v1/stations/{station_code}/ack-alert/{alert_id}")
def acknowledge_alert(station_code: str, alert_id: int, x_api_key: str | None = Header(None)) -> Dict[str, Any]:
    _require_admin_key(x_api_key)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE alerts SET acknowledged = TRUE WHERE id = %s AND station_code = %s RETURNING id",
                (alert_id, station_code),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Alert not found")
            return {"ok": True, "alert_id": row["id"], "acknowledged": True}


@app.get("/api/v1/stations/{station_code}/queue")
def station_queue(station_code: str, limit: int = Query(default=20, ge=1, le=100)) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_id, received_at, processing_status, processing_started_at,
                       processed_at, processing_worker, process_message
                FROM webhook_events_raw
                WHERE station_code = %s
                ORDER BY received_at DESC
                LIMIT %s
                """,
                (station_code, limit),
            )
            return [dict(row) for row in cur.fetchall()]


@app.get("/api/v1/stations/{station_code}/camera/current.jpg")
def camera_current(station_code: str) -> Response:
    station = _fetch_station_or_404(station_code)
    snapshot_url = station.get("snapshot_url") or settings.default_snapshot_url
    try:
        if snapshot_url.startswith("sample://"):
            from app.services.vision_service import _read_frame  # reuse existing mock logic

            frame, _ = _read_frame(snapshot_url, snapshot_url)
            ok, encoded = cv2.imencode('.jpg', frame)
            if not ok:
                raise RuntimeError('Encode failed')
            return Response(content=encoded.tobytes(), media_type="image/jpeg")
        resp = requests.get(snapshot_url, timeout=10)
        resp.raise_for_status()
        return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Camera snapshot unavailable: {exc}")


@app.post("/api/v1/stations/{station_code}/mock/{scenario_name}")
def trigger_mock(station_code: str, scenario_name: str, x_api_key: str | None = Header(None)) -> Dict[str, Any]:
    _require_admin_key(x_api_key)
    from uuid import uuid4

    if scenario_name not in {"scenario-1", "scenario-2", "normal", "scenario-3"}:
        raise HTTPException(status_code=404, detail="Scenario not found")

    camera_scene = "clear"
    if scenario_name == "scenario-2":
        camera_scene = "polluted"

    now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    base_payload = {
        "event_id": f"evt_{uuid4().hex[:12]}",
        "event_type": "sensor.batch",
        "source": "envisoft",
        "station_code": station_code,
        "station_name": "Trạm Xả thải A",
        "timestamp_utc": now_utc,
        "sampling_cycle_seconds": 60,
        "camera": {
            "camera_id": "CAM_ST001_01",
            "camera_url": f"http://simulator:8090/camera/{camera_scene}/stream.mjpg",
            "snapshot_url": f"http://simulator:8090/camera/{camera_scene}/snapshot.jpg",
        },
        "sensors": [],
        "signature": "mocked_signature",
    }
    if scenario_name == "normal":
        base_payload["sensors"] = [
            {"sensor_code": "ph", "value": 7.0, "unit": "", "quality": "good"},
            {"sensor_code": "cod", "value": 60.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "tss", "value": 80.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "nh4", "value": 7.0, "unit": "mg/L", "quality": "good"},
        ]
    elif scenario_name == "scenario-1":
        base_payload["sensors"] = [
            {"sensor_code": "ph", "value": 6.8, "unit": "", "quality": "good"},
            {"sensor_code": "cod", "value": 130.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "tss", "value": 88.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "nh4", "value": 8.0, "unit": "mg/L", "quality": "good"},
        ]
    elif scenario_name == "scenario-3":
        base_payload["sensors"] = [
            {"sensor_code": "ph", "value": None, "unit": "", "quality": "null"},
            {"sensor_code": "cod", "value": 99999.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "tss", "value": 81.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "nh4", "value": 7.2, "unit": "mg/L", "quality": "good"},
        ]
    else:
        base_payload["sensors"] = [
            {"sensor_code": "ph", "value": 5.1, "unit": "", "quality": "good"},
            {"sensor_code": "cod", "value": 120.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "tss", "value": 180.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "nh4", "value": 14.0, "unit": "mg/L", "quality": "good"},
        ]

    payload = SensorWebhookPayload.model_validate(base_payload)
    return ingest_sensor_webhook(payload, settings.webhook_token)
