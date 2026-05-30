# ADR-0009 — Escenario Banco Inti S.A.A. (IntiBank): activo defendido bancario

| Campo | Valor |
|-------|-------|
| Status | ✅ Accepted · 2026-05-30 |
| Deciders | P1 (Enzo) — confirmado por todo el equipo en standup |
| Supersedes / amends | Concreta el ADR-0008 (multi-vector scope): define el escenario empresarial específico que sustenta UC-04, UC-07, UC-08 |
| Related | SAD §2 (Asset Defendido), USE_CASES UC-04/07/08, manuales P2/P3/P4 |

---

## 1. Contexto

ADR-0008 expandió el scope a multi-vector (ransomware + DDoS + DB attacks + false positives) pero NO definió cómo se ve concretamente el activo defendido. Sin esto:

- P3 (Detection) no puede armar Sigma rules de DB porque no sabe qué tablas existen.
- P2 (ML) no puede generar synthetic data realista para entrenar el modelo de query patterns.
- P4 (Infra) no puede armar `init.sql` con el schema.
- Los mensajes de la UI y notificaciones no tienen branding consistente.

Este ADR cierra todos esos gaps con decisiones concretas y no negociables (salvo cambio explícito vía ADR posterior).

## 2. Decisión

### 2.1 Branding

| Contexto | Nombre |
|----------|--------|
| Razón social en documentos formales (informe, ADRs, USE_CASES, README) | **Banco Inti S.A.A.** |
| Brand en UI, notificaciones Telegram, Discord, mensajes Twilio, Streamlit Console | **IntiBank** |
| Regulación ficticia | Superintendencia de Banca, Seguros y AFP (SBS) del Perú |
| Sede | Lima, Perú |
| Tipo | Banco múltiple — modela operación de banca minorista + transferencias internacionales |

Justificación: dual branding es práctica estándar en banca peruana (BCP / Banco de Crédito del Perú; Interbank / Banco Internacional del Perú). Eso le da realismo al demo. El brand corto entra en UI donde el espacio es limitado; la razón social en docs donde formalidad importa.

### 2.2 Schema PostgreSQL (`app_prod`)

Siete tablas. DDL ejecutable directamente en `lab/postgres/init.sql`:

```sql
-- ============================================================
-- Banco Inti S.A.A. — schema productivo defendido
-- ============================================================

CREATE SCHEMA IF NOT EXISTS intibank;
SET search_path TO intibank, public;

-- Clientes del banco
CREATE TABLE customers (
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
CREATE INDEX idx_customers_dni ON customers(dni);

-- Cuentas (ahorros, corrientes, plazo)
CREATE TABLE accounts (
    id              bigserial PRIMARY KEY,
    customer_id     bigint NOT NULL REFERENCES customers(id),
    account_number  varchar(20) UNIQUE NOT NULL,
    account_type    varchar(20) CHECK (account_type IN ('savings','checking','cd','loan')),
    currency        varchar(3)  CHECK (currency IN ('PEN','USD','EUR')) DEFAULT 'PEN',
    balance         numeric(15,2) NOT NULL DEFAULT 0.00,
    status          varchar(20) CHECK (status IN ('active','frozen','closed')) DEFAULT 'active',
    opened_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_accounts_customer ON accounts(customer_id);

-- Tarjetas (débito y crédito)
CREATE TABLE cards (
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
CREATE TABLE transactions (
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
CREATE INDEX idx_tx_account_date ON transactions(account_id, created_at DESC);

-- Transferencias (incluye internacionales)
CREATE TABLE transfers (
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
CREATE INDEX idx_transfers_dest_country ON transfers(dest_country);

-- Empleados/usuarios internos del banco
CREATE TABLE internal_users (
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
CREATE TABLE audit_log (
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
CREATE INDEX idx_audit_user_ts ON audit_log(user_name, ts DESC);

-- Constraint: nunca borrar ni actualizar audit_log
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;
```

### 2.3 Volúmenes objetivo (seed data)

