from __future__ import annotations

from typing import Any, Dict

from app.core.config import settings
from app.services.cleaning_service import clean_sensor_batch
from app.services.fusion_engine import fuse
from app.services.persistence_service import (
    fetch_station,
    fetch_thresholds,
    reset_event_outputs,
    save_alert,
    save_readings,
    save_vision,
    update_station_camera_sources,
)
from app.services.rule_engine import evaluate_sensor_state
from app.services.vision_service import analyze_camera
from pathlib import Path

def process_event_payload(payload_dict: Dict[str, Any]) -> Dict[str, Any]:
    station_code = payload_dict["station_code"]
    station = fetch_station(station_code)
    if not station:
        raise RuntimeError(f"Station not found: {station_code}")

    thresholds = fetch_thresholds(station_code)
    reset_event_outputs(payload_dict["event_id"], station_code)

    cleaned = clean_sensor_batch(station_code, payload_dict["sensors"])
    save_readings(payload_dict, cleaned, payload_dict["timestamp_utc"])
    sensor_state, sensor_issues = evaluate_sensor_state(cleaned, thresholds)

    vision_state = "UNKNOWN"
    vision_result = None
    camera_obj = payload_dict.get("camera") or {}
    camera_url = camera_obj.get("camera_url") if isinstance(camera_obj, dict) else None
    snapshot_url = camera_obj.get("snapshot_url") if isinstance(camera_obj, dict) else None
    media_file = camera_obj.get("media_file") if isinstance(camera_obj, dict) else None
    media_meta = camera_obj.get("media_meta") if isinstance(camera_obj, dict) else None
    scenario = camera_obj.get("scenario") if isinstance(camera_obj, dict) else None

    if not camera_url:
        camera_url = station.get("camera_url") or settings.default_camera_url
    if not snapshot_url:
        snapshot_url = station.get("snapshot_url") or settings.default_snapshot_url

    update_station_camera_sources(station_code, camera_url, snapshot_url)

    if sensor_state != "NORMAL":
        try:
            roi = (station["roi_x"], station["roi_y"], station["roi_w"], station["roi_h"])
            vision_result = analyze_camera(
                station_code=station_code,
                event_id=payload_dict["event_id"],
                camera_url=camera_url,
                snapshot_url=snapshot_url,
                roi=roi,
                media_path=media_path,
                media_file=media_file,
                media_meta=media_meta,
            )
            save_vision(payload_dict, payload_dict["timestamp_utc"], vision_result)
            vision_state = vision_result["vision_state"]
        except Exception as exc:
            vision_state = "UNKNOWN"
            vision_result = None
            sensor_issues.append(f"vision_error: {exc}")

    fusion_result = fuse(sensor_state, vision_state, sensor_issues, vision_result)
    alert_id = save_alert(payload_dict, payload_dict["timestamp_utc"], sensor_state, vision_state, fusion_result, vision_result)
    return {
        "event_id": payload_dict["event_id"],
        "station_code": station_code,
        "sensor_state": sensor_state,
        "vision_state": vision_state,
        "final_state": fusion_result["final_state"],
        "alert_id": alert_id,
        "message": fusion_result["explain_text"],
        "operator_hint": fusion_result["operator_hint"],
        "sensor_issues": sensor_issues,
    }
