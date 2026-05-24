# Manual P2 — Sebastian Montenegro (ML + LLM Triage)

| Campo | Valor |
|-------|-------|
| Rol | Owner de capas estadísticas e IA |
| Owns | Layer 2 — Isolation Forest + One-Class SVM + Shannon entropy (`ml/`) · Layer 4 — LLM Triage con RAG (`ml/llm_triage/`, `ml/rag/`) |
| No owns | Sigma/Wazuh (P3) · Canary FIM (P3) · SOAR Decision Engine (P1) · Infra (P4) |
| Outputs blocking otros | `events:normalized` con `layer_origin=ml` y `layer_origin=llm` → consumido por P1 |
| Deadline | **2026-06-13 (sábado)** |
| Cómo leer | Linealmente. Cada fase asume la anterior cerrada. No avances si la checklist de la sección está incompleta. |

---

## 0. Tu charter

> Tus capas convierten señales débiles (un proceso raro, una secuencia de syscalls) en confianza numérica que el Tier Router de P1 pueda usar. Si tus modelos sobreajustan o tu LLM alucina, ARGOS pierde su mejor argumento de diferenciación frente a un SIEM tradicional.

### 0.1 Tu camino crítico

```
FASE 1 ──→ FASE 2 ──→ FASE 3 ──────→ FASE 4
prereqs    Layer 2:    Inferencia      rehearsals
cuentas    IsoForest   contra Wazuh    LLM under load
datos      OC-SVM      stream          cache hit
sintéticos Shannon                     fallback Llama
           Layer 4:
           LLM client (OpenAI + Llama)
           RAG (BM25 + BGE + RRF)
```

### 0.2 Recursos requeridos

- Espacio disco: ~12 GB (Llama 3.1 8B Q4 ≈ 5 GB + BGE-large ≈ 1.4 GB + datasets + venv).
- RAM: 16 GB mínimo si vas a correr Llama local (8 GB efectivos para el modelo).
- GPU: opcional pero acelera Llama 10×. Si no tienes, CPU inference es ~3 tokens/s — suficiente para demo (incidents llegan de a uno).

---

# FASE 1 — Cimientos

## 1.1 Verificar prerequisites

```bash
python3 --version              # OUTPUT ESPERADO: Python 3.11.x
pip --version                  # OUTPUT ESPERADO: pip 23.x o superior
docker --version               # OUTPUT ESPERADO: Docker version 24.x
nvidia-smi 2>/dev/null && echo "GPU OK" || echo "No GPU - CPU mode"
# OUTPUT ESPERADO: "GPU OK" si tienes NVIDIA; "No GPU - CPU mode" si no
free -h | head -2
# OUTPUT ESPERADO:
#                total        used        free      shared  buff/cache   available
# Mem:            15Gi       6.0Gi       3.0Gi       400Mi       6.0Gi       8.0Gi
# (necesitas "available" >= 8Gi para Llama local; menos = solo OpenAI)
```

| Check | Esperado |
|-------|----------|
| Python 3.11.x | sí |
| Docker daemon corre | `docker ps` sin error |
| RAM available ≥ 8 GB | sí (o aceptas usar solo OpenAI) |
| Disco free ≥ 15 GB | `df -h .` columna Available |

## 1.2 Crear cuenta OpenAI + API key

Ver Manual P1 §1.2.4. La key vive en `.env` (compartida con P1). **Importante**: P1 ya creó la key; tú la usas. **No crees otra** — duplicarás billing y complicarás revocación.

## 1.3 Instalar Ollama + descargar Llama 3.1 8B (fallback)

```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh
# OUTPUT ESPERADO (última línea):
# >>> The Ollama API is now available at 127.0.0.1:11434.

# Verificar servicio
systemctl status ollama --no-pager
# OUTPUT ESPERADO:
# ● ollama.service - Ollama Service
#      Loaded: loaded (...; enabled; ...)
#      Active: active (running) since ...

# Descargar Llama 3.1 8B Instruct (quantizado Q4_K_M ≈ 4.7 GB)
ollama pull llama3.1:8b-instruct-q4_K_M
# OUTPUT ESPERADO (al final):
# pulling manifest
# pulling ... 100%
# pulling ... 100%
# success

# Smoke test
ollama run llama3.1:8b-instruct-q4_K_M "Respond with one word: ARGOS"
# OUTPUT ESPERADO:
# ARGOS
```

| Check | Esperado |
|-------|----------|
| `ollama list` muestra `llama3.1:8b-instruct-q4_K_M` | sí |
| `curl http://localhost:11434/api/version` responde JSON | sí |
| Inference smoke test responde en ≤ 10s (CPU) o ≤ 2s (GPU) | sí |

## 1.4 Clonar repo + venv + deps ML

```bash
mkdir -p ~/code && cd ~/code
git clone git@github.com:enzizoor/argos.git
cd argos
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# Contratos compartidos
pip install -e ./argos_contracts
python -c "import argos_contracts; print(argos_contracts.__version__)"
# OUTPUT ESPERADO: 1.1.0

# Deps de ML
pip install -r ml/requirements.txt
# OUTPUT ESPERADO (últimas líneas):
# Successfully installed scikit-learn-1.4.x scipy-1.12.x numpy-1.26.x pandas-2.2.x
#                       sentence-transformers-2.x rank-bm25-0.2.x httpx-0.27.x ...

# Smoke
pytest ml/ -q
# OUTPUT ESPERADO:
# ........                                                          [100%]
# 8 passed in 0.18s
```

| Check Fase 1 | Esperado |
|-------------|----------|
| `python -c "import sklearn, scipy, numpy"` no falla | sí |
| Tests existentes ML pasan | 8 passed |
| `.env` cargado con `OPENAI_API_KEY` y opcional `LLM_BACKEND` | sí |
| Ollama responde si vas a usar Llama | sí |

---

# FASE 2 — Skeletons funcionales

