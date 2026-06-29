# RUNBOOK — Boot Fase 1A (core + víctima Linux)

Para Diego/Enzo en la **máquina de demo**. Levanta el lab real mínimo:
**Wazuh manager (core) + víctima Linux (PostgreSQL IntiBank)**. Lo que el lab
demuestra de verdad: **canary L3 + active-response**. La detección Sigma NO está
desplegada (C18) → UC-01(Sigma)/04/06/07/08 van por **injector**, no por el lab.

> Fase 1B (víctima Windows) está **diferida** — va como video. No se levanta acá.

---

## ⛔ PREREQUISITO BLOQUEANTE — Hyper-V debe estar APAGADO

**VirtualBox NO arranca VMs si Hyper-V está activo en Windows.** Síntoma exacto
(visto el 2026-06-29 en la máquina de Enzo):

```
VBoxManage.exe: error: The virtual machine 'argos-core' has terminated
unexpectedly during startup with exit code 1 (0x1).
VBoxManage.exe: error: Details: code E_FAIL (0x80004005)
```

El box descarga e importa bien; **falla al `startvm`** porque el hipervisor de
Windows (Hyper-V) ya tomó VT-x. Causa raíz acá: **Docker Desktop / WSL2** mantienen
Hyper-V encendido (`vmcompute` y `vmms` corriendo).

### Conflicto que tenés que entender (mutua exclusión en UNA sola máquina)
- **Lab VBox (Track A)** ⇒ Hyper-V **OFF**.
- **Docker Desktop / `docker compose` del host (Track B + servicios core)** ⇒ Hyper-V **ON**.
- En la **misma** máquina **no podés tener los dos a la vez**: alternar Track A ↔ Track B
  requiere **reboot**. Planificá el Go/No-Go con esto en cuenta (no es un switch instantáneo).

### Cómo chequear Hyper-V
```powershell
Get-Service vmcompute, vmms | Select-Object Name, Status     # Running = Hyper-V activo
bcdedit /enum "{current}" | findstr hypervisorlaunchtype     # Auto/On = activo
```

### Cómo apagar Hyper-V (admin + REBOOT)
```powershell
# 1) Apagar Docker Desktop (system tray -> Quit) y WSL:
wsl --shutdown
# 2) Deshabilitar el lanzamiento del hipervisor:
bcdedit /set hypervisorlaunchtype off
# 3) (si están instalados como feature, opcional) deshabilitar Hyper-V/VMP:
#    Disable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All, VirtualMachinePlatform
# 4) REINICIAR Windows.
# Para volver a Track B/Docker: bcdedit /set hypervisorlaunchtype auto  + reboot.
```

> **Alternativa recomendada:** booteá el lab en una **máquina distinta sin Docker
> Desktop/Hyper-V** (o un host Linux con VirtualBox/KVM), y dejá esta máquina para
> Track B (docker compose). Evita el baile de reboots el día de la demo.

### Otros prerequisitos
- Vagrant 2.4+ y VirtualBox 7.x instalados (`vagrant --version`, `VBoxManage --version`).
- VT-x/AMD-V habilitado en BIOS.
- ~8 GB RAM libre (core 4 GB + linux 2.5 GB) y ~15 GB disco.
- Internet en el host (los boxes y el `apt`/`docker build` del provision lo usan vía NAT).

---

## Boot

```bash
cd lab
vagrant up core linux-victim          # ~20-40 min la primera vez (boxes + provision)
vagrant status                        # core y linux-victim => running
```

Primera vez descarga `ubuntu/jammy64` (~600 MB) y `debian/bookworm64` (~300 MB).
El provision corre `apt` (Wazuh, PostgreSQL, docker) + `docker compose build` dentro
de las VMs — necesita internet y paciencia.

---

## Gates de validación (lo que el lab SÍ demuestra)

### G1 — VMs arriba
```bash
vagrant status        # core: running, linux-victim: running
```

### G2 — Agente enrolado (real)
```bash
vagrant ssh core -c "sudo /var/ossec/bin/agent_control -l"
# Esperado: LIN-VICTIM-01 ... Active
```

### G3 — DB IntiBank cargada
**Validar con `inti_dba` (superuser, ve las 7 tablas), NO `inti_app`.**
```bash
vagrant ssh linux-victim -c "PGPASSWORD=inti_dba_secret_2026 psql -h 127.0.0.1 -U inti_dba -d app_prod -c '\dt intibank.*'"
# Esperado: 7 tablas (customers, accounts, cards, transactions, transfers, internal_users, audit_log)
vagrant ssh linux-victim -c "PGPASSWORD=inti_dba_secret_2026 psql -h 127.0.0.1 -U inti_dba -d app_prod -c 'SELECT count(*) FROM intibank.customers'"
# Esperado: ~10000
```
> ⚠️ Con `inti_app` el `\dt` muestra **5** tablas, no 7 — `inti_app` no tiene GRANT sobre
> `internal_users` ni `audit_log` (ADR-0009 §2.4). **No es error**, es separation of duties.
> Para validar el schema completo usá `inti_dba`.

### G4 — Canary L3 real → events:normalized
```bash
# Disparar el canary en la víctima:
vagrant ssh linux-victim -c "sudo rm -f /opt/argos/canary/passwords.csv"
# En el core, ver la alerta cruda y el evento normalizado:
vagrant ssh core -c "sudo tail -n5 /var/ossec/logs/alerts/alerts.json"
vagrant ssh core -c "docker compose -f /argos/docker-compose.yml exec -T redis redis-cli XREVRANGE events:normalized + - COUNT 1"
# Esperado: una entrada con el campo `payload` (NO `data`) = NormalizedAlert JSON
```

