# Manual P2 — Sebastian Montenegro · ML + LLM Triage

| Campo | Valor |
|-------|-------|
| Rol | Owner de capas estadísticas e IA |
| Owns | Layer 2 — Isolation Forest + OC-SVM + Shannon entropy (`ml/`) · Layer 4 — LLM Triage + RAG (`ml/llm_triage/`, `ml/rag/`) |
| No owns | Sigma/Wazuh (P3) · Canary FIM (P3) · SOAR Decision Engine (P1) · Infra (P4) |
| Outputs blocking | `events:normalized` con `layer_origin=ml` y `layer_origin=llm` → consumido por P1 |
| Entrega final | **13 de junio de 2026** |

---

## 0. Tu charter

> Tus capas convierten señales débiles (un proceso raro, una secuencia de syscalls) en confianza numérica que el Tier Router de P1 pueda usar. Si tus modelos sobreajustan o tu LLM alucina, ARGOS pierde su mejor argumento de diferenciación frente a un SIEM tradicional.

### 0.1 Recursos requeridos

- Espacio disco: ~12 GB (Llama 3.1 8B Q4 ≈ 5 GB + BGE-large ≈ 1.4 GB + datasets + venv).
- RAM: 16 GB mínimo si vas a correr Llama local (8 GB efectivos para el modelo).
- GPU: opcional pero acelera Llama 10×. Sin GPU el CPU inference da ~3 tokens/s — suficiente para demo (incidents llegan de a uno).

### 0.2 Cómo leer cada sub-sección

Cada componente sigue: **Contexto** → **Pasos manuales** si aplica → **Comandos** → **Salida esperada** → **Verificación** → **Si algo falla**.

---

# Fase 1 — Cimientos

## 1.1 Prerequisites

### Comandos

```bash
python3 --version
docker --version
nvidia-smi 2>/dev/null && echo "GPU OK" || echo "No GPU - CPU mode"
free -h | head -2
df -h ~ | tail -1
```

### Salida esperada

```text
Python 3.11.7
Docker version 24.x.x
No GPU - CPU mode
              total  used  free  shared  buff/cache  available
Mem:           15Gi  6.0Gi 3.0Gi 400Mi   6.0Gi       8.0Gi
/dev/sda1     200G  150G  50G   75% /home/usuario
```

### Verificación

```verify
python3 -c "import sys; assert sys.version_info[:2]==(3,11); print('Python OK')"
docker ps >/dev/null && echo "Docker OK"
test $(df -BG ~ | tail -1 | awk '{print $4}' | tr -d 'G') -ge 15 && echo "Disco OK"
```

Esperado:

```text
Python OK
Docker OK
Disco OK
```

---

## 1.2 OpenAI API key

### Contexto

P1 ya creó la cuenta y la key. **No crees otra** — duplicarías el billing y complicarías la revocación. Tu paso es solo verificar que P1 te pasó la key y que funciona.

### Pasos manuales

1. Pide a P1 la `OPENAI_API_KEY` por canal privado (Signal/Telegram DM, NO Discord público).
2. Guárdala en tu `.env` local.

### Verificación

```verify
export OPENAI_API_KEY="sk-proj-xxxx"
curl -s https://api.openai.com/v1/models \
  -H "Authorization: Bearer ${OPENAI_API_KEY}" | jq '.data[0].id'
```

Esperado:

```text
"gpt-4o-mini-2024-07-18"
```

---

## 1.3 Instalar Ollama + Llama 3.1 8B (fallback)

### Contexto

Llama 3.1 8B corriendo local en Ollama es el _fallback_ a OpenAI. Es la diferencia entre "demo cae cuando WiFi del salón bloquea OpenAI" y "demo sigue funcionando". El switch entre uno y otro es una sola env var.

### Pasos manuales

1. Instalar Ollama (oneliner oficial):
   - Linux: el comando de abajo.
   - macOS: `brew install --cask ollama` (o descarga desde `https://ollama.com/download`).
   - Windows: descarga el instalador desde `https://ollama.com/download/windows`.
2. Verificar servicio.
3. Descargar el modelo (4.7 GB).
4. Smoke test.

### Comandos

```bash
curl -fsSL https://ollama.com/install.sh | sh

systemctl status ollama --no-pager
ollama pull llama3.1:8b-instruct-q4_K_M
ollama run llama3.1:8b-instruct-q4_K_M "Respond with one word: ARGOS"
```

### Salida esperada

```text
>>> The Ollama API is now available at 127.0.0.1:11434.

● ollama.service - Ollama Service
     Loaded: loaded (...; enabled; ...)
     Active: active (running) since ...

pulling manifest
pulling ... 100%
success

ARGOS
```

