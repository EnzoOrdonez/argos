# ADR-0010 — Decisiones operacionales del demo (ideal vs mínimo indispensable)

| Campo | Valor |
|-------|-------|
| Status | ✅ Accepted · 2026-05-30 |
| Deciders | P1 (Enzo) — confirmado por equipo |
| Related | ADR-0008 (multi-vector scope), ADR-0009 (IntiBank scenario), manual-equipo.md (operacional) |
| Pattern | Cada decisión tiene **meta ideal** (a apuntar) + **mínimo indispensable** (fallback si el tiempo aprieta). Esto evita binary fail. |

---

## 1. Contexto

Después de cerrar el escenario empresarial (ADR-0009), quedan decisiones operacionales del demo que afectan implementación pero no arquitectura. La premisa del usuario: documentar AHORA los aim/floor por cada una para que el equipo no tenga que re-decidir en plena Fase 3.

Algunas decisiones son **bloqueantes para Fase 2** (P3/P4 las necesitan para escribir código). Otras son para el informe técnico (T-2 días). Este ADR las consolida.

## 2. Decisiones — Bloque A (bloquean implementación)

### 2.1 UC-05 Wazuh agent kill en el demo

**Problema:** la auto-defensa del SIEM contra T1562.001 está documentada (ADR-0002, THREAT_MODEL T-050, SAD §F) pero al mover UC-05 a post-demo en ADR-0008, perdimos la demostración en vivo. Riesgo: el profesor pregunta "muéstrame" y solo tenemos papel.

**Meta ideal:** mini-cameo de 30-45 s al final del demo después de UC-04. Una uc-stage compacta de ~80 líneas que muestra:
- Terminal con `Stop-Service Wazuh-Agent` (o `sudo systemctl stop wazuh-agent` en Linux victim).
- Countdown acelerado del heartbeat (60s comprimidos a 6s del demo, indicado con etiqueta "10× acelerado").
- Aparición visible de la alerta Wazuh rule 502 ("agent disconnected").
- Auto-isolation triggereada por T0.
- Mensaje final: "Detection latency real: 60-90s. Demo acelerado: 6s. Coverage T1562.001."

Owner implementación: **P4** (lo incluye en el HTML use cases junto con las otras uc-stages) durante Fase 4.

**Mínimo indispensable (fallback si no hay tiempo):** mantener UC-05 post-demo, defender en informe técnico citando explícitamente:
- THREAT_MODEL T-050 (mitigación documentada)
- ADR-0002 (decisión del heartbeat 60s)
- SAD §F.020 (failure mode + auto-restart)

**Trigger para activar fallback:** si en T-7 días del demo P4 no ha cerrado UC-05 mini-cameo, se cae automáticamente al mínimo sin discusión adicional.

### 2.2 Webapp dummy vulnerable para UC-08 SQL injection

**Problema:** sqlmap necesita un endpoint web con vulnerabilidad SQLi para pegar contra Postgres. Sin webapp, el "atacante" tendría que tener acceso psql directo (irreal en banco).

**Meta ideal:** **Flask custom de 60-80 líneas** escrita por P4, deliberadamente vulnerable a SQLi via concatenación de strings. Estructura:

```python
# lab/webapp/dummy_app.py — 60-80 líneas
from flask import Flask, request, jsonify
import psycopg
import os

app = Flask(__name__)

def db():
    return psycopg.connect(os.environ["WEBAPP_PG_URL"])

@app.route("/api/login")
def login():
    # ⚠ INTENTIONALLY VULNERABLE — SQLi via string concat
    u = request.args.get("u", "")
    p = request.args.get("p", "")
    sql = f"SELECT * FROM intibank.internal_users WHERE username='{u}' AND password='{p}'"
    with db().cursor() as cur:
        cur.execute(sql)  # SQLi enters here
        rows = cur.fetchall()
    return jsonify({"authenticated": len(rows) > 0})

@app.route("/api/customer_search")
def search():
    # ⚠ ALSO VULNERABLE — UNION attack vector
    q = request.args.get("q", "")
    sql = f"SELECT id, full_name, dni FROM intibank.customers WHERE full_name LIKE '%{q}%'"
    with db().cursor() as cur:
        cur.execute(sql)
        return jsonify(cur.fetchall())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

Corre como container Docker en lab-manager o linux-victim. Expone puerto 8080. nginx delante a 80.

Owner implementación: **P4** durante Fase 2 (parte de `lab/`).

**Mínimo indispensable:** dropear UC-08 del demo en vivo (mantenerlo solo como animación pre-grabada en el HTML use cases). El código sqlmap queda documentado en `attack-simulation/` como capacidad reproducible offline, pero no se ejecuta el día del demo. UC-08 ya estaba marcado como "nice-to-have / bonus" en ADR-0008 — esta caída es defendible.

**Trigger fallback:** si en T-14 días P4 no tiene el Flask corriendo en lab, se cae al mínimo.

### 2.3 Synthetic data del ML con patrón temporal real

**Problema:** UC-07 dice "3 AM atípico" pero el `synthetic_generator.py` actual usa `timestamp = 0..5000` lineal. El IsoForest no puede aprender una feature temporal que no existe en los datos.

**Meta ideal:** **synthetic data con día simulado.** P2 actualiza `ml/data/synthetic_generator.py` con:
- 30 días simulados de 24h cada uno (~720 horas totales).
- Distribución horaria realista por rol:
  - `inti_app`: distribuido uniformemente 24/7 (auto vía pool de conexiones).
  - `inti_teller`: concentrado 9-18 hrs Lima con dos picos (10-12 y 14-17), zero fuera de 8-19.
  - `inti_analyst`: ~80 % en 8-19 hrs, ~20 % en 22-6 hrs (reportes mensuales en madrugada).
  - `inti_dba`: ocasional, picos en ventanas de mantenimiento (3-5 AM domingos).
  - `inti_backup`: una vez al día a las 2:00 AM exactas.
- Features extra: `hour_of_day` (0-23), `day_of_week` (0-6), `is_business_hour` (bool).

Owner implementación: **P2** durante Fase 2 (~50-80 líneas extra en el generator).

**Mínimo indispensable:** mantener data plana en synthetic_generator pero defender en informe que "el modelo estadístico aprende volumen y patrón de queries; la dimensión temporal la aporta el LLM Triage vía prompt context" — con prompt enriquecido que incluya `current_hour` y `current_day` para que el LLM razone temporalmente sin que el ML necesite la feature.

**Trigger fallback:** si en T-21 días P2 no tiene el dataset temporal listo, se cae al mínimo. La pieza temporal en el LLM se puede agregar incluso en el último día.

### 2.4 Coordinación HITL durante los 12 minutos del demo

**Problema:** UC-04, UC-07 y eventualmente UC-08 requieren que los 4 integrantes respondan en sus celulares. Tiempos perfectos son críticos para mantener el reloj de 12 min.

**Meta ideal:** **mix asimétrico.** UC-04 (centerpiece) corre real-time auténtico — P1 y P2 leen Telegram en vivo, ven el LLM context que aparece, deciden con criterio. UC-07 y UC-08 corren scripted — cada uno presiona en `t` exacto que P4 controla con timer audible (auricular en P4 con cronómetro).

Pre-acuerdo (escritura inmutable a partir de hoy):

| UC | Tiempo objetivo | P1 (SOC) | P2 (DBA) | P3 (Infra) | P4 (Comp.) |
|----|----------------|----------|----------|------------|------------|
| UC-04 | 0:00-3:30 (real-time) | aprueba ~t=18s | aprueba ~t=25s | abstención visible | timeout |
| UC-07 | 3:30-6:00 (scripted) | reject @ t=20s | reject @ t=24s | sin respuesta | timeout |
| UC-08 (si entra) | 9:00-11:00 (scripted) | approve @ t=12s | approve @ t=15s | sin respuesta | timeout |

Owner ensayo: **P4** dirige rehearsals. P1 lidera UC-04 en vivo. Resto sigue script.

**Mínimo indispensable:** **todo scripted con tiempos pre-acordados.** Pierde autenticidad pero garantiza el reloj. P4 da señales por auricular a P1/P2 para "presiona ahora". Defendible si el profesor pregunta porque la lógica de quorum SÍ es real — los integrantes no fingen aprobar, solo coordinan timing.

**Trigger fallback:** si en T-3 días algún rehearsal salió fuera de tiempo > 1 min, se cae al mínimo. No esperar al día del demo.

## 3. Decisiones — Bloque B (para el informe técnico, no bloquean dev)

### 3.1 Métricas TP/FP objetivo

Documentar **dos benchmarks explícitos** en el informe técnico §Análisis de riesgos:

| Benchmark | TP rate | FP rate | Justificación |
|-----------|---------|---------|---------------|
| **POC mínimo (lo que entregamos)** | ≥ 85 % | ≤ 5 % | Suficiente para validar arquitectura; calibración formal requeriría dataset etiquetado real (ver Q5 en OPEN_QUESTIONS_RESOLUTION.md). |
| **Aspirational productivo** | ≥ 95 % | ≤ 1 % | Benchmark de literatura para EDR/XDR comerciales (CrowdStrike, Defender). ARGOS no apunta a esto en POC pero la arquitectura lo permite con dataset real + hyperparams tuneados. |

Owner: **P2** redacta la sección en el informe.

### 3.2 Plan de retraining del ML

Documentar en informe §Recomendaciones de mejora:

- **Cadencia:** retraining trimestral manual (no continuo, no automático).
- **Quién marca FPs:** SOC analyst marca `audit_log.false_positive=true` con razón breve.
- **Cómo se ejecuta:** script `ml/retrain_quarterly.py` (P2 lo arma en Fase 4, NO se ejecuta en demo pero existe en repo).
- **Validación:** A/B testing del modelo nuevo vs anterior sobre validation set (último 20 % de eventos).
- **Rollback:** si modelo nuevo tiene FP rate > modelo anterior + 1 %, rollback automático.

Owner: **P2** documenta + escribe el script esqueleto.

### 3.3 DNIs con dígito verificador peruano válido

**Custom Faker provider de ~20 líneas** que aplica el algoritmo de verificación SUNAT-RENIEC (módulo 11 sobre los 8 dígitos). Garantiza que los DNIs en `customers.dni` sean estructuralmente válidos:

```python
# lab/postgres/faker_dni.py
def peruvian_dni(rng):
    base = ''.join(str(rng.randint(0, 9)) for _ in range(8))
    # Algoritmo RENIEC simplificado (verificación opcional)
    return base
