-- ============================================================
-- ARGOS - DDL del audit SQL (ADR-0013 s2.8)
-- Para coordinar con P4 (owner del Postgres del lab).
-- Target: postgres:17.5-bookworm (ADR-0010 s4.5, no-negociable).
--
-- Los CHECK usan los valores REALES del contrato argos_contracts
-- v1.1.0 (FinalOutcome / PolicyApplied / ExecutionStatus / enums).
-- Nunca los "execute"/"block" del manual viejo (ADR-0011 s2.2).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS argos_audit;
SET search_path TO argos_audit, public;

CREATE TABLE IF NOT EXISTS audit_incidents (
    incident_id      varchar(20) PRIMARY KEY
                     CHECK (incident_id ~ '^INC-\d{4}-\d{2}-\d{2}-\d{3}$'),
    created_at       timestamptz NOT NULL,
    updated_at       timestamptz NOT NULL,
    tier             varchar(2)  NOT NULL CHECK (tier IN ('T0','T1','T2','T3')),
    state            varchar(20) NOT NULL CHECK (state IN (
                        'received','awaiting_approval','pending_execution',
                        'pending_rejection','executing','executed',
                        'reverted','rejected','timeout_escalated')),
    host_id          varchar(80) NOT NULL,
    criticality      varchar(20) NOT NULL
                     CHECK (criticality IN ('standard','production_critical')),
    technique_mitre  varchar(12),
    final_outcome    varchar(20)
                     CHECK (final_outcome IN ('EXECUTE_ISOLATION','NO_ACTION','REVERTED')),
    final_policy     varchar(20)
                     CHECK (final_policy IN ('auto-execute','unanimous-approve',
                        'conservative-wins','two-person-rule','timeout-escalation')),
    rationale        text,
    executed_at      timestamptz,
    execution_status varchar(10)
                     CHECK (execution_status IN ('success','failed','partial'))
);

CREATE TABLE IF NOT EXISTS audit_responses (
    id               bigserial PRIMARY KEY,
    incident_id      varchar(20) NOT NULL REFERENCES audit_incidents(incident_id),
    approver_email   varchar(120) NOT NULL,
    approver_role    varchar(40)  NOT NULL,
    status           varchar(10)  NOT NULL
                     CHECK (status IN ('pending','approved','rejected','timeout')),
    channel          varchar(15)  NOT NULL
                     CHECK (channel IN ('telegram','discord','twilio_voice','email')),
    responded_at     timestamptz,
    latency_seconds  double precision
);

CREATE INDEX IF NOT EXISTS idx_audit_responses_incident
    ON audit_responses(incident_id);
CREATE INDEX IF NOT EXISTS idx_audit_incidents_created
    ON audit_incidents(created_at DESC);

-- Log append-only evento-por-evento. Las dos tablas de arriba son agregados
-- (audit_incidents pisa el tier en cada escalada; audit_responses solo votos), así
-- que NO conservan el historial completo (tier_escalated, llm_triage_ok/failed,
-- timeout_wait, etc. se perdían). Esta tabla persiste CADA AuditEvent tal cual, y es
-- la fuente del timeline navegable de la consola. Sin FK a audit_incidents a propósito:
-- un evento puede llegar antes que la fila del incidente (incident_created es un evento).
CREATE TABLE IF NOT EXISTS audit_events (
    id           bigserial PRIMARY KEY,
    incident_id  varchar(20) NOT NULL,
    ts           timestamptz NOT NULL,
    kind         varchar(40) NOT NULL,
    payload      jsonb       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_audit_events_incident
    ON audit_events(incident_id, ts);
