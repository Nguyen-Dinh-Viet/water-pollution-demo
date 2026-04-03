from __future__ import annotations
from typing import Any, Dict, List, Tuple


def compare_to_threshold(reading: Dict[str, Any], threshold: Dict[str, Any]) -> Tuple[str, str | None]:
    code = reading["sensor_code"]
    value = reading["value"]
    if reading["is_null"]:
        return "null", f"{code}: null/bad"
    if reading["is_outlier"]:
        return "suspect", f"{code}: outlier"
    if value is None:
        return "null", f"{code}: null"

    min_th = threshold.get("min_threshold")
    max_th = threshold.get("max_threshold")

    if code == "ph":
        if min_th is not None and value < min_th:
            return ("severe", f"pH thấp ({value})") if value < 5.0 else ("mild", f"pH dưới ngưỡng ({value})")
        if max_th is not None and value > max_th:
            return ("severe", f"pH cao ({value})") if value > 9.5 else ("mild", f"pH trên ngưỡng ({value})")
        return "normal", None

    if max_th is not None and value > max_th:
        severe_cutoff = {
            "cod": 90.0,
            "tss": 130.0,
            "nh4": 12.0,
        }.get(code, max_th * 1.2)
        if value > severe_cutoff:
            return "severe", f"{code} vượt ngưỡng mạnh ({value})"
        return "mild", f"{code} vượt ngưỡng ({value})"

    return "normal", None


def evaluate_sensor_state(readings: List[Dict[str, Any]], thresholds: Dict[str, Dict[str, Any]]) -> tuple[str, List[str]]:
    issues: List[str] = []
    severe_count = 0
    mild_count = 0
    null_count = 0

    for r in readings:
        status, issue = compare_to_threshold(r, thresholds.get(r["sensor_code"], {}))
        if issue:
            issues.append(issue)
        if status == "severe":
            severe_count += 1
        elif status == "mild":
            mild_count += 1
        elif status in {"null", "suspect"}:
            null_count += 1

    if severe_count >= 1 or (mild_count + severe_count) >= 2:
        return "ALERT", issues
    if mild_count == 1 or null_count >= 1:
        return "SUSPECT", issues
    return "NORMAL", issues