### Verificación

```verify
ollama list | grep llama3.1
curl -s http://localhost:11434/api/version | jq .version
```

Esperado:

```text
llama3.1:8b-instruct-q4_K_M    a8...   4.7 GB   ...
"0.1.x"
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `curl http://localhost:11434` da `Connection refused` | Servicio no arrancó | `sudo systemctl start ollama` o, en macOS, abrir la app de Ollama |
| `ollama pull` falla a la mitad | Red inestable | Reintenta — `ollama pull` reanuda desde el último chunk |
| Inferencia se cuelga > 30 s | RAM insuficiente | Usar modelo más chico: `ollama pull llama3.1:8b-instruct-q4_0` (3 GB) |

---

## 1.4 Clone repo + venv + deps ML

### Comandos

```bash
mkdir -p ~/code && cd ~/code
git clone git@github.com:EnzoOrdonez/argos.git
cd argos
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ./argos_contracts
pip install -r ml/requirements.txt
pytest ml/ -q
```

### Salida esperada

```text
Successfully installed argos_contracts-1.1.0 pydantic-2.x.x
Successfully installed scikit-learn-1.4.x scipy-1.12.x numpy-1.26.x pandas-2.2.x sentence-transformers-2.x rank-bm25-0.2.x httpx-0.27.x
........  [100%]
8 passed in 0.18s
```

### Verificación

```verify
python -c "import sklearn, scipy, numpy, sentence_transformers; print('imports OK')"
python -c "import argos_contracts; print(argos_contracts.__version__)"
```

Esperado:

```text
imports OK
1.1.0
```

---

## ✅ Checklist Fase 1

| # | Check | OK |
|---|-------|----|
| 1 | Python 3.11.x · Docker · ≥ 15 GB libre | ☐ |
| 2 | OpenAI key funciona | ☐ |
| 3 | Ollama corre y `llama3.1:8b-instruct-q4_K_M` listo | ☐ |
| 4 | Tests existentes ML pasan (8 passed) | ☐ |

---

# Fase 2 — Skeletons funcionales

## 2.1 Generar datasets sintéticos

### Contexto

Layer 2 necesita un baseline de comportamiento normal y ejemplos sintéticos de ransomware para validar que detecta. El lab real lo tendrás en Fase 3; aquí trabajas con datos generados.

### `ml/data/synthetic_generator.py`

```python
"""Generador sintético: eventos host-level benignos + ransomware."""

from __future__ import annotations
import argparse, csv, random
from pathlib import Path

random.seed(42)

BENIGN = [
    "chrome.exe", "code.exe", "explorer.exe", "svchost.exe",
    "spoolsv.exe", "outlook.exe", "winword.exe", "powershell.exe",
]
RANSOM = ["lockbit.exe", "encryptor.exe", "wmic.exe", "vssadmin.exe"]


def benign_row(t: int, host: str) -> dict:
    proc = random.choice(BENIGN)
    return dict(
        timestamp=t, host=host, pid=random.randint(1000, 9999), process=proc,
        syscalls_per_min=random.randint(50, 800),
        files_touched_per_min=random.randint(0, 30),
        entropy_of_written_bytes=round(random.uniform(2.0, 5.5), 3),
        network_kbps=random.randint(0, 200),
        parent_process="explorer.exe" if proc != "explorer.exe" else "userinit.exe",
        command_line_len=random.randint(20, 120),
    )


def ransom_row(t: int, host: str) -> dict:
    proc = random.choice(RANSOM)
    return dict(
        timestamp=t, host=host, pid=random.randint(1000, 9999), process=proc,
        syscalls_per_min=random.randint(3000, 9000),
        files_touched_per_min=random.randint(150, 1500),
        entropy_of_written_bytes=round(random.uniform(7.6, 7.99), 3),
        network_kbps=random.randint(0, 50),
        parent_process=random.choice(["cmd.exe", "powershell.exe"]),
        command_line_len=random.randint(80, 600),
    )


def generate(n_benign: int, n_attack: int, out: Path) -> None:
    rows = [(benign_row(t, "WIN-VICTIM-01"), 0) for t in range(n_benign)]
    rows += [(ransom_row(n_benign + t, "WIN-VICTIM-01"), 1) for t in range(n_attack)]
    random.shuffle(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0][0].keys()) + ["label"])
        w.writeheader()
        for row, label in rows:
            row["label"] = label
            w.writerow(row)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--benign", type=int, default=5000)
    p.add_argument("--attack", type=int, default=200)
    p.add_argument("--out", type=Path, default=Path("ml/data/synthetic.csv"))
    a = p.parse_args()
    generate(a.benign, a.attack, a.out)
    print(f"wrote {a.out} (benign={a.benign}, attack={a.attack})")
```

