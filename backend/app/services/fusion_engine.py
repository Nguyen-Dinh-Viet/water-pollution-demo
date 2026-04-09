from __future__ import annotations
from typing import Any, Dict, List


def _sensor_summary(sensor_issues: List[str]) -> str:
    if not sensor_issues:
        return "Không ghi nhận bất thường từ sensor."
    return "; ".join(sensor_issues)


def _vision_summary(vision_metrics: Dict[str, Any] | None, vision_state: str) -> str:
    if not vision_metrics:
        return "Chưa có kết quả AI camera."

    area = vision_metrics.get("abnormal_area_percent", 0)
    turb = vision_metrics.get("turbidity_score", 0)
    motion = vision_metrics.get("motion_score", 0)
    bbox = vision_metrics.get("bbox_count", len(vision_metrics.get("bbox_list", [])))

    if vision_state == "ABNORMAL":
        return (
            f"AI camera dự đoán có dấu hiệu ô nhiễm "
            f"(vùng bất thường={area}%, đậm/đục={turb}, chuyển động={motion}, bbox={bbox})."
        )
    if vision_state == "NORMAL":
        return (
            f"AI camera chưa phát hiện dấu hiệu ô nhiễm rõ "
            f"(vùng bất thường={area}%, đậm/đục={turb}, chuyển động={motion}, bbox={bbox})."
        )
    return "AI camera chưa đủ dữ liệu để kết luận."


def fuse(sensor_state: str, vision_state: str, sensor_issues: List[str], vision_metrics: Dict[str, Any] | None) -> Dict[str, Any]:
    sensor_text = _sensor_summary(sensor_issues)
    vision_text = _vision_summary(vision_metrics, vision_state)

    if sensor_state == "ALERT":
        return {
            "final_state": "CRITICAL_ALERT",
            "severity": 2,
            "explain_text": f"Có chỉ số vượt ngưỡng ô nhiễm: {sensor_text}. {vision_text}",
            "operator_hint": "Phát cảnh báo ngay. Kiểm tra hiện trường, đối chiếu camera và thông báo đơn vị vận hành.",
        }

    if sensor_state == "SUSPECT":
        return {
            "final_state": "CHECK_DEVICE",
            "severity": 1,
            "explain_text": f"Dữ liệu sensor nghi ngờ bất thường: {sensor_text}. {vision_text}",
            "operator_hint": "Kiểm tra đầu đo, hiệu chuẩn sensor, đường truyền và chất lượng dữ liệu.",
        }

    if sensor_state == "NORMAL" and vision_state == "ABNORMAL":
        return {
            "final_state": "SUSPICIOUS",
            "severity": 1,
            "explain_text": f"Sensor chưa vượt ngưỡng nhưng AI camera nghi ngờ bất thường. {vision_text}",
            "operator_hint": "Kiểm tra camera, ROI, ánh sáng và xác minh trực tiếp hiện trường.",
        }

    return {
        "final_state": "NORMAL",
        "severity": 0,
        "explain_text": "Tất cả chỉ số đang trong ngưỡng cho phép và chưa có dấu hiệu bất thường rõ từ AI camera.",
        "operator_hint": "Tiếp tục giám sát theo chu kỳ.",
    }