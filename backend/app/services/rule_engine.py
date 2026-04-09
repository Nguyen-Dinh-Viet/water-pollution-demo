from __future__ import annotations
from typing import Any, Dict, List, Tuple


def compare_to_threshold(reading: Dict[str, Any], threshold_cfg: Dict[str, Any]) -> Tuple[str, str | None]:
    code = reading["sensor_code"]
    value = reading["value"]

    if reading["is_null"]:
        return "suspect", f"{code} thiếu dữ liệu"
    if reading["is_outlier"]:
        return "suspect", f"{code} là giá trị ngoại lai"
    if reading["is_spike"]:
        return "suspect", f"{code} biến động đột ngột"

    if value is None:
        return "suspect", f"{code} không có giá trị"

    min_th = threshold_cfg.get("min_threshold")
    max_th = threshold_cfg.get("max_threshold")

    if code == "ph":
        if min_th is not None and value < min_th:
            return "alert", f"pH thấp hơn ngưỡng ({value} < {min_th})"
        if max_th is not None and value > max_th:
            return "alert", f"pH cao hơn ngưỡng ({value} > {max_th})"
        return "normal", None

    if min_th is not None and value < min_th:
        return "alert", f"{code} thấp hơn ngưỡng ({value} < {min_th})"

    if max_th is not None and value > max_th:
        return "alert", f"{code} vượt ngưỡng ({value} > {max_th})"

    return "normal", None


def evaluate_sensor_state(readings: List[Dict[str, Any]], thresholds: Dict[str, Dict[str, Any]]) -> tuple[str, List[str]]:
    issues: List[str] = []
    has_alert = False
    has_suspect = False

    for r in readings:
        status, issue = compare_to_threshold(r, thresholds.get(r["sensor_code"], {}))
        if issue:
            issues.append(issue)

        if status == "alert":
            has_alert = True
        elif status == "suspect":
            has_suspect = True

    if has_alert:
        return "ALERT", issues
    if has_suspect:
        return "SUSPECT", issues
    return "NORMAL", issues