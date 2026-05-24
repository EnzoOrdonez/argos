# Sprint Semana 1 — Manual de P2 (Sebastian Montenegro)

| Field | Value |
|-------|-------|
| Owner | Sebastian Montenegro |
| Rol | P2 · Ingeniero ML |
| Goal de la semana | Capa 2 ML completa (ensemble ransomware Isolation Forest + One-Class SVM) + modelos especializados para UC-06 network y UC-07 query patterns + pipeline Redis consumer + métricas A/B/C + captura forense |
| Effort estimado | 6 horas reales/día × 7 días = 42 horas |
| Pre-requisitos | Leer `docs/team/sprint-week-1-common-intro.md` y `docs/decisions/0008-multi-vector-scope-expansion.md` |

---

## Antes de empezar — chequeo de prerequisitos

### Hardware

- Laptop con **mínimo 16 GB RAM** (entrenar modelos ML + Jupyter + IDE come 12 GB fácil).
- 30 GB disco libre para datasets y modelos.
- macOS / Linux / Windows con WSL2.

### Software base

```bash
python3 --version    # 3.11+
git --version
# Jupyter Lab opcional pero útil para EDA
```

### Cuentas externas

Para P2 no necesitas cuentas externas adicionales. Tu trabajo es 100% local + acceso al repo. P1 te compartirá credenciales si necesitas tocar Redis/OpenSearch del lab de demo, pero al inicio del sprint puedes usar fakeredis para todo.

---

## Día 1 (Lunes) — Setup ambiente ML + investigación de baseline

**Goal del día:** entorno Python listo, scikit-learn + scipy + pandas funcionando, primer Isolation Forest entrenado con datos sintéticos, plan de baseline real definido.

**Tiempo:** 5-6 horas.

### Paso 1.1 — Clonar repo y crear venv (15 min)

```bash
cd ~/projects
git clone https://github.com/EnzoOrdonez/argos.git
cd argos

python3 -m venv .venv
source .venv/bin/activate              # Linux/macOS
# .venv\Scripts\activate               # Windows

pip install -U pip setuptools wheel
pip install -e ".[ml,dev]"
```

**Verificación:**
```bash
pytest argos_contracts/tests/ -v
# Esperado: 69 passed
python -c "import sklearn, scipy, pandas, numpy, joblib; print('ML stack OK')"
```

### Paso 1.2 — Crear estructura del módulo ml/

```bash
mkdir -p ml/features ml/models ml/consumer ml/notebooks ml/tests
touch ml/__init__.py ml/features/__init__.py ml/models/__init__.py ml/consumer/__init__.py ml/tests/__init__.py
```

### Paso 1.3 — Investigar features para ransomware (1.5 h)

Lee:
- SAD §5.2 (features ventana 60s)
- ADR-0008 §"Capa 2 ML — modelos especializados"
- Surveys de ML anomaly detection para ransomware (papers IEEE 2023-2024)

Las 7 features ya definidas en `argos_contracts/ml_score.py` → `MLFeatures`:

```python
file_write_rate: float            # archivos escritos por minuto
avg_entropy: float                # Shannon entropy promedio del contenido escrito
extension_modification_ratio: float  # ratio de archivos con extensión cambiada
crypto_api_calls: int             # CryptEncrypt, BCryptEncrypt (Windows); openssl/libsodium hooks (Linux)
new_outbound_connections: int     # conexiones C2 sospechosas
cpu_burst_score: float            # picos de CPU sostenidos
io_burst_score: float             # picos de I/O sostenidos
```

### Paso 1.4 — Feature extractor con datos sintéticos (2 h)

Crea `ml/features/extractor.py`:

```python
"""Feature extraction per process per 60s window for ransomware detection.

Reference: SAD §5.2.
"""
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from argos_contracts import MLFeatures


@dataclass
class ProcessTelemetry:
    """Telemetría capturada para un proceso en una ventana de 60s."""
    pid: int
    process_name: str
    files_written: list[Path]
    file_contents_sample: dict[Path, bytes]    # primeros 4KB de cada archivo
    extensions_before: list[str]
    extensions_after: list[str]
    crypto_api_calls_count: int
    outbound_connections_new: int
    cpu_samples: list[float]                    # uso CPU% cada 5s
    io_read_bytes: int
    io_write_bytes: int
    window_duration_s: float = 60.0


def shannon_entropy(data: bytes) -> float:
    """Entropía Shannon de un blob binario, normalizada a [0, 8]."""
    if not data:
        return 0.0
    counter = Counter(data)
    length = len(data)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counter.values()
        if count > 0
    )


def extract_features(t: ProcessTelemetry) -> MLFeatures:
    """Convierte ProcessTelemetry en MLFeatures (Pydantic contract)."""
    # File write rate (archivos/min)
    file_write_rate = len(t.files_written) / (t.window_duration_s / 60.0)

    # Average entropy
    entropies = [shannon_entropy(content) for content in t.file_contents_sample.values()]
    avg_entropy = sum(entropies) / len(entropies) if entropies else 0.0

    # Extension modification ratio
    if not t.extensions_before:
        extension_modification_ratio = 0.0
    else:
        modified = sum(
            1 for before, after in zip(t.extensions_before, t.extensions_after)
            if before != after
        )
        extension_modification_ratio = modified / len(t.extensions_before)

    # CPU burst score (max sostenido)
    cpu_burst_score = max(t.cpu_samples) / 100.0 if t.cpu_samples else 0.0

    # I/O burst score (proxy: write bytes / duration)
    io_burst_score = min(1.0, t.io_write_bytes / (10_000_000 * t.window_duration_s))  # >10MB/s = 1.0

    return MLFeatures(
        file_write_rate=file_write_rate,
        avg_entropy=avg_entropy,
        extension_modification_ratio=extension_modification_ratio,
        crypto_api_calls=t.crypto_api_calls_count,
        new_outbound_connections=t.outbound_connections_new,
        cpu_burst_score=cpu_burst_score,
        io_burst_score=io_burst_score,
    )
```

**Test rápido**:
```bash
python -c "
from ml.features.extractor import ProcessTelemetry, extract_features
t = ProcessTelemetry(
    pid=1234, process_name='ransom.exe',
    files_written=[],
    file_contents_sample={},
    extensions_before=['.txt', '.docx'],
    extensions_after=['.txt.locked', '.docx.locked'],
    crypto_api_calls_count=42,
    outbound_connections_new=1,
    cpu_samples=[90.0, 95.0, 92.0],
    io_read_bytes=0,
    io_write_bytes=50_000_000,
)
features = extract_features(t)
print(features.model_dump_json(indent=2))
"
```

### Paso 1.5 — Primera Isolation Forest con datos sintéticos (1.5 h)

Crea `ml/models/train_baseline.py`:

```python
"""Entrenamiento inicial de Isolation Forest sobre datos sintéticos.

Esto es Day 1 — los datos son sintéticos para validar el pipeline.
Día 3 entrenamos sobre baseline real del lab.
"""
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest


def generate_synthetic_baseline(n_samples: int = 1000, seed: int = 42) -> np.ndarray:
    """Genera 1000 muestras de actividad benigna sintética.

    Cada muestra es un vector de 7 features (orden de MLFeatures).
    """
    rng = np.random.default_rng(seed)
    return np.column_stack([
        rng.normal(5, 2, n_samples).clip(0, None),       # file_write_rate baseline ~5/min
        rng.normal(4.0, 0.5, n_samples).clip(0, 8),       # avg_entropy benigna ~4 (texto normal)
        rng.beta(1, 10, n_samples),                       # extension_modification_ratio benigna ~0.1
        rng.poisson(2, n_samples),                        # crypto_api_calls benignas ~2
        rng.poisson(1, n_samples),                        # new_outbound_connections ~1
        rng.beta(2, 5, n_samples),                        # cpu_burst_score benigno ~0.3
        rng.beta(2, 5, n_samples),                        # io_burst_score benigno ~0.3
    ])


def train_isolation_forest(X: np.ndarray, n_estimators: int = 100) -> IsolationForest:
    """Isolation Forest con contamination 0.1 (10% outliers esperados)."""
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=0.1,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X)
    return model


if __name__ == "__main__":
    X = generate_synthetic_baseline(n_samples=1000)
    model = train_isolation_forest(X)
    output = Path("ml/models/iforest_synthetic_v0.joblib")
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output)
    print(f"Saved {output} (n_estimators=100, contamination=0.1)")

    # Sanity check: predict sobre un caso ransomware
    ransom = np.array([[120, 7.8, 0.95, 42, 3, 0.9, 0.95]])  # ransomware features
    score = model.score_samples(ransom)[0]
    print(f"Ransom case score: {score:.3f} (negativo = más anómalo)")
```

