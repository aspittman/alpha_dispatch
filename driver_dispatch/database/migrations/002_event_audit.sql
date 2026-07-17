CREATE TABLE IF NOT EXISTS event_normalization_audit (
  event_id TEXT PRIMARY KEY,
  normalized_at TEXT NOT NULL,
  source_names_json TEXT NOT NULL,
  source_event_ids_json TEXT NOT NULL,
  source_urls_json TEXT NOT NULL,
  conflicting_fields_json TEXT NOT NULL,
  selected_values_json TEXT NOT NULL,
  selection_reasons_json TEXT NOT NULL,
  FOREIGN KEY(event_id) REFERENCES events(id)
);
CREATE INDEX IF NOT EXISTS idx_event_audit_normalized_at ON event_normalization_audit(normalized_at);