### Comandos

```bash
python -m ml.data.synthetic_generator --benign 5000 --attack 200
wc -l ml/data/synthetic.csv
```

### Salida esperada

```text
wrote ml/data/synthetic.csv (benign=5000, attack=200)
5201 ml/data/synthetic.csv
```

### Verificación

```verify
head -1 ml/data/synthetic.csv | tr ',' '\n' | wc -l
test $(wc -l < ml/data/synthetic.csv) -eq 5201 && echo "row count OK"
```

Esperado:

```text
11
row count OK
```

---

## 2.2 Layer 2 — Isolation Forest + One-Class SVM

### Contexto

Dos detectores de anomalía complementarios entrenados sobre el baseline (label=0). Cualquier punto que ambos consideren anómalo es candidato fuerte. La intersección es más específica; la unión más sensible. Reportamos ambos al SOAR.

### `ml/anomaly/trainer.py`

```python
"""Entrena IsolationForest + OneClassSVM sobre features numéricas del baseline."""

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
    iso = IsolationForest(n_estimators=200, contamination=0.01,
                          random_state=42, n_jobs=-1).fit(X)
    svm = OneClassSVM(kernel="rbf", gamma="scale", nu=0.01).fit(X)
    joblib.dump(scaler, MODELS_DIR / "scaler.joblib")
    joblib.dump(iso,    MODELS_DIR / "iso_forest.joblib")
    joblib.dump(svm,    MODELS_DIR / "oc_svm.joblib")
    print(f"trained on {len(benign)} benign samples")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, default=Path("ml/data/synthetic.csv"))
    train(p.parse_args().csv)
```

### `ml/anomaly/scorer.py`

```python
"""Inferencia: AnomalyScore por evento."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import joblib
import numpy as np

from ml.anomaly.trainer import FEATURES, MODELS_DIR


@dataclass(frozen=True)
class AnomalyScore:
    iso_score: float
    svm_score: float
    is_anomaly: bool
    confidence: float


class AnomalyScorer:
    def __init__(self, scaler, iso, svm):
        self._scaler = scaler
        self._iso = iso
        self._svm = svm

    @classmethod
    def load(cls, models_dir: Path = MODELS_DIR) -> "AnomalyScorer":
        return cls(
            scaler=joblib.load(models_dir / "scaler.joblib"),
            iso=joblib.load(models_dir / "iso_forest.joblib"),
            svm=joblib.load(models_dir / "oc_svm.joblib"),
        )

    def score(self, features: dict) -> AnomalyScore:
        vec = np.array([[features[f] for f in FEATURES]])
        x = self._scaler.transform(vec)
        iso_s = float(self._iso.decision_function(x)[0])
        svm_s = float(self._svm.decision_function(x)[0])
        is_anom = (iso_s < 0) and (svm_s < 0)
        norm = max(abs(iso_s), abs(svm_s), 0.001)
        conf = min(1.0, norm * 1.3) if is_anom else 0.0
        return AnomalyScore(iso_s, svm_s, is_anom, conf)
```

### Comandos

```bash
python -m ml.anomaly.trainer --csv ml/data/synthetic.csv
ls -la ml/anomaly/models/
```

### Salida esperada

```text
trained on 5000 benign samples

-rw-r--r-- ... iso_forest.joblib   (~2-3 MB)
-rw-r--r-- ... oc_svm.joblib       (~500 KB - 1 MB)
-rw-r--r-- ... scaler.joblib       (~1 KB)
```

### Verificación

```verify
python - << 'PY'
import pandas as pd
from ml.anomaly.scorer import AnomalyScorer
from ml.anomaly.trainer import FEATURES

df = pd.read_csv("ml/data/synthetic.csv")
attacks = df[df["label"] == 1]
benign  = df[df["label"] == 0].sample(200, random_state=0)
s = AnomalyScorer.load()

tp = sum(s.score(dict(zip(FEATURES, [r[f] for f in FEATURES]))).is_anomaly for r in attacks.itertuples(index=False))
fp = sum(s.score(dict(zip(FEATURES, [r[f] for f in FEATURES]))).is_anomaly for r in benign.itertuples(index=False))
print(f"TP rate: {tp}/200 = {tp/200:.1%}")
print(f"FP rate: {fp}/200 = {fp/200:.1%}")
assert tp/200 >= 0.85, "TP rate bajo"
assert fp/200 <= 0.05, "FP rate alto"
print("anomaly OK")
PY
```

