CREATE TABLE IF NOT EXISTS click_events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT    NOT NULL,
  page      TEXT    NOT NULL,
  link_url  TEXT    NOT NULL,
  link_text TEXT,
  link_type TEXT    NOT NULL DEFAULT 'unknown'
);

CREATE INDEX IF NOT EXISTS idx_ts      ON click_events (ts);
CREATE INDEX IF NOT EXISTS idx_page    ON click_events (page);
CREATE INDEX IF NOT EXISTS idx_type    ON click_events (link_type);
