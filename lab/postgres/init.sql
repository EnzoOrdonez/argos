-- ============================================================
-- Banco Inti S.A.A. (IntiBank) — schema productivo defendido
-- DDL canónico: ADR-0009 §2.2 (tablas) + §2.4 (roles).
-- Se ejecuta una vez en la VM víctima (192.168.56.21) sobre la DB app_prod.
-- El seed de datos lo carga lab/postgres/seed.py (o el snapshot pg_dump).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS intibank;
SET search_path TO intibank, public;

-- ------------------------------------------------------------
-- Tablas (ADR-0009 §2.2, verbatim)
-- ------------------------------------------------------------

-- Clientes del banco
CREATE TABLE IF NOT EXISTS customers (
    id              bigserial PRIMARY KEY,
    dni             varchar(8)  UNIQUE NOT NULL,
    full_name       varchar(120) NOT NULL,
    email           varchar(120) NOT NULL,
    phone           varchar(20),
    address         varchar(200),
    city            varchar(60) DEFAULT 'Lima',
    kyc_level       int CHECK (kyc_level BETWEEN 0 AND 3) DEFAULT 1,
    pep_flag        boolean DEFAULT false,  -- Persona Expuesta Políticamente
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_customers_dni ON customers(dni);

-- Cuentas (ahorros, corrientes, plazo)
CREATE TABLE IF NOT EXISTS accounts (
    id              bigserial PRIMARY KEY,
    customer_id     bigint NOT NULL REFERENCES customers(id),
    account_number  varchar(20) UNIQUE NOT NULL,
    account_type    varchar(20) CHECK (account_type IN ('savings','checking','cd','loan')),
    currency        varchar(3)  CHECK (currency IN ('PEN','USD','EUR')) DEFAULT 'PEN',
    balance         numeric(15,2) NOT NULL DEFAULT 0.00,
    status          varchar(20) CHECK (status IN ('active','frozen','closed')) DEFAULT 'active',
    opened_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);

-- Tarjetas (débito y crédito)
CREATE TABLE IF NOT EXISTS cards (
    id              bigserial PRIMARY KEY,
    customer_id     bigint NOT NULL REFERENCES customers(id),
    card_type       varchar(20) CHECK (card_type IN ('debit','credit')),
    last_4          varchar(4) NOT NULL,
    pan_hash        char(64) NOT NULL,           -- SHA-256 del PAN completo
    expiry_month    int CHECK (expiry_month BETWEEN 1 AND 12),
    expiry_year     int CHECK (expiry_year BETWEEN 2026 AND 2040),
    status          varchar(20) CHECK (status IN ('active','blocked','expired')) DEFAULT 'active',
    issued_at       timestamptz NOT NULL DEFAULT now()
);

-- Transacciones (movimientos de cuenta)
CREATE TABLE IF NOT EXISTS transactions (
    id              bigserial PRIMARY KEY,
    account_id      bigint NOT NULL REFERENCES accounts(id),
    type            varchar(20) CHECK (type IN ('deposit','withdrawal','fee','interest','transfer_in','transfer_out')),
    amount          numeric(15,2) NOT NULL,
    currency        varchar(3) NOT NULL,
    description     varchar(200),
    counterparty    varchar(120),
    status          varchar(20) CHECK (status IN ('pending','completed','reversed','flagged')) DEFAULT 'completed',
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tx_account_date ON transactions(account_id, created_at DESC);

-- Transferencias (incluye internacionales)
CREATE TABLE IF NOT EXISTS transfers (
    id              bigserial PRIMARY KEY,
    source_account_id   bigint NOT NULL REFERENCES accounts(id),
    dest_account_number varchar(34) NOT NULL,  -- IBAN si internacional
    dest_bank_swift     varchar(11),
    dest_country        varchar(2) DEFAULT 'PE',
    amount              numeric(15,2) NOT NULL,
    currency            varchar(3) NOT NULL,
    status              varchar(20) CHECK (status IN ('pending','processing','completed','rejected','held')) DEFAULT 'pending',
    hold_reason         varchar(120),
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_transfers_dest_country ON transfers(dest_country);

-- Empleados/usuarios internos del banco
CREATE TABLE IF NOT EXISTS internal_users (
    id              bigserial PRIMARY KEY,
    employee_dni    varchar(8) UNIQUE NOT NULL,
    username        varchar(40) UNIQUE NOT NULL,
    role            varchar(40) CHECK (role IN ('teller','analyst','dba','manager','auditor','officer')),
    department      varchar(40),
    mfa_enabled     boolean DEFAULT true,
    last_login_at   timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Audit log inmutable (append-only, no UPDATE/DELETE permitidos)
CREATE TABLE IF NOT EXISTS audit_log (
    id              bigserial PRIMARY KEY,
    user_name       varchar(40) NOT NULL,        -- conector de la sesión PG
    action          varchar(40) NOT NULL,        -- SELECT, INSERT, UPDATE, DELETE, DDL, LOGIN
    table_affected  varchar(80),
    query_hash      char(64),
    rows_returned   int,
    ip_address      inet,
    user_agent      varchar(200),
    ts              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_log(user_name, ts DESC);

-- Constraint: nunca borrar ni actualizar audit_log
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

-- ------------------------------------------------------------
-- Roles bancarios (ADR-0009 §2.4 — separation of duties).
-- Credenciales SOLO-LAB. Cada rol tiene un patrón de uso característico
-- que alimenta al ML L2 y al LLM Triage. Idempotente para re-runs.
-- ------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'inti_app') THEN
        CREATE ROLE inti_app     LOGIN PASSWORD 'inti_app_secret_2026';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'inti_teller') THEN
        CREATE ROLE inti_teller  LOGIN PASSWORD 'inti_teller_secret_2026';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'inti_analyst') THEN
        CREATE ROLE inti_analyst LOGIN PASSWORD 'inti_analyst_secret_2026';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'inti_dba') THEN
        CREATE ROLE inti_dba     LOGIN PASSWORD 'inti_dba_secret_2026' SUPERUSER;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'inti_backup') THEN
        CREATE ROLE inti_backup  LOGIN PASSWORD 'inti_backup_secret_2026';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'inti_auditor') THEN
        CREATE ROLE inti_auditor LOGIN PASSWORD 'inti_auditor_secret_2026';
    END IF;