Esperado (aproximado, depende de seed):

```text
TP rate: 185/200 = 92.5%
FP rate: 6/200 = 3.0%
anomaly OK
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| TP < 85 % | Dataset poco contrastado o modelo mal calibrado | Re-generar dataset con seed diferente o subir `n_estimators=400` |
| FP > 10 % | `contamination` muy alta | Bajar `contamination=0.005` en el trainer |
| `FileNotFoundError: scaler.joblib` | Olvidaste entrenar | `python -m ml.anomaly.trainer --csv ml/data/synthetic.csv` |

---

## 2.3 Layer 2 — Shannon entropy

### Contexto

Señal complementaria barata. Ransomware cifra → bytes parecen aleatorios → entropía → ~8.0. Software legítimo escribe formatos estructurados → entropía 4-6.

### `ml/entropy/shannon.py`

```python
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
    if entropy >= 7.5: return "encrypted_or_random"
    if entropy >= 6.5: return "compressed"
    if entropy >= 4.5: return "structured_text_or_binary"
    return "low_entropy"
```

### Tests completos

```python
# ml/entropy/tests/test_shannon.py
import os
import pytest
from ml.entropy.shannon import shannon_entropy, classify_write


def test_empty():
    assert shannon_entropy(b"") == 0.0


def test_single_byte_value():
    assert shannon_entropy(b"\x00" * 1000) == pytest.approx(0.0)


def test_uniform_near_max():
    data = bytes(range(256)) * 4
    assert shannon_entropy(data) == pytest.approx(8.0, abs=0.01)


def test_random_bytes_close_to_8():
    assert shannon_entropy(os.urandom(8192)) > 7.9


def test_ascii_text_lower():
    text = b"the quick brown fox jumps over the lazy dog " * 200
    assert 4.0 < shannon_entropy(text) < 5.0


def test_classify_buckets():
    assert classify_write(7.9) == "encrypted_or_random"
    assert classify_write(6.9) == "compressed"
    assert classify_write(5.0) == "structured_text_or_binary"
    assert classify_write(2.0) == "low_entropy"
```

### Verificación

```verify
pytest ml/entropy/tests/ -v
```

Esperado:

```text
test_shannon.py::test_empty                         PASSED
test_shannon.py::test_single_byte_value             PASSED
test_shannon.py::test_uniform_near_max              PASSED
test_shannon.py::test_random_bytes_close_to_8       PASSED
test_shannon.py::test_ascii_text_lower              PASSED
test_shannon.py::test_classify_buckets              PASSED
======================= 6 passed in 0.05s =======================
```

---

## 2.4 Layer 4 — Cliente LLM dual (OpenAI + Llama)

### Contexto

Interfaz `LLMClient` con dos implementaciones intercambiables vía `LLM_BACKEND`. El consumer no sabe cuál usa.

### `ml/llm_triage/client.py`

```python
"""Cliente LLM unificado: OpenAI primario, Llama local fallback."""

from __future__ import annotations
import os, time, json
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
                 model: str = "gpt-4o-mini", timeout: float = 10.0):
        self._key   = api_key or os.environ["OPENAI_API_KEY"]
        self._model = model
        self._http  = httpx.AsyncClient(timeout=timeout)

    async def classify(self, prompt: str) -> LLMVerdict:
        t0 = time.monotonic()
        r = await self._http.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system",
                     "content": "You are a SOC analyst. Respond with strict JSON: "
                                "{\"label\":\"malicious|benign|uncertain\","
                                "\"confidence\":0.0..1.0,\"reasoning\":\"...\"}"},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            },
        )
        r.raise_for_status()
        parsed = json.loads(r.json()["choices"][0]["message"]["content"])
        return LLMVerdict(
            label=parsed["label"], confidence=float(parsed["confidence"]),
            reasoning=parsed["reasoning"], backend="openai_gpt4o_mini",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


class OllamaClient(LLMClient):
    def __init__(self, model: str = "llama3.1:8b-instruct-q4_K_M",
                 base_url: str = "http://localhost:11434",
                 timeout: float = 30.0):
        self._model = model
        self._url   = base_url
        self._http  = httpx.AsyncClient(timeout=timeout)

    async def classify(self, prompt: str) -> LLMVerdict:
        t0 = time.monotonic()
        r = await self._http.post(
            f"{self._url}/api/chat",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system",
                     "content": "Respond JSON only: "
                                "{\"label\":..., \"confidence\":..., \"reasoning\":...}"},
                    {"role": "user", "content": prompt},
                ],
                "format": "json", "stream": False,
                "options": {"temperature": 0.0},
            },
        )
        r.raise_for_status()
        parsed = json.loads(r.json()["message"]["content"])
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

