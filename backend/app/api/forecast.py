from fastapi import APIRouter, HTTPException, Query

from app.core.db import get_conn
from app.services.evaluation_service import calc_metrics
from app.services.forecast_service import rolling_backtest
from app.services.persistence_service import save_forecast_result

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])

ALLOWED_SENSOR_CODES = {"cod", "tss", "nh4", "ph"}
ALLOWED_MODEL_NAMES = {"naive_last", "moving_avg_3"}


def load_sensor_history(conn, station_code: str, sensor_code: str, limit: int = 200):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT timestamp_utc, value, is_outlier, is_null
        FROM sensor_readings
        WHERE station_code = %s
          AND sensor_code = %s
        ORDER BY timestamp_utc ASC
        LIMIT %s
        """,
        (station_code, sensor_code, limit),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


@router.get("/run")
def run_forecast(
    station_code: str = Query(..., description="Mã trạm, ví dụ ST001"),
    sensor_code: str = Query(..., description="Mã sensor: cod | tss | nh4 | ph"),
    model_name: str = Query("naive_last", description="Mô hình: naive_last | moving_avg_3"),
    limit: int = Query(200, ge=20, le=2000, description="Số điểm lịch sử tối đa"),
    lookback: int = Query(6, ge=3, le=50, description="Số điểm lịch sử tối thiểu cho rolling backtest"),
):
    sensor_code = sensor_code.lower().strip()
    model_name = model_name.strip()

    if sensor_code not in ALLOWED_SENSOR_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"sensor_code không hợp lệ. Chỉ chấp nhận: {', '.join(sorted(ALLOWED_SENSOR_CODES))}",
        )

    if model_name not in ALLOWED_MODEL_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"model_name không hợp lệ. Chỉ chấp nhận: {', '.join(sorted(ALLOWED_MODEL_NAMES))}",
        )

    with get_conn() as conn:
        rows = load_sensor_history(conn, station_code, sensor_code, limit=limit)

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"Không tìm thấy dữ liệu sensor cho station_code={station_code}, sensor_code={sensor_code}",
            )

        timestamps = []
        values = []

        for row in rows:
            ts = row.get("timestamp_utc")
            value = row.get("value")
            is_outlier = row.get("is_outlier", False)
            is_null = row.get("is_null", False)

            if is_null or is_outlier or value is None:
                continue

            timestamps.append(ts.isoformat() if hasattr(ts, "isoformat") else str(ts))
            values.append(float(value))

        if len(values) < max(lookback + 2, 8):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Không đủ dữ liệu sạch để forecast. "
                    f"Cần ít nhất {max(lookback + 2, 8)} điểm hợp lệ, hiện có {len(values)}."
                ),
            )

        result = rolling_backtest(
            values=values,
            timestamps=timestamps,
            model_name=model_name,
            lookback=lookback,
        )

        y_obs = result.get("y_obs", [])
        y_fore = result.get("y_fore", [])
        t_test = result.get("timestamps", [])

        if not y_obs or not y_fore or len(y_obs) != len(y_fore):
            raise HTTPException(
                status_code=500,
                detail="Kết quả backtest không hợp lệ: chuỗi observed/forecast rỗng hoặc không khớp chiều dài.",
            )

        metrics = calc_metrics(y_obs, y_fore)

        run_id = save_forecast_result(
            conn=conn,
            station_code=station_code,
            sensor_code=sensor_code,
            model_name=model_name,
            horizon_steps=1,
            timestamps=t_test,
            y_obs=y_obs,
            y_fore=y_fore,
            metrics=metrics,
        )

        return {
            "ok": True,
            "run_id": run_id,
            "station_code": station_code,
            "sensor_code": sensor_code,
            "model_name": model_name,
            "lookback": lookback,
            "series": {
                "timestamps": t_test,
                "y_obs": y_obs,
                "y_fore": y_fore,
            },
            "metrics": metrics,
            "message": "Chạy forecast thành công",
        }