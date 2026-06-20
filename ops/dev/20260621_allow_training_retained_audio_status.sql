ALTER TABLE audio_files
  DROP CONSTRAINT IF EXISTS audio_files_status_check;

ALTER TABLE audio_files
  ADD CONSTRAINT audio_files_status_check CHECK (
    status IN (
      'uploaded',
      'converted',
      'rejected',
      'analyzed',
      'raw_deleted',
      'training_retained',
      'deleted'
    )
  );
