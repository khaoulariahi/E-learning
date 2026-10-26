CREATE TABLE IF NOT EXISTS notebooks (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  notebook_id TEXT REFERENCES notebooks(id),
  type TEXT NOT NULL,                 -- 'demo', 'ingest_file', 'resume', 'podcast', ...
  params_json TEXT NOT NULL,
  status TEXT NOT NULL,               -- queued | running | done | failed | cancelled
  priority INTEGER NOT NULL DEFAULT 0,
  worker_id TEXT,
  heartbeat_at TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  result_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority DESC, created_at);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  key TEXT NOT NULL,                  -- stable key, e.g. 'page:12', 'chunk:3'
  kind TEXT NOT NULL,                 -- 'ocr_page', 'embed_batch', ...
  stage TEXT,
  status TEXT NOT NULL,               -- pending | running | done | failed | skipped
  attempts INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER,
  error TEXT,
  result_json TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(job_id, key)
);
CREATE INDEX IF NOT EXISTS idx_tasks_job ON tasks(job_id, status);

CREATE TABLE IF NOT EXISTS call_cache (
  key TEXT PRIMARY KEY,               -- sha256 of (kind, model, version, input)
  kind TEXT NOT NULL,                 -- 'llm', 'embed', 'ocr', 'asr', ...
  model TEXT,
  pipeline_version TEXT,
  value TEXT NOT NULL,                -- JSON
  created_at TEXT NOT NULL,
  hits INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  stage TEXT NOT NULL,
  model TEXT,
  duration_ms INTEGER,
  cache_hit INTEGER,
  status TEXT,                        -- ok | error | rate_limited
  tokens_in INTEGER,
  tokens_out INTEGER,
  job_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);