END
$$;

-- Default search_path para que cada rol vea el schema sin calificar
ALTER ROLE inti_app     SET search_path TO intibank, public;
ALTER ROLE inti_teller  SET search_path TO intibank, public;
ALTER ROLE inti_analyst SET search_path TO intibank, public;
ALTER ROLE inti_dba     SET search_path TO intibank, public;
ALTER ROLE inti_backup  SET search_path TO intibank, public;
ALTER ROLE inti_auditor SET search_path TO intibank, public;

GRANT USAGE ON SCHEMA intibank TO
    inti_app, inti_teller, inti_analyst, inti_backup, inti_auditor;

-- inti_app: INSERT/UPDATE en transactions, transfers · SELECT en customers, accounts, cards
GRANT INSERT, UPDATE ON transactions, transfers TO inti_app;
GRANT SELECT          ON customers, accounts, cards TO inti_app;
GRANT USAGE, SELECT   ON ALL SEQUENCES IN SCHEMA intibank TO inti_app;

-- inti_teller: INSERT en transactions · SELECT en customers, accounts (NO transfers, NO cards)
GRANT INSERT ON transactions TO inti_teller;
GRANT SELECT ON customers, accounts TO inti_teller;
GRANT USAGE, SELECT ON SEQUENCE transactions_id_seq TO inti_teller;

-- inti_analyst: SELECT en TODAS las tablas (patrón normal: queries largas, baja frecuencia)
GRANT SELECT ON ALL TABLES IN SCHEMA intibank TO inti_analyst;

-- inti_backup: solo lectura global para pg_dump (1x/día 2:00 AM)
GRANT SELECT ON ALL TABLES IN SCHEMA intibank TO inti_backup;

-- inti_auditor: SELECT solo en audit_log
GRANT SELECT ON audit_log TO inti_auditor;

-- inti_dba: SUPERUSER (DDL/mantenimiento); no necesita GRANTs explícitos.

-- audit_log sigue append-only incluso para los roles con SELECT:
REVOKE UPDATE, DELETE ON audit_log FROM
    inti_app, inti_teller, inti_analyst, inti_backup, inti_auditor;
