CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, source_event_id TEXT, name TEXT NOT NULL,
  start_datetime TEXT, city TEXT, status TEXT NOT NULL, payload_json TEXT NOT NULL,
  first_seen TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_datetime);
CREATE TABLE IF NOT EXISTS event_sources (
  event_id TEXT NOT NULL, source TEXT NOT NULL, source_event_id TEXT,
  PRIMARY KEY(event_id, source, source_event_id), FOREIGN KEY(event_id) REFERENCES events(id)
);
CREATE TABLE IF NOT EXISTS venues (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS weather_snapshots (id INTEGER PRIMARY KEY, event_id TEXT, captured_at TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS weekly_reports (id INTEGER PRIMARY KEY, week_start TEXT NOT NULL, created_at TEXT NOT NULL, html_path TEXT, text_path TEXT, payload_json TEXT);
CREATE TABLE IF NOT EXISTS recommendations (id INTEGER PRIMARY KEY, report_id INTEGER, event_id TEXT, opportunity_score REAL, confidence_score REAL, payload_json TEXT NOT NULL, scoring_version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS driving_sessions (id INTEGER PRIMARY KEY, session_date TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prediction_outcomes (id INTEGER PRIMARY KEY, recommendation_id INTEGER, session_id INTEGER, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_errors (id INTEGER PRIMARY KEY, source TEXT NOT NULL, occurred_at TEXT NOT NULL, message TEXT NOT NULL, details_json TEXT);
CREATE TABLE IF NOT EXISTS configuration_history (id INTEGER PRIMARY KEY, captured_at TEXT NOT NULL, config_json TEXT NOT NULL);

