# ARGOS Capa 2 — Detección de anomalías con ML

La Capa 2 implementa la ruta de detección de ransomware basada en anomalías para ARGOS.

Utiliza:

- Extracción de características a partir de ventanas de actividad de procesos.
- Entropía de Shannon sobre muestras de bytes de archivos.
- Isolation Forest.
- SVM de una clase.
- Puntuación ponderada por ensamble.
- Conversión de `MLScore` a señales de enrutamiento compatibles con SOAR.
- Evaluación sintética con precisión, recall, F1, cobertura MITRE y ablación.
- Registros seguros de instantáneas forenses simuladas.

## Módulos implementados

```text
ml/features/
  entropy.py
  extractor.py

ml/models/
  vectorizer.py
  ensemble.py

ml/evaluation/
  metrics.py
  mitre.py
  ablation.py

ml/forensics/
  snapshot.py

ml/demo/
  run_layer2_demo.py