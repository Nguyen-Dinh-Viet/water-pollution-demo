import math
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import requests
from fastapi import FastAPI
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MOCK_DIR = BASE_DIR / "mock_data"
MEDIA_DIR = Path("/app/media")

CURRENT_SCENARIO = "normal"
CURRENT_MEDIA_FILE = None

with open(MEDIA_DIR / "manifest.json", "r", encoding="utf-8") as f:
    MEDIA_MANIFEST = json.load(f)

TARGET_WEBHOOK = os.getenv("SIMULATOR_TARGET_WEBHOOK", "http://api:8000/api/v1/webhooks/envisoft/sensor")
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "envisoft_webhook_st001_2026")
APP_PORT = int(os.getenv("SIMULATOR_PORT", "8090"))

app = FastAPI(title="EnviSoft Simulator")
BASE_DIR = Path(__file__).resolve().parent
MOCK_DIR = BASE_DIR / "mock_data"
# app.mount("/videos", StaticFiles(directory=str(MOCK_DIR)), name="videos")

FRAME_COUNTER = {"clear": 0, "polluted": 0}

def get_media_candidates(scenario: str):
    files = []
    for filename, meta in MEDIA_MANIFEST.items():
        if meta.get("scenario") == scenario:
            files.append(filename)
    return files

CURRENT_MEDIA_FILE = None

def pick_media_for_scenario(scenario: str):
    global CURRENT_MEDIA_FILE
    candidates = get_media_candidates(scenario)
    if not candidates:
        CURRENT_MEDIA_FILE = None
        return None
    CURRENT_MEDIA_FILE = candidates[0]
    return CURRENT_MEDIA_FILE

def _media_path_from_filename(filename: str) -> Path:
    meta = MEDIA_MANIFEST.get(filename, {})
    scenario = meta.get("scenario", "normal")
    folder = "polluted" if scenario == "real_pollution" else "normal"
    return MEDIA_DIR / folder / filename