### Verificación OpenAI

```verify
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
    print(v.label, v.confidence, v.backend, f"{v.latency_ms}ms")
asyncio.run(main())
PY
```

Esperado:

```text
malicious 0.95 openai_gpt4o_mini 687ms
```

### Verificación Llama

```verify
export LLM_BACKEND=llama_local
python - << 'PY'
import asyncio
from ml.llm_triage.client import make_client

async def main():
    c = make_client()
    v = await c.classify("Same prompt as above.")
    print(v.label, v.confidence, v.backend, f"{v.latency_ms}ms")
asyncio.run(main())
PY
```

Esperado (con GPU):

```text
malicious 0.92 llama_local 1200ms
```

Sin GPU el `latency_ms` puede ser ~4500.

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `401 Unauthorized` (OpenAI) | Key inválida | Revisa `.env`, vuelve a copiar del dashboard |
| `429 Rate limited` | Demasiadas llamadas | Solo durante burst tests; para demo es improbable |
| Llama responde no-JSON | Q4 quant a veces produce prefijos | Wrap con regex: `re.search(r"\{.*\}", content, re.DOTALL)` |
| `Connection refused 11434` | Ollama no corre | `sudo systemctl start ollama` |

---

## 2.5 Layer 4 — RAG (BM25 + BGE-large + RRF)

### Contexto

Antes de pasar la alerta cruda al LLM, recuperar 3-5 documentos relevantes (definiciones MITRE, runbook, variantes históricas) y inyectarlos como contexto. Reduce alucinación y mejora confidence.

Decisión (ADR-0001 v2): **sin cross-encoder reranker**. BM25 + BGE-large + RRF (Reciprocal Rank Fusion) es suficiente para el corpus pequeño que tenemos.

### `ml/rag/index.py`

```python
"""Indexa corpus markdown para BM25 + BGE."""

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
    source: str
    title: str
    text: str


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def load_corpus() -> list[Doc]:
    docs = []
    for md in CORPUS_ROOT.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip() if text else md.stem
        docs.append(Doc(id=str(md.relative_to(CORPUS_ROOT)),
                        source=md.parent.name, title=title, text=text))
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

### `ml/rag/retriever.py`

```python
"""Retriever híbrido BM25 + denso, fusión con Reciprocal Rank Fusion."""

from __future__ import annotations
import json, pickle
from typing import Iterable

import numpy as np
from sentence_transformers import SentenceTransformer

from ml.rag.index import INDEX_DIR, EMBED_MODEL, Doc, _tokenize

RRF_K = 60


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
        bm25_scores = self._bm25.get_scores(_tokenize(query))
        bm25_rank = list(np.argsort(bm25_scores)[::-1])
        qv = self._model.encode([query], normalize_embeddings=True)[0]
        dense_scores = self._embeds @ qv
        dense_rank = list(np.argsort(dense_scores)[::-1])
        fused = _rrf([bm25_rank[:30], dense_rank[:30]])
        return [self._docs[idx] for idx, _ in fused[:k]]
```

### Pasos manuales — poblar el corpus

1. Crea estructura:

```bash
mkdir -p ml/rag/corpus/mitre ml/rag/corpus/runbook ml/rag/corpus/variants
```

2. Para cada técnica MITRE relevante (T1486, T1490, T1083, T1190, T1498, T1499), crea un archivo `ml/rag/corpus/mitre/<técnica>.md` con: título, descripción tomada de attack.mitre.org, ejemplos comunes.
3. Para runbooks, crea `ml/rag/corpus/runbook/<nombre>.md` con instrucciones del equipo SOC.
4. Para variantes históricas, crea `ml/rag/corpus/variants/<familia>.md` (LockBit, Conti, REvil, etc.) con descripciones técnicas.

### Comandos (corpus de smoke test)

```bash
mkdir -p ml/rag/corpus/mitre ml/rag/corpus/runbook
cat > ml/rag/corpus/mitre/T1486.md << 'EOF'
# T1486 — Data Encrypted for Impact

Adversaries may encrypt data on target systems or large numbers of systems in
a network to interrupt availability. Ransomware families commonly observed:
LockBit, Conti, REvil, Ryuk, BlackCat.

Indicators: high file-write entropy (~8.0), mass file rename to .locked extension,
deletion of volume shadow copies via vssadmin.
EOF

