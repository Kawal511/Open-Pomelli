PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT,
  display_name TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  status TEXT NOT NULL,
  current_node TEXT NOT NULL,
  refinement_count INTEGER NOT NULL DEFAULT 0,
  start_payload TEXT NOT NULL,
  cco TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaign_checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  node_name TEXT NOT NULL,
  status TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaign_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  ts TEXT NOT NULL,
  agent TEXT NOT NULL,
  level TEXT NOT NULL,
  message TEXT NOT NULL,
  latency_ms INTEGER,
  extra_json TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS brand_identity_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  normalized_brand_name TEXT NOT NULL,
  profile_json TEXT NOT NULL,
  source_campaign_id TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (source_campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_campaign_checkpoints_campaign
  ON campaign_checkpoints (campaign_id, created_at);

CREATE INDEX IF NOT EXISTS idx_brand_identity_normalized
  ON brand_identity_cache (user_id, normalized_brand_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_brand_identity_user_brand
  ON brand_identity_cache (user_id, normalized_brand_name);

CREATE TABLE IF NOT EXISTS generated_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  node_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  asset_type TEXT NOT NULL,
  prompt TEXT NOT NULL,
  image_url TEXT,
  image_path TEXT,
  provider TEXT,
  model TEXT,
  width INTEGER,
  height INTEGER,
  status TEXT,
  attempted_providers TEXT,
  error TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_generated_images_campaign
  ON generated_images (user_id, campaign_id, node_name, asset_type);

CREATE INDEX IF NOT EXISTS idx_generated_images_provider
  ON generated_images (provider);

CREATE INDEX IF NOT EXISTS idx_generated_images_status
  ON generated_images (status);
