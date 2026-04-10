-- Kích hoạt extension UUID
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. BẢNG USERS: Bảo mật & Quản trị
CREATE TABLE USERS (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) NOT NULL CHECK (char_length(username) >= 3),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL, 
    fluency_level INT NOT NULL DEFAULT 1 CHECK (fluency_level IN (1, 2, 3)),
    quota_minutes INT NOT NULL DEFAULT 60,
    is_active BOOLEAN DEFAULT TRUE,
    is_banned BOOLEAN DEFAULT FALSE, -- Chặn người dùng phá hoại
    deleted_at TIMESTAMP WITH TIME ZONE, -- Soft Delete
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
    overall_score NUMERIC(4,2),
    fluency_score NUMERIC(4,2),
    grammar_score NUMERIC(4,2),
    vocab_score NUMERIC(4,2),
    detailed_corrections JSONB, 
    ai_summary_feedback TEXT,
    graded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- INDEXING: Tối ưu hóa triệt để
CREATE INDEX idx_sessions_user_id ON SESSIONS(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_grading_session_id ON GRADING_RESULTS(session_id);
CREATE INDEX idx_users_email ON USERS(email) WHERE deleted_at IS NULL;