cat > ml/rag/corpus/runbook/ransomware_response.md << 'EOF'
# Runbook — Ransomware response

If file-write entropy > 7.5 AND files_touched_per_min > 100, isolate host
immediately. Do NOT wait for confirmation; encryption is destructive and fast.

Steps:
1. Trigger Wazuh active-response to disable host network.
2. Snapshot memory if forensics capability available.
3. Notify SOC manager via Telegram + Discord.
EOF

python -m ml.rag.index
```

### Salida esperada

(Primera vez descarga BGE-large, puede tomar 1-2 min):

```text
indexed 2 docs (BM25 + BGE-1024d)
```

### Verificación

```verify
python - << 'PY'
from ml.rag.retriever import HybridRetriever
r = HybridRetriever()
for d in r.retrieve("Process encrypting files in bulk", k=2):
    print(d.id, "→", d.title)
PY
```

Esperado:

```text
mitre/T1486.md → T1486 — Data Encrypted for Impact
runbook/ransomware_response.md → Runbook — Ransomware response
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| `corpus vacío` | No hay archivos `.md` en `corpus/` | Agrega al menos 1 archivo `.md` en `ml/rag/corpus/<algo>/` |
| Descarga BGE muy lenta | Conexión a HuggingFace bloqueada | `export HF_ENDPOINT=https://hf-mirror.com` |
| Memoria insuficiente con BGE-large | RAM limitada | Cambia a `BAAI/bge-base-en-v1.5` (~400 MB) en `EMBED_MODEL` |

---

## 2.6 Layer 4 — Triage end-to-end

### `ml/llm_triage/triage.py`

```python
"""Ensambla: evento → prompt con contexto RAG → LLM → LLMVerdict."""

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
    docs = _retriever().retrieve(f"{event.mitre_technique} {event.host}", k=4)
    prompt = _build_prompt(event, docs)
    return await _client().classify(prompt)
```

### Y exporta:

```python
# ml/llm_triage/__init__.py
from ml.llm_triage.triage import classify
__all__ = ["classify"]
```

### Verificación

```verify
python - << 'PY'
import asyncio
from argos_contracts.incident import NormalizedEvent
from argos_contracts.enums import Severity
from ml.llm_triage import classify

evt = NormalizedEvent(
    event_id="evt-llm-001", severity=Severity.MEDIUM,
    mitre_technique="T1486", num_layers_fired=2, confidence_score=0.71,
    host="WIN-VICTIM-01", layer_origin="sigma",
)
v = asyncio.run(classify(evt))
print(v.label, v.confidence, v.backend, f"{v.latency_ms}ms")
PY
```

Esperado:

```text
malicious 0.93 openai_gpt4o_mini 750ms
```

---

## ✅ Checklist Fase 2

| # | Check | OK |
|---|-------|----|
| 1 | Synthetic dataset (5201 filas) | ☐ |
| 2 | 3 modelos `.joblib` entrenados | ☐ |
| 3 | TP ≥ 85 %, FP ≤ 5 % | ☐ |
| 4 | Shannon entropy: 6 tests passed | ☐ |
| 5 | OpenAI client devuelve verdict | ☐ |
| 6 | Llama client devuelve verdict | ☐ |
| 7 | RAG indexa corpus y recupera por similaridad | ☐ |
| 8 | `classify(event)` end-to-end < 2 s con OpenAI | ☐ |
| 9 | `pytest ml/ -q` → ≥ 20 passed | ☐ |

---

# Fase 3 — Integración real

## 3.1 Consumer del stream `events:raw_wazuh` → emite `events:normalized`

### Contexto

Te suscribes al stream que P3 emite desde Wazuh (`events:raw_wazuh`). Para cada evento computas features, corres Layer 2, opcionalmente Layer 4, y emites `NormalizedEvent` al stream que P1 consume.

### `ml/consumer.py`

