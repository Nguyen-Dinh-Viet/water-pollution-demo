import math
from typing import List, Optional, Dict


def _validate_series(y_obs: List[float], y_fore: List[float]) -> bool:
    return (
        y_obs is not None
        and y_fore is not None
        and len(y_obs) > 0
        and len(y_obs) == len(y_fore)
    )


def calc_rmse(y_obs: List[float], y_fore: List[float]) -> Optional[float]:
    if not _validate_series(y_obs, y_fore):
        return None
    mse = sum((a - b) ** 2 for a, b in zip(y_obs, y_fore)) / len(y_obs)
    return math.sqrt(mse)


def calc_mae(y_obs: List[float], y_fore: List[float]) -> Optional[float]:
    if not _validate_series(y_obs, y_fore):
        return None
    return sum(abs(a - b) for a, b in zip(y_obs, y_fore)) / len(y_obs)


def calc_nrmse(y_obs, y_fore):
    if not y_obs or not y_fore or len(y_obs) != len(y_fore):
        return None

    y_max = max(y_obs)
    y_min = min(y_obs)
    denom = y_max - y_min

    if denom == 0:
        return None

    mse = sum((a - b) ** 2 for a, b in zip(y_obs, y_fore)) / len(y_obs)
    rmse = mse ** 0.5
    return rmse / denom


def calc_metrics(y_obs: List[float], y_fore: List[float]) -> Dict:
    return {
        "rmse": calc_rmse(y_obs, y_fore),
        "mae": calc_mae(y_obs, y_fore),
        "nrmse": calc_nrmse(y_obs, y_fore),
        "n_points": len(y_obs) if y_obs and y_fore and len(y_obs) == len(y_fore) else 0
    }