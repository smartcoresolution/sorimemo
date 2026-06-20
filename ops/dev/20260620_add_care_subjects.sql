CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE users ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS user_name text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_purpose text NOT NULL DEFAULT 'parent_care';
ALTER TABLE users ADD COLUMN IF NOT EXISTS age_group text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

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

ALTER TABLE consents ADD COLUMN IF NOT EXISTS subject_id uuid REFERENCES care_subjects(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users (lower(email)) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_care_subjects_user ON care_subjects(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_consents_subject ON consents(subject_id);

GRANT ALL PRIVILEGES ON TABLE care_subjects TO sorimemo_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sorimemo_app;
