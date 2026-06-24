# Guía de Despliegue y Ejecución — P3 (Angeles Castillo)

Esta guía asume que **todo ya está listo**: el laboratorio de P4 (Vagrant +
Wazuh manager + hosts víctima) está levantado, `<WAZUH_MANAGER>` y
`<VICTIM_LAB_IP>` ya tienen valores reales, y tú tienes acceso (SSH/consola)
a esos hosts. Es la versión "día de la demo" de todo lo que ya construimos.

Sigue el orden de las fases tal cual — cada una depende de la anterior.

---

## Fase 0 — Preparación del entorno local

```bash
# Desde la raíz del monorepo (donde está pyproject.toml)
python -m venv .venv
source .venv/bin/activate          # Git Bash / Linux / Mac

pip install -e ".[dev]"
pip install -r detection/requirements.txt
pip install -r deception/requirements.txt
```

Verifica que `sigma-cli` quedó instalado:

```bash
sigma-cli --version
sigma-cli list targets       # confirma que "wazuh" aparece en la lista
```

> Si `wazuh` no aparece como target, revisa `sigma-cli convert --help` —
> el nombre exacto del target puede variar según la versión del plugin.
> Esto está marcado como variable en `detection/README.md`.

---

## Fase 1 — Validar y compilar las reglas Sigma (Layer 1)

```bash
# 1. Validar sintaxis de todas las reglas
sigma-cli check detection/sigma-rules/

# 2. Convertir Sigma -> Wazuh (esto genera/sobreescribe local_rules.xml)
sigma-cli convert -t wazuh -o detection/wazuh-rules/local_rules.xml detection/sigma-rules/

# 3. Correr los tests de mi capa antes de desplegar nada
pytest detection/tests/ -v
```

Resultado esperado: 0 errores de sintaxis, `local_rules.xml` generado, tests en verde.

---

## Fase 2 — Desplegar Layer 1 al Wazuh Manager

Sustituye `<WAZUH_MANAGER>` por el host/IP real que te dé P4.

```bash
# Copiar las reglas convertidas al manager
scp detection/wazuh-rules/local_rules.xml <WAZUH_MANAGER>:/var/ossec/etc/rules/

# Reiniciar el manager para que cargue las reglas nuevas
ssh <WAZUH_MANAGER> "sudo systemctl restart wazuh-manager"

# Confirmar que el servicio levantó sin errores
ssh <WAZUH_MANAGER> "sudo systemctl status wazuh-manager"
```

Si usas Vagrant en vez de SSH directo:

```bash
vagrant ssh wazuh-mgr -c "sudo systemctl restart wazuh-manager"
```

---

## Fase 3 — Generar y desplegar los Canary Files (Layer 3)

### 3.1 Generar los canaries en el host víctima

Este paso asume que `generator.py` corre **directamente en el host víctima**
(copialo ahí, o ejecútalo vía `ssh <VICTIM_LAB_IP> "python3 - " < generator.py`
si prefieres no copiar el archivo).

```bash
# En el host victim-windows-01 o victim-linux-01:
python deception/canary-generator/generator.py \
    --config deception/canary-generator/config.yaml \
    --host victim-windows-01
    # SIN --local-sandbox: esto escribe en las rutas reales de config.yaml
```

> ⚠️ Sin `--local-sandbox`, el script escribe en las rutas reales
> (`C:\Users\victim\...`, `/home/victim/...`). Verifica primero en modo
> sandbox (`--local-sandbox`) si quieres confirmar el comportamiento antes
> de tocar el host real.

### 3.2 Desplegar configuración FIM al agente Wazuh

```bash
# Windows
scp deception/fim-configs/ossec-windows.conf <WAZUH_MANAGER>:/var/ossec/etc/agents/victim-windows-01/

# Linux (además del FIM, instala/activa auditd si no está)
scp deception/fim-configs/ossec-linux.conf <WAZUH_MANAGER>:/var/ossec/etc/agents/victim-linux-01/
ssh victim-linux-01 "sudo apt install -y auditd && sudo augenrules --load"
```

### 3.3 Desplegar la regla Wazuh de canarios

```bash
scp deception/wazuh-rules/canary_rules.xml <WAZUH_MANAGER>:/var/ossec/etc/rules/
ssh <WAZUH_MANAGER> "sudo /var/ossec/bin/wazuh-control restart"
```

### 3.4 Verificar integridad de los canaries

```bash
bash deception/integrity-check/verify_canaries.sh \
    --config deception/canary-generator/config.yaml \
    --host victim-windows-01 \
    --recreate
```

### 3.5 Correr tests de deception antes de validar en vivo

```bash
pytest deception/tests/ -v
```

---

## Fase 4 — Validar que las alertas realmente disparan

### 4.1 Probar Layer 3 (la más simple de confirmar)

```bash
# En el host víctima, toca un canary a propósito:
ssh victim-windows-01 "type C:\Users\victim\Desktop\passwords.txt"
```

Luego, en el Wazuh Manager, revisa que la alerta llegó:

```bash
ssh <WAZUH_MANAGER> "sudo tail -f /var/ossec/logs/alerts/alerts.json"
# o, si tienes el dashboard de Wazuh:
# abrir https://<WAZUH_MANAGER>:443 y filtrar por rule.id:100100
```

Deberías ver un JSON con: ruta del canary, usuario, PID, parent PID, y
`rule.level` 12 o 13.

### 4.2 Probar Layer 1 con Atomic Red Team

```bash
# En el host víctima (requiere Atomic Red Team instalado por P4/infra):
Invoke-AtomicTest T1490 -TestNumbers 1
```

Confirma en `alerts.json` que la alerta de `vssadmin_delete_shadows.yml`
disparó (`rule.mitre.id: T1490`).

### 4.3 Correr los simuladores controlados de P3

```bash
# UC-01 — LockBit-like, 100% local, no requiere el lab
python detection/simulators/uc01_lockbit_like.py --sandbox-root ./sandbox-uc01 --run
# revisar sandbox-uc01/_simulated_events.log y los .locked generados
python detection/simulators/uc01_lockbit_like.py --sandbox-root ./sandbox-uc01 --cleanup

# UC-06 — DDoS controlado (requiere <VICTIM_LAB_IP> real)
python detection/simulators/uc06_ddos_controlled.py \
    --target <VICTIM_LAB_IP> --mode hping3 --rate-pps 50 --duration-s 15
# revisa el comando impreso, confirma que el target es correcto, y SOLO entonces:
python detection/simulators/uc06_ddos_controlled.py \
    --target <VICTIM_LAB_IP> --mode hping3 --rate-pps 50 --duration-s 15 \
    --i-confirm-this-is-my-lab

# UC-08 — SQL Injection (requiere la URL real de la app vulnerable del lab)
python detection/simulators/uc08_sqli_controlled.py \
    --target-url "http://<VICTIM_LAB_IP>/login.php?id=1"
# revisa el comando impreso, y SOLO entonces:
python detection/simulators/uc08_sqli_controlled.py \
    --target-url "http://<VICTIM_LAB_IP>/login.php?id=1" \
    --i-confirm-this-is-my-lab
```

Después de cada simulador, repite el paso 4.1 (revisar `alerts.json`) para
confirmar que la regla correspondiente disparó.

---

## Fase 5 — Verificar que los eventos llegan al pipeline (downstream)

Esto depende de infraestructura de P1/P4 (Redis, stream de eventos). Si el
stream `events:raw_wazuh` (o el nombre que el equipo haya acordado) ya
existe:

```bash
# Ejemplo genérico — el comando exacto depende de cómo P1/P4 expongan Redis
redis-cli -h <POSTGRES_LAB_HOST> XRANGE events:raw_wazuh - +
```

> Si ese stream todavía no existe o no sabes el nombre exacto,
> **pendiente de confirmar con P1/P4** — no asumas el comando exacto.

---

## Fase 6 — Checklist rápido de "todo encendido"

Ejecuta esto de corrido el día de la demo, en orden:

```bash
# 1. Validar reglas
sigma-cli check detection/sigma-rules/

# 2. Convertir
sigma-cli convert -t wazuh -o detection/wazuh-rules/local_rules.xml detection/sigma-rules/

# 3. Tests completos de mi parte
pytest detection/tests/ deception/tests/ -v

# 4. Verificar canaries
bash deception/integrity-check/verify_canaries.sh --config deception/canary-generator/config.yaml --host victim-windows-01 --recreate

# 5. Desplegar (si hubo cambios desde la última vez)
scp detection/wazuh-rules/local_rules.xml <WAZUH_MANAGER>:/var/ossec/etc/rules/
scp deception/wazuh-rules/canary_rules.xml <WAZUH_MANAGER>:/var/ossec/etc/rules/
ssh <WAZUH_MANAGER> "sudo systemctl restart wazuh-manager"

# 6. Disparar un evento de prueba y ver la alerta
ssh victim-windows-01 "type C:\Users\victim\Desktop\passwords.txt"
ssh <WAZUH_MANAGER> "sudo tail -n 50 /var/ossec/logs/alerts/alerts.json"
```

Si los 6 pasos corren sin error y ves la alerta del canary en
`alerts.json`, tu parte está lista para la demo.

---

## Resumen de qué es "tuyo" vs qué depende de otros

| Paso | Depende de |
|---|---|
| Fase 0, 1, 4.3 (parte de mostrar) | Solo P3 — nada externo |
| Fase 2, 3.2, 3.3 (despliegue real al manager/agente) | **P4** debe tener `<WAZUH_MANAGER>` y los hosts víctima arriba |
| Fase 4.2 (Atomic Red Team) | **P4/infra** debe tener Atomic Red Team instalado en el host víctima |
| Fase 4.3 (UC-06, UC-08 ejecutados de verdad) | **P4** debe confirmar `<VICTIM_LAB_IP>` y la app vulnerable |
| Fase 5 (stream de eventos) | **P1/P4** deben confirmar que el stream existe y su nombre exacto |
