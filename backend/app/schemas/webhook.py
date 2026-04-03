from typing import List, Optional
from pydantic import BaseModel, Field


from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CameraPayload(BaseModel):
    camera_id: Optional[str] = None
    camera_url: Optional[str] = None
    snapshot_url: Optional[str] = None
    video_url: Optional[str] = None
    media_file: Optional[str] = None
    scenario: Optional[str] = None
    media_meta: Optional[Dict[str, Any]] = None


class SensorItem(BaseModel):
    sensor_code: str
    value: Optional[float] = None
    unit: Optional[str] = None
    quality: str = "good"


class SensorWebhookPayload(BaseModel):
    event_id: str
    event_type: str = Field(default="sensor.batch")
    source: str = "envisoft"
    station_code: str
    station_name: str
    timestamp_utc: str
    sampling_cycle_seconds: int = 60
    camera: Optional[CameraPayload] = None
    sensors: List[SensorItem]
    signature: Optional[str] = None
