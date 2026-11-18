-- Idempotent upgrade for existing volumes; fresh installs also use schema.sql.
CREATE TABLE IF NOT EXISTS notification_history (
    id bigserial PRIMARY KEY,
    device_id text NOT NULL REFERENCES devices(id),
    endpoint text NOT NULL,
    dispatch_id uuid,
    notification_type text NOT NULL CHECK (notification_type IN ('STATE', 'FORECAST')),
    status text NOT NULL DEFAULT 'PENDING'
        CONSTRAINT notification_history_status_check
        CHECK (status IN ('PENDING', 'SENT', 'FAILED', 'UNKNOWN')),
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,
    error text
);
ALTER TABLE notification_history ADD COLUMN IF NOT EXISTS dispatch_id uuid;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'notification_history'::regclass
          AND conname = 'notification_history_status_check'
          AND pg_get_constraintdef(oid) LIKE '%UNKNOWN%'
    ) THEN
        ALTER TABLE notification_history DROP CONSTRAINT IF EXISTS notification_history_status_check;
        ALTER TABLE notification_history ADD CONSTRAINT notification_history_status_check
            CHECK (status IN ('PENDING', 'SENT', 'FAILED', 'UNKNOWN'));
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_notification_history_device
    ON notification_history (device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_history_type_status
    ON notification_history (device_id, notification_type, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_history_pending
    ON notification_history (created_at) WHERE status = 'PENDING';