## 2.1 Generar datasets sintéticos (baseline + ransomware)

### Qué estás haciendo

Layer 2 necesita un baseline de comportamiento normal (qué procesos, syscalls, file-IO se ven en un host limpio) y ejemplos sintéticos de ransomware para validar que detecta. El lab real lo tendrás recién en Fase 3; aquí trabajas con datasets generados.

### Script generador (código completo)

```python
# ml/data/synthetic_generator.py
"""
Genera dataset sintético de eventos host-level para entrenar el baseline y
para tests reproducibles.

Schema por fila (CSV):
    timestamp, host, pid, process, syscalls_per_min, files_touched_per_min,
    entropy_of_written_bytes, network_kbps, parent_process, command_line_len

label en columna separada:
    0 = benigno
    1 = ransomware (alta entropía + muchos files touched + supresión de shadow copies)
"""

from __future__ import annotations

import argparse, csv, random
from pathlib import Path

random.seed(42)   # reproducible

BENIGN_PROCESSES = [
    "chrome.exe", "code.exe", "explorer.exe", "svchost.exe",
    "spoolsv.exe", "outlook.exe", "winword.exe", "powershell.exe",
]

RANSOMWARE_HINTS = [
    "lockbit.exe", "encryptor.exe", "wmic.exe", "vssadmin.exe",
]


def benign_row(t: int, host: str) -> dict:
    proc = random.choice(BENIGN_PROCESSES)
    return {
        "timestamp": t, "host": host, "pid": random.randint(1000, 9999),
        "process": proc,
        "syscalls_per_min":           random.randint(50, 800),
        "files_touched_per_min":      random.randint(0, 30),
        "entropy_of_written_bytes":   round(random.uniform(2.0, 5.5), 3),
        "network_kbps":               random.randint(0, 200),
        "parent_process":             "explorer.exe" if proc != "explorer.exe" else "userinit.exe",
        "command_line_len":           random.randint(20, 120),
    }


def ransomware_row(t: int, host: str) -> dict:
    proc = random.choice(RANSOMWARE_HINTS)
    return {
        "timestamp": t, "host": host, "pid": random.randint(1000, 9999),
        "process": proc,
        "syscalls_per_min":           random.randint(3000, 9000),  # rampage
        "files_touched_per_min":      random.randint(150, 1500),   # masivo
        "entropy_of_written_bytes":   round(random.uniform(7.6, 7.99), 3),  # ≈ random
        "network_kbps":               random.randint(0, 50),       # local
        "parent_process":             random.choice(["cmd.exe", "powershell.exe"]),
        "command_line_len":           random.randint(80, 600),
    }


def generate(n_benign: int, n_attack: int, out: Path) -> None:
    rows = []
    for t in range(n_benign):
        rows.append((benign_row(t, "WIN-VICTIM-01"), 0))
    for t in range(n_attack):
        rows.append((ransomware_row(n_benign + t, "WIN-VICTIM-01"), 1))
    random.shuffle(rows)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0][0].keys()) + ["label"])
        writer.writeheader()
        for row, label in rows:
            row["label"] = label
            writer.writerow(row)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--benign", type=int, default=5000)
    p.add_argument("--attack", type=int, default=200)
    p.add_argument("--out", type=Path, default=Path("ml/data/synthetic.csv"))
    args = p.parse_args()
    generate(args.benign, args.attack, args.out)
    print(f"wrote {args.out} (benign={args.benign}, attack={args.attack})")
```

### Correr

```bash
python -m ml.data.synthetic_generator --benign 5000 --attack 200
# OUTPUT ESPERADO:
# wrote ml/data/synthetic.csv (benign=5000, attack=200)

head -3 ml/data/synthetic.csv
# OUTPUT ESPERADO (estructura, no valores exactos por random):
# timestamp,host,pid,process,syscalls_per_min,files_touched_per_min,entropy_of_written_bytes,network_kbps,parent_process,command_line_len,label
# 1234,WIN-VICTIM-01,5821,chrome.exe,512,18,4.123,87,explorer.exe,73,0
# ...

wc -l ml/data/synthetic.csv
# OUTPUT ESPERADO: 5201 ml/data/synthetic.csv  (5000 + 200 + header)
```

| Check (2.1) | Esperado |
|-------------|----------|
| Archivo CSV generado con 5201 líneas | sí |
| Columnas: 11 (10 features + label) | sí |
| `seed=42` → mismo archivo en otro laptop | sí (reproducible) |

---

## 2.2 Layer 2 — Isolation Forest + One-Class SVM (anomaly detection)

### Qué estás haciendo

Entrenar dos detectores de anomalía complementarios sobre el dataset baseline (sólo `label=0`). Cualquier punto que ambos consideren anómalo es candidato fuerte a evento sospechoso. La unión (cualquiera de los dos firing) es más sensible; la intersección es más específica. Reportamos ambos al SOAR.

### Código central (`ml/anomaly/trainer.py`)

```python
# ml/anomaly/trainer.py
"""
Entrena IsolationForest + OneClassSVM sobre features numéricas del baseline.

Outputs:
    ml/anomaly/models/iso_forest.joblib
    ml/anomaly/models/oc_svm.joblib
    ml/anomaly/models/scaler.joblib   (StandardScaler compartido)

Hiperparámetros elegidos por gut + literatura — Q3 de calibración formal
queda para semana 2 (ver docs/CONTEXT.md).
"""

from __future__ import annotations

import argparse, joblib
from pathlib import Path

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM


FEATURES = [
    "syscalls_per_min", "files_touched_per_min",
    "entropy_of_written_bytes", "network_kbps", "command_line_len",
]

MODELS_DIR = Path("ml/anomaly/models")


def train(csv_path: Path) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path)
    benign = df[df["label"] == 0][FEATURES].values

    scaler = StandardScaler().fit(benign)
    X = scaler.transform(benign)

    iso = IsolationForest(
        n_estimators=200, contamination=0.01,
        random_state=42, n_jobs=-1,
    ).fit(X)

    svm = OneClassSVM(kernel="rbf", gamma="scale", nu=0.01).fit(X)

    joblib.dump(scaler, MODELS_DIR / "scaler.joblib")
    joblib.dump(iso,    MODELS_DIR / "iso_forest.joblib")
    joblib.dump(svm,    MODELS_DIR / "oc_svm.joblib")
    print(f"trained on {len(benign)} benign samples")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, default=Path("ml/data/synthetic.csv"))
    args = p.parse_args()
    train(args.csv)
```

