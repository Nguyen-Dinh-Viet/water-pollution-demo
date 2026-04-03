from dataclasses import dataclass
import os


@dataclass
class Settings:
    app_env: str = os.getenv("APP_ENV", "dev")
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    database_url: str = os.getenv("DATABASE_URL", "postgresql://waterdemo:waterdemo_pass@db:5432/waterdemo")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "demo_admin_key_2026")
    webhook_token: str = os.getenv("WEBHOOK_TOKEN", "envisoft_webhook_st001_2026")
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "UTC")
    frame_storage_path: str = os.getenv("FRAME_STORAGE_PATH", "/app/data/frames")
    annotated_storage_path: str = os.getenv("ANNOTATED_STORAGE_PATH", "/app/data/annotated")
    default_camera_url: str = os.getenv("DEFAULT_CAMERA_URL", "sample://clear_water")
    default_snapshot_url: str = os.getenv("DEFAULT_SNAPSHOT_URL", "sample://clear_water")
    worker_poll_seconds: float = float(os.getenv("WORKER_POLL_SECONDS", "1.5"))
    worker_name: str = os.getenv("WORKER_NAME", "worker-1")


settings = Settings()
