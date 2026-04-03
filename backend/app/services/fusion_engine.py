from __future__ import annotations
from typing import Any, Dict, List


def _sensor_summary(sensor_issues: List[str]) -> str:
    if not sensor_issues:
        return "Không ghi nhận bất thường từ sensor."
    return "; ".join(sensor_issues)


def _vision_summary(vision_metrics: Dict[str, Any] | None) -> str:
    if not vision_metrics:
        return "Không có dữ liệu vision."
    return (
        f"AI vision: area={vision_metrics.get('abnormal_area_percent', 0)}%, "
        f"turbidity={vision_metrics.get('turbidity_score', 0)}, "
        f"motion={vision_metrics.get('motion_score', 0)}, "
        f"bbox={vision_metrics.get('bbox_count', len(vision_metrics.get('bbox_list', [])))}"
    )


def fuse(sensor_state: str, vision_state: str, sensor_issues: List[str], vision_metrics: Dict[str, Any] | None) -> Dict[str, Any]:
    sensor_text = _sensor_summary(sensor_issues)
    vision_text = _vision_summary(vision_metrics)

    if sensor_state == "NORMAL" and vision_state == "NORMAL":
        return {
            "final_state": "NORMAL",
            "severity": 0,
            "explain_text": "Số liệu và hình ảnh đều bình thường.",
            "operator_hint": "Tiếp tục giám sát theo chu kỳ hiện tại.",
        }

    if sensor_state in {"SUSPECT", "ALERT"} and vision_state == "NORMAL":
        return {
            "final_state": "CHECK_DEVICE",
            "severity": 1,
            "explain_text": f"Sensor bất thường ({sensor_text}) nhưng camera không ghi nhận nước màu lạ. {vision_text}.",
            "operator_hint": "Kiểm tra đầu đo, hiệu chuẩn sensor và đường truyền dữ liệu.",
        }

    if sensor_state in {"SUSPECT", "ALERT"} and vision_state == "ABNORMAL" and vision_metrics:
        return {
            "final_state": "CRITICAL_ALERT",
            "severity": 2,
            "explain_text": f"Sensor bất thường ({sensor_text}) và camera ghi nhận dấu hiệu xả thải bất thường. {vision_text}.",
            "operator_hint": "Cảnh báo nguy cấp. Đề nghị xác minh hiện trường và thông báo đơn vị vận hành ngay.",
        }

    if sensor_state == "NORMAL" and vision_state == "ABNORMAL":
        return {
            "final_state": "SUSPICIOUS",
            "severity": 1,
            "explain_text": f"Camera bất thường nhưng sensor chưa vượt ngưỡng. {vision_text}.",
            "operator_hint": "Kiểm tra lại camera, ánh sáng, ROI và đối chiếu màu nước tại hiện trường.",
        }

    return {
        "final_state": "VERIFY_CAMERA",
        "severity": 1,
        "explain_text": f"Không đủ dữ liệu camera để kết luận. Sensor: {sensor_text}",
        "operator_hint": "Kiểm tra kết nối camera hoặc chuyển sang nguồn video dự phòng.",
    }