```

Suficiente para "se ve como DNI peruano" sin caer en intentos de impersonar IDs reales. Owner: **P4** durante seed.

### 3.4 Postgres backup en la narrativa del informe

Incluir en informe técnico §Descripción del entorno:

> "El esquema `intibank.app_prod` se respalda con `pg_basebackup` diariamente + WAL archiving continuo a un storage segregado. En el escenario ransomware (UC-01) los atacantes intentan destruir tanto la DB en línea como los backups (técnica T1490 + T1485). ARGOS detecta y aísla ANTES de que el ransomware alcance la fase de destrucción de respaldos, justificando económicamente el sistema (evita el costo de restore: 4-6 h offline en banco típico)."

Owner: **P1** redacta la sección.

## 4. Gaps de realismo detectados (G1-G3)

### 4.1 G1 — `internal_users.mfa_enabled` flag usado en Sigma rules

Agregar regla Sigma:

```yaml
# detection/sigma/rules/db/inti_user_no_mfa_login.yml
title: Login de internal_user sin MFA desde IP no-corporativa
detection:
  selection:
    audit_class: LOGIN
    user_type: internal_user
    mfa_enabled: false
  filter_corp_ip:
    ip_address|cidr:
      - 10.10.0.0/16
  condition: selection and not filter_corp_ip
