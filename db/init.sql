CREATE TABLE IF NOT EXISTS stations (
  id SERIAL PRIMARY KEY,
  station_code VARCHAR(50) UNIQUE NOT NULL,
  station_name VARCHAR(255) NOT NULL,
  timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
  camera_url TEXT,
  snapshot_url TEXT,
  roi_x INT DEFAULT 120,
  roi_y INT DEFAULT 210,
  roi_w INT DEFAULT 560,
  roi_h INT DEFAULT 220,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS station_sensors (
  id SERIAL PRIMARY KEY,
  station_id INT NOT NULL REFERENCES stations(id),
  sensor_code VARCHAR(50) NOT NULL,
  sensor_name VARCHAR(100) NOT NULL,
  unit VARCHAR(50),
  min_threshold DOUBLE PRECISION,
  max_threshold DOUBLE PRECISION,
  UNIQUE(station_id, sensor_code)
);

CREATE TABLE IF NOT EXISTS webhook_events_raw (
  id BIGSERIAL PRIMARY KEY,
  event_id VARCHAR(100) UNIQUE NOT NULL,
  source VARCHAR(50) NOT NULL,
  station_code VARCHAR(50) NOT NULL,
  payload JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed BOOLEAN NOT NULL DEFAULT FALSE,
  processing_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  processing_started_at TIMESTAMPTZ,
  processed_at TIMESTAMPTZ,
  processing_worker VARCHAR(100),
  process_message TEXT
);

CREATE TABLE IF NOT EXISTS sensor_readings (
  id BIGSERIAL PRIMARY KEY,
  event_id VARCHAR(100) NOT NULL,
  station_code VARCHAR(50) NOT NULL,
  sensor_code VARCHAR(50) NOT NULL,
  value DOUBLE PRECISION,
  unit VARCHAR(20),
  quality VARCHAR(20),
  is_null BOOLEAN NOT NULL DEFAULT FALSE,
  is_outlier BOOLEAN NOT NULL DEFAULT FALSE,
  is_spike BOOLEAN NOT NULL DEFAULT FALSE,
  timestamp_utc TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(event_id, sensor_code)
);

CREATE TABLE IF NOT EXISTS vision_results (
  id BIGSERIAL PRIMARY KEY,
  event_id VARCHAR(100) UNIQUE NOT NULL,
  station_code VARCHAR(50) NOT NULL,
  frame_timestamp_utc TIMESTAMPTZ NOT NULL,
  abnormal_area_percent DOUBLE PRECISION,
  turbidity_score DOUBLE PRECISION,
  motion_score DOUBLE PRECISION,
  vision_state VARCHAR(20) NOT NULL,
  bbox_json JSONB,
  raw_frame_path TEXT,
  annotated_frame_path TEXT,
  media_file TEXT,
  media_meta JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
  id BIGSERIAL PRIMARY KEY,
  event_id VARCHAR(100) UNIQUE NOT NULL,
  station_code VARCHAR(50) NOT NULL,
  sensor_state VARCHAR(20) NOT NULL,
  vision_state VARCHAR(20) NOT NULL,
  final_state VARCHAR(40) NOT NULL,
  severity INT NOT NULL,
  explain_text TEXT NOT NULL,
  acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
  timestamp_utc TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_evidences (
  id BIGSERIAL PRIMARY KEY,
  alert_id BIGINT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
  evidence_type VARCHAR(30) NOT NULL,
  file_path TEXT NOT NULL,
  meta JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_station_time ON sensor_readings(station_code, timestamp_utc DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_station_time ON alerts(station_code, timestamp_utc DESC);
CREATE INDEX IF NOT EXISTS idx_vision_station_time ON vision_results(station_code, frame_timestamp_utc DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_station_received ON webhook_events_raw(station_code, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_processing_status ON webhook_events_raw(processing_status, received_at ASC);

CREATE TABLE IF NOT EXISTS forecast_runs (
  id BIGSERIAL PRIMARY KEY,
  station_code VARCHAR(50) NOT NULL,
  sensor_code VARCHAR(50) NOT NULL,
  model_name VARCHAR(50) NOT NULL,
  horizon_steps INT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS forecast_predictions (
  id BIGSERIAL PRIMARY KEY,
  run_id BIGINT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
  timestamp_utc TIMESTAMPTZ NOT NULL,
  y_obs DOUBLE PRECISION,
  y_fore DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS forecast_metrics (
  id BIGSERIAL PRIMARY KEY,
  run_id BIGINT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
  rmse DOUBLE PRECISION,
  mae DOUBLE PRECISION,
  nrmse DOUBLE PRECISION,
  n_points INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO stations (station_code, station_name, timezone, camera_url, snapshot_url)
VALUES (
  'ST001',
  'Trạm Xả thải A',
  'UTC',
  'http://simulator:8090/camera/clear/stream.mjpg',
  'http://simulator:8090/camera/clear/snapshot.jpg'
)
ON CONFLICT (station_code) DO NOTHING;

INSERT INTO station_sensors (station_id, sensor_code, sensor_name, unit, min_threshold, max_threshold)
SELECT s.id, 'ph', 'pH', '', 5.5, 9.0
FROM stations s WHERE s.station_code = 'ST001'
ON CONFLICT (station_id, sensor_code) DO NOTHING;

INSERT INTO station_sensors (station_id, sensor_code, sensor_name, unit, min_threshold, max_threshold)
SELECT s.id, 'cod', 'COD', 'mg/L', NULL, 75.0
FROM stations s WHERE s.station_code = 'ST001'
ON CONFLICT (station_id, sensor_code) DO NOTHING;

INSERT INTO station_sensors (station_id, sensor_code, sensor_name, unit, min_threshold, max_threshold)
SELECT s.id, 'tss', 'TSS', 'mg/L', NULL, 100.0
FROM stations s WHERE s.station_code = 'ST001'
ON CONFLICT (station_id, sensor_code) DO NOTHING;

INSERT INTO station_sensors (station_id, sensor_code, sensor_name, unit, min_threshold, max_threshold)
SELECT s.id, 'nh4', 'NH4', 'mg/L', NULL, 10.0
FROM stations s WHERE s.station_code = 'ST001'
ON CONFLICT (station_id, sensor_code) DO NOTHING;


