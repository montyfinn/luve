-- Kích hoạt extension UUID
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. BẢNG USERS: Bảo mật & Quản trị
CREATE TABLE USERS (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) NOT NULL CHECK (char_length(username) >= 3),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT, -- NULL for Google-only accounts (see chk_users_auth_method)
    google_sub TEXT, -- Google OIDC subject; NULL for password accounts (parity with migration 0004)
    fluency_level INT NOT NULL DEFAULT 1 CHECK (fluency_level IN (1, 2, 3)),
    quota_minutes INT NOT NULL DEFAULT 60,
    is_active BOOLEAN DEFAULT TRUE,
    is_banned BOOLEAN DEFAULT FALSE, -- Chặn người dùng phá hoại
    deleted_at TIMESTAMP WITH TIME ZONE, -- Soft Delete
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_users_auth_method CHECK (password_hash IS NOT NULL OR google_sub IS NOT NULL)
);

-- 2. BẢNG LESSONS: Thư viện kịch bản
CREATE TABLE LESSONS (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100), 
    system_prompt TEXT NOT NULL,
    target_level INT NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE, -- Soft Delete
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. BẢNG SESSIONS: Lưu trữ kịch bản & Trạng thái phục hồi
CREATE TABLE SESSIONS (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES USERS(id) ON DELETE CASCADE,
    lesson_id UUID REFERENCES LESSONS(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'waiting', 
    raw_backup_json JSONB, 
    total_tokens INT DEFAULT 0,
    manual_stops_count INT DEFAULT 0,
    -- metadata: Lưu thông tin phục hồi (Session Recovery) hoặc các thông số AI tùy biến
    metadata JSONB DEFAULT '{}'::jsonb, 
    deleted_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP WITH TIME ZONE
);

-- 4. BẢNG GRADING_RESULTS: Hậu kiểm sư phạm
CREATE TABLE GRADING_RESULTS (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID UNIQUE REFERENCES SESSIONS(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'graded' CHECK (status IN ('processing', 'graded', 'failed')),
    provider TEXT NOT NULL DEFAULT 'unknown',
    grader_version TEXT NOT NULL DEFAULT 'legacy',
    score_schema_version TEXT NOT NULL DEFAULT 'grading.v1',
    overall_score NUMERIC(4,2),
    fluency_score NUMERIC(4,2),
    grammar_score NUMERIC(4,2),
    vocab_score NUMERIC(4,2),
    pronunciation_score NUMERIC(4,2),
    detailed_corrections JSONB, 
    ai_summary_feedback TEXT,
    skill_feedback_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    input_quality_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    attempt_count INT NOT NULL DEFAULT 0,
    graded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE GRADING_SKIP_LOG (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL UNIQUE REFERENCES SESSIONS(id) ON DELETE CASCADE,
    skipped_reason TEXT NOT NULL CHECK (skipped_reason IN (
        'no_raw_backup',
        'invalid_raw_backup',
        'no_user_turns',
        'insufficient_words'
    )),
    student_word_count INT,
    min_words_threshold INT,
    source TEXT NOT NULL DEFAULT 'worker' CHECK (source IN (
        'worker',
        'scanner',
        'backfill',
        'manual'
    )),
    skipped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. BẢNG SESSION_OUTBOX: Transactional outbox (T7) — session.completed event
-- được ghi cùng transaction với trạng thái session; relay publish sang RabbitMQ sau.
CREATE TABLE SESSION_OUTBOX (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES SESSIONS(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'v1',
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'published', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP WITH TIME ZONE,
    UNIQUE (session_id, event_type)
);

-- INDEXING: Tối ưu hóa triệt để
CREATE INDEX idx_sessions_user_id ON SESSIONS(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_grading_session_id ON GRADING_RESULTS(session_id);
CREATE INDEX idx_grading_status ON GRADING_RESULTS(status);
CREATE INDEX idx_grading_updated_at ON GRADING_RESULTS(updated_at DESC);
CREATE INDEX grading_skip_log_skipped_reason_idx ON GRADING_SKIP_LOG(skipped_reason);
CREATE INDEX grading_skip_log_skipped_at_idx ON GRADING_SKIP_LOG(skipped_at DESC);
CREATE INDEX idx_users_email ON USERS(email) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_key ON USERS (google_sub) WHERE google_sub IS NOT NULL;
CREATE INDEX session_outbox_pending_idx ON SESSION_OUTBOX(created_at) WHERE status = 'pending';