```python
"""Pipeline ML: raw Wazuh event → features → Layer 2 + (opcional) Layer 4 → normalized."""

from __future__ import annotations
import asyncio, json, logging, os, uuid
import redis.asyncio as redis

from argos_contracts.enums import Severity
from argos_contracts.incident import NormalizedEvent
from ml.anomaly.scorer import AnomalyScorer

logger = logging.getLogger(__name__)

IN_STREAM  = "events:raw_wazuh"
OUT_STREAM = "events:normalized"
GROUP      = "ml-pipeline"
CONSUMER   = os.environ.get("ML_CONSUMER_NAME", "ml-1")

_scorer = AnomalyScorer.load()


def _features_from_wazuh(evt: dict) -> dict:
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
        return
    norm = NormalizedEvent(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        severity=Severity.MEDIUM if score.confidence < 0.85 else Severity.HIGH,
        mitre_technique=evt.get("mitre_technique", "Unknown"),
        num_layers_fired=1,
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
        resp = await r.xreadgroup(GROUP, CONSUMER, {IN_STREAM: ">"}, count=10, block=5000)
        for _, entries in resp or []:
            for entry_id, fields in entries:
                try:
                    await _process(r, fields)
                    await r.xack(IN_STREAM, GROUP, entry_id)
                except Exception:  # noqa: BLE001
                    logger.exception("failed to process %s", entry_id)


if __name__ == "__main__":
    asyncio.run(run())
```

### Comandos

```bash
# Terminal A
python -m ml.consumer

# Terminal B (inyectar evento Wazuh simulado)
redis-cli XADD events:raw_wazuh '*' data \
  '{"host":"WIN-VICTIM-01","mitre_technique":"T1486","syscalls_per_min":5500,"files_touched_per_min":800,"entropy_of_written_bytes":7.85,"network_kbps":10,"command_line":"powershell.exe -enc xxxxxx"}'
```

### Salida esperada (terminal A)

```text
INFO:ml.consumer:ml emit evt-abc123 host=WIN-VICTIM-01 conf=0.93
```

### Verificación

```verify
redis-cli XLEN events:normalized
redis-cli XREVRANGE events:normalized + - COUNT 1
```

Esperado (XLEN ≥ 1, último elemento es JSON con `event_id`, `confidence_score`, `host`):

```text
1
1) 1) "1234-0"
   2) 1) "data"
      2) "{\"event_id\":\"evt-abc123\",\"severity\":\"HIGH\",...}"
```

### Si algo falla

| Síntoma | Causa | Fix |
|---------|-------|-----|
| Consumer no emite nada | Evento no pasa `is_anomaly` | Inyecta evento con `entropy=7.9` y `files_touched=1000` |
| `joblib.load` falla | Modelos no entrenados | `python -m ml.anomaly.trainer --csv ml/data/synthetic.csv` |
| `BUSYGROUP` warning | Grupo ya existe | Ignorar — el código lo maneja |

---

## 3.2 Smoke end-to-end con P1

Coordina con P1 una corrida conjunta: él levanta su consumer SOAR, tú tu consumer ML, P3 (o tú con un comando manual) inyecta a `events:raw_wazuh`. Verifica que `incident:*` aparece en Redis y la notif llega a Telegram con `layer_origin=ml` en los logs.

### Verificación

```verify
redis-cli KEYS 'incident:*' | head -5
redis-cli GET $(redis-cli KEYS 'incident:*' | tail -1) | jq '.llm_verdict.label, .llm_verdict.backend'
```

Esperado (para un T2):

```text
incident:inc-abc123def456
"malicious"
"openai_gpt4o_mini"
```

---

## ✅ Checklist Fase 3

| # | Check | OK |
|---|-------|----|
| 1 | ML consumer corre y procesa stream | ☐ |
| 2 | Emisión solo cuando `is_anomaly` | ☐ |
| 3 | Integración con P1 verificada end-to-end | ☐ |
| 4 | `llm_verdict` poblado para T2 | ☐ |
| 5 | Audit log (P1) refleja `layer_origin=ml` | ☐ |

---

# Fase 4 — Rehearsal y polish

## 4.1 Rehearsal de carga

### Comandos

```bash
for i in $(seq 1 50); do
  redis-cli XADD events:raw_wazuh '*' data \
    "{\"host\":\"WIN-VICTIM-01\",\"mitre_technique\":\"T1486\",\"syscalls_per_min\":$((RANDOM % 5000 + 1000)),\"files_touched_per_min\":$((RANDOM % 800 + 100)),\"entropy_of_written_bytes\":7.8,\"network_kbps\":5,\"command_line\":\"x\"}" > /dev/null
done
sleep 5
redis-cli XLEN events:normalized
```

### Verificación

```verify
test $(redis-cli XLEN events:normalized) -ge 30 && echo "throughput OK"
ps -o rss= -p $(pgrep -f 'ml.consumer') | awk '{print "ML RSS: "$1/1024" MB"}'
```

Esperado:

```text
throughput OK
ML RSS: 480 MB
```

(Memoria estable entre antes y después del burst = no leak.)

---

## 4.2 Failover OpenAI → Llama

### Pasos manuales

1. Simular OpenAI caído invalidando la key:
   ```bash
   export OPENAI_API_KEY=sk-invalid-test
   ```
