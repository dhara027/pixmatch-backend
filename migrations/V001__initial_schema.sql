-- ============================================================
-- Migration V001: Complete PixMatch enterprise schema
-- ============================================================
-- Run once on a clean database.
-- For existing DBs: apply as incremental migration via Alembic.

BEGIN;

-- ── Extensions ───────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";   -- pgvector for face embeddings

-- ── Users ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email            VARCHAR(255) NOT NULL,
    mobile_no        VARCHAR(20)  NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,
    is_email_verified BOOLEAN    NOT NULL DEFAULT FALSE,
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    last_login_at    TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email   ON users(email);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_mobile  ON users(mobile_no);
CREATE        INDEX IF NOT EXISTS idx_users_active  ON users(is_active) WHERE is_active = TRUE;

-- ── Events ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    photographer_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    photographer_name  VARCHAR(200) NOT NULL,
    event_name         VARCHAR(200) NOT NULL,
    event_location     VARCHAR(500) NOT NULL,
    event_date         DATE        NOT NULL,
    is_active          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_photographer ON events(photographer_id);
CREATE INDEX IF NOT EXISTS idx_events_date         ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_events_active       ON events(photographer_id, is_active)
    WHERE is_active = TRUE;

-- ── Photos ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS photos (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id              UUID        NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    cloudinary_public_id  VARCHAR(500) NOT NULL,
    cloudinary_secure_url TEXT        NOT NULL,
    original_filename     VARCHAR(500),
    file_size_bytes       BIGINT,
    mime_type             VARCHAR(100),
    embedding_status      VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | processing | done | failed
    uploaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_photos_event          ON photos(event_id);
CREATE INDEX IF NOT EXISTS idx_photos_embed_status   ON photos(embedding_status)
    WHERE embedding_status = 'pending';

-- ── Event Photo Count (denormalized for fast read) ────────────
CREATE TABLE IF NOT EXISTS event_photo_count (
    event_id     UUID    PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    total_photos INT     NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Face Embeddings (pgvector) ────────────────────────────────
-- 512-dim embedding from InsightFace buffalo_l model
CREATE TABLE IF NOT EXISTS photo_face_embeddings (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    photo_id    UUID    NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    face_index  INT     NOT NULL,    -- 0-indexed within photo
    embedding   VECTOR(512) NOT NULL,
    bbox        JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (photo_id, face_index)
);

-- IVFFlat index for cosine similarity — faster at scale than exact scan
-- For < 100k vectors, flat scan is fine; create this index when scaling up.
-- CREATE INDEX idx_embeddings_cosine ON photo_face_embeddings
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── Face Match Jobs ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS face_match_jobs (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id      UUID        NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    status        VARCHAR(20) NOT NULL DEFAULT 'queued',
    -- queued | processing | completed | failed
    result        JSONB,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_status     ON face_match_jobs(status)
    WHERE status IN ('queued', 'processing');
CREATE INDEX IF NOT EXISTS idx_jobs_event      ON face_match_jobs(event_id);

-- ── Auto-update updated_at trigger ────────────────────────────
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

CREATE OR REPLACE TRIGGER trg_events_updated_at
    BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

CREATE OR REPLACE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON face_match_jobs
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

COMMIT;