### Inferencia (`ml/anomaly/scorer.py`)

```python
# ml/anomaly/scorer.py
"""
Carga modelos entrenados y produce score por evento.

API expuesta al consumer del stream:
    scorer = AnomalyScorer.load()
    result = scorer.score(features_dict)
    # result = AnomalyScore(iso=-0.15, svm=-0.4, is_anomaly=True, confidence=0.83)

confidence: combinación lineal de ambos scores normalizada [0,1].
"""

from __future__ import annotations

import joblib
import numpy as np
from dataclasses import dataclass
from pathlib import Path

from ml.anomaly.trainer import FEATURES, MODELS_DIR


@dataclass(frozen=True)
class AnomalyScore:
    iso_score: float           # < 0 = anomalía (sklearn convention)
    svm_score: float           # < 0 = anomalía
    is_anomaly: bool           # ambos < 0
    confidence: float          # [0,1]


class AnomalyScorer:
    def __init__(self, scaler, iso, svm):
        self._scaler = scaler
        self._iso    = iso
        self._svm    = svm

    @classmethod
    def load(cls, models_dir: Path = MODELS_DIR) -> "AnomalyScorer":
        return cls(
            scaler=joblib.load(models_dir / "scaler.joblib"),
            iso   =joblib.load(models_dir / "iso_forest.joblib"),
            svm   =joblib.load(models_dir / "oc_svm.joblib"),
        )

    def score(self, features: dict) -> AnomalyScore:
        vec = np.array([[features[f] for f in FEATURES]])
        x = self._scaler.transform(vec)
        iso_s = float(self._iso.decision_function(x)[0])
        svm_s = float(self._svm.decision_function(x)[0])
        is_anom = (iso_s < 0) and (svm_s < 0)
        # Confidence: penalizar cuanto más negativos ambos.
        norm = max(abs(iso_s), abs(svm_s), 0.001)
        conf = min(1.0, norm * 1.3) if is_anom else 0.0
        return AnomalyScore(
            iso_score=iso_s, svm_score=svm_s,
            is_anomaly=is_anom, confidence=conf,
        )
```

### Entrenar y verificar

```bash
python -m ml.anomaly.trainer --csv ml/data/synthetic.csv
# OUTPUT ESPERADO:
# trained on 5000 benign samples

ls -la ml/anomaly/models/
# OUTPUT ESPERADO:
# -rw-r--r-- ... iso_forest.joblib   (~2-3 MB)
# -rw-r--r-- ... oc_svm.joblib       (~500 KB - 1 MB)
# -rw-r--r-- ... scaler.joblib       (~ 1 KB)

# Test contra los 200 ransomware del dataset
python - << 'PY'
import pandas as pd
from ml.anomaly.scorer import AnomalyScorer
from ml.anomaly.trainer import FEATURES

df = pd.read_csv("ml/data/synthetic.csv")
attacks = df[df["label"] == 1]
benign  = df[df["label"] == 0].sample(200, random_state=0)
scorer = AnomalyScorer.load()

attack_hits = sum(scorer.score(r._asdict() if hasattr(r,'_asdict') else dict(zip(FEATURES, [r[f] for f in FEATURES]))).is_anomaly
                  for r in attacks.itertuples(index=False))
benign_fps = sum(scorer.score(dict(zip(FEATURES, [r[f] for f in FEATURES]))).is_anomaly
                 for r in benign.itertuples(index=False))
print(f"True positives:  {attack_hits}/200  ({attack_hits/200:.1%})")
print(f"False positives: {benign_fps}/200  ({benign_fps/200:.1%})")
PY
# OUTPUT ESPERADO (aproximado, depende de seed):
# True positives:  185/200  (92.5%)
# False positives: 6/200  (3.0%)
```

| Check (2.2) | Esperado |
|-------------|----------|
| 3 archivos `.joblib` generados | sí |
| TP rate ≥ 85% sobre el subset de ataque sintético | sí |
| FP rate ≤ 5% sobre baseline | sí (si supera 10%, regenera dataset con seed diferente y reporta) |

---

## 2.3 Layer 2 — Shannon entropy en file-writes

### Qué estás haciendo

Una señal complementaria muy barata: medir entropía de Shannon de los bytes escritos a disco por un proceso. Ransomware cifra → bytes parecen aleatorios → entropía → 8.0 (máximo teórico para bytes). Software legítimo escribe formatos estructurados → entropía 4-6.

### Código (`ml/entropy/shannon.py`)

```python
# ml/entropy/shannon.py
"""Shannon entropy de bloques de bytes."""

from __future__ import annotations

import math
from collections import Counter


def shannon_entropy(data: bytes) -> float:
    """Entropy in bits per byte. Max = 8.0 (uniformly random)."""
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def classify_write(entropy: float) -> str:
    """Categoriza para uso en heurística downstream."""
    if entropy >= 7.5:
        return "encrypted_or_random"
    if entropy >= 6.5:
        return "compressed"
    if entropy >= 4.5:
        return "structured_text_or_binary"
    return "low_entropy"
```

### Tests (completos)

