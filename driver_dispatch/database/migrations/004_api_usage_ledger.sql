CREATE TABLE IF NOT EXISTS api_usage_ledger (
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL,
  service TEXT NOT NULL,
  sku_category TEXT,
  request_type TEXT NOT NULL,
  request_id TEXT NOT NULL UNIQUE,
  run_id TEXT,
  timestamp TEXT NOT NULL,
  billing_month TEXT NOT NULL,
  billing_day TEXT NOT NULL,
  origin_count INTEGER NOT NULL DEFAULT 0,
  destination_count INTEGER NOT NULL DEFAULT 0,
  element_count INTEGER NOT NULL DEFAULT 0,
  cache_hit INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  estimated_cost REAL,
  reserved INTEGER NOT NULL DEFAULT 0,
  completed INTEGER NOT NULL DEFAULT 0,
  error_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_usage_provider_month ON api_usage_ledger(provider, service, billing_month, status);
CREATE INDEX IF NOT EXISTS idx_api_usage_provider_day ON api_usage_ledger(provider, service, billing_day, status);
