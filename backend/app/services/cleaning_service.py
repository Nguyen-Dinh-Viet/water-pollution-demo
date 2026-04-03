from __future__ import annotations
from collections import deque
from statistics import median
from typing import Any, Dict, List


OUTLIER_LIMITS = {
    "ph": (0.0, 14.0),
    "cod": (0.0, 5000.0),
    "tss": (0.0, 10000.0),
    "nh4": (0.0, 1000.0),
}


class SpikeMemory:
    def __init__(self) -> None:
        self.history: dict[str, deque[float]] = {}

    def check_and_update(self, key: str, value: float | None) -> bool:
        if value is None:
            return False
        bucket = self.history.setdefault(key, deque(maxlen=5))
        is_spike = False
        if len(bucket) >= 3:
            med = median(bucket)
            if med > 0 and abs(value - med) / max(med, 1) > 3.0:
                is_spike = True
        bucket.append(value)
        return is_spike


SPIKE_MEMORY = SpikeMemory()


def clean_sensor_item(station_code: str, item: Dict[str, Any]) -> Dict[str, Any]:
    code = item["sensor_code"].strip().lower()
    raw_value = item.get("value")
    quality = (item.get("quality") or "good").lower()

    is_null = raw_value is None or quality == "null"
    value = None if is_null else float(raw_value)
    min_valid, max_valid = OUTLIER_LIMITS.get(code, (float("-inf"), float("inf")))
    is_outlier = value is not None and not (min_valid <= value <= max_valid)
    is_spike = False
    if value is not None and not is_outlier:
        is_spike = SPIKE_MEMORY.check_and_update(f"{station_code}:{code}", value)

    if is_outlier:
        quality = "suspect"

    return {
        "sensor_code": code,
        "value": value,
        "unit": item.get("unit"),
        "quality": quality,
        "is_null": is_null,
        "is_outlier": is_outlier,
        "is_spike": is_spike,
    }


def clean_sensor_batch(station_code: str, sensors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [clean_sensor_item(station_code, sensor) for sensor in sensors]
