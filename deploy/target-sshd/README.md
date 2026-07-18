# Host de prueba descartable (sshd + agente Wazuh) — validación Fase 6

Contenedor **descartable** para la validación end-to-end del vector SSH brute-force. Corre `sshd`
con un usuario de prueba de password débil (`labuser:password123`, a propósito — es el blanco) y un
agente Wazuh que reporta al manager de ARGOS. Trae los scripts de active-response de ARGOS instalados
para que la contención real (`argos-isolate`/`argos-kill`/...) ejecute acá.

> ⚠️ **Solo para un lab descartable.** El password débil es intencional. No exponer este contenedor a
> ninguna red que no controles.

## Build

```bash
# Desde la raíz del repo (el contexto de build es la raíz porque copia active-response/):
docker build -f deploy/target-sshd/Dockerfile -t argos-target-sshd .
```

## Run (enrolando al manager de ARGOS)

```bash
docker run -d --name target-sshd -p 2222:22 \
  -e WAZUH_MANAGER=<ip-del-host-donde-corre-docker-compose> \
  argos-target-sshd
```

`WAZUH_MANAGER` = la IP donde escucha el `wazuh-manager` del `docker compose --profile real`
(puertos 1514/1515 publicados). El entrypoint enrola el agente vía authd y arranca sshd.

## Verificar el enrolamiento

En el manager: `docker compose exec wazuh-manager /var/ossec/bin/agent_control -l` debe listar el
agente como `Active`. El `agent.name` que aparezca es el `host_id` que ARGOS usa — tiene que coincidir
con la clave de `config/host_inventory.json`.

## Correr el ataque (validación real — Fase 6, con go-ahead explícito)

```bash
python detection/simulators/ssh_bruteforce_controlled.py --target 127.0.0.1 --port 2222 --user labuser
# revisar el comando impreso, y SOLO entonces:
python detection/simulators/ssh_bruteforce_controlled.py --target 127.0.0.1 --port 2222 --user labuser \
  --i-confirm-this-is-my-lab
```

El brute-force dispara la regla nativa de sshd → la regla hija de ARGOS la etiqueta Layer 1 / T1110 →
incidente Tier 2 en la consola → aprobación → contención real → la IP atacante queda bloqueada.

## Teardown

```bash
docker rm -f target-sshd
```

## Estado

Este scaffolding se **prepara** en cadena (Fase 6-PREP). El boot real (build + enrolamiento + ataque +
aprobación + verificación del bloqueo) es la **Fase 6-REAL**, que corre con Enzo presente y su go-ahead
explícito en el momento — no automatizada.