```bash
python ml/models/train_baseline.py
# Esperado: archivo creado + score muy negativo (ej. -0.4)
```

### Paso 1.6 — Definir plan de baseline real (45 min)

Crea `ml/notebooks/00_baseline_plan.md`:

```markdown
# Plan de recolección de baseline benigno

**Objetivo:** capturar ~2 semanas de actividad benigna real del lab para entrenar Isolation Forest + One-Class SVM sobre features reales, no sintéticos.

**Actividades benignas a simular:**
1. Editar archivos de texto (notepad, vim) → file_write_rate bajo, avg_entropy bajo
2. Compresión con 7zip / tar → write rate medio, entropy ALTO (este es un FP típico!)
3. Backup con duplicati o restic → write rate medio, muchos archivos
4. Update de sistema (apt upgrade) → muchos files modified
5. Browsing web (descargar archivos) → new outbound connections altas
6. Compilación de software → CPU/IO burst alto

**Captura:** P4 levantará Wazuh y yo conectaré mi consumer al stream Redis durante la semana de baseline.

**Deliverable:** dataset CSV con ~10K muestras etiquetadas como BENIGN.
```

### Paso 1.7 — Commit + PR (10 min)

```bash
git checkout -b feature/p2/ml-features-baseline
git add ml/
git commit -m "feat(p2): feature extractor + IF synthetic baseline v0"
git push origin feature/p2/ml-features-baseline
```

### Verificación EOD Día 1

- [ ] `pytest argos_contracts/tests/` pasa 69 tests
- [ ] `python ml/models/train_baseline.py` crea archivo .joblib
- [ ] Score de caso ransomware es claramente negativo
- [ ] PR abierto

### Bloqueos comunes Día 1

| Problema | Causa | Fix |
|----------|-------|-----|
| `ImportError: No module named sklearn` | venv no activado o `[ml]` no instalado | `source .venv/bin/activate && pip install -e ".[ml,dev]"` |
| `IsolationForest.score_samples` returns NaN | datos con NaN | Limpieza: `X = X[~np.isnan(X).any(axis=1)]` |

---

## Día 2 (Martes) — One-Class SVM + ensemble + Redis consumer

**Goal:** OC-SVM entrenado, ensemble combinando ambos modelos, Redis consumer que lee alertas Wazuh y publica MLScore.

**Tiempo:** 6 horas.

### Paso 2.1 — One-Class SVM training (1.5 h)

Añade a `ml/models/train_baseline.py`:

```python
from sklearn.svm import OneClassSVM

def train_one_class_svm(X: np.ndarray, nu: float = 0.1) -> OneClassSVM:
    """One-Class SVM con kernel RBF.

    nu = fraction esperada de outliers (0.1 = 10%).
    """
    model = OneClassSVM(kernel="rbf", nu=nu, gamma="scale")
    model.fit(X)
    return model
```

### Paso 2.2 — Ensemble (1 h)

Crea `ml/models/ensemble.py`:

```python
"""Ensemble Isolation Forest (0.6) + One-Class SVM (0.4) per SAD §5.2."""
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM


class RansomwareEnsemble:
    """Combina IF + OC-SVM en un score [0,1]."""

    IF_WEIGHT = 0.6
    SVM_WEIGHT = 0.4

    def __init__(self, iforest: IsolationForest, ocsvm: OneClassSVM):
        self.iforest = iforest
        self.ocsvm = ocsvm

    def score(self, X: np.ndarray) -> tuple[float, float, float]:
        """Returns (iforest_score, svm_score, ensemble_score) en [0,1]."""
        # Isolation Forest: score_samples returns higher = more normal. Convertimos a anomaly score.
        if_raw = self.iforest.score_samples(X)
        if_anomaly = 1.0 - self._normalize(if_raw)

        # OC-SVM: decision_function returns higher = more normal.
        svm_raw = self.ocsvm.decision_function(X)
        svm_anomaly = 1.0 - self._normalize(svm_raw)

        ensemble = self.IF_WEIGHT * if_anomaly + self.SVM_WEIGHT * svm_anomaly
        return float(if_anomaly[0]), float(svm_anomaly[0]), float(ensemble[0])

    @staticmethod
    def _normalize(scores: np.ndarray) -> np.ndarray:
        """Min-max scaling — para Day 2 con rango fijo asumido."""
        # Rangos típicos observados durante calibración
        return np.clip((scores + 0.5) / 1.0, 0.0, 1.0)

    def save(self, path: str) -> None:
        joblib.dump({"iforest": self.iforest, "ocsvm": self.ocsvm}, path)

    @classmethod
    def load(cls, path: str) -> "RansomwareEnsemble":
        data = joblib.load(path)
        return cls(iforest=data["iforest"], ocsvm=data["ocsvm"])
```

### Paso 2.3 — Redis consumer (2 h)

Crea `ml/consumer/consumer.py`:

```python
"""Consume alertas Wazuh desde Redis stream, extrae features, publica MLScore."""
import asyncio
import json
from datetime import datetime, timezone

import redis.asyncio as redis

from argos_contracts import MLScore, NormalizedAlert
from ml.features.extractor import extract_features
from ml.models.ensemble import RansomwareEnsemble


class MLConsumer:
    def __init__(self, redis_url: str = "redis://localhost:6379/0", ensemble_path: str = "ml/models/ransomware_ensemble.pkl"):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.ensemble = RansomwareEnsemble.load(ensemble_path)

    async def run(self, stream: str = "wazuh:alerts", group: str = "ml-consumers", consumer: str = "p2-1"):
        # Create consumer group si no existe
        try:
            await self.redis.xgroup_create(stream, group, id="$", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        while True:
            messages = await self.redis.xreadgroup(
                group, consumer, {stream: ">"}, count=10, block=5000,
            )
            for _stream, entries in messages:
                for entry_id, fields in entries:
                    await self._process(fields, entry_id, stream, group)

    async def _process(self, fields: dict, entry_id: str, stream: str, group: str):
        try:
            alert = NormalizedAlert.model_validate_json(fields["data"])
            # ... extract features from alert telemetry (Day 3 wires Wazuh process_info correctly)
            # Por ahora generamos features de prueba:
            import numpy as np
            X = np.array([[10.0, 5.0, 0.2, 5, 1, 0.4, 0.4]])
            if_score, svm_score, ensemble = self.ensemble.score(X)

            score = MLScore(
                score_id=f"score-{alert.alert_id}",
                timestamp=datetime.now(timezone.utc),
                host_id=alert.host_id,
                isolation_forest_score=if_score,
                one_class_svm_score=svm_score,
                ensemble_score=ensemble,
                features=...,  # MLFeatures real
                model_version="ransomware-ensemble-v0",
            )
            await self.redis.xadd("ml:scores", {"data": score.model_dump_json()})
            await self.redis.xack(stream, group, entry_id)
        except Exception as e:
            print(f"Error processing {entry_id}: {e}")


if __name__ == "__main__":
    asyncio.run(MLConsumer().run())
```

### Paso 2.4 — Tests con fakeredis (1 h)

`ml/tests/test_consumer.py`:

```python
import pytest
from fakeredis import aioredis as fakeredis_async
# ... test que el consumer lee alerts del stream y publica MLScore
```

