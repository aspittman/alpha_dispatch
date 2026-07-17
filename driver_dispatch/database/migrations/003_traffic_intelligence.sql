CREATE TABLE IF NOT EXISTS traffic_check_runs (
  id INTEGER PRIMARY KEY, run_mode TEXT NOT NULL, origin_name TEXT NOT NULL,
  captured_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traffic_runs_mode_time ON traffic_check_runs(run_mode, captured_at);
CREATE TABLE IF NOT EXISTS route_snapshots (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, zone TEXT NOT NULL, captured_at TEXT NOT NULL, payload_json TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES traffic_check_runs(id));
CREATE TABLE IF NOT EXISTS traffic_incidents (source TEXT NOT NULL, source_id TEXT NOT NULL, last_seen TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(source, source_id));
CREATE TABLE IF NOT EXISTS zone_recommendations (id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, zone TEXT NOT NULL, classification TEXT NOT NULL, payload_json TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES traffic_check_runs(id));
