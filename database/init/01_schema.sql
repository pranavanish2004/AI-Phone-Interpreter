-- ============================================================================
-- AI Phone Interpreter - Initial PostgreSQL Schema (Phase 1)
--
-- Design notes:
--   - Redis holds LIVE/ephemeral call state (CallSession, see call_session.py)
--     for speed. Postgres holds DURABLE records for anything we need after
--     the call ends: billing, history, "who talked to whom", debugging.
--   - We use UUID primary keys (not auto-increment ints) because in a
--     microservices/distributed system, services may need to generate IDs
--     independently before a row is inserted into Postgres at all (e.g.
--     call_id is created by api_gateway and immediately used in Redis/Kafka
--     messages, before conversation_service ever writes the row).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- provides gen_random_uuid()

-- ----------------------------------------------------------------------------
-- users: account + profile + language preference (Phase 4: Authentication)
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number        VARCHAR(20) UNIQUE NOT NULL,   -- India phone auth (OTP-based, Phase 4)
    display_name        VARCHAR(100) NOT NULL,
    preferred_language  VARCHAR(10) NOT NULL DEFAULT 'en',
        -- matches LanguageCode enum values: te, hi, en, te-en, hi-en
    password_hash       VARCHAR(255),
        -- nullable: India apps commonly use OTP-only auth; password is optional
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_phone_number ON users(phone_number);

-- ----------------------------------------------------------------------------
-- calls: one row per call session (Phase 5: WebRTC Audio Streaming)
-- ----------------------------------------------------------------------------
CREATE TABLE calls (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status              VARCHAR(20) NOT NULL DEFAULT 'initiated',
        -- matches CallStatus enum: initiated, ringing, connected, ended, failed
    initiated_by        UUID NOT NULL REFERENCES users(id),
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ,
    end_reason          VARCHAR(50),  -- 'hangup', 'network_error', 'timeout', etc.
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_calls_initiated_by ON calls(initiated_by);
CREATE INDEX idx_calls_status ON calls(status);

-- ----------------------------------------------------------------------------
-- call_participants: many-to-many between users and calls, with the
-- language each participant wanted THAT call translated into (a user's
-- preferred_language can differ per call from their profile default)
-- ----------------------------------------------------------------------------
CREATE TABLE call_participants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id             UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id),
    language_for_call   VARCHAR(10) NOT NULL,
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at             TIMESTAMPTZ,
    UNIQUE(call_id, user_id)
);

CREATE INDEX idx_call_participants_call_id ON call_participants(call_id);
CREATE INDEX idx_call_participants_user_id ON call_participants(user_id);

-- ----------------------------------------------------------------------------
-- conversation_turns: durable log of every utterance + its translation.
-- This is the persisted version of what conversation_service keeps "hot" in
-- Redis for context (Phase 11), written here for history/analytics/QA.
-- ----------------------------------------------------------------------------
CREATE TABLE conversation_turns (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id             UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    utterance_id        VARCHAR(100) NOT NULL,
    speaker_user_id     UUID NOT NULL REFERENCES users(id),
    listener_user_id    UUID NOT NULL REFERENCES users(id),

    source_text         TEXT NOT NULL,
    source_language     VARCHAR(10) NOT NULL,
    translated_text     TEXT NOT NULL,
    target_language     VARCHAR(10) NOT NULL,

    used_context        BOOLEAN NOT NULL DEFAULT FALSE,
    turn_index          INTEGER NOT NULL,
        -- 0-based order within the call, needed to rebuild conversation
        -- context/history in the correct sequence
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_conversation_turns_call_id ON conversation_turns(call_id, turn_index);

-- ----------------------------------------------------------------------------
-- updated_at auto-touch trigger for `users` (small piece of DB hygiene we'll
-- reuse later for other mutable tables)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
