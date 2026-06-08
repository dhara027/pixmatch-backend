-- V002: Production hardening
-- Run this migration against the Supabase DIRECT connection (port 5432, not pooler).
-- Execute: python migrations/migrate.py  (or paste into Supabase SQL editor)

-- ── 1. pgvector IVFFlat index for cosine similarity search ───────────────────
-- Without this index every face-match query scans ALL embeddings (O(n)).
-- With lists=100, approximate search reduces scans by ~100x.
-- NOTE: effective only after >= 3,900 rows. Run ANALYZE after bulk data loads.
CREATE INDEX IF NOT EXISTS idx_embeddings_cosine
    ON photo_face_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ── 2. job_token column for anonymous job ownership ───────────────────────────
ALTER TABLE face_match_jobs
    ADD COLUMN IF NOT EXISTS job_token TEXT;

-- Backfill existing rows (already completed/stale jobs)
UPDATE face_match_jobs
    SET job_token = encode(gen_random_bytes(32), 'base64')
    WHERE job_token IS NULL;

-- Make NOT NULL going forward
ALTER TABLE face_match_jobs
    ALTER COLUMN job_token SET NOT NULL,
    ALTER COLUMN job_token SET DEFAULT encode(gen_random_bytes(32), 'base64');

-- ── 3. UNIQUE constraint on cloudinary_public_id (idempotent) ─────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_photos_cloudinary_public_id'
          AND conrelid = 'photos'::regclass
    ) THEN
        ALTER TABLE photos
            ADD CONSTRAINT uq_photos_cloudinary_public_id
            UNIQUE (cloudinary_public_id);
    END IF;
END;
$$;

-- ── 4. embedding_status default ───────────────────────────────────────────────
ALTER TABLE photos
    ALTER COLUMN embedding_status SET DEFAULT 'pending';

COMMENT ON COLUMN photos.embedding_status IS
    'Face embedding state: pending → processing → done | failed';

-- ── 5. Partial index on face_match_jobs for status polling ────────────────────
CREATE INDEX IF NOT EXISTS idx_face_match_jobs_status
    ON face_match_jobs (status)
    WHERE status IN ('queued', 'processing');

-- ── 6. Cleanup function: remove completed/failed jobs older than 30 days ──────
CREATE OR REPLACE FUNCTION cleanup_old_face_match_jobs() RETURNS void AS $$
BEGIN
    DELETE FROM face_match_jobs
    WHERE status IN ('completed', 'failed')
      AND created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- ── 7. Additional query-pattern indexes ───────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_events_photographer_created
    ON events (photographer_id, created_at DESC)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_photos_event_uploaded
    ON photos (event_id, uploaded_at DESC);
