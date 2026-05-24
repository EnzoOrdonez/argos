# Sprint Semana 1 — Manual de P3 (Angeles Castillo)

| Field | Value |
|-------|-------|
| Owner | Angeles Castillo |
| Rol | P3 · Detection Engineer + Deception |
| Goal de la semana | Capa 1 (Sigma rules para ransomware + network + database + webapp) + Capa 3 (canary generator + FIM whodata) + validación con Atomic Red Team y Caldera + 2-4 PRs Sigma upstream a SigmaHQ |
| Effort estimado | 6 horas/día × 7 días = 42 horas |
| Pre-requisitos | Leer `docs/team/sprint-week-1-common-intro.md` y `docs/decisions/0008-multi-vector-scope-expansion.md` |

---

## Antes de empezar — prerequisitos

### Hardware

- Laptop con **8 GB RAM mínimo** (no necesitas correr VMs locales — usas el lab de P4 o sintéticos).
- 20 GB disco libre.
- macOS / Linux / Windows.

### Software base

```bash
python3 --version    # 3.11+
git --version
# Editor: VSCode con extensiones YAML, Sigma syntax highlight (Microsoft Sentinel pack)
```

### Cuentas externas

- **GitHub** con fork de `SigmaHQ/sigma` (para PRs upstream).
- Acceso al repo `EnzoOrdonez/argos` con permiso de PR.

---

## Día 1 (Lunes) — Setup sigma-cli + Atomic Red Team

**Goal:** entorno listo, primera regla Sigma para `vssadmin delete shadows` escrita, convertida a Wazuh y validada localmente.

**Tiempo:** 5 horas.

### Paso 1.1 — Clonar repo y crear venv (15 min)

```bash
cd ~/projects
git clone https://github.com/EnzoOrdonez/argos.git
cd argos

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ".[dev]"
pip install sigma-cli pysigma-backend-wazuh
```

**Verificación:**
```bash
sigma --help
# debe mostrar comandos: convert, check, list
sigma list backends | grep wazuh
# debe mostrar wazuh backend disponible
```

### Paso 1.2 — Crear estructura del módulo detection/ (10 min)

```bash
mkdir -p detection/sigma-rules/{ransomware,network,database,webapp}
mkdir -p detection/wazuh-rules detection/tests
touch detection/__init__.py
mkdir -p deception/canary_generator deception/fim-configs
```

### Paso 1.3 — Fork de SigmaHQ y clonar Atomic Red Team (30 min)

```bash
# Ve a github.com/SigmaHQ/sigma, haz Fork a tu usuario
# Clónalo en otro directorio:
cd ~/projects
git clone https://github.com/<tu-usuario>/sigma.git sigmahq-fork
cd sigmahq-fork
git remote add upstream https://github.com/SigmaHQ/sigma.git

# Clonar Atomic Red Team (para validar reglas)
cd ~/projects
git clone https://github.com/redcanaryco/atomic-red-team.git
```

### Paso 1.4 — Primera regla Sigma: T1490 vssadmin (1.5 h)

Crea `detection/sigma-rules/ransomware/T1490_vssadmin_delete_shadows.yml`:

```yaml
title: Volume Shadow Copies Deletion (vssadmin)
id: 4a9b1c2d-5e6f-7890-abcd-ef0123456789
status: experimental
description: |
  Detects vssadmin.exe being used to delete Volume Shadow Copies,
  a common ransomware pre-encryption step (T1490 Inhibit System Recovery).
references:
  - https://attack.mitre.org/techniques/T1490/
  - https://www.bleepingcomputer.com/news/security/lockbit-ransomware-deletes-shadow-copies/
author: Angeles Castillo (ARGOS P3)
date: 2026-05-24
tags:
  - attack.impact
  - attack.t1490
  - argos.ransomware
logsource:
  product: windows
  category: process_creation
detection:
  selection:
    Image|endswith: '\vssadmin.exe'
    CommandLine|contains|all:
      - 'delete'
      - 'shadows'
  condition: selection
falsepositives:
  - Legitimate backup software using vssadmin (rare in production)
level: high
```

**Validar con sigma-cli:**
```bash
sigma check detection/sigma-rules/ransomware/T1490_vssadmin_delete_shadows.yml
# Esperado: ✅ valid Sigma rule
```

