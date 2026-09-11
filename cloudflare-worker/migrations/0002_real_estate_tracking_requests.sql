CREATE TABLE IF NOT EXISTS real_estate_tracking_requests (
  id INTEGER PRIMARY KEY,
  lawd_cd TEXT NOT NULL CHECK(length(lawd_cd)=5),
  apt_name TEXT NOT NULL,
  dong TEXT NOT NULL DEFAULT '',
  requester_hash TEXT NOT NULL,
  requested_date TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  UNIQUE(lawd_cd, apt_name, dong, requester_hash, requested_date)
);
CREATE INDEX IF NOT EXISTS idx_tracking_requests_region_date
  ON real_estate_tracking_requests(lawd_cd, requested_at DESC);