| Tabla | Filas | Cómo se genera |
|---|---:|---|
| `customers` | 50 000 | `Faker(locale='es_PE')` para nombres, DNIs, direcciones |
| `accounts` | 75 000 | 1.5 cuentas promedio por cliente |
| `cards` | 60 000 | 1.2 tarjetas promedio por cliente |
| `transactions` | 2 000 000 | ~27 transacciones promedio por cuenta sobre 12 meses simulados |
| `transfers` | 350 000 | Subset: ~17 % son transferencias (resto son depósitos/retiros) |
| `internal_users` | 80 | 80 empleados ficticios con roles distribuidos |
| `audit_log` | ~12 M | 6 meses simulados de actividad (~2000 queries/día) |

Generador en `lab/postgres/seed.py` usando `Faker('es_PE')` + `numpy.random` con seed=42 para reproducibilidad.

### 2.4 Roles PostgreSQL (separation of duties bancaria)

Seis roles, cada uno con su patrón de uso característico (esto alimenta al modelo ML y al LLM Triage):

| Rol | Permisos | Patrón normal | Anomalía típica |
|---|---|---|---|
| **`inti_app`** | `INSERT/UPDATE` en transactions, transfers · `SELECT` en customers, accounts, cards | Queries cortas, alta frecuencia (50-200/min), 24/7 vía pool de conexiones | Query larga con JOIN cross-tabla; SELECT masivo |
| **`inti_teller`** | `INSERT` en transactions · `SELECT` en customers, accounts · ❌ no transfers · ❌ no cards | Queries cortas (sub-segundo), horario laboral (9-18 hrs Lima), 1-2 por minuto | Acceso fuera de horario; SELECT en `transfers`; UPDATE de balance directo |
| **`inti_analyst`** | `SELECT` en TODAS las tablas | Queries largas con JOIN, baja frecuencia (5-20/día), horario mixto incluyendo madrugadas para reportes mensuales | Cambio brusco de patrón (de 10 queries/día a 500/día) |
| **`inti_dba`** | superuser registrado | DDL ocasional; mantenimiento (VACUUM, REINDEX); ❌ NUNCA `SELECT *` productivo | Cualquier `SELECT` masivo de tabla productiva |
| **`inti_backup`** | `pg_dump` permissions específicas | Único patrón: una vez al día a las 2:00 AM, `pg_dump` completo | Ejecutarse fuera de horario; cualquier query interactiva |
| **`inti_auditor`** | `SELECT` solo en `audit_log` | Activo solo durante revisiones programadas (~1-2 semanas/trimestre) | Acceso a tablas distintas de `audit_log`; lectura masiva de `audit_log` |

Credenciales (sólo para lab; los `pg_hba.conf` aceptan estas):

```
inti_app      / inti_app_secret_2026
inti_teller   / inti_teller_secret_2026
inti_analyst  / inti_analyst_secret_2026
inti_dba      / inti_dba_secret_2026     (admin, mantener seguro)
inti_backup   / inti_backup_secret_2026
inti_auditor  / inti_auditor_secret_2026
```

### 2.5 Umbrales Sigma DB — porcentual + absoluto combinados

Regla base de detección de "lectura masiva":

```
ALERT IF rows_returned >= MIN_ABSOLUTE AND rows_returned / table_size >= MIN_PERCENT
```

Umbrales por tabla (ambas condiciones DEBEN cumplirse):

| Tabla | MIN_ABSOLUTE | MIN_PERCENT | Severity inicial | Justificación |
|---|---:|---:|---|---|
| `customers` | 1 000 | 10 % | MEDIUM | Extracción de PII — significativo si >= 5k clientes |
| `accounts` | 500 | 5 % | HIGH | Saldos — muy sensible, threshold bajo |
| `cards` | 100 | 2 % | HIGH | Tarjetas — máxima sensibilidad |
| `transactions` | 50 000 | 5 % | MEDIUM | Volumen normal alto — debe ser ruidoso para alertar |
| `transfers` | 1 000 | 5 % | HIGH | Movimientos críticos cross-border |
| `internal_users` | 20 | 25 % | HIGH | Tabla chica, ratio alto = enumeración |
| `audit_log` | 5 000 | 5 % | CRITICAL | Lectura masiva = atacante borrando huellas |

El bridge Wazuh→Redis enriquece cada evento `audit_class=READ` con el campo computado `rows_returned_pct` ANTES de mandarlo a Sigma, así las reglas evalúan ambas condiciones nativamente:

```yaml
# detection/sigma/rules/db/pg_mass_read.yml
detection:
  selection:
    audit_class: 'READ'
    table_affected: 'intibank.accounts'
    rows_returned|gte: 500
    rows_returned_pct|gte: 0.05
  condition: selection
level: high
```

