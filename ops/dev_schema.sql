-- SoriMemo development PostgreSQL schema.
-- This mirrors production basics and adds account, security, signed notice,
-- and analysis job tables for local development.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text UNIQUE,
    password_hash text,
    user_name text,
    display_name text,
    signup_purpose text NOT NULL DEFAULT 'parent_care',
    age_group text,
    role text NOT NULL DEFAULT 'user',
    status text NOT NULL DEFAULT 'active',
    email_verified_at timestamptz,
    last_login_at timestamptz,
    failed_login_count integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    password_changed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    withdrawn_at timestamptz,
    CONSTRAINT users_role_check CHECK (role IN ('user', 'admin', 'operator')),
    CONSTRAINT users_status_check CHECK (status IN ('active', 'locked', 'withdrawn'))
);

CREATE TABLE IF NOT EXISTS care_subjects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_type text NOT NULL DEFAULT 'parent',
    relation text,
    display_name text,
    age_group text,
    gender text,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT care_subjects_type_check CHECK (subject_type IN ('self', 'parent')),
    CONSTRAINT care_subjects_status_check CHECK (status IN ('active', 'archived'))
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash text NOT NULL UNIQUE,
    user_agent text,
    ip_address inet,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    request_ip inet,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    request_ip inet,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_change_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    new_email text NOT NULL,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    request_ip inet,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS consents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    subject_id uuid REFERENCES care_subjects(id) ON DELETE SET NULL,
    consent_token uuid NOT NULL UNIQUE,
    policy_version text NOT NULL,
    data_collection_agreed boolean NOT NULL DEFAULT false,
    privacy_policy_agreed boolean NOT NULL DEFAULT false,
    non_medical_disclaimer_agreed boolean NOT NULL DEFAULT false,
    third_party_voice_agreed boolean NOT NULL DEFAULT false,
    agreed_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

CREATE TABLE IF NOT EXISTS signed_notices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    notice_type text NOT NULL,
    notice_version text NOT NULL,
    title text NOT NULL,
    body_snapshot text NOT NULL,
    signer_name text,
    signature_text text,
    signed_at timestamptz NOT NULL DEFAULT now(),
    ip_address inet,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audio_files (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    consent_id uuid REFERENCES consents(id) ON DELETE SET NULL,
    original_filename text NOT NULL,
    original_format text,
    mime_type text,
    storage_bucket text,
    storage_path text,
    wav_path text,
    checksum_sha256 text,
    file_size_bytes bigint,
    duration_seconds numeric,
    snr_db numeric,
    silence_ratio numeric,
    sample_rate integer,
    channels integer,
    quality_pass boolean,
    rejection_reason text,
    status text NOT NULL DEFAULT 'uploaded',
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    analyzed_at timestamptz,
    raw_deleted_at timestamptz,
    deleted_at timestamptz,
    retention_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT audio_files_status_check CHECK (
        status IN ('uploaded', 'converted', 'rejected', 'analyzed', 'raw_deleted', 'training_retained', 'deleted')
    )
);

CREATE TABLE IF NOT EXISTS voice_samples (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    consent_id uuid REFERENCES consents(id) ON DELETE SET NULL,
    original_filename text NOT NULL,
    storage_path text NOT NULL,
    checksum_sha256 text,
    duration_seconds numeric,
    embedding jsonb,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CONSTRAINT voice_samples_status_check CHECK (status IN ('active', 'replaced', 'deleted'))
);

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    audio_file_id uuid REFERENCES audio_files(id) ON DELETE SET NULL,
    voice_sample_id uuid REFERENCES voice_samples(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'queued',
    error_message text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT analysis_jobs_status_check CHECK (status IN ('queued', 'processing', 'completed', 'failed'))
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id uuid PRIMARY KEY,
    job_id uuid REFERENCES analysis_jobs(id) ON DELETE SET NULL,
    audio_file_id uuid REFERENCES audio_files(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'completed',
    cognitive_status text,
    risk_score numeric,
    risk_level text,
    risk_probability numeric,
    model_probabilities jsonb,
    confidence_score numeric,
    result_payload jsonb NOT NULL,
    retention_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    body text NOT NULL,
    is_published boolean NOT NULL DEFAULT false,
    published_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS board_posts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    body text NOT NULL,
    author_name text,
    is_published boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor text,
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    actor_role text,
    action text NOT NULL,
    target_type text,
    target_id uuid,
    ip_address inet,
    user_agent text,
    metadata jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_care_subjects_user ON care_subjects(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_user ON email_verification_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_email_change_tokens_user ON email_change_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_consents_token ON consents(consent_token);
CREATE INDEX IF NOT EXISTS idx_consents_user ON consents(user_id);
CREATE INDEX IF NOT EXISTS idx_signed_notices_user ON signed_notices(user_id);
CREATE INDEX IF NOT EXISTS idx_audio_files_user_created ON audio_files(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audio_files_created_at ON audio_files(created_at);
CREATE INDEX IF NOT EXISTS idx_audio_files_status ON audio_files(status);
CREATE INDEX IF NOT EXISTS idx_voice_samples_user_created ON voice_samples(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_user_created ON analysis_jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_analysis_results_created_at ON analysis_results(created_at);
CREATE INDEX IF NOT EXISTS idx_analysis_results_job ON analysis_results(job_id);
CREATE INDEX IF NOT EXISTS idx_notices_published ON notices(is_published, published_at);
CREATE INDEX IF NOT EXISTS idx_board_posts_created_at ON board_posts(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_created ON audit_logs(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action_created ON audit_logs(action, created_at DESC);
