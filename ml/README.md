# ml/ — Layer 2 (ML Anomaly Detection)

| Field | Value |
|-------|-------|
| Owner | **P2 · Sebastian Montenegro** (ML Engineer) |
| Status | 📅 Planned · Weeks 2-9 (Gate 1 baseline · Gate 2 ensemble · Gate 3 eval) |
| Related | [`docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md`](../docs/architecture/SOLUTION_ARCHITECTURE_DOCUMENT.md) §5.2, [`docs/use-cases/USE_CASES.md`](../docs/use-cases/USE_CASES.md) UC-03 (centerpiece), [`docs/decisions/OPEN_QUESTIONS_RESOLUTION.md`](../docs/decisions/OPEN_QUESTIONS_RESOLUTION.md) §Q5 (tier calibration) |

---

## Purpose

Layer 2 of the defense-in-depth stack. Unsupervised models trained on a benign baseline that flag deviations the Sigma rules can't catch. **Higher recall against novel variants, higher false-positive rate** — Layer 1 corroborates and Layer 3 acts as zero-FP confirmation.

This layer is the **centerpiece of UC-03** (novel variant + split-brain) — the only layer that fires in that scenario.

---

## Stack

| Tool | Role |
|------|------|
| scikit-learn 1.4+ | Isolation Forest + One-Class SVM |
| scipy | Shannon entropy computation |
| pandas | Feature engineering / EDA |
| redis-py | Stream consumer (alerts in) and publisher (scores out) |
| pytest + hypothesis | Unit tests + property-based tests for features |
| Pydantic v2 | I/O validation via `argos_contracts` |
| joblib | Model serialization with hash verification |
| matplotlib + seaborn | ROC curves + ablation plots for the informe |

---

## What lives here (planned)

```
ml/
├── README.md                   # This file
├── requirements.txt
├── features/
│   ├── extractor.py            # Per-process 60s window → MLFeatures
│   ├── entropy.py              # Shannon entropy of file writes
│   ├── crypto_calls.py         # CryptoAPI / OpenSSL hook detection
│   └── network.py              # New outbound connections counter
├── models/
│   ├── isolation_forest.py     # Training + scoring
│   ├── one_class_svm.py        # Training + scoring
│   ├── ensemble.py             # Ensemble logic (weighted average → MLScore)
│   └── artifacts/              # .joblib model files (signed hash, .gitignored)
├── consumer/
│   └── stream_consumer.py      # Redis subscriber → features → score → publish
├── notebooks/
│   ├── 01-eda-baseline.ipynb
│   ├── 02-feature-selection.ipynb
│   ├── 03-tier-calibration.ipynb   # ← deliverable for OPEN_QUESTIONS Q5
│   └── 04-ablation-rules-vs-ml.ipynb
└── tests/
    ├── test_features.py
    ├── test_models.py
    └── test_consumer_integration.py
```

---

## Contracts (`argos_contracts`)

This layer is the **first heavy consumer** of `argos_contracts`. Read-write data:

| Direction | Model | Notes |
|-----------|:-----:|-------|
| **Consumes** | `NormalizedAlert` | From Decision Engine via Redis stream |
| **Consumes** | `MLFeatures` | Internal computation, then validated via the Pydantic model before scoring |
| **Produces** | `MLScore` | Published back to Decision Engine — must include `isolation_forest_score`, `one_class_svm_score`, `ensemble_score`, the full `features` payload, and `model_version` |

Strict typing **at the boundary**: never publish a raw dict to Redis. Always serialize via `MLScore.model_dump_json()` so downstream gets schema validation for free.

---

## Feature spec (per SAD §5.2)

Per process, 60-second window:

| Feature | Type | Source |
|---------|------|--------|
| `file_write_rate` | float (writes/s) | Wazuh FIM events |
| `avg_entropy` | float (Shannon entropy 0-8) | Read first 4KB of each modified file |
| `extension_modification_ratio` | float (0-1) | Distinct extensions touched / total files |
| `crypto_api_calls` | int | Sysmon EventID 7 (image load) for `bcrypt.dll`, `crypt32.dll`; auditd hooks for OpenSSL |
| `new_outbound_connections` | int | Sysmon EventID 3 / auditd connect() syscall |
| `cpu_burst_score` | float | Standardized CPU% over window mean |
| `io_burst_score` | float | Standardized IOPS over window mean |

---

## How to run

```bash
cd ml/
pip install -r requirements.txt

# Train baseline (requires baseline log dataset from lab/ in W3-4)
python -m ml.models.isolation_forest --train --data data/baseline/ --out models/artifacts/iforest-v1.0.joblib

# Run consumer (requires Redis + lab/ up)
python -m ml.consumer.stream_consumer

# Tests
pytest tests/ -v

# Notebooks
jupyter lab notebooks/
```

---

## Tests

| Type | What it validates |
|------|-------------------|
| `test_features.py` | Each extractor produces correct value on synthetic events; `MLFeatures` validation rejects out-of-range values |
| `test_models.py` | Trained model produces score ∈ [0,1]; serialized + reloaded model gives identical scores; hash verification rejects tampered file |
| `test_consumer_integration.py` | End-to-end: synthetic `NormalizedAlert` in Redis stream → consumer reads → score published as `MLScore` |
| `notebooks/03-tier-calibration.ipynb` | Q5 protocol: precision-recall curve per layer + threshold-setting evidence for informe |

Target coverage: **≥50% line coverage** for feature extractors (SAD §13.5 tiered targets).

---

## Milestones by Gate

| Gate | Week | Deliverable |
|------|:----:|-------------|
| **Gate 1** | 5 | Isolation Forest trained on initial baseline (manual run), per-process scoring on synthetic alert produces sensible numbers |
| **Gate 2** | 7 | One-Class SVM + ensemble integrated; real-time consumer connected to Redis; FP rate measured |
| **Gate 3** | 9 | Full P/R/F1 per layer in `03-tier-calibration.ipynb`; Q5 protocol complete; ablation report (rules-only vs ML-only vs ensemble) |
| **Week 10-11** | — | Ablation + ROC curves polished for informe; concept drift detection cadence documented (F-011 mitigation) |

---

## Open dependencies

- **Baseline dataset (Week 3-4):** depends on `lab/` running normal user activity for 48h. Coordinate with P4.
- **Q5 calibration protocol:** P2 leads, P1 inputs on tier semantics. Deliverable: `notebooks/03-tier-calibration.ipynb` per `OPEN_QUESTIONS_RESOLUTION.md` §Q5.
- **UC-03 attack variant:** P4 builds the variant that evades Sigma; P2 ensures ML catches it (deliberate adversarial test).

---

## References

- SAD §5.2 (Layer 2 spec).
- USE_CASES UC-03 (centerpiece — ML is the only layer that fires).
- THREAT_MODEL.md §3.2 (T-012 model tampering, T-013 baseline contamination), §4.2 (F-010..013 ML failure modes).
- `OPEN_QUESTIONS_RESOLUTION.md` §Q5 (tier calibration protocol, P2 leads).