### G5 — Active-response + anti-brick real
```bash
# Disparar el aislamiento (desde el SOAR o directo en la víctima para smoke):
vagrant ssh linux-victim -c "echo '{\"command\":\"add\"}' | sudo /var/ossec/active-response/bin/argos-isolate"
vagrant ssh linux-victim -c "sudo iptables -L -n --line-numbers | grep argos-isolate"
# Esperado: las reglas ACCEPT para 192.168.56.10 puertos 1514,1515 ANTES del DROP.
vagrant ssh core -c "sudo /var/ossec/bin/agent_control -l"   # el agente SIGUE Active (no se brickeó)
# Revertir:
vagrant ssh linux-victim -c "echo '{\"command\":\"delete\"}' | sudo /var/ossec/active-response/bin/argos-isolate"
```

> **NO son gate (van por injector, no por el lab):** UC-01 Sigma vssadmin, UC-04, UC-06,
> UC-07, UC-08. La capa Sigma no está desplegada (C18); el `demo_injector` ya los corre
> por el pipeline real (tiers/HITL/audit) de forma determinista.

---

## Reset entre corridas
```bash
# Limpiar el AR (quitar reglas de aislamiento) sin re-provisionar:
vagrant ssh linux-victim -c "echo '{\"command\":\"delete\"}' | sudo /var/ossec/active-response/bin/argos-isolate"
# Recrear el canary borrado:
vagrant ssh linux-victim -c "echo 'intibank-canary-do-not-touch' | sudo tee /opt/argos/canary/passwords.csv"
# Re-correr el provision (idempotente) si algo quedó sucio:
vagrant provision linux-victim
# Estado limpio total:
vagrant destroy -f core linux-victim     # y vagrant up de nuevo
```

---

## Troubleshooting

| Síntoma | Causa / fix |
|---|---|
| `startvm ... E_FAIL`, `terminated unexpectedly exit code 1` | **Hyper-V activo.** Ver la sección ⛔ arriba. Apagar Hyper-V (reboot) o usar otra máquina. |
| Agente no aparece en `agent_control -l` | Enrolamiento falló. Revisar 1514/1515 abiertos en el manager; `vagrant ssh linux-victim -c "sudo /var/ossec/bin/agent-auth -m 192.168.56.10 -A LIN-VICTIM-01"` + `systemctl restart wazuh-agent`. |
| `argos-isolate: MANAGER_IP sin configurar -> abort` | Anti-brick funcionando: falta `/var/ossec/etc/argos-ar.conf` con `MANAGER_IP=192.168.56.10`. El provision lo escribe; si no, crearlo a mano. **Sin esto NO aísla (por diseño, evita auto-brick).** |
| `apt: postgresql-15-pgaudit no encontrado` | Esperado: pgAudit no está en Debian main (vive en PGDG). El provision lo hace best-effort; el lab corre sin pgAudit (su consumidor, reglas DB, está deferido — C17). |
| `docker compose: POSTGRES_PASSWORD ... must be set` | El `.env` (mont. ro en `/argos`) trae `POSTGRES_PASSWORD` placeholder. Si falta, exportarlo o editar el `.env` del host antes del `up`. |
| `docker compose build` lento/falla en el core | Buildea `argos-core:latest` desde `/argos` (montado ro — el build lee, no escribe; ok). Necesita internet. Reintentar `vagrant provision core`. |
| Canary no genera alerta | FIM whodata puede tardar; verificar `<directories ...>/opt/argos/canary</directories>` en el `ossec.conf` del agente y `systemctl restart wazuh-agent`. |

---

## Boot offline / pre-generar el snapshot del seed

El provision necesita internet (apt Wazuh/PostgreSQL, pip Faker). `victim-linux.sh`
**falla ruidoso al inicio** si no hay egress (guard F4). Si la máquina de demo va a estar
sin internet, pre-generá el snapshot del seed en una máquina CON red y commitealo:

```bash
# En una máquina con PostgreSQL + red:
createdb app_prod
psql -d app_prod -f lab/postgres/init.sql
pip install faker numpy psycopg2-binary
VICTIM_PG_HOST=127.0.0.1 VICTIM_PG_DB=app_prod \
  VICTIM_PG_SEED_USER=inti_dba VICTIM_PG_SEED_PASSWORD=inti_dba_secret_2026 \
  python lab/postgres/seed.py
pg_dump --no-owner app_prod | gzip > lab/postgres/seed_snapshot.sql.gz
```

Con `seed_snapshot.sql.gz` presente, `victim-linux.sh` lo carga (no regenera). Igual
el apt/Wazuh del provision necesita red — el snapshot solo evita regenerar el seed.

## Qué NO valida este runbook (honesto)
"Código escrito" ≠ "lab funciona". Este runbook **no fue ejecutado end-to-end contra
Wazuh/PostgreSQL reales** (la máquina de Claude Code tiene el bloqueo Hyper-V). Los
provision scripts pasan `bash -n` y el Vagrantfile pasa `vagrant validate`, pero los
fallos de runtime (Wazuh apt/GPG, `agent-auth`, `sed` de ossec.conf, timing del docker
build) **solo se descubren en un `vagrant up` real**. Primer boot exitoso = primer test real.