```python
# ml/entropy/tests/test_shannon.py
import os
import pytest
from ml.entropy.shannon import shannon_entropy, classify_write


def test_empty():
    assert shannon_entropy(b"") == 0.0


def test_single_byte_value():
    assert shannon_entropy(b"\x00" * 1000) == pytest.approx(0.0)


def test_uniform_distribution_near_max():
    data = bytes(range(256)) * 4   # 1024 bytes, uniforme
    assert shannon_entropy(data) == pytest.approx(8.0, abs=0.01)


def test_random_bytes_close_to_8():
    random_data = os.urandom(8192)
    assert shannon_entropy(random_data) > 7.9


def test_ascii_text_lower():
    text = b"the quick brown fox jumps over the lazy dog " * 200
    # Texto ASCII tiene entropía ~4-4.5
    e = shannon_entropy(text)
    assert 4.0 < e < 5.0


def test_classify_buckets():
    assert classify_write(7.9) == "encrypted_or_random"
    assert classify_write(6.9) == "compressed"
    assert classify_write(5.0) == "structured_text_or_binary"
    assert classify_write(2.0) == "low_entropy"
```

### Correr

```bash
pytest ml/entropy/tests/ -v
# OUTPUT ESPERADO:
# test_shannon.py::test_empty                          PASSED
# test_shannon.py::test_single_byte_value              PASSED
# test_shannon.py::test_uniform_distribution_near_max  PASSED
# test_shannon.py::test_random_bytes_close_to_8        PASSED
# test_shannon.py::test_ascii_text_lower               PASSED
# test_shannon.py::test_classify_buckets               PASSED
# ============================== 6 passed in 0.05s ==============================
```

| Check (2.3) | Esperado |
|-------------|----------|
| 6 tests pasan | sí |
| Shannon de archivo cifrado real (`openssl enc -aes-256-cbc ...`) ≥ 7.8 | sí |

---

## 2.4 Layer 4 — Cliente LLM dual (OpenAI + Llama local)

### Qué estás haciendo

Una interfaz `LLMClient` con dos implementaciones intercambiables vía `LLM_BACKEND` env var. El consumer no sabe cuál usa.

### Código central completo

```python
# ml/llm_triage/client.py
"""
Cliente LLM unificado.

Dos backends:
  - OpenAIClient (openai_gpt4o_mini)  → primario; latencia ~600ms; precisión alta
  - OllamaClient (llama_local)        → fallback; latencia 2-4s CPU, ~700ms GPU

El consumer hace:
    client = make_client()
    verdict = await client.classify(prompt)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional

import httpx


@dataclass(frozen=True)
class LLMVerdict:
    label: Literal["malicious", "benign", "uncertain"]
    confidence: float
    reasoning: str
    backend: str
    latency_ms: int


class LLMClient(ABC):
    @abstractmethod
    async def classify(self, prompt: str) -> LLMVerdict: ...


class OpenAIClient(LLMClient):
    def __init__(self, api_key: Optional[str] = None,
                 model: str = "gpt-4o-mini",
                 timeout: float = 10.0):
        self._key   = api_key or os.environ["OPENAI_API_KEY"]
        self._model = model
        self._http  = httpx.AsyncClient(timeout=timeout)

    async def classify(self, prompt: str) -> LLMVerdict:
        import time
        t0 = time.monotonic()
        r = await self._http.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system",
                     "content": "You are a SOC analyst. Respond with strict JSON: "
                                "{\"label\": \"malicious|benign|uncertain\","
                                "\"confidence\": 0.0..1.0, \"reasoning\": \"...\"}"},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            },
        )
        r.raise_for_status()
        import json
        content = r.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return LLMVerdict(
            label=parsed["label"], confidence=float(parsed["confidence"]),
            reasoning=parsed["reasoning"], backend="openai_gpt4o_mini",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


class OllamaClient(LLMClient):
    def __init__(self,
                 model: str = "llama3.1:8b-instruct-q4_K_M",
                 base_url: str = "http://localhost:11434",
                 timeout: float = 30.0):
        self._model = model
        self._url   = base_url
        self._http  = httpx.AsyncClient(timeout=timeout)

    async def classify(self, prompt: str) -> LLMVerdict:
        import time, json
        t0 = time.monotonic()
        r = await self._http.post(
            f"{self._url}/api/chat",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system",
                     "content": "Respond JSON only: {\"label\":..., \"confidence\":..., "
                                "\"reasoning\":...}"},
                    {"role": "user", "content": prompt},
                ],
                "format": "json", "stream": False,
                "options": {"temperature": 0.0},
            },
        )
        r.raise_for_status()
        content = r.json()["message"]["content"]
        parsed = json.loads(content)
        return LLMVerdict(
            label=parsed.get("label", "uncertain"),
            confidence=float(parsed.get("confidence", 0.5)),
            reasoning=parsed.get("reasoning", ""),
            backend="llama_local",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


def make_client() -> LLMClient:
    backend = os.environ.get("LLM_BACKEND", "openai_gpt4o_mini")
    if backend == "openai_gpt4o_mini":
        return OpenAIClient()
    if backend == "llama_local":
        return OllamaClient()
    raise ValueError(f"unknown LLM_BACKEND: {backend}")
```

### Smoke test

```bash
# OpenAI
export LLM_BACKEND=openai_gpt4o_mini
python - << 'PY'
import asyncio
from ml.llm_triage.client import make_client
async def main():
    c = make_client()
    v = await c.classify(
        "A process called encryptor.exe wrote 1500 files in 30 seconds with "
        "Shannon entropy 7.9. Is this malicious?"
    )
    print(v)
asyncio.run(main())
PY
# OUTPUT ESPERADO (verdict puede variar en `reasoning`):
# LLMVerdict(label='malicious', confidence=0.95, reasoning='...', backend='openai_gpt4o_mini', latency_ms=687)

# Llama local
export LLM_BACKEND=llama_local
python - << 'PY'
import asyncio
from ml.llm_triage.client import make_client
async def main():
    c = make_client()
    v = await c.classify("Same prompt as above.")
    print(v)
asyncio.run(main())
PY
# OUTPUT ESPERADO (con GPU):
# LLMVerdict(label='malicious', confidence=0.92, reasoning='...', backend='llama_local', latency_ms=1200)
# Sin GPU: latency_ms ~ 4500
```