**Convertir a Wazuh:**
```bash
sigma convert -t wazuh -f xml \
  detection/sigma-rules/ransomware/T1490_vssadmin_delete_shadows.yml \
  -o detection/wazuh-rules/T1490_vssadmin_delete_shadows.xml
cat detection/wazuh-rules/T1490_vssadmin_delete_shadows.xml
```

### Paso 1.5 — Validar con Atomic Red Team (1 h)

Cada regla Sigma debe parearse con un Atomic test que la dispare. Para T1490:

```bash
# Buscar atomic tests para T1490
grep -l "T1490" ~/projects/atomic-red-team/atomics/T1490/*
# Esperado: vssadmin delete shadows test exists

# Para correr este atomic test necesitarás coordinar con P4 que tenga la Windows VM
# Por ahora documenta el atomic test en detection/tests/atomic_pairings.md
```

Crea `detection/tests/atomic_pairings.md`:

```markdown
# Sigma rules ↔ Atomic Red Team pairings

| Sigma rule | Atomic test | Status |
|------------|-------------|--------|
| T1490_vssadmin_delete_shadows.yml | `T1490/Atomic Test #1` | Pending: needs Windows VM (P4) |
```

### Paso 1.6 — Commit + PR (10 min)

```bash
git checkout -b feature/p3/sigma-ransomware-batch1
git add detection/
git commit -m "feat(p3): primera regla Sigma T1490 vssadmin + wazuh conversion"
git push origin feature/p3/sigma-ransomware-batch1
```

### Verificación EOD Día 1

- [ ] `sigma --help` funciona
- [ ] 1 regla Sigma valid + convertida a Wazuh
- [ ] PR abierto

---

## Día 2 (Martes) — 4 reglas más de ransomware

**Goal:** 5 reglas Sigma core para ransomware mappeadas a las técnicas MITRE T1486, T1083, T1562.001, T1021, T1071.

**Tiempo:** 6 horas.

### Paso 2.1 — T1486 Mass file encryption (1 h)

`detection/sigma-rules/ransomware/T1486_mass_file_encryption_extension.yml`:

```yaml
title: Mass File Renames to Ransomware Extension
id: <generate uuid4>
status: experimental
description: |
  Detects mass file rename operations to known ransomware extensions
  (.locked, .crypt, .enc, .lockbit, etc.) within a short time window.
references:
  - https://attack.mitre.org/techniques/T1486/
author: Angeles Castillo
date: 2026-05-24
tags:
  - attack.impact
  - attack.t1486
logsource:
  product: windows
  category: file_event
detection:
  selection:
    EventID: 11   # Sysmon FileCreate
    TargetFilename|endswith:
      - '.locked'
      - '.lockbit'
      - '.crypt'
      - '.enc'
      - '.aes'
      - '.ryk'
  timeframe: 60s
  condition: selection | count() > 20
level: critical
```

### Paso 2.2 — T1083 File enumeration burst (1 h)

```yaml
title: Suspicious File Enumeration Burst
description: Process enumerating >1000 files in user directory in <30s
detection:
  selection:
    EventID: 11
    TargetFilename|contains: '\Documents\'
  timeframe: 30s
  condition: selection | count() by Image > 1000
level: medium
```

### Paso 2.3 — T1562.001 Disable Defender (45 min)

```yaml
title: Windows Defender Disabled
detection:
  selection:
    Image|endswith:
      - '\powershell.exe'
      - '\cmd.exe'
    CommandLine|contains|all:
      - 'Set-MpPreference'
      - '-DisableRealtimeMonitoring'
      - '$true'
  condition: selection
level: high
```

### Paso 2.4 — T1021 SMB lateral movement (45 min)

```yaml
title: SMB Lateral Movement Indicator
detection:
  selection:
    EventID: 3
    DestinationPort: 445
    DestinationIp|cidr: '10.0.0.0/24'
  condition: selection | count() by SourceIp > 5
timeframe: 60s
level: medium
```

### Paso 2.5 — T1071 Beacon C2 (45 min)

```yaml
title: Suspicious Outbound HTTP Beacon Pattern
detection:
  selection:
    EventID: 3
    Initiated: true
    DestinationPort: 443
  filter:
    Image|endswith:
      - '\chrome.exe'
      - '\firefox.exe'
      - '\edge.exe'
  condition: selection and not filter | count() by Image > 30
