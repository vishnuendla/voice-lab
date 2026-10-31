-- Applied idempotently on pool creation. No migration tool by design:
-- CREATE ... IF NOT EXISTS for new installs, ALTER ... IF NOT EXISTS for old ones.

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'active',
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ
);
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary TEXT;

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    sequence_number INT NOT NULL,
    role TEXT NOT NULL,
    -- `content`, `tool_call_id` and `tool_calls` are convenience columns for
    -- humans and SQL; `payload` is the exact provider-shaped message dict
    -- Pipecat gave us, and is what we replay.
    content TEXT,
    tool_call_id TEXT,
    tool_calls JSONB,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, sequence_number)
);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS tool_call_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS tool_calls JSONB;

-- Long-term, reusable facts about a user, carried across sessions.
CREATE TABLE IF NOT EXISTS memories (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    source_session_id TEXT REFERENCES sessions(id),
    memory TEXT NOT NULL,
    importance INT NOT NULL DEFAULT 50 CHECK (importance BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, memory)
);

CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions (user_id);
CREATE INDEX IF NOT EXISTS messages_session_seq_idx ON messages (session_id, sequence_number);
CREATE INDEX IF NOT EXISTS memories_user_id_idx ON memories (user_id, importance DESC);