| Check (2.4) | Esperado |
|-------------|----------|
| OpenAI devuelve verdict válido con confidence numérica | sí |
| Llama local devuelve verdict válido | sí |
| Switching backend solo con env var (sin tocar código) | sí |
| Si OpenAI key inválida → `HTTPStatusError 401` propagado (el caller lo captura) | sí |

---

## 2.5 Layer 4 — RAG (BM25 + BGE-large + RRF)

### Qué estás haciendo

Antes de pasar la alerta cruda al LLM, recuperar 3-5 documentos relevantes (definiciones MITRE, ejemplos de variantes históricas, runbook del equipo) y inyectarlos como contexto. Esto reduce alucinación y mejora confidence.

> **Decisión de scope (ADR-0001 v2)**: NO cross-encoder reranker. BM25 + BGE-large + RRF (Reciprocal Rank Fusion) es suficiente; el reranker añadía 2× latencia para ganancia marginal en el corpus pequeño que tenemos.

### Estructura

```
ml/rag/
├── __init__.py
├── index.py        ← build BM25 + BGE embeddings (full)
├── retriever.py    ← BM25 + dense + RRF fusion (full)
├── prompt.py       ← template y armado de prompt (full, pequeño)
└── corpus/
    ├── mitre/      ← markdown por técnica (P2 cura)
    ├── runbook/    ← runbook de respuesta por escenario
    └── variants/   ← variantes históricas (LockBit, Conti, ...)
```

### `index.py` — construir índice (código completo)

```python
# ml/rag/index.py
"""
Indexa documentos markdown del corpus para BM25 + BGE.

Output:
    ml/rag/_index/bm25.pkl         (rank_bm25 BM25Okapi)
    ml/rag/_index/embeddings.npy   (matriz N × 1024)
    ml/rag/_index/docs.jsonl       (texto + metadata por documento)
"""

from __future__ import annotations

import json, pickle, re
from pathlib import Path
from dataclasses import dataclass, asdict

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

CORPUS_ROOT = Path("ml/rag/corpus")
INDEX_DIR   = Path("ml/rag/_index")
EMBED_MODEL = "BAAI/bge-large-en-v1.5"


@dataclass
class Doc:
    id: str
    source: str        # mitre / runbook / variant
    title: str
    text: str


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def load_corpus() -> list[Doc]:
    docs = []
    for md in CORPUS_ROOT.rglob("*.md"):
        source = md.parent.name
        text = md.read_text(encoding="utf-8")
        # primera línea suele ser # Titulo
        title = text.splitlines()[0].lstrip("# ").strip() if text else md.stem
        docs.append(Doc(id=str(md.relative_to(CORPUS_ROOT)),
                        source=source, title=title, text=text))
    return docs


def build() -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    docs = load_corpus()
    if not docs:
        raise RuntimeError(f"corpus vacío en {CORPUS_ROOT}")

    tokenized = [_tokenize(d.text) for d in docs]
    bm25 = BM25Okapi(tokenized)
    with (INDEX_DIR / "bm25.pkl").open("wb") as f:
        pickle.dump(bm25, f)

    model = SentenceTransformer(EMBED_MODEL)
    embeddings = model.encode([d.text for d in docs], normalize_embeddings=True)
    np.save(INDEX_DIR / "embeddings.npy", embeddings)

    with (INDEX_DIR / "docs.jsonl").open("w") as f:
        for d in docs:
            f.write(json.dumps(asdict(d)) + "\n")

    print(f"indexed {len(docs)} docs (BM25 + BGE-{embeddings.shape[1]}d)")


if __name__ == "__main__":
    build()
```

### `retriever.py` — recuperar top-k con RRF (completo)

```python
# ml/rag/retriever.py
"""Retriever híbrido BM25 + denso, fusión con Reciprocal Rank Fusion."""

from __future__ import annotations

import json, pickle
from pathlib import Path
from typing import Iterable

import numpy as np
from sentence_transformers import SentenceTransformer

from ml.rag.index import INDEX_DIR, EMBED_MODEL, Doc, _tokenize


RRF_K = 60   # constante estándar


def _rrf(rankings: Iterable[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for rank in rankings:
        for pos, doc_idx in enumerate(rank):
            scores[doc_idx] = scores.get(doc_idx, 0.0) + 1.0 / (k + pos + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    def __init__(self):
        with (INDEX_DIR / "bm25.pkl").open("rb") as f:
            self._bm25 = pickle.load(f)
        self._embeds = np.load(INDEX_DIR / "embeddings.npy")
        with (INDEX_DIR / "docs.jsonl").open() as f:
            self._docs = [Doc(**json.loads(line)) for line in f]
        self._model = SentenceTransformer(EMBED_MODEL)

    def retrieve(self, query: str, k: int = 5) -> list[Doc]:
        # BM25 ranking
        bm25_scores = self._bm25.get_scores(_tokenize(query))
        bm25_rank = list(np.argsort(bm25_scores)[::-1])
        # Dense ranking
        qv = self._model.encode([query], normalize_embeddings=True)[0]
        dense_scores = self._embeds @ qv
        dense_rank = list(np.argsort(dense_scores)[::-1])

        fused = _rrf([bm25_rank[:30], dense_rank[:30]])
        return [self._docs[idx] for idx, _ in fused[:k]]
```

### Construir índice y verificar

