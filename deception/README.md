# deception/ — Layer 3 (Canary Files + FIM whodata)

**Owner: P3 · Angeles Castillo**

Esta es la capa de "honeypot files": archivos cebo colocados en rutas que un
usuario legítimo nunca tocaría. El primer acceso/modificación dispara una
**alerta crítica de máxima confianza** (zero-FP por diseño).

No modifica `lab/`, Vagrant, OpenSearch, Redis ni infraestructura base
(eso es P4). Los pasos de despliegue real están marcados como pendientes.

---

## 1. Qué me corresponde aquí

- Generador de canaries (`canary-generator/generator.py` + `config.yaml`).
- Configuración FIM whodata (Windows) / auditd (Linux) (`fim-configs/`).
- Regla Wazuh de severidad crítica para cualquier toque de canary (`wazuh-rules/canary_rules.xml`).
- Script de verificación de integridad de canaries (`integrity-check/verify_canaries.sh`).
- Tests del generador y de la cobertura FIM.

## 2. Qué NO toco aquí

- No despliego `lab/`, Vagrant ni el Wazuh manager real — eso es P4.
- No modifico `argos_contracts/` (solo referencia de campos esperados para `NormalizedAlert`, `source_layer = Layer.LAYER_3`).
- No implemento el Decision Engine ni el ruteo a auto-isolation — eso es `soar/` (P1).

## 3. Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install -r deception/requirements.txt
```

## 4. Comandos de trabajo diario

```bash
# Generar canaries en una ruta sandbox local (NO en producción ni fuera del lab)
python deception/canary-generator/generator.py --config deception/canary-generator/config.yaml --host victim-windows-01

# Verificar integridad de canaries
bash deception/integrity-check/verify_canaries.sh

# Correr tests
pytest deception/tests/ -v
```

## 5. Despliegue (⚠️ pendiente de confirmar con P4)

```bash
# Placeholders — requieren que P4 tenga el host/lab levantado
scp deception/fim-configs/ossec-windows.conf <WAZUH_MANAGER>:/var/ossec/etc/agents/victim-windows-01/
scp deception/wazuh-rules/canary_rules.xml <WAZUH_MANAGER>:/var/ossec/etc/rules/
ssh <WAZUH_MANAGER> "sudo /var/ossec/bin/wazuh-control restart"
```

## 6. Disciplina de diseño de canaries (del manual)

| Regla | Por qué |
|---|---|
| Rutas absolutas, nunca wildcards | Evita que el atacante esquive el canary creando archivos con el mismo nombre en otra ruta |
| Contenido realista, no vacío | Evita la señal obvia de que es un archivo cebo |
| Timestamps realistas (60-180 días atrás) | Hace que el archivo parezca legítimo y antiguo |
| Nombres que un atacante priorizaría | `financials_Q4_2025.xlsx`, `passwords.txt`, `db_backup.sql`, `accounts_admin.csv` |

## 7. Contrato con downstream (`argos_contracts`, vía el normalizador/bridge — ADR-0014)

Esta capa no importa `argos_contracts` directamente. El **normalizador/bridge**
(ADR-0014, dueño P2/P4 — NO el SOAR, que solo consume per ADR-0013 §3) lee la
alerta Wazuh de canary y construye el `NormalizedAlert` que publica en
`events:normalized` (campo `payload`). Ese `NormalizedAlert` **debe** incluir:

- Ruta del canary (verbatim del evento FIM).
- Árbol de proceso: PID, parent PID, command line (capturado por whodata/auditd).
- `source_layer = Layer.LAYER_3` (o equivalente en grupo/descripción de la regla Wazuh).
- `severity_score >= 0.95` (zero-FP por diseño, según ADR-0003).

Esto se refleja en `wazuh-rules/canary_rules.xml` — ver comentarios en el archivo.

## 8. Estructura

```
deception/
├── README.md
├── requirements.txt
├── canary-generator/
│   ├── generator.py
│   ├── config.yaml
│   └── templates/
│       ├── financials.xlsx   (placeholder de texto, ver nota abajo)
│       ├── passwords.txt
│       └── db_backup.sql
├── fim-configs/
│   ├── ossec-windows.conf
│   └── ossec-linux.conf
├── wazuh-rules/
│   └── canary_rules.xml
├── integrity-check/
│   └── verify_canaries.sh
└── tests/
    ├── test_generator.py
    └── test_fim_config.py
```

> **Nota sobre `templates/financials.xlsx`:** un `.xlsx` real es un ZIP
> binario; este repo no genera binarios "a mano". El generador
> (`generator.py`) crea el contenido dummy de forma programática usando
> `openpyxl` (declarado en `requirements.txt`) en tiempo de ejecución —
> no se versiona un `.xlsx` binario en el repo. La carpeta `templates/`
> contiene plantillas de texto/CSV reutilizables para los formatos
> basados en texto (`.txt`, `.sql`, `.csv`).

## 9. Casos de uso cubiertos por esta capa

- **UC-02 (Canary path):** caso principal — único caso donde Layer 3 dispara sola.
