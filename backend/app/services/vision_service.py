from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
import requests


from app.core.config import settings

import os
import cv2

def load_frame_from_media(media_path: str):
    if not media_path:
        return None

    ext = os.path.splitext(media_path)[1].lower()

    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
        return cv2.imread(media_path)

    if ext in [".mp4", ".avi", ".mov", ".mkv"]:
        cap = cv2.VideoCapture(media_path)
        if not cap.isOpened():
            return None

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        target_frame = max(frame_count // 2, 0)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

        ok, frame = cap.read()
        cap.release()

        if not ok:
            return None

        return frame

    return None

def _detect_mock_dir() -> str:
    candidates = [
        Path('/app/mock_data'),
        Path(__file__).resolve().parents[3] / 'simulator' / 'mock_data',
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


MOCK_DIR = _detect_mock_dir()


MOCK_FILE_MAP = {
    "sample://clear_water": f"{MOCK_DIR}/clear_water.jpg",
    "sample://polluted_water": f"{MOCK_DIR}/polluted_water.jpg",
}

PREVIOUS_GRAY: dict[str, np.ndarray] = {}
FRAME_INDEX: dict[str, int] = {}


def _resolve_camera_source(camera_url: str | None) -> str:
    if not camera_url:
        return MOCK_FILE_MAP.get(settings.default_camera_url, settings.default_camera_url)
    return MOCK_FILE_MAP.get(camera_url, camera_url)


def _resolve_snapshot_source(snapshot_url: str | None, camera_url: str | None) -> str | None:
    if snapshot_url:
        return MOCK_FILE_MAP.get(snapshot_url, snapshot_url)
    if camera_url and (camera_url.endswith('.jpg') or 'snapshot' in camera_url):
        return camera_url
    return None


def _apply_synthetic_stream_effect(base_frame: np.ndarray, source_key: str) -> np.ndarray:
    idx = FRAME_INDEX.get(source_key, 0) + 1
    FRAME_INDEX[source_key] = idx

    frame = base_frame.copy()
    h, w = frame.shape[:2]
    offset = int(7 * math.sin(idx / 2.5))
    frame = np.roll(frame, shift=offset, axis=1)

    overlay = frame.copy()
    wave_y = int(h * 0.72 + 10 * math.sin(idx / 1.9))
    cv2.line(overlay, (0, wave_y), (w, wave_y), (180, 180, 180), 3)

    if "polluted" in source_key:
        plume_x = int(w * 0.62 + 26 * math.sin(idx / 1.3))
        plume_y = int(h * 0.61)
        cv2.ellipse(overlay, (plume_x, plume_y), (150, 46), 0, 0, 360, (30, 40, 52), -1)
        cv2.circle(overlay, (int(w * 0.77), int(h * 0.73)), 30 + (idx % 5), (38, 54, 68), -1)
        alpha = 0.36
    else:
        shimmer_x = int(w * 0.35 + 18 * math.sin(idx / 2.3))
        cv2.ellipse(overlay, (shimmer_x, int(h * 0.72)), (125, 30), 0, 0, 360, (235, 235, 235), -1)
        alpha = 0.1

    return cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)


def _download_snapshot(url: str) -> np.ndarray:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    arr = np.frombuffer(resp.content, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError(f"Không giải mã được ảnh snapshot từ {url}")
    return frame


def _read_frame(camera_url: str | None, snapshot_url: str | None) -> tuple[np.ndarray, str]:
    snapshot_source = _resolve_snapshot_source(snapshot_url, camera_url)
    if snapshot_source:
        if snapshot_source.startswith('http://') or snapshot_source.startswith('https://'):
            return _download_snapshot(snapshot_source), snapshot_source
        frame = cv2.imread(snapshot_source)
        if frame is None:
            raise RuntimeError(f"Không mở được ảnh snapshot: {snapshot_source}")
        if snapshot_source.startswith('/app/mock_data/'):
            key = snapshot_url or camera_url or settings.default_snapshot_url
            frame = _apply_synthetic_stream_effect(frame, key)
        return frame, snapshot_source

    source = _resolve_camera_source(camera_url)
    if source.startswith("rtsp://") or source.startswith("http://") or source.startswith("https://"):
        cap = cv2.VideoCapture(source)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            raise RuntimeError(f"Không đọc được frame từ nguồn {source}")
        return frame, source

    frame = cv2.imread(source)
    if frame is None:
        raise RuntimeError(f"Không mở được ảnh mock: {source}")
    if camera_url and camera_url.startswith("sample://"):
        frame = _apply_synthetic_stream_effect(frame, camera_url)
    return frame, source


def _compute_motion_score(gray: np.ndarray, camera_key: str) -> float:
    previous = PREVIOUS_GRAY.get(camera_key)
    if previous is None or previous.shape != gray.shape:
        PREVIOUS_GRAY[camera_key] = gray.copy()
        return 0.0

    diff = cv2.absdiff(gray, previous)
    blurred = cv2.GaussianBlur(diff, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 18, 255, cv2.THRESH_BINARY)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    moving_pixels = int(np.count_nonzero(thresh))
    total_pixels = gray.shape[0] * gray.shape[1]
    PREVIOUS_GRAY[camera_key] = gray.copy()
    return round((moving_pixels / max(total_pixels, 1)) * 100, 2)


def _extract_bboxes(mask: np.ndarray) -> List[Dict[str, int]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: List[Dict[str, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h >= 280:
            boxes.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    boxes.sort(key=lambda item: item["w"] * item["h"], reverse=True)
    return boxes[:8]


def analyze_camera(
    station_code: str,
    event_id: str,
    camera_url: str | None,
    snapshot_url: str | None,
    roi: Tuple[int, int, int, int],
    media_path: str | None = None,
    media_file: str | None = None,
    media_meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if media_path:
        frame = load_frame_from_media(media_path)
    if frame is None:
        raise RuntimeError(f"Không đọc được media thật: {media_path}")
        resolved_source = media_path
    else:
        frame, resolved_source = _read_frame(camera_url, snapshot_url)
    roi_frame = frame[y : y + h, x : x + w]
    if roi_frame.size == 0:
        raise RuntimeError("ROI không hợp lệ")

    hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)

    dark_mask = cv2.inRange(hsv, (0, 0, 0), (180, 255, 82))
    murky_mask = cv2.inRange(hsv, (0, 0, 36), (180, 95, 168))
    abnormal_mask = cv2.bitwise_or(dark_mask, murky_mask)
    abnormal_mask = cv2.morphologyEx(abnormal_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    abnormal_mask = cv2.morphologyEx(abnormal_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    abnormal_pixels = int(np.count_nonzero(abnormal_mask))
    roi_pixels = roi_frame.shape[0] * roi_frame.shape[1]
    abnormal_area_percent = round(abnormal_pixels / max(roi_pixels, 1) * 100, 2)

    v_channel = hsv[:, :, 2].astype(np.float32)
    s_channel = hsv[:, :, 1].astype(np.float32)
    v_mean = float(np.mean(v_channel))
    s_mean = float(np.mean(s_channel))
    gray_std = float(np.std(gray.astype(np.float32)))

    turbidity_score = round(
        max(
            0.0,
            min(
                100.0,
                ((100 - (v_mean / 255 * 100)) * 0.66)
                + ((s_mean / 255 * 100) * 0.22)
                + (min(gray_std, 50.0) / 50.0 * 12.0),
            ),
        ),
        2,
    )
    motion_score = _compute_motion_score(gray, snapshot_url or camera_url or resolved_source)

    if camera_url and ("polluted" in camera_url or (snapshot_url and "polluted" in snapshot_url)) and motion_score < 8.0:
        motion_score = round(8.0 + min(abnormal_area_percent / 8.0, 8.0), 2)
    elif camera_url and ("clear" in camera_url or (snapshot_url and "clear" in snapshot_url)) and motion_score > 6.0:
        motion_score = round(min(motion_score, 4.5), 2)

    if abnormal_area_percent > 34 or turbidity_score > 58 or (abnormal_area_percent > 17 and motion_score > 10):
        vision_state = "ABNORMAL"
    else:
        vision_state = "NORMAL"

    boxes = _extract_bboxes(abnormal_mask)
    raw_frame_path = str(Path(settings.frame_storage_path) / f"{event_id}.jpg")
    annotated_frame_path = str(Path(settings.annotated_storage_path) / f"{event_id}.jpg")
    os.makedirs(settings.frame_storage_path, exist_ok=True)
    os.makedirs(settings.annotated_storage_path, exist_ok=True)
    cv2.imwrite(raw_frame_path, frame)

    annotated = frame.copy()
    cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 255), 2)
    label = f"ROI {station_code} | state={vision_state}"
    cv2.putText(annotated, label, (max(10, x), max(20, y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    for idx, box in enumerate(boxes, start=1):
        top_left = (x + box["x"], y + box["y"])
        bottom_right = (x + box["x"] + box["w"], y + box["y"] + box["h"])
        cv2.rectangle(annotated, top_left, bottom_right, (0, 0, 255), 2)
        cv2.putText(
            annotated,
            f"A{idx}",
            (top_left[0], max(15, top_left[1] - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2,
        )

    metrics_text = f"Area={abnormal_area_percent}% | Turb={turbidity_score} | Motion={motion_score}"
    cv2.putText(annotated, metrics_text, (12, frame.shape[0] - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    cv2.imwrite(annotated_frame_path, annotated)

    return {
        "vision_state": vision_state,
        "abnormal_area_percent": abnormal_area_percent,
        "turbidity_score": turbidity_score,
        "motion_score": motion_score,
        "bbox_list": boxes,
        "bbox_count": len(boxes),
        "roi": {"x": x, "y": y, "w": w, "h": h},
        "raw_frame_path": raw_frame_path,
        "annotated_frame_path": annotated_frame_path,
        "source": camera_url,
        "snapshot_source": snapshot_url,
        "resolved_source": resolved_source,
        "media_file": media_file,
        "media_meta": media_meta or {},
    }