```bash
# Asegúrate de tener al menos 3 docs en corpus/ (incluso lorem ipsum sirve para smoke)
mkdir -p ml/rag/corpus/mitre ml/rag/corpus/runbook
cat > ml/rag/corpus/mitre/T1486.md << 'DOC'
# T1486 — Data Encrypted for Impact

Adversaries may encrypt data on target systems...
DOC
cat > ml/rag/corpus/runbook/ransomware_response.md << 'DOC'
# Ransomware response runbook

If file-write entropy > 7.5 and files_touched > 100/min, isolate the host...
DOC

python -m ml.rag.index
# OUTPUT ESPERADO (primer run descarga el modelo BGE — puede tomar 1-2 min):
# indexed 2 docs (BM25 + BGE-1024d)

python - << 'PY'
from ml.rag.retriever import HybridRetriever
r = HybridRetriever()
results = r.retrieve("Process encrypting files in bulk", k=2)
for d in results:
    print(d.id, "→", d.title)
PY
# OUTPUT ESPERADO:
# mitre/T1486.md → T1486 — Data Encrypted for Impact
# runbook/ransomware_response.md → Ransomware response runbook
```

| Check (2.5) | Esperado |
|-------------|----------|
| `_index/` tiene 3 archivos | sí |
| Query relevante recupera doc esperado en top-2 | sí |
| Tiempo de retrieval ≤ 500ms tras warm-up | sí |

---

## 2.6 Layer 4 — Triage end-to-end

### Código (`ml/llm_triage/triage.py`)

```python
# ml/llm_triage/triage.py
"""
Ensambla: evento → prompt con contexto RAG → LLM → LLMVerdict.

API pública usada por el consumer SOAR:
    verdict = await classify(event)
"""

from __future__ import annotations

import logging
from typing import Optional

from argos_contracts.incident import NormalizedEvent

from ml.llm_triage.client import LLMVerdict, make_client
from ml.rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)

_RETRIEVER: Optional[HybridRetriever] = None
_CLIENT = None


def _retriever() -> HybridRetriever:
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = HybridRetriever()
    return _RETRIEVER


def _client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = make_client()
    return _CLIENT


def _build_prompt(event: NormalizedEvent, ctx_docs) -> str:
    ctx = "\n\n".join(f"### {d.title}\n{d.text[:600]}" for d in ctx_docs)
    return (
        f"## Event\n"
        f"Host: {event.host}\n"
        f"MITRE technique: {event.mitre_technique}\n"
        f"Severity: {event.severity}\n"
        f"Layers fired: {event.num_layers_fired}\n"
        f"Confidence (stat): {event.confidence_score}\n"
        f"\n## Context (top RAG docs)\n{ctx}\n"
        f"\n## Task\nClassify the event."
    )


async def classify(event: NormalizedEvent) -> LLMVerdict:
    docs = _retriever().retrieve(
        f"{event.mitre_technique} {event.host}", k=4
    )
    prompt = _build_prompt(event, docs)
    return await _client().classify(prompt)
```

### Probar contra evento sintético

```bash
python - << 'PY'
import asyncio
from argos_contracts.incident import NormalizedEvent
from argos_contracts.enums import Severity
from ml.llm_triage.triage import classify

evt = NormalizedEvent(
    event_id="evt-llm-001", severity=Severity.MEDIUM,
    mitre_technique="T1486", num_layers_fired=2, confidence_score=0.71,
    host="WIN-VICTIM-01", layer_origin="sigma",
)
print(asyncio.run(classify(evt)))
PY
# OUTPUT ESPERADO:
# LLMVerdict(label='malicious', confidence=0.93, reasoning='...references T1486 and high entropy...', backend='openai_gpt4o_mini', latency_ms=750)
```

| Check (2.6) | Esperado |
|-------------|----------|
| End-to-end devuelve verdict en ≤ 2s (OpenAI) o ≤ 6s (Llama CPU) | sí |
| RAG inyecta ≥ 2 docs relevantes en el prompt | sí |
| Sin context (corpus vacío) → aún devuelve verdict pero `confidence < 0.7` | sí |

---

## ✅ Checklist Fase 2

| # | Check | OK |
|---|-------|----|
| 1 | Synthetic dataset generado (5201 filas) | ☐ |
| 2 | IsoForest + OC-SVM entrenados (3 `.joblib`) | ☐ |
| 3 | TP rate ≥ 85%, FP rate ≤ 5% sobre dataset sintético | ☐ |
| 4 | Shannon entropy tests (6) pasan | ☐ |
| 5 | OpenAI client devuelve verdict válido | ☐ |
| 6 | Llama local client devuelve verdict válido | ☐ |
| 7 | RAG indexa corpus y recupera por similaridad | ☐ |
| 8 | `classify(event)` end-to-end funciona en ≤ 2s | ☐ |
| 9 | `pytest ml/ -q` pasa (esperado ≥ 20 tests) | ☐ |

---

# FASE 3 — Integración real

## 3.1 Consumer del stream Wazuh → emitir a `events:normalized`

### Qué estás haciendo

Suscribirte al stream de eventos crudos que P3 emite desde Wazuh (`events:raw_wazuh`). Para cada evento, computar features, correr Layer 2, opcionalmente Layer 4, y emitir `NormalizedEvent` al stream que P1 consume (`events:normalized`).

### Código central (`ml/consumer.py`)