### Paso 2.5 — Commit (10 min)

```bash
git add ml/
git commit -m "feat(p2): One-Class SVM + ensemble + Redis consumer (ransomware)"
git push
```

### Verificación EOD Día 2

- [ ] Ensemble retorna scores válidos en [0,1]
- [ ] Consumer con fakeredis no crashea
- [ ] PR actualizado

---

## Día 3 (Miércoles) — Baseline real del lab + retraining

**Goal:** P4 tiene Wazuh manager arriba. P2 conecta consumer al lab real, recolecta baseline (~4 horas de actividad benigna simulada), reentrena ensemble.

**Tiempo:** 6 horas.

### Paso 3.1 — Coordinar con P4 (15 min)

Mensaje en `#argos-help`: "Hey P4, necesito acceso al Redis del lab para conectar mi ML consumer. ¿Me das el endpoint del stream?"

P4 te responde con el `LAB_MANAGER_IP` del Vagrantfile (típicamente `10.0.0.10`) y el puerto Redis (6379).

### Paso 3.2 — Conectar consumer al lab (1 h)

Edita `.env` local:
```
REDIS_HOST=10.0.0.10
REDIS_PORT=6379
```

Levanta consumer:
```bash
python -m ml.consumer.consumer
```

P4 ejecuta actividad benigna en las VMs víctima (browsing, file edits, etc.). Tú observas que llegan alertas al stream y tu consumer las procesa.

### Paso 3.3 — Recolectar baseline (2-4 h pasivas)

Mientras corre el consumer, tú trabajas en otra cosa (research papers, ablation prep). El consumer va llenando un CSV con features observadas:

```python
# ml/consumer/consumer.py, añadir:
import csv

def __init__(self, ..., baseline_csv: str = "ml/data/baseline.csv"):
    ...
    self.baseline_writer = csv.writer(open(baseline_csv, "a"))
```

Al final de ~4 horas tienes ~500-1000 muestras benignas reales.

### Paso 3.4 — Retraining sobre baseline real (1 h)

```python
import pandas as pd
df = pd.read_csv("ml/data/baseline.csv", names=["file_write_rate", "avg_entropy", ...])
X = df.values
ensemble = RansomwareEnsemble(
    iforest=train_isolation_forest(X),
    ocsvm=train_one_class_svm(X),
)
ensemble.save("ml/models/ransomware_ensemble.pkl")
```

### Paso 3.5 — Commit (10 min)

```bash
git add ml/models/ransomware_ensemble.pkl ml/data/baseline.csv
git commit -m "feat(p2): baseline real recolectado + ensemble retrained"
git push
```

### Verificación EOD Día 3

- [ ] Consumer conecta al Redis del lab sin errores
- [ ] Baseline CSV tiene >500 muestras reales
- [ ] Ensemble retrained, archivo .pkl actualizado

---

## Día 4 (Jueves) — Modelo network anomaly (UC-06)

**Goal:** Modelo ML especializado para UC-06 DDoS. Features distintas: connections/sec, packet rate, source IP entropy.

**Tiempo:** 6 horas.

### Paso 4.1 — Features de network traffic (1.5 h)

```python
# ml/features/network_features.py
@dataclass
class NetworkWindowTelemetry:
    connections_count: int
    packets_count: int
    unique_source_ips: int
    avg_packet_size: float
    syn_count: int
    duration_s: float = 60.0

def extract_network_features(t: NetworkWindowTelemetry):
    return {
        "connections_per_sec": t.connections_count / t.duration_s,
        "packets_per_sec": t.packets_count / t.duration_s,
        "src_ip_entropy": math.log2(t.unique_source_ips) if t.unique_source_ips > 1 else 0.0,
        "avg_packet_size": t.avg_packet_size,
        "syn_ratio": t.syn_count / max(t.packets_count, 1),
    }
```

### Paso 4.2 — Entrenar `network_traffic_anomaly.pkl` (2 h)

```python
# Synthetic network baseline
benign_network = np.array([
    rng.normal(50, 20, n).clip(0),     # connections/sec normal
    rng.normal(500, 200, n).clip(0),   # packets/sec normal
    rng.beta(2, 8, n) * 10,            # src IP entropy bajo (pocos clientes únicos)
    rng.normal(800, 300, n).clip(0),   # avg packet size normal
    rng.beta(1, 20, n),                # SYN ratio bajo
])

# DDoS sería: 10000 connections/sec, 100000 packets/sec, src_ip_entropy=15 (muchas IPs), SYN ratio=0.9
network_model = train_isolation_forest(benign_network.T)
joblib.dump(network_model, "ml/models/network_traffic_anomaly.pkl")
```

### Paso 4.3 — Wiring con SOAR (coordinar con P1) (1 h)

P1 necesita que tu MLScore tenga un campo identificador del dominio. Usar `model_version` para esto: `"ransomware-ensemble-v1"` vs `"network-anomaly-v1"`.

### Paso 4.4 — Tests + commit (1 h)

```bash
git commit -m "feat(p2): network traffic anomaly model for UC-06"
```

### Verificación EOD Día 4

- [ ] Modelo network entrenado
- [ ] Caso DDoS sintético da score >0.9

---

## Día 5 (Viernes) — Modelo query patterns (UC-07)

**Goal:** Modelo ML para detectar SELECT masivo anómalo. **Este es el modelo más importante** porque alimenta UC-07 (la pieza clave del HITL).

**Tiempo:** 7 horas (el día más largo).

### Paso 5.1 — Features de query patterns (2 h)

```python
# ml/features/query_features.py
@dataclass
class QueryWindowTelemetry:
    rows_returned: int
    query_duration_ms: float
    hour_of_day: int
    user_id: str
    query_template_hash: str
    bytes_returned: int

def extract_query_features(t: QueryWindowTelemetry):
    return {
        "log_rows_returned": math.log10(max(t.rows_returned, 1)),
        "log_duration_ms": math.log10(max(t.query_duration_ms, 1)),
        "hour_sin": math.sin(2 * math.pi * t.hour_of_day / 24),
        "hour_cos": math.cos(2 * math.pi * t.hour_of_day / 24),
        "user_hash": hash(t.user_id) % 1000 / 1000,
        "bytes_per_row": t.bytes_returned / max(t.rows_returned, 1),
    }
```

### Paso 5.2 — Coordinar con P4 sobre pgAudit (30 min)

P4 instala pgAudit en PostgreSQL VM. Cada query loggeada tiene: timestamp, user, query, rows_returned, duration. P2 recibe estos como stream Redis `pg:queries`.

### Paso 5.3 — Entrenar baseline de queries normales (2 h)

Genera 1000 queries sintéticas "normales":
- SELECT pequeño (10-100 filas), duration <1s, horario laboral, usuarios variados
- INSERT/UPDATE pequeños
- Algunos JOIN moderados (1000-5000 filas)

Entrena Isolation Forest sobre esas 1000 muestras.

### Paso 5.4 — Test escenario UC-07 (1 h)

```python
# UC-07: Sebastian a las 3 AM hace SELECT que devuelve 100K filas
uc07_case = np.array([[
    math.log10(100000),    # log_rows_returned = 5
    math.log10(8000),       # log_duration_ms = 3.9
    math.sin(2 * math.pi * 3 / 24),    # hour_sin (3 AM)
    math.cos(2 * math.pi * 3 / 24),    # hour_cos
    hash("sebastian") % 1000 / 1000,    # user_hash
    50,                      # bytes_per_row
]])
score = query_model.score_samples(uc07_case)
print(f"UC-07 score: {score}")  # debe ser anómalo pero no extremo (~ -0.3)
```

### Paso 5.5 — Commit (10 min)

```bash
git commit -m "feat(p2): query pattern anomaly model for UC-07"
```

### Verificación EOD Día 5

- [ ] Modelo query trained
- [ ] Caso UC-07 (SELECT masivo) sale con anomaly score ~0.65 (medio, T2 territory)
- [ ] Caso normal (SELECT pequeño en horario laboral) sale con score bajo (~0.2)

---

## Día 6 (Sábado) — Captura forense + métricas

**Goal:** Pipeline de captura forense (process tree, hashes, command-line) + computación de métricas A/B/C.

**Tiempo:** 6 horas.

### Paso 6.1 — Forensic capture pipeline (2 h)

```python
# evaluation/forensics/capture.py
import hashlib
import psutil

def capture_process_tree(pid: int) -> dict:
    """Snapshot del process tree alrededor del PID ofensor."""
    proc = psutil.Process(pid)
    return {
        "pid": pid,
        "name": proc.name(),
        "cmdline": proc.cmdline(),
        "parent_pid": proc.ppid(),
        "children": [{"pid": c.pid, "name": c.name()} for c in proc.children(recursive=True)],
        "open_files": [f.path for f in proc.open_files()],
        "network_connections": [
            {"local": str(c.laddr), "remote": str(c.raddr), "status": c.status}
            for c in proc.net_connections()
        ],
    }

def hash_files(paths: list[str]) -> dict[str, str]:
    """SHA-256 de cada archivo."""
    return {p: hashlib.sha256(open(p, "rb").read()).hexdigest() for p in paths}
```

### Paso 6.2 — Métricas A/B/C (3 h)

`evaluation/metrics/compute.py`:
- **A. Demo headline**: TTD, files affected, FP rate
- **B. Forensic timeline**: complete event chain
- **C. System evaluation**: P/R/F1 per layer, MITRE coverage, ablation

```python
def compute_pr_f1(predictions, ground_truth):
    from sklearn.metrics import precision_recall_fscore_support
    return precision_recall_fscore_support(ground_truth, predictions, average="binary")
```

### Paso 6.3 — Commit (10 min)

### Verificación EOD Día 6

- [ ] Forensic capture funciona contra un PID real
- [ ] Métricas P/R/F1 calculan sobre dataset sintético

---

## Día 7 (Domingo) — Rehearsals + calibración inicial

**Mañana (9-13h):** rehearsals con P1+P3+P4. Tu rol es asegurar que ML scores aparecen correctamente en la Streamlit Console durante UC-01, UC-03, UC-06, UC-07.

**Tarde (14-18h):** bug bash. Bugs típicos del ML:
- Threshold demasiado bajo → muchos false positives
- Modelo no entrenado con suficientes datos → scores erráticos
- Feature normalization rota cuando cambian rangos

**Noche (19-21h):** documentar status en `evaluation/notes/sprint-w1-status.md`.

### Entregable EOD Día 7

- [ ] 4 modelos entrenados (ransomware + network + query + opcional NSL-KDD para EV)
- [ ] Métricas iniciales calculadas (P/R/F1 sobre synthetic + baseline real)
- [ ] PR final mergeado

---

## Apéndice A — Comandos diarios

```bash
# Activar env
cd ~/projects/argos && source .venv/bin/activate

# Levantar consumer
python -m ml.consumer.consumer

# Reentrenar ensemble
python ml/models/train_baseline.py

# Tests rápidos
pytest argos_contracts/tests/ ml/tests/ -x

# Limpiar fakeredis state
redis-cli -h 10.0.0.10 FLUSHDB

# Jupyter para EDA
jupyter lab ml/notebooks/
```

---

## Apéndice B — Troubleshooting

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `ImportError: sklearn` | venv no activado | `source .venv/bin/activate && pip install -e ".[ml]"` |
| Modelo predice todo benigno | contamination demasiado bajo | Subir a 0.15-0.2 |
| Score muy errático | features no normalizadas | Aplicar StandardScaler antes del train |
| Redis connection refused | Lab P4 no levantado | Coordinar con P4 |
| `MLScore validation error` | features incompletas | Verificar todos los 7 campos en MLFeatures |

---

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 1.0 | 2026-05-24 | Initial manual P2 — Capa 2 ML completa + modelos especializados UC-06/07 + forensics + métricas. | P1 |
