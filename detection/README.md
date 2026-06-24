# detection/ — Layer 1 (Rule-Based Detection)

**Owner: P3 · Angeles Castillo**

Este README es la guía operativa de mi parte (P3) dentro de `detection/`.
No modifica nada de `ml/`, `llm_triage/`, `soar/`, `ui/` ni `lab/`.

---

## 1. Qué me corresponde como P3

- Escribir reglas Sigma (YAML) para las técnicas MITRE asignadas.
- Mantener `mitre-mapping.yaml` (matriz técnica → regla).
- Convertir las reglas Sigma a formato Wazuh (`wazuh-rules/local_rules.xml`).
- Escribir tests que validen sintaxis Sigma, mapeo MITRE y pareo con Atomic Red Team.
- Documentar PRs upstream a `SigmaHQ/sigma` (carpeta `upstream-prs/`).

## 2. Qué NO toco aquí

- No importo ni modifico `argos_contracts/` (solo lo leo como referencia de nombres MITRE válidos — `MITRE_WHITELIST`).
- No implemento el Decision Engine, normalización de alertas, ni notificaciones — eso es `soar/` (P1).
- No despliego infraestructura (`lab/`, Vagrant, Wazuh manager real) — eso es P4. Los comandos de despliegue de abajo usan placeholders y están marcados como pendientes.

## 3. Instalación (solo lo de P3)

```bash
# Desde la raíz del monorepo
python -m venv .venv
source .venv/bin/activate          # En Git Bash / Linux / Mac
# .venv\Scripts\activate           # En CMD de Windows (no Git Bash)

# Dependencias de desarrollo compartidas (pytest, ruff, etc.) — ya están en pyproject.toml
pip install -e ".[dev]"

# Dependencias específicas de detection/ (NO instalar extras de ml, soar, llm, ui)
pip install -r detection/requirements.txt
```

> ⚠️ No ejecutar `pip install -e ".[ml]"`, `".[soar]"`, `".[llm]"` ni `".[ui]"`. Esas son de otros integrantes.

## 4. Comandos de trabajo diario

```bash
# Validar sintaxis de todas las reglas Sigma
sigma-cli check detection/sigma-rules/

# Si el target "wazuh" no existe en tu versión de sigma-cli, verifica con:
sigma-cli list targets
sigma-cli convert --help

# Convertir Sigma → Wazuh
sigma-cli convert -t wazuh -o detection/wazuh-rules/local_rules.xml detection/sigma-rules/

# Correr los tests de mi capa
pytest detection/tests/ -v
```

## 5. Despliegue (⚠️ pendiente de confirmar con P4)

Estos pasos requieren que P4 tenga `lab/` levantado (Vagrant + Wazuh manager). **No ejecutar contra nada que no sea el laboratorio aislado.**

```bash
# Placeholders — sustituir cuando P4 confirme el host real
scp detection/wazuh-rules/local_rules.xml <WAZUH_MANAGER>:/var/ossec/etc/rules/
ssh <WAZUH_MANAGER> "sudo systemctl restart wazuh-manager"
```

## 6. Validación con Atomic Red Team / Caldera

Cada regla debe tener al menos un Atomic test asociado (referenciado en el comentario `# Validated by:` dentro del YAML). La ejecución real de Atomic Red Team contra `<VICTIM_LAB_IP>` depende de que el laboratorio de P4 exista — **pendiente de confirmar con P4**.

## 7. Estructura

```
detection/
├── README.md
├── requirements.txt
├── sigma-rules/
│   ├── ransomware/
│   ├── network/
│   ├── database/
│   ├── webapp/
│   ├── defense-evasion/
│   └── discovery/
├── wazuh-rules/
│   └── local_rules.xml          # generado, no editar a mano
├── mitre-mapping.yaml
├── tests/
│   ├── test_rule_syntax.py
│   ├── test_atomic_pairs.py
│   ├── test_mitre_mapping.py
│   └── fixtures/
└── upstream-prs/
```

## 8. Nota sobre `pyproject.toml`

El `testpaths` actual de `[tool.pytest.ini_options]` **no incluye `detection/tests`**. Para que `pytest` desde la raíz del repo recoja estos tests automáticamente, hace falta agregar `"detection/tests"` a esa lista.

➡️ **Esto es un cambio al archivo compartido — opcional, coordinar con el equipo antes de tocarlo.** Mientras tanto, corre los tests apuntando directamente a la carpeta: `pytest detection/tests/ -v`.