```python
# ml/consumer.py
"""
Pipeline ML: raw Wazuh event → features → Layer 2 + (opcional) Layer 4 → normalized.

Stream input:  events:raw_wazuh
Stream output: events:normalized  (consumido por P1)
Group:         ml-pipeline
"""

from __future__ import annotations

import asyncio, json, logging, os, time, uuid
import redis.asyncio as redis

from argos_contracts.enums import Severity
from argos_contracts.incident import NormalizedEvent
from ml.anomaly.scorer import AnomalyScorer
from ml.llm_triage.triage import classify as llm_classify

logger = logging.getLogger(__name__)

IN_STREAM  = "events:raw_wazuh"
OUT_STREAM = "events:normalized"
GROUP      = "ml-pipeline"
CONSUMER   = os.environ.get("ML_CONSUMER_NAME", "ml-1")

_scorer = AnomalyScorer.load()


def _features_from_wazuh(evt: dict) -> dict:
    """Adaptador del schema Wazuh → features dict para AnomalyScorer."""
    return {
        "syscalls_per_min":         evt.get("syscalls_per_min", 0),
        "files_touched_per_min":    evt.get("files_touched_per_min", 0),
        "entropy_of_written_bytes": evt.get("entropy_of_written_bytes", 0.0),
        "network_kbps":             evt.get("network_kbps", 0),
        "command_line_len":         len(evt.get("command_line", "")),
    }


async def _process(r: redis.Redis, raw: dict) -> None:
    evt = json.loads(raw["data"])
    feats = _features_from_wazuh(evt)
    score = _scorer.score(feats)

    if not score.is_anomaly:
        return   # sub-threshold → no emit

    norm = NormalizedEvent(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        severity=Severity.MEDIUM if score.confidence < 0.85 else Severity.HIGH,
        mitre_technique=evt.get("mitre_technique", "Unknown"),
        num_layers_fired=1,   # ML alone; SOAR puede consolidar con otras capas
        confidence_score=score.confidence,
        host=evt.get("host", "unknown"),
        layer_origin="ml",
    )
    await r.xadd(OUT_STREAM, {"data": norm.model_dump_json()})
    logger.info("ml emit %s host=%s conf=%.2f",
                norm.event_id, norm.host, norm.confidence_score)


async def run() -> None:
    r = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        await r.xgroup_create(IN_STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    while True:
        resp = await r.xreadgroup(GROUP, CONSUMER, {IN_STREAM: ">"},
                                  count=10, block=5000)
        for _, entries in resp or []:
            for entry_id, fields in entries:
                try:
                    await _process(r, fields)
                    await r.xack(IN_STREAM, GROUP, entry_id)
                except Exception:
                    logger.exception("failed to process %s", entry_id)
```

### Verificar con eventos inyectados

```bash
# Terminal 1: arranca consumer ML
python -m ml.consumer

# Terminal 2: simula evento Wazuh
redis-cli XADD events:raw_wazuh '*' data \
  '{"host":"WIN-VICTIM-01","mitre_technique":"T1486","syscalls_per_min":5500,"files_touched_per_min":800,"entropy_of_written_bytes":7.85,"network_kbps":10,"command_line":"powershell.exe -enc xxxxxx"}'
# OUTPUT ESPERADO: "1234-0"

# Terminal 1 debería loguear:
# INFO:ml.consumer:ml emit evt-abc123 host=WIN-VICTIM-01 conf=0.93

# Verificar emisión al stream consumido por P1:
redis-cli XLEN events:normalized
# OUTPUT ESPERADO: 1 (o más, si corriste antes)
redis-cli XREVRANGE events:normalized + - COUNT 1
# OUTPUT ESPERADO (JSON):
# 1) 1) "1234-0"
#    2) 1) "data"
#       2) "{\"event_id\":\"evt-abc123\",\"severity\":\"HIGH\",...}"
```

| Check (3.1) | Esperado |
|-------------|----------|
| Consumer ML levanta sin error | sí |
| Eventos benignos NO se emiten a `events:normalized` | sí (`xlen` no crece) |
| Eventos ransomware-like SÍ se emiten | sí |
| `confidence_score` correlaciona con severidad del evento | sí |

---

## 3.2 LLM Triage callable desde el SOAR

P1 lo importa así: `from ml.llm_triage import classify as llm_classify`. Asegúrate de exportarlo desde `ml/llm_triage/__init__.py`:

```python
# ml/llm_triage/__init__.py
from ml.llm_triage.triage import classify
__all__ = ["classify"]
```

Y verifica:

```bash
python -c "from ml.llm_triage import classify; print(classify)"
# OUTPUT ESPERADO:
# <function classify at 0x...>
```

| Check (3.2) | Esperado |
|-------------|----------|
| `from ml.llm_triage import classify` funciona desde cualquier dir del repo | sí |
| Si Ollama caído y `LLM_BACKEND=llama_local`, error captura sin crashear el consumer P1 | sí |

---

## 3.3 Smoke end-to-end con P1

Coordina con P1 una corrida conjunta:

```bash
# P1 corre:
python -m soar.decision_engine.consumer

# Tú corres:
python -m ml.consumer

# P3 (o tú con un comando manual) inyecta a events:raw_wazuh
# Verifica: incident:* aparece en Redis, notif llega a Telegram con
# layer_origin=ml en los logs.
```

| Check (3.3) | Esperado |
|-------------|----------|
| Evento raw → ML normaliza → SOAR consume → Telegram en ≤ 8s | sí |
| `incident.llm_verdict` poblado para T2 | sí |

---

## ✅ Checklist Fase 3

| # | Check | OK |
|---|-------|----|
| 1 | ML consumer corre y procesa stream | ☐ |
| 2 | Emisión solo cuando is_anomaly | ☐ |
| 3 | Integración con P1 verificada end-to-end | ☐ |
| 4 | LLM verdict atadito al incident en Redis | ☐ |
| 5 | Audit log (P1) refleja `layer_origin=ml` | ☐ |

---

# FASE 4 — Rehearsal y polish

## 4.1 Rehearsal de carga (cómo se comporta bajo varios eventos seguidos)

```bash
# Inyectar 50 eventos en burst
for i in $(seq 1 50); do
  redis-cli XADD events:raw_wazuh '*' data \
    "{\"host\":\"WIN-VICTIM-01\",\"mitre_technique\":\"T1486\",\"syscalls_per_min\":$((RANDOM % 5000 + 1000)),\"files_touched_per_min\":$((RANDOM % 800 + 100)),\"entropy_of_written_bytes\":7.8,\"network_kbps\":5,\"command_line\":\"x\"}" > /dev/null
done

# Medir cuántos llegaron a events:normalized
sleep 5
redis-cli XLEN events:normalized
# OUTPUT ESPERADO:
# Un número entre 35 y 50 (dependiendo de cuántos pasen el threshold).
# Si < 30, tu ML está descartando demasiado → revisar threshold.
# Si = 50 todos, contamination está muy alta → 1% es razonable.
```

