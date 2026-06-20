ALTER TABLE consents
  ADD COLUMN IF NOT EXISTS model_training_agreed boolean NOT NULL DEFAULT false;

ALTER TABLE consents
  ADD COLUMN IF NOT EXISTS model_training_retention_days integer;

CREATE INDEX IF NOT EXISTS idx_consents_model_training
  ON consents(model_training_agreed);