### 2.6 Matriz Capa × UC — qué firing en cada caso

Decisión arquitectónica: las 4 capas son complementarias, no redundantes. Cada UC enciende solo las que tienen sentido. El SAD §6 ya describe las capas; esta tabla aclara qué capa firing en cada UC para que el `tier_router` calibre `num_layers_fired` correctamente.

| UC | Capa 1 Sigma | Capa 2 ML | Capa 3 Canary | Capa 4 LLM Triage |
|---|:-:|:-:|:-:|:-:|
| UC-01 Ransomware multi-layer | ✅ T1486/T1490 host rules | ✅ entropy + file write rate | ✅ canary file touch | ➖ opcional |
| UC-02 Canary path | ➖ | ➖ | ✅ FIM whodata | ➖ |
| UC-04 Postgres attack two-person | ✅ DB rules (`pg_mass_read`, `pg_balance_update_offhours`) | ✅ query pattern outlier | ➖ | ✅ **decisivo** (contexto) |
| UC-06 DDoS | ✅ network T1498/T1499 | ➖ (Sigma ya tiene la tasa) | ➖ | ➖ (no aporta) |
| UC-07 SELECT FP | ✅ DB rules `pg_mass_read` | ✅ ML detecta anomalía | ➖ | ✅ **decisivo** (cancela FP) |
| UC-08 SQL injection | ✅ DB rules `pg_sqli_pattern` + nginx logs | ✅ query pattern abrupto | ➖ | ✅ patrón sqlmap evidente |

> **Capa 4 LLM no aplica a DDoS.** El LLM aporta contexto cuando hay ambigüedad humana ("¿esto es legítimo o ataque?"). DDoS es saturación de red — no hay ambigüedad, la rule de tasa lo detecta sin contexto adicional.

### 2.7 IPs y red ficticia

Para realismo y para que las Sigma rules sobre `ip_address` puedan distinguir tráfico interno vs externo:

| Rango | Uso | Ejemplo |
|---|---|---|
| `10.10.0.0/16` | Red corporativa interna IntiBank (oficinas, dev, prod) | `inti_teller` se conecta desde `10.10.20.x` |
| `10.10.50.0/24` | Servidores aplicación (app middleware) | `inti_app` se conecta desde `10.10.50.10` |
| `203.0.113.0/24` | IPs públicas legítimas (NAT corporativo de oficinas) | Aprobadores HITL responden desde aquí |
| `198.51.100.0/24` | IPs de atacantes simulados (RFC 5737, no enrutables internet) | Los attack simulators dicen ser de aquí |

Cuando una Sigma rule ve `ip_address NOT IN (red corporativa) AND user=inti_teller` → red flag inmediato.

### 2.8 Roles y aprobadores HITL — mapeo a integrantes del equipo

Para el demo en vivo, los 4 integrantes asumen estos roles ficticios del banco. Los mensajes Telegram/Discord usan estos títulos en lugar de "P1/P2/P3/P4":

| Integrante | Rol bancario ficticio | Decisión típica en HITL |
|---|---|---|
| **P1 Enzo Ordoñez** | SOC Lead — Security Operations Center | Aprueba acciones de containment con criterio técnico |
| **P2 Sebastian Montenegro** | Database Administrator (DBA) | Aprueba acciones sobre la DB con criterio operacional |
| **P3 Angeles Castillo** | Infrastructure Lead — Networks & SRE | Aprueba aislamiento de red e iptables |
| **P4 Diego Jara** | Compliance Officer — Gobierno de riesgos | Veta acciones que afecten datos PII sin justificación |

> La two-person rule queda como: "se necesitan 2 aprobadores entre 4 notificados; la diversidad de roles asegura que ninguna decisión depende de una sola perspectiva (técnica vs operacional vs compliance)".

### 2.9 Compliance — referencias concretas

Para evitar la pregunta del profesor "¿qué clausula exactamente?", referencias reales que aplican a banca peruana + el demo cubre:

| Norma | Cláusula | Cómo ARGOS la cubre |
|---|---|---|
| **SBS Resolución 504-2021** (Ciberseguridad) | §6 Gestión de incidentes; §8 Monitoreo continuo | SOAR + audit log + tier router |
| **ISO/IEC 27001:2022** | A.5.24 (Incident management planning), A.5.25 (Assessment of incidents), A.8.16 (Monitoring) | Manuales operativos + Streamlit Console |
| **SOC 2 Type II** | CC6.6 (Logical access — least privilege), CC7.2 (Monitoring activities) | Postgres roles + Wazuh + Sigma |
| **PCI DSS 4.0** (aplicable a `cards`) | Req 10.2 (Audit trail of user activities) | pgAudit + audit_log append-only |

## 3. Consecuencias

### 3.1 Positivas

- **P3 desbloqueado** para escribir Sigma rules DB-específicas con targets reales.
- **P2 desbloqueado** para generar synthetic data realista con Faker(es_PE).
- **P4 desbloqueado** para escribir `init.sql` y seed scripts.
- **Branding consistente** — todos los componentes usan Banco Inti SAA / IntiBank.
- **Defensa frente a preguntas del profesor** sobre realismo y compliance — referencias concretas a SBS, ISO, SOC 2, PCI.
- **El demo se ve enterprise**, no estudiantil.

### 3.2 Negativas

- Aumenta el seed inicial: 12M filas de audit_log + 2M de transactions requieren ~3 GB de disco en Postgres.
- Faker(es_PE) y la generación del seed pueden tomar ~10 min en primera ejecución.
- Si el profesor pide ver datos reales de una tabla durante la defensa, hay que asegurar que el dataset sintético se vea coherente (DNIs válidos por formato, salarios en rangos razonables).

### 3.3 Riesgos a monitorear

- **Performance**: `transactions` con 2M filas + queries de UC-07 que devuelven 5 % = 100k filas pueden saturar la VM si Postgres no está bien configurado (`shared_buffers`, `work_mem`). P4 valida en su Fase 2.
- **Carga del seed**: 10 min de seed en `vagrant up` se puede mitigar con un snapshot Postgres pre-poblado (P4 lo arma una vez, lo commitea como blob en Git LFS o lo deja en `lab/postgres/seed_snapshot.sql.gz`).

## 4. Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Datos genéricos sin sector específico (e-commerce, generic SaaS) | Pierde la fuerza narrativa "DB bancaria con saldos = ataque destructivo". Banca tiene compliance obvia (SBS, PCI DSS) que la audiencia entiende sin explicación previa. |
| Schema más chico (3-4 tablas) | UC-07 (SELECT masivo cross-tabla) y UC-08 (sqlmap enum) pierden riqueza. 7 tablas es el mínimo realista. |
| Schema más grande (15-20 tablas) | Sobre-ingeniería para demo académico. Cada tabla extra significa más Sigma rules a mantener y poco valor adicional. |
| Sin separación de roles (un solo user) | Imposible distinguir UC-04 (atacante) de UC-07 (analista) sin contexto de rol. Roles separados son centrales al diseño HITL. |
| Solo umbral absoluto en rows_returned | No escala con crecimiento de tablas. Combinado con porcentaje es el mínimo defendible. |

## 5. Implementación

### 5.1 Quién hace qué

- **P4 (Diego)**: implementa `lab/postgres/init.sql` con el DDL y `lab/postgres/seed.py` con Faker. Owner del lab Postgres.
- **P3 (Angeles)**: implementa Sigma rules en `detection/sigma/rules/db/` usando los umbrales por tabla.
- **P2 (Sebastian)**: ajusta `ml/data/synthetic_generator.py` para generar query patterns con los 6 roles. RAG corpus incluye el "historial del usuario" de cada rol para que el LLM Triage tenga contexto.
- **P1 (Enzo)**: integra el `rows_returned_pct` en el bridge Wazuh→Redis. Actualiza Streamlit Console con branding IntiBank.

### 5.2 Orden de implementación

1. P4 escribe `init.sql` (DDL only, sin seed). Vagrant levanta. Postgres responde.
2. P3 escribe 5-6 Sigma rules contra DB y las valida con `sigma check`.
3. P4 escribe `seed.py` con Faker (mínimo 10k customers + 50k transactions para empezar).
4. P2 ajusta su synthetic_generator para emitir features compatibles.
5. P1 actualiza el bridge para incluir `rows_returned_pct`.
6. P4 escala el seed a los volumes finales documentados en §2.3.

## 6. Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-30 | Initial — bloqueado por P1 tras conversaciones con profesor y team standup | P1 |