2. Inyectar un evento T2 al stream. El consumer P1 debería loguear `llm classify failed; continuing without enrichment` y NO crashear.
3. Switch a Llama:
   ```bash
   export LLM_BACKEND=llama_local
   ```
4. Reinicia ML consumer. Los siguientes eventos enriquecen con Llama.

### Verificación

```verify
# Después del switch:
redis-cli XADD events:raw_wazuh '*' data '{"host":"WIN-VICTIM-01","mitre_technique":"T1486","syscalls_per_min":5000,"files_touched_per_min":500,"entropy_of_written_bytes":7.8,"network_kbps":5,"command_line":"x"}'
sleep 5
redis-cli GET $(redis-cli KEYS 'incident:*' | tail -1) | jq '.llm_verdict.backend'
```

Esperado:

```text
"llama_local"
```

---

## 4.3 Pre-cache de embeddings (T-1h del demo)

### Comandos

```bash
python - << 'PY'
from ml.rag.retriever import HybridRetriever
_ = HybridRetriever()
print("RAG retriever ready")
PY
```

### Salida esperada (primera vez)

```text
RAG retriever ready
```

(Tras 5-15 s.)

Mantén el proceso vivo durante el demo o expone como servicio con `uvicorn`.

---

## ✅ Checklist Fase 4

| # | Check | OK |
|---|-------|----|
| 1 | Burst test 50 eventos en ≤ 3 s | ☐ |
| 2 | Failover OpenAI → Llama probado | ☐ |
| 3 | RAG pre-warmed antes del demo | ☐ |
| 4 | TP/FP registrados en `docs/LESSONS_LEARNED.md` | ☐ |
| 5 | Rehearsal con P1 y P3 cerrado | ☐ |

---

# Apéndice A — Troubleshooting

| # | Síntoma | Diagnóstico | Fix |
|---|---------|-------------|-----|
| A.1 | `sentence-transformers` descarga falla | HuggingFace bloqueado | `export HF_ENDPOINT=https://hf-mirror.com` |
| A.2 | OpenAI `429` | Rate limit | Bajar concurrencia; para demo no aplica |
| A.3 | Llama responde no-JSON | Q4 prefijos | Regex extractor `re.search(r"\{.*\}", content, re.DOTALL)` |
| A.4 | IsoForest predice todo como anomalía | Scaler no cargado en inferencia | Carga `joblib.load(scaler.joblib)` y aplica a TODOS los features |
| A.5 | BM25 scores cero | Query tokenizada distinto | Usa `_tokenize` del módulo `index` |
| A.6 | Ollama "model not loaded" | Modelo descargado pero no cargado | `ollama run llama3.1:8b-instruct-q4_K_M ""` para forzar carga |
| A.7 | Memoria insuficiente con BGE-large | RAM limitada | Cambia a BGE-base (~400 MB) en `EMBED_MODEL` |

---

# Apéndice B — Comandos de emergencia

```bash
# Reentrenar modelos en frío (~5 min)
python -m ml.data.synthetic_generator --benign 5000 --attack 200
python -m ml.anomaly.trainer --csv ml/data/synthetic.csv

# Reconstruir índice RAG (1-2 min)
python -m ml.rag.index

# Forzar Llama (sin tocar P1)
export LLM_BACKEND=llama_local
pkill -f 'ml.consumer' && nohup python -m ml.consumer > /tmp/ml.log 2>&1 &

# Liberar memoria si Ollama acapara
ollama stop llama3.1:8b-instruct-q4_K_M

# Resetear consumer group ML
redis-cli XGROUP DESTROY events:raw_wazuh ml-pipeline
redis-cli XGROUP CREATE events:raw_wazuh ml-pipeline 0 MKSTREAM
```

---

# Apéndice C — Referencias cruzadas

| Cuando estés en... | Lee |
|--------------------|-----|
| `ml/anomaly/` | SAD §6.3, ADR-0001 v2 |
| `ml/llm_triage/` | SAD §6.5, ADR-0001 v2 |
| `ml/rag/` | SAD §6.5.2, `docs/CONTEXT.md` |
| Calibración Q5 (post-demo) | `docs/CONTEXT.md` Q3 |

---

## Change log

| Versión | Fecha | Cambio |
|---------|-------|--------|
| 3.0 | 2026-05-24 | Reestructurado: Contexto → Pasos manuales → Comandos → Salida → Verificación → Si algo falla. Bloques bash listos para copy buttons. Sin referencias temporales. Renombrado de `sprint-week-1-p2-sebastian.md`. |
