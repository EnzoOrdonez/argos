# active-response/ — scripts Wazuh AR de ARGOS (Fase 3, ADR-0015 §2.3)

La contención real. El `WazuhActiveResponseExecutor` (`soar/playbooks/wazuh.py`) ordena al Wazuh
manager (`PUT /active-response`) ejecutar un comando **por nombre** en el agente víctima; el agente
corre el script de este directorio. El SOAR **no** shell-ea a la víctima (ADR-0012 §5).

Lab confirmado (ADR-0015 §2.4 enmendado): **3 VMs** — core Wazuh+SOAR en 1 VM Linux; víctimas =
**1 endpoint Windows** + **1 DB Debian (Linux)**. Por eso hay scripts para los dos sistemas.

## Comandos (== `DEFAULT_RUN_COMMANDS`/`DEFAULT_REVERT_COMMANDS` del executor)

| Comando | Acción | Linux | Windows |
|---|---|---|---|
| `argos-throttle` / `argos-unthrottle` | limita/restaura CPU-IO del PID | `renice`+`ionice`+`cpulimit` | `PriorityClass=Idle/Normal` |
| `argos-snapshot` | copia demo-safe del dir (no VSS) | `tar -czf` | `Copy-Item -Recurse` |
| `argos-isolate` / `argos-unisolate` | aísla/restaura red | `iptables` | `netsh advfirewall` |
| `argos-kill` | mata el PID | `kill -9` | `Stop-Process -Force` |

## REGLA CRÍTICA — anti auto-brick

`argos-isolate` **whitelistea la IP del manager (puertos 1514/1515) ANTES del block-all**. Si aísla
TODA la red, mata el canal agente↔manager y el manager no puede revertir ni confirmar. La IP del
manager se lee de `ARGOS_MANAGER_IP` (env) o del archivo `argos-ar.conf` (ver abajo); si falta, el
script **aborta** en vez de aislar a ciegas. Un test verifica que la regla allow precede al block.

## Despliegue (un nombre, ejecutable OS-correcto por agente)

El `<command>` del manager referencia el **nombre** (`argos-isolate`); cada agente debe tener su
ejecutable bajo ese nombre en `/var/ossec/active-response/bin/`.

**Manager (1 VM Linux):**
```bash
# Incluir los fragmentos en el ossec.conf (o copiarlos a etc/shared)
cat active-response/ossec/argos-ar-commands.conf active-response/ossec/argos-ar-active-response.conf \
    | sudo tee -a /var/ossec/etc/ossec.conf
sudo systemctl restart wazuh-manager
```

**Agente víctima Linux (Debian):**
```bash
sudo install -m 0750 -o root -g wazuh active-response/linux/argos-isolate.sh   /var/ossec/active-response/bin/argos-isolate
sudo install -m 0750 -o root -g wazuh active-response/linux/argos-unisolate.sh /var/ossec/active-response/bin/argos-unisolate
# ... idem throttle/unthrottle/snapshot/kill (sin extensión, el nombre == el <executable>)
sudo apt install -y jq iptables cpulimit
echo "MANAGER_IP=<IP_DEL_MANAGER>" | sudo tee /var/ossec/etc/argos-ar.conf
```

**Agente víctima Windows:** Wazuh corre AR vía `.exe`/`.cmd`. Por cada acción, un wrapper
`argos-isolate.cmd` en `...\ossec-agent\active-response\bin\` que invoca el `.ps1`:
```bat
@echo off
PowerShell -ExecutionPolicy Bypass -File "%~dp0argos-isolate.ps1"
```
Copiar los `.ps1` de `active-response/windows/` junto a sus wrappers; crear
`...\ossec-agent\argos-ar.conf` con `MANAGER_IP=<IP>`. (El `<executable>` del manager apunta al wrapper.)

## Interfaz (lo que recibe cada script)

Wazuh pasa por **stdin** un JSON `{"command":"add|delete","parameters":{"alert":{"data":{"argos":{...}}}}}`.
`argos = action.parameters` del SOAR: `pid` (throttle/kill), `cpu_percent_limit` (throttle); isolate/snapshot
no llevan params (target = host; el dir/manager salen de config/env). `add` = aplicar, `delete` = revertir
(timeout de Wazuh).

## Validación

- Acá (sin lab): `python -m pytest active-response/tests` — estructura del ossec, coincidencia de nombres
  con el executor, presencia de scripts, el invariante whitelist, y `bash -n`.
- **Real (lab de Diego, 3 VMs):** el SOAR ordena `argos-isolate` → el agente se aísla **sin perder el
  manager** → `argos-unisolate` revierte. Solo ahí se valida iptables/netsh de verdad.