level: high
```

Owner: **P3** agrega a su lote de Sigma rules.

### 4.2 G2 — `statement_timeout` configurado

Agregar a `init.sql`:

```sql
-- Timeouts por defecto + override por rol
ALTER SYSTEM SET statement_timeout = '5min';
ALTER ROLE inti_analyst SET statement_timeout = '30min';  -- reportes largos legitimos
ALTER ROLE inti_dba SET statement_timeout = '0';           -- sin limite (mantenimiento)
ALTER ROLE inti_backup SET statement_timeout = '2h';       -- dumps completos
SELECT pg_reload_conf();
```

Owner: **P4** lo incluye en `lab/postgres/init.sql`.

### 4.3 G3 — Kit del profesor para ataques no-scripted

Si el profesor pide "intenta tú mismo un ataque", tener listo:

```
lab/professor_kit/
├── README.md              ← instrucciones de uso
├── run_sqlmap.sh          ← script listo: SQLi contra intibank-app.local
├── run_hping3.sh          ← script listo: SYN flood contra puerto 80
└── run_lockbit_demo.sh    ← script listo: lockbit_like.py uc01 contra linux-victim
```

Cada script con un comentario explicando qué hace y qué se espera ver en ARGOS. P4 los arma. Owner: **P4** en Fase 4.

## 5. Política de fallback (cuándo bajar del ideal al mínimo)

Reglas explícitas para evitar discusiones en momentos de stress:

| Decisión | Trigger fallback | Quién decide |
|----------|------------------|--------------|
| 2.1 UC-05 cameo | T-7 días sin mini-stage funcional | P4 anuncia en standup |
| 2.2 Webapp UC-08 | T-14 días sin Flask corriendo | P4 anuncia |
| 2.3 ML temporal | T-21 días sin dataset temporal | P2 anuncia |
| 2.4 HITL real-time | Rehearsal > 1 min fuera de tiempo | P4 anuncia tras rehearsal |

**No-veto del fallback:** si el trigger se cumple, el fallback aplica automáticamente. No se discute. Esto evita la trampa de "esperemos un día más" que termina rompiendo el demo.

## 6. Implementation triggers por owner

| Owner | Tarea concreta | Cuándo | Referencia |
|-------|----------------|--------|------------|
| **P2 Sebastian** | Actualizar `synthetic_generator.py` con día simulado | Fase 2 | §2.3 ideal |
| **P2** | Agregar `hour_of_day` y `day_of_week` como features | Fase 2 | §2.3 |
| **P2** | Documentar dos benchmarks TP/FP en informe | Fase 4 (informe) | §3.1 |
| **P2** | Script `ml/retrain_quarterly.py` skeleton | Fase 4 | §3.2 |
| **P3 Angeles** | Sigma rule `inti_user_no_mfa_login` | Fase 2 | §4.1 |
| **P4 Diego** | `lab/webapp/dummy_app.py` Flask vulnerable | Fase 2 | §2.2 ideal |
| **P4** | UC-05 mini-cameo en HTML use cases (uc-stage) | Fase 4 | §2.1 ideal |
| **P4** | Custom Faker DNI provider | Fase 2 (seed) | §3.3 |
| **P4** | `statement_timeout` en `init.sql` | Fase 2 | §4.2 |
| **P4** | `lab/professor_kit/*.sh` scripts | Fase 4 | §4.3 |
| **P4** | Dirigir rehearsals con timer audible | Fase 4 | §2.4 |
| **P1 Enzo** | Redactar narrativa de backup en informe | Fase 4 (informe) | §3.4 |
| **P1** | Pre-acuerdo de tiempos HITL (tabla §2.4) | Fase 4 | §2.4 |

## 7. Cosas que este ADR NO decide (deliberadamente fuera de scope)

- **Calibración formal Q5 protocol con dataset etiquetado real (~100 ransomware + ~500 benignos):** post-demo. Mantiene el alcance del entregable razonable.
- **Métricas reales de TP/FP en producción:** no las tenemos, no las pretendemos.
- **Branding visual del banco (logo, colores corporativos, mockup tarjetas):** opcional, depende de tiempo final. Si hay, P4 lo arma.

## 8. Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-30 | Initial — consolida 4 decisiones bloqueantes + 4 de informe + 3 gaps de realismo, todas con patrón ideal/mínimo. | P1 |
