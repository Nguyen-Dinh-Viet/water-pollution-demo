from typing import List, Dict
import pandas as pd


def forecast_naive_last(series: List[float], horizon: int) -> List[float]:
    if not series:
        return []
    last_value = series[-1]
    return [last_value for _ in range(horizon)]


def forecast_moving_avg(series: List[float], horizon: int, window: int = 3) -> List[float]:
    if not series:
        return []
    w = min(window, len(series))
    avg_value = sum(series[-w:]) / w
    return [avg_value for _ in range(horizon)]


def rolling_backtest(values, timestamps, model_name="naive_last", lookback=6):
    y_obs = []
    y_fore = []
    t_test = []

    if len(values) <= lookback:
        return {"timestamps": [], "y_obs": [], "y_fore": []}

    for i in range(lookback, len(values)):
        history = values[:i]
        actual = values[i]

        if model_name == "moving_avg_3":
            pred = sum(history[-3:]) / min(3, len(history))
        else:
            pred = history[-1]

        y_obs.append(actual)
        y_fore.append(pred)
        t_test.append(timestamps[i])

    return {"timestamps": t_test, "y_obs": y_obs, "y_fore": y_fore}