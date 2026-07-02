-- DB de aplicación (target del ataque)
CREATE DATABASE app_prod;-- DB de auditoría (consumida por audit sink de P1)
CREATE DATABASE argos_audit;
\c argos_audit
CREATE TABLE IF NOT EXISTS audit_incidents (
    incident_id   text PRIMARY KEY,
    tier          text NOT NULL,
    severity      text NOT NULL,
    host          text NOT NULL,
    technique     text NOT NULL,
    created_at    timestamptz NOT NULL,
    final_outcome text,
    final_policy  text,
    final_at      timestamptz,
    payload       jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_responses (
    id            bigserial PRIMARY KEY,
    incident_id   text REFERENCES audit_incidents(incident_id) ON DELETE CASCADE,
    approver_id   text NOT NULL,
    channel       text NOT NULL,
    decision      text NOT NULL,
    received_at   timestamptz NOT NULL
);
CREATE INDEX idx_audit_incidents_created  ON audit_incidents(created_at DESC);
CREATE INDEX idx_audit_responses_incident ON audit_responses(incident_id);
CREATE USER argos   WITH PASSWORD 'argos';
GRANT ALL PRIVILEGES ON DATABASE argos_audit TO argos;
GRANT ALL ON ALL TABLES IN SCHEMA public TO argos;
CREATE USER analyst WITH PASSWORD 'analyst_pwd';
GRANT CONNECT ON DATABASE app_prod TO analyst;