| Check (4.1) | Esperado |
|-------------|----------|
| ML procesa 50 events en ≤ 3s | sí |
| No memory leak (RSS estable durante el burst) | sí |
| Logs no muestran ERROR | sí |

## 4.2 Failover OpenAI → Llama

```bash
# Simular OpenAI caído (revocar key temporalmente o cambiar a una inválida)
export OPENAI_API_KEY=sk-invalid-test
export LLM_BACKEND=openai_gpt4o_mini

python -m ml.consumer &
redis-cli XADD events:raw_wazuh '*' data '...'
# El consumer P1 debería loguear:
# ERROR:soar.decision_engine.consumer:llm classify failed; continuing without enrichment
# Y NO crashearse.

# Switch a Llama local
export LLM_BACKEND=llama_local
# Restart consumer ML — los nuevos eventos enriquecen con Llama.
```

| Check (4.2) | Esperado |
|-------------|----------|
| OpenAI down NO crashea ningún componente | sí |
| Switch a Llama sin tocar código (solo env var) | sí |
| Tiempo total de switch ≤ 30s | sí |

## 4.3 Pre-cache de embeddings

Antes del demo (T-1h), pre-calienta el modelo BGE y deja el HybridRetriever instanciado:

```bash
python - << 'PY'
from ml.rag.retriever import HybridRetriever
_ = HybridRetriever()  # carga modelo + índices
print("RAG retriever ready")
PY
# OUTPUT ESPERADO (primera vez):
# RAG retriever ready  (tras 5-15s)
```

Y mantén el proceso vivo (o usa un servidor que cargue una vez).

---

## ✅ Checklist Fase 4 — listo para demo

| # | Check | OK |
|---|-------|----|
| 1 | Burst test pasa con 50 events | ☐ |
| 2 | Failover OpenAI → Llama probado | ☐ |
| 3 | RAG pre-warmed antes del demo | ☐ |
| 4 | Métricas TP/FP registradas en `docs/LESSONS_LEARNED.md` | ☐ |
| 5 | Rehearsal con P1, P3 cerrado | ☐ |

---

# Apéndice A — Troubleshooting ML/LLM

### A.1 `sentence-transformers` descarga falla / lenta

```bash
# Usar HuggingFace mirror si tu conexión bloquea HF directo
export HF_ENDPOINT=https://hf-mirror.com
# O descarga manual del modelo a ~/.cache/huggingface/hub
```

### A.2 OpenAI `429 Rate limited`

Reduce `temperature` y/o agrega un sleep entre llamadas. Para el demo es improbable (1 incident a la vez) pero en burst tests sí ocurre.

### A.3 Llama responde no-JSON

A veces (Q4 quant) la salida está casi-JSON pero con un prefijo o sufijo. Usa `json.loads` con regex extractor:

```python
import re, json
m = re.search(r"\{.*\}", content, re.DOTALL)
parsed = json.loads(m.group(0)) if m else {}
```

### A.4 IsoForest predice todo como anomalía

Causa: `contamination` mal calibrado o features no escalados.

Fix: revisa que el `StandardScaler` se haya cargado (no entrenes uno nuevo en inferencia). Verifica `joblib.load(scaler.joblib)` y aplicar a TODOS los features.

### A.5 BM25 retorna scores cero

Causa: query tokenizada distinto a docs. Usa siempre `_tokenize` del index.

### A.6 Ollama "model not loaded"

```bash
ollama ps                                   # ¿modelo cargado?
ollama run llama3.1:8b-instruct-q4_K_M ""   # forzar carga
```

### A.7 Memoria insuficiente con BGE-large

Cambia a BGE-base (~400 MB) en `EMBED_MODEL = "BAAI/bge-base-en-v1.5"` y reconstruye índice. Pierdes ~3 puntos de calidad — aceptable para demo.

---

# Apéndice B — Comandos de emergencia

```bash
# Reentrenar modelos en frío (5 min)
python -m ml.data.synthetic_generator --benign 5000 --attack 200
python -m ml.anomaly.trainer --csv ml/data/synthetic.csv

# Reconstruir índice RAG (1-2 min)
python -m ml.rag.index

# Forzar Llama (sin tocar P1)
export LLM_BACKEND=llama_local && systemctl --user restart ml-consumer 2>/dev/null || pkill -f 'ml.consumer'

# Limpiar memoria si Ollama acapara
ollama stop llama3.1:8b-instruct-q4_K_M
ollama run llama3.1:8b-instruct-q4_K_M ""

# Resetear consumer group ML
redis-cli XGROUP DESTROY events:raw_wazuh ml-pipeline
redis-cli XGROUP CREATE events:raw_wazuh ml-pipeline 0 MKSTREAM
```

---

# Apéndice C — Referencias

| Cuando estés en... | Lee |
|--------------------|-----|
| `ml/anomaly/` | SAD §6.3 (Layer 2), ADR-0001 v2 |
| `ml/llm_triage/` | SAD §6.5 (Layer 4), ADR-0001 v2 |
| `ml/rag/` | SAD §6.5.2 (RAG), `docs/CONTEXT.md` Q3 |
| Calibración | `docs/CONTEXT.md` (Q3 protocol — semana 2) |

---

## Change log

| Versión | Fecha | Cambio | Autor |
|---------|-------|--------|-------|
| 2.0 | 2026-05-24 | Reorganización day-by-day → feature-based (Fase 1-4). Comandos completos, outputs esperados literales, checklists por sección, troubleshooting y emergencia. | P1 |