timeframe: 5min
level: low
```

### Paso 2.6 — Convertir todas a Wazuh + tests (1 h)

```bash
for f in detection/sigma-rules/ransomware/*.yml; do
    name=$(basename "$f" .yml)
    sigma convert -t wazuh -f xml "$f" -o "detection/wazuh-rules/$name.xml"
done
ls detection/wazuh-rules/
# Esperado: 5 archivos XML
```

### Paso 2.7 — Commit (10 min)

```bash
git add detection/
git commit -m "feat(p3): 4 reglas Sigma más para ransomware kill chain"
git push
```

### Verificación EOD Día 2

- [ ] 5 reglas Sigma totales, todas valid con `sigma check`
- [ ] 5 archivos Wazuh XML en `detection/wazuh-rules/`

---

## Día 3 (Miércoles) — Canary generator + FIM rules

**Goal:** Capa 3 deception completa: generador de canary files + reglas FIM whodata.

**Tiempo:** 6 horas.

### Paso 3.1 — Canary generator Python (2 h)

`deception/canary_generator/generator.py`:

```python
"""Genera canary files con contenido dummy realista en paths estratégicos."""
import os
import random
import string
from pathlib import Path
from datetime import datetime


CANARY_PROFILES = {
    "financials_Q4_2025.xlsx": {
        "size_kb": 24,
        "content_seed": "PK\x03\x04",  # ZIP magic (xlsx is ZIP)
    },
    "passwords.txt": {
        "size_kb": 2,
        "content_seed": "alice@example.com:Admin1234\n",
    },
    "db_backup.sql": {
        "size_kb": 156,
        "content_seed": "-- PostgreSQL database dump\nSET statement_timeout = 0;\n",
    },
}


def generate_canary(path: Path, profile_name: str) -> None:
    profile = CANARY_PROFILES[profile_name]
    seed = profile["content_seed"].encode()
    target_size = profile["size_kb"] * 1024
    padding = target_size - len(seed)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(seed)
        f.write(b" " * padding)

    # Antedatar el mtime para que parezca un archivo viejo
    old_time = datetime(2024, 6, 15).timestamp()
    os.utime(path, (old_time, old_time))


def deploy_canaries(base_dir: Path) -> list[Path]:
    """Deploya los 3 canaries en sub-directorios estratégicos."""
    deployed = []
    for name in CANARY_PROFILES:
        target = base_dir / "Documents" / name
        generate_canary(target, name)
        deployed.append(target)
    return deployed


if __name__ == "__main__":
    import sys
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/argos-canaries-test")
    deployed = deploy_canaries(base)
    for p in deployed:
        print(f"Deployed: {p} ({p.stat().st_size} bytes)")
```

**Test:**
```bash
python -m deception.canary_generator.generator /tmp/argos-canaries-test
ls -la /tmp/argos-canaries-test/Documents/
```

### Paso 3.2 — FIM whodata config (1.5 h)

`deception/fim-configs/wazuh-fim-canary-windows.xml`:

```xml
<!-- Wazuh syscheck config for canary monitoring (Windows) -->
<syscheck>
  <directories check_all="yes" realtime="yes" whodata="yes" report_changes="yes">
    C:\Users\Demo\Documents\financials_Q4_2025.xlsx,
    C:\Users\Demo\Documents\passwords.txt,
    C:\Users\Demo\Documents\db_backup.sql
  </directories>
</syscheck>
```

`deception/fim-configs/wazuh-fim-canary-linux.xml`:

```xml
<syscheck>
  <directories check_all="yes" realtime="yes" whodata="yes" report_changes="yes">
    /var/backups/postgres/db_backup.sql,
    /home/argos-demo/Documents/financials_Q4_2025.xlsx,
    /home/argos-demo/Documents/passwords.txt
  </directories>
</syscheck>
```

### Paso 3.3 — Wazuh custom rule canary fire (1 h)

`detection/wazuh-rules/canary_access.xml`:

```xml
<group name="argos,canary,">
  <rule id="100100" level="12">
    <if_sid>550,553,554</if_sid>  <!-- syscheck-related Wazuh internal rules -->
    <match>db_backup.sql|passwords.txt|financials_Q4_2025.xlsx</match>
    <description>ARGOS canary file accessed — possible ransomware activity</description>
    <mitre>
      <id>T1486</id>
    </mitre>
  </rule>
</group>
```

### Paso 3.4 — Commit (10 min)

```bash
git add deception/ detection/wazuh-rules/canary_access.xml
git commit -m "feat(p3): canary generator + FIM whodata + Wazuh custom rule"
git push
```

### Verificación EOD Día 3

- [ ] `python -m deception.canary_generator.generator /tmp/test` crea 3 archivos
- [ ] FIM configs XML válidos
- [ ] Custom Wazuh rule sintácticamente correcta

---

## Día 4 (Jueves) — Reglas network para UC-06 (DDoS)

**Goal:** Reglas Sigma rate-based para detectar DDoS volumetric.

**Tiempo:** 6 horas.

### Paso 4.1 — Investigar rate rules nativas en Wazuh (1 h)

Lee la doc de Wazuh sobre `<frequency>X</frequency>` y `<timeframe>Y</timeframe>` que cuentan eventos en ventanas. Wazuh tiene rate rules nativas — no necesitas escribir Sigma para esto, escribir directamente Wazuh XML.

### Paso 4.2 — Regla DDoS SYN flood (2 h)

`detection/sigma-rules/network/T1498_syn_flood.yml`:

```yaml
title: TCP SYN Flood Detection
id: <uuid>
status: experimental
description: Detects excessive SYN packets to a single destination port (T1498 Direct Network Flood)
tags:
  - attack.impact
  - attack.t1498.001
logsource:
  product: linux
  service: iptables
detection:
  selection:
    log_msg|contains: 'TCP SYN'
  timeframe: 10s
  condition: selection | count() by DESTINATION_IP > 1000
level: critical
```

Más una rule Wazuh directa para HTTP flood:

`detection/wazuh-rules/network_flood.xml`:

```xml
<group name="argos,network,ddos,">
  <rule id="100200" level="10" frequency="500" timeframe="10">
    <if_matched_sid>31100</if_matched_sid>  <!-- Wazuh's HTTP access rule -->
    <description>Possible HTTP flood: >500 requests in 10s from same IP</description>
    <mitre>
      <id>T1498</id>
    </mitre>
  </rule>
</group>
```

### Paso 4.3 — Validar con hping3 (coordinar con P4) (1 h)

P4 lanza desde otra máquina:
```bash
sudo hping3 --flood --syn -p 80 <linux-vm-ip>
```

Verificar que Wazuh dispara rule 100200 dentro de 10 segundos.

### Paso 4.4 — Commit (10 min)

```bash
git add detection/sigma-rules/network/ detection/wazuh-rules/network_flood.xml
git commit -m "feat(p3): regla DDoS SYN flood + HTTP flood rate-based"
git push
```

### Verificación EOD Día 4

- [ ] 2 reglas network creadas
- [ ] Rule Wazuh dispara con hping3 flood

---

## Día 5 (Viernes) — Reglas database + webapp (UC-07, UC-08)

**Goal:** Reglas para query patterns sospechosos (UC-07) y SQL injection patterns (UC-08).

**Tiempo:** 6 horas.

### Paso 5.1 — Regla query masivo (UC-07) (2 h)

`detection/sigma-rules/database/anomalous_query_pattern.yml`:

```yaml
title: Anomalous Database Query Pattern
id: <uuid>
description: |
  Detects large SELECT queries (>10K rows returned, >5s duration)
  outside business hours. Possible exfiltration or legitimate FP.
tags:
  - attack.collection
  - attack.t1078
logsource:
  product: postgresql
  service: pgaudit
detection:
  selection:
    log_type: 'READ'
    statement|contains: 'SELECT'
    rows_returned: '>10000'
  timefilter:
    hour: '<6 OR >22'   # fuera de horario laboral 6 AM - 10 PM
  condition: selection AND timefilter
level: medium
```

### Paso 5.2 — Reglas SQL injection (UC-08) (3 h)

`detection/sigma-rules/webapp/T1190_sql_injection_patterns.yml`:

```yaml
title: SQL Injection Patterns in HTTP Requests
id: <uuid>
description: Detects common SQL injection signatures in HTTP query parameters
tags:
  - attack.initial_access
  - attack.t1190.001
logsource:
  category: webserver
  product: nginx
detection:
  selection_keywords:
    request|contains|any:
      - "' OR '1'='1"
      - "' OR 1=1--"
      - "UNION SELECT"
      - "' UNION SELECT NULL"
      - "'; DROP TABLE"
      - "WAITFOR DELAY"
      - "SLEEP("
      - "INFORMATION_SCHEMA"
  condition: selection_keywords
level: high
```

### Paso 5.3 — Validar con sqlmap (coordinar con P4) (1 h)

P4 ejecuta:
```bash
sqlmap -u "http://<webapp>/?id=1" --batch --dbs --threads=5
```

Verificar que dispara la regla.

### Paso 5.4 — Commit (10 min)

### Verificación EOD Día 5

- [ ] 2 reglas database/webapp creadas
- [ ] sqlmap dispara la regla SQLi

---

## Día 6 (Sábado) — PRs upstream a SigmaHQ

**Goal:** Abrir 2-4 PRs en `SigmaHQ/sigma` con las reglas más generalizables.

**Tiempo:** 6 horas.

### Paso 6.1 — Identificar reglas upstream-worthy (1 h)

Las reglas más generalizables (no específicas a ARGOS):
- T1490 vssadmin delete shadows (clásica, puede tener una en SigmaHQ ya — verificar)
- T1486 mass file rename to ransomware extension
- T1562.001 Defender disabled via PowerShell

### Paso 6.2 — Adaptar a estándares SigmaHQ (2 h)

Cada regla debe tener:
- UUID único
- `references` con URLs públicos
- `author` con tu nombre
- `falsepositives` exhaustivo
- Sin tags `argos.*` (eliminar tags privados)

### Paso 6.3 — Abrir PRs (2 h)

En tu fork SigmaHQ:
```bash
cd ~/projects/sigmahq-fork
git checkout -b argos/T1490-vssadmin-delete-shadows
cp ../argos/detection/sigma-rules/ransomware/T1490_vssadmin_delete_shadows.yml rules/windows/process_creation/proc_creation_win_vssadmin_delete_shadows_argos.yml
# Editar para quitar tags argos.* y ajustar al estilo SigmaHQ
git commit -m "rules(windows): add vssadmin delete shadows detection"
git push origin argos/T1490-vssadmin-delete-shadows
# Abrir PR en github.com/SigmaHQ/sigma
```

### Paso 6.4 — Documentar PRs (30 min)

`detection/tests/upstream_prs.md`:

```markdown
# SigmaHQ upstream PR tracker

| PR # | Rule | Status | Reviewer feedback |
|------|------|--------|------------------|
| SigmaHQ/sigma#XXXX | T1490 vssadmin delete shadows | Open | Pending |
| SigmaHQ/sigma#YYYY | T1486 mass file rename | Open | Pending |
```

### Verificación EOD Día 6

- [ ] 2-4 PRs abiertos en SigmaHQ
- [ ] Tracker documentado

---

## Día 7 (Domingo) — Rehearsals + iteración

**Mañana:** Rehearsals con P4 ejecutando los 5 simuladores. Verificar cada regla dispara correctamente.

**Tarde:** Bug fixing — reglas que no disparan, falsos positivos descubiertos en baseline benigno.

**Noche:** Status update.

### Entregable EOD Día 7

- [ ] ~10 reglas Sigma totales (5 ransomware + 2 network + 1 database + 2 webapp)
- [ ] 2-4 PRs upstream abiertos
- [ ] FIM whodata configurado y disparando

---

## Apéndice A — Comandos diarios

```bash
# Activar env
cd ~/projects/argos && source .venv/bin/activate

# Validar todas las reglas Sigma
for f in detection/sigma-rules/**/*.yml; do
    sigma check "$f"
done

# Convertir todas a Wazuh
for f in detection/sigma-rules/**/*.yml; do
    out="detection/wazuh-rules/$(basename "$f" .yml).xml"
    sigma convert -t wazuh -f xml "$f" -o "$out"
done

# Validar XML Wazuh
xmllint --noout detection/wazuh-rules/*.xml && echo "All Wazuh XML valid"

# Listar Atomic tests por técnica
ls ~/projects/atomic-red-team/atomics/ | head -20
```

---

## Apéndice B — Troubleshooting

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `sigma: command not found` | venv no activado | `source .venv/bin/activate` |
| `sigma check` fail | YAML mal formado | `python -c "import yaml; print(yaml.safe_load(open('rule.yml')))"` para ver el error |
| Regla no dispara en Wazuh | Conversion sigma→wazuh perdió campos | Comparar el XML output con regla manual |
| FIM whodata no captura proceso | Sysmon no instalado correctamente | Coordinar con P4 |

---

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-24 | Initial manual P3 — 10 reglas Sigma (ransomware + network + database + webapp) + canary FIM + 2-4 PRs upstream. | P1 |
