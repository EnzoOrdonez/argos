# detection/simulators/ — Validación controlada (Fase 5)

**Owner: P3 · Angeles Castillo**

Scripts para generar eventos de laboratorio que disparan las reglas Sigma
de mi capa. Todos son **seguros, reversibles y limitados** según las
reglas del manual P3.

## Resumen de seguridad por script

| Script | UC | Riesgo si se ejecuta mal | Salvaguarda implementada |
|---|---|---|---|
| `uc01_lockbit_like.py` | UC-01 | Ninguno fuera del sandbox — falla explícitamente si la ruta resuelta sale de `--sandbox-root` | Guard de ruta (`_assert_inside_sandbox`) en cada operación de archivo |
| `uc06_ddos_controlled.py` | UC-06 | Tráfico real de red si se ejecuta sin pensar | **No ejecuta nada por defecto** — solo imprime el comando. Requiere `--i-confirm-this-is-my-lab` explícito. Bloquea IPs públicas conocidas y `<VICTIM_LAB_IP>` sin reemplazar. Límite de `rate-pps <= 200`. |
| `uc08_sqli_controlled.py` | UC-08 | Tráfico real de ataque si se ejecuta sin pensar | Mismo patrón: solo imprime por defecto, bloquea placeholders e IPs públicas, `--risk` conservador por defecto (1). |

## Cómo correr cada uno

```bash
# UC-01 — LockBit-like (100% local, sandbox real)
python detection/simulators/uc01_lockbit_like.py --sandbox-root ./sandbox-uc01 --run
python detection/simulators/uc01_lockbit_like.py --sandbox-root ./sandbox-uc01 --cleanup

# UC-06 — DDoS controlado (PENDIENTE: requiere <VICTIM_LAB_IP> real de P4)
python detection/simulators/uc06_ddos_controlled.py --target <VICTIM_LAB_IP> --mode hping3 --rate-pps 50
# Solo después de confirmar visualmente el target:
python detection/simulators/uc06_ddos_controlled.py --target <VICTIM_LAB_IP> --mode hping3 --rate-pps 50 --i-confirm-this-is-my-lab

# UC-08 — SQL Injection (PENDIENTE: requiere que P4 confirme la app vulnerable)
python detection/simulators/uc08_sqli_controlled.py --target-url "http://<VICTIM_LAB_IP>/login.php?id=1"
python detection/simulators/uc08_sqli_controlled.py --target-url "http://<VICTIM_LAB_IP>/login.php?id=1" --i-confirm-this-is-my-lab
```

## Importante

- `uc06` y `uc08` **nunca ejecutan nada por defecto** — el modo por defecto solo construye e imprime el comando, para que tú lo revises antes de correrlo de verdad.
- Ninguno de los tres scripts toca infraestructura fuera de lo explícitamente pasado por `--target` / `--target-url` / `--sandbox-root`.
- `hping3`, `slowhttptest` y `sqlmap` deben estar instalados en el host donde se ejecuten (no se instalan automáticamente desde aquí).
