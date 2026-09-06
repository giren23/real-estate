CREATE TABLE IF NOT EXISTS paper_portfolios (
  account_id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_paper_portfolios_updated_at
  ON paper_portfolios(updated_at);
