from fastapi import APIRouter, HTTPException, Query

from app.core.db import get_conn
from app.services.evaluation_service import calc_metrics
from app.services.forecast_service import rolling_backtest
from app.services.persistence_service import save_forecast_result

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])


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
    station_code: str = Query(...),
    sensor_code: str = Query(...),
    model_name: str = Query("naive_last"),
    limit: int = Query(200, ge=20, le=2000),
):
    if model_name not in {"naive_last", "moving_avg_3"}:
        raise HTTPException(status_code=400, detail="model_name không hợp lệ")

    with get_conn() as conn:
        rows = load_sensor_history(conn, station_code, sensor_code, limit=limit)

        timestamps = []
        values = []

        for row in rows:
            ts = row["timestamp_utc"]
            value = row["value"]
            is_outlier = row["is_outlier"]
            is_null = row["is_null"]

            if is_null or is_outlier or value is None:
                continue

            timestamps.append(ts.isoformat() if hasattr(ts, "isoformat") else str(ts))
            values.append(float(value))

        if len(values) < 8:
            raise HTTPException(status_code=400, detail="Không đủ dữ liệu để forecast")

        result = rolling_backtest(values, timestamps, model_name=model_name, lookback=6)
        metrics = calc_metrics(result["y_obs"], result["y_fore"])

        run_id = save_forecast_result(
            conn=conn,
            station_code=station_code,
            sensor_code=sensor_code,
            model_name=model_name,
            horizon_steps=1,
            timestamps=result["timestamps"],
            y_obs=result["y_obs"],
            y_fore=result["y_fore"],
            metrics=metrics,
        )

        return {
            "run_id": run_id,
            "station_code": station_code,
            "sensor_code": sensor_code,
            "model_name": model_name,
            "series": result,
            "metrics": metrics,
        }