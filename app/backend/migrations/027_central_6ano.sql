-- Migration 027: Central 6o Ano & R1 (rotina, calendario de plantoes, curriculo e marcos)

CREATE TABLE IF NOT EXISTS user_six_year_plan (
    user_id TEXT PRIMARY KEY,
    routine_mode_enabled INTEGER NOT NULL DEFAULT 0,
    enamed_concept INTEGER NOT NULL DEFAULT 5 CHECK (enamed_concept IN (3, 4, 5)),
    foco_override_json TEXT NOT NULL DEFAULT '{}',
    ritual_done_json TEXT NOT NULL DEFAULT '{}',
    feed_token_hash TEXT,
    feed_token_created_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_six_year_plan_feed_token
    ON user_six_year_plan (feed_token_hash);

CREATE TABLE IF NOT EXISTS user_week_marcha (
    user_id TEXT NOT NULL,
    week_iso TEXT NOT NULL,
    marcha_id TEXT NOT NULL CHECK (marcha_id IN ('4_sprint', '3_normal', '2_pesada', '1_sobrevivencia')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, week_iso)
);

CREATE TABLE IF NOT EXISTS user_shifts (
    user_id TEXT NOT NULL,
    date_iso TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('plantao_12h_dia', 'plantao_noturno', 'plantao_24h')),
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, date_iso, kind)
);

CREATE TABLE IF NOT EXISTS user_day_overrides (
    user_id TEXT NOT NULL,
    date_iso TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('pos_plantao', 'folga', 'meio_periodo', 'integral')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, date_iso)
);

CREATE TABLE IF NOT EXISTS user_curriculum_entries (
    user_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    proof_status TEXT NOT NULL DEFAULT 'falta' CHECK (proof_status IN ('falta', 'em_andamento', 'pdf_pronto')),
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, item_id)
);

CREATE TABLE IF NOT EXISTS user_r1_milestones (
    user_id TEXT NOT NULL,
    id TEXT NOT NULL,
    titulo TEXT NOT NULL,
    data_iso TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT 'prova' CHECK (categoria IN ('curriculo', 'estudo', 'graduacao', 'prova', 'ingresso')),
    done INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, id)
);
