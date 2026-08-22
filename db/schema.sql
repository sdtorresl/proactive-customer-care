-- Database schema for the proactive-customer-care/Twilio anomaly detection system

CREATE TABLE IF NOT EXISTS alert_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    client_id       TEXT NOT NULL,
    error_code      TEXT NOT NULL,
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    count           INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alert_snapshots_client_code
    ON alert_snapshots (client_id, error_code, period_start DESC);

CREATE TABLE IF NOT EXISTS incidents (
    id                  BIGSERIAL PRIMARY KEY,
    client_id           TEXT NOT NULL,
    error_code          TEXT NOT NULL,
    current_count       INTEGER NOT NULL,
    baseline_avg        NUMERIC NOT NULL,
    baseline_stddev     NUMERIC NOT NULL,
    pct_increase        NUMERIC NOT NULL,
    streak              INTEGER NOT NULL,
    zendesk_ticket_id   TEXT,
    zendesk_ticket_url  TEXT,
    notified_at         TIMESTAMPTZ,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incidents_client_code_time
    ON incidents (client_id, error_code, detected_at DESC);

CREATE TABLE IF NOT EXISTS run_log (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    clients_processed INTEGER,
    anomalies_found INTEGER,
    status          TEXT,
    error_message   TEXT
);