def _load_base_frame_for_scene(scene: str):
    scenario = "real_pollution" if scene == "polluted" else "normal"
    candidates = get_media_candidates(scenario)

    if not candidates:
        raise RuntimeError(f"Không có media cho scenario={scenario}")

    filename = candidates[0]
    path = _media_path_from_filename(filename)

    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        frame = cv2.imread(str(path))
        if frame is None:
            raise RuntimeError(f"Không đọc được ảnh media: {path}")
        return frame, filename

    if ext in {".mp4", ".avi", ".mov", ".mkv"}:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Không mở được video media: {path}")
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        target_frame = max(frame_count // 2, 0)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            raise RuntimeError(f"Không đọc được frame từ video: {path}")
        return frame, filename

    raise RuntimeError(f"Định dạng media không hỗ trợ: {path}")

def _scene_assets(scene: str):
    scene = "polluted" if scene == "polluted" else "clear"
    image_path = MOCK_DIR / ("polluted_water.jpg" if scene == "polluted" else "clear_water.jpg")
    video_path = MOCK_DIR / ("polluted_water.mp4" if scene == "polluted" else "clear_water.mp4")
    return image_path, video_path


def _make_dynamic_frame(scene: str) -> np.ndarray:
    frame, _ = _load_base_frame_for_scene(scene)
    if frame is None:
        raise RuntimeError(f"Missing mock image: {image_path}")

    FRAME_COUNTER[scene] += 1
    idx = FRAME_COUNTER[scene]
    h, w = frame.shape[:2]

    overlay = frame.copy()
    wave_y = int(h * 0.72 + 10 * math.sin(idx / 2.1))
    cv2.line(overlay, (0, wave_y), (w, wave_y), (185, 185, 185), 3)

    if scene == "polluted":
        plume_x = int(w * 0.60 + 20 * math.sin(idx / 1.4))
        cv2.ellipse(overlay, (plume_x, int(h * 0.62)), (150, 45), 0, 0, 360, (34, 44, 55), -1)
        cv2.circle(overlay, (int(w * 0.75), int(h * 0.73)), 28 + (idx % 5), (44, 58, 72), -1)
        alpha = 0.34
    else:
        shimmer_x = int(w * 0.35 + 15 * math.sin(idx / 2.6))
        cv2.ellipse(overlay, (shimmer_x, int(h * 0.72)), (120, 30), 0, 0, 360, (236, 236, 236), -1)
        alpha = 0.10

    frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
    frame = np.roll(frame, shift=int(5 * math.sin(idx / 2.4)), axis=1)
    return frame


def _jpeg_bytes(frame: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buffer.tobytes()


def _camera_urls(scene: str):
    scene = "polluted" if scene == "polluted" else "clear"
    return {
        "camera_url": f"http://simulator:{APP_PORT}/camera/{scene}/stream.mjpg",
        "snapshot_url": f"http://simulator:{APP_PORT}/camera/{scene}/snapshot.jpg",
        "video_url": f"http://simulator:{APP_PORT}/camera/{scene}/video.mp4",
    }


def _payload_for(scenario: str):
    now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    scene = "clear"
    scenario_key = "real_pollution" if scene == "polluted" else "normal"
    picked = pick_media_for_scenario(scenario_key)
    media_meta = MEDIA_MANIFEST.get(picked, {}) if picked else {}
    base = {
        "event_id": f"evt_{uuid4().hex[:12]}",
        "event_type": "sensor.batch",
        "source": "envisoft",
        "station_code": "ST001",
        "station_name": "Trạm Xả thải A",
        "timestamp_utc": now_utc,
        "sampling_cycle_seconds": 60,
        "camera": {
            "camera_id": "CAM_ST001_01",
            **_camera_urls(scene),
            "media_file": picked,
            "scenario": scenario_key,
            "media_meta": media_meta,
        },
        "signature": "mocked_signature",
    }
    if scenario == "sensor_fault":
        base["sensors"] = [
            {"sensor_code": "ph", "value": 6.8, "unit": "", "quality": "good"},
            {"sensor_code": "cod", "value": 130.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "tss", "value": 88.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "nh4", "value": 8.0, "unit": "mg/L", "quality": "good"},
        ]
    elif scenario == "real_pollution":
        scene = "polluted"
        base["camera"] = {"camera_id": "CAM_ST001_01", **_camera_urls(scene)}
        base["sensors"] = [
            {"sensor_code": "ph", "value": 5.1, "unit": "", "quality": "good"},
            {"sensor_code": "cod", "value": 120.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "tss", "value": 180.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "nh4", "value": 14.0, "unit": "mg/L", "quality": "good"},
        ]
    elif scenario == "null_outlier":
        base["sensors"] = [
            {"sensor_code": "ph", "value": None, "unit": "", "quality": "null"},
            {"sensor_code": "cod", "value": 99999.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "tss", "value": 82.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "nh4", "value": 7.1, "unit": "mg/L", "quality": "good"},
        ]
    else:
        base["sensors"] = [
            {"sensor_code": "ph", "value": 7.0, "unit": "", "quality": "good"},
            {"sensor_code": "cod", "value": 60.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "tss", "value": 80.0, "unit": "mg/L", "quality": "good"},
            {"sensor_code": "nh4", "value": 7.0, "unit": "mg/L", "quality": "good"},
        ]
    return base


def _send(scenario: str):
    payload = _payload_for(scenario)
    resp = requests.post(TARGET_WEBHOOK, json=payload, headers={"X-Webhook-Token": WEBHOOK_TOKEN}, timeout=30)
    return {"status_code": resp.status_code, "body": resp.json(), "payload": payload}


@app.get("/")
def root():
    return {"service": "simulator", "target": TARGET_WEBHOOK}


@app.get("/camera/{scene}/snapshot.jpg")
def camera_snapshot(scene: str):
    frame = _make_dynamic_frame(scene)
    return Response(content=_jpeg_bytes(frame), media_type="image/jpeg")


@app.get("/camera/{scene}/stream.mjpg")
def camera_stream(scene: str):
    scene = "polluted" if scene == "polluted" else "clear"

    def generate():
        while True:
            frame = _make_dynamic_frame(scene)
            jpg = _jpeg_bytes(frame)
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/camera/{scene}/video.mp4")
def camera_video(scene: str):
    scenario = "real_pollution" if scene == "polluted" else "normal"
    candidates = get_media_candidates(scenario)
    if not candidates:
        return Response(status_code=404, content=b"Media not found")

    filename = candidates[0]
    path = _media_path_from_filename(filename)

    if not path.exists():
        return Response(status_code=404, content=b"Media file missing")

    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.post("/scenario/normal")
def normal():
    return _send("normal")


@app.post("/scenario/sensor-fault")
def sensor_fault():
    return _send("sensor_fault")


@app.post("/scenario/real-pollution")
def real_pollution():
    return _send("real_pollution")


@app.post("/scenario/null-outlier")
def null_outlier():
    return _send("null_outlier")
