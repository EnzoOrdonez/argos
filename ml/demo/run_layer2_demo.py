"""Console demo for ARGOS Layer 2.

Run from project root:

    python -m ml.demo.run_layer2_demo
"""

from __future__ import annotations

from argos_contracts.ml_score import MLFeatures

from ml.evaluation.ablation import run_ablation_study
from ml.evaluation.metrics import evaluate_binary_detection, sweep_thresholds
from ml.evaluation.mitre import build_mitre_coverage_report
from ml.models.ensemble import Layer2AnomalyEnsemble
from ml.soar_adapter import ml_score_to_normalized_alert, ml_score_to_routing_signal
from soar.decision_engine.tier_router import route
from ml.forensics.snapshot import build_forensic_snapshot_record


def build_benign_windows(size: int = 100) -> list[MLFeatures]:
    rows: list[MLFeatures] = []

    for index in range(size):
        rows.append(
            MLFeatures(
                file_write_rate=0.01 + (index % 5) * 0.003,
                avg_entropy=3.1 + (index % 7) * 0.10,
                extension_modification_ratio=0.02 + (index % 4) * 0.01,
                crypto_api_calls=index % 2,
                new_outbound_connections=1 if index % 13 == 0 else 0,
                cpu_burst_score=(index % 4) * 0.10,
                io_burst_score=(index % 5) * 0.10,
            )
        )

    return rows


def build_ransomware_like_window() -> MLFeatures:
    return MLFeatures(
        file_write_rate=5.0,
        avg_entropy=7.9,
        extension_modification_ratio=0.95,
        crypto_api_calls=30,
        new_outbound_connections=5,
        cpu_burst_score=8.0,
        io_burst_score=10.0,
    )


def format_tier(tier: object) -> str:
    return getattr(tier, "name", str(tier))


def main() -> None:
    print("=" * 72)
    print("ARGOS LAYER 2 DEMO")
    print("Isolation Forest + One-Class SVM + SOAR Routing")
    print("=" * 72)

    print("\n[1] Building benign synthetic training windows...")
    benign_windows = build_benign_windows(size=100)
    print(f"    Benign windows: {len(benign_windows)}")

    print("\n[2] Training Layer 2 anomaly ensemble...")
    model = Layer2AnomalyEnsemble().fit(benign_windows)
    print(f"    Model version: {model.model_version}")

    print("\n[3] Scoring ransomware-like activity window...")
    suspicious_features = build_ransomware_like_window()

    ml_score = model.predict_score(
        suspicious_features,
        host_id="WIN-VICTIM-01",
        process_id=4321,
        process_name="unknown.exe",
    )

    print(f"    Isolation Forest score : {ml_score.isolation_forest_score}")
    print(f"    One-Class SVM score    : {ml_score.one_class_svm_score}")
    print(f"    Ensemble score         : {ml_score.ensemble_score}")

    print("\n[4] Converting MLScore to SOAR-compatible alert...")
    alert = ml_score_to_normalized_alert(ml_score)

    print(f"    Alert ID       : {alert.alert_id}")
    print(f"    Source layer   : {alert.source_layer}")
    print(f"    Severity score : {alert.severity_score}")
    print(f"    Severity label : {alert.severity_label}")
    print(f"    MITRE technique: {alert.technique_mitre}")

    print("\n[5] Routing through SOAR tier router...")
    signal = ml_score_to_routing_signal(ml_score)
    tier = route(signal)

    print(f"    SOAR tier decision: {format_tier(tier)}")

    if format_tier(tier) == "T2":
        print("    Result: Human-in-the-loop approval required.")
    elif format_tier(tier) == "T0":
        print("    Result: Automatic response allowed.")
    else:
        print("    Result: Lower-priority triage path.")
        
    print("\n[5.1] Creating safe simulated forensic snapshot...")
    snapshot = build_forensic_snapshot_record(ml_score)

    print(f"    Snapshot ID   : {snapshot.snapshot_id}")
    print(f"    Snapshot type : {snapshot.snapshot_type}")
    print(f"    Storage path  : {snapshot.storage_path}")

    print("\n[6] Synthetic detection metrics...")
    y_true = [0, 0, 0, 1, 1]
    y_score = [0.10, 0.20, 0.30, ml_score.ensemble_score, 0.91]

    metrics = evaluate_binary_detection(y_true, y_score, threshold=0.74)

    print(f"    Threshold : {metrics.threshold}")
    print(f"    Precision : {metrics.precision}")
    print(f"    Recall    : {metrics.recall}")
    print(f"    F1-score  : {metrics.f1}")
    print(f"    Accuracy  : {metrics.accuracy}")
    print(
        "    Confusion : "
        f"TP={metrics.true_positives}, "
        f"FP={metrics.false_positives}, "
        f"TN={metrics.true_negatives}, "
        f"FN={metrics.false_negatives}"
    )

    print("\n[7] Threshold sweep...")
    for result in sweep_thresholds(y_true, y_score):
        print(
            f"    threshold={result.threshold:.2f} "
            f"precision={result.precision:.2f} "
            f"recall={result.recall:.2f} "
            f"f1={result.f1:.2f}"
        )

    print("\n[8] MITRE coverage report...")
    mitre_report = build_mitre_coverage_report(
        {
            "CU-01": {"T1486", "T1490", "T1083"},
            "CU-03": {"T1486", "T1562"},
        }
    )

    print(
        f"    Covered techniques: "
        f"{mitre_report.covered_count}/{mitre_report.total_count} "
        f"({mitre_report.coverage_ratio})"
    )

    print("\n[9] Ablation study...")
    ablation_results = run_ablation_study(
        y_true,
        {
            "rules_only": [0.10, 0.20, 0.30, 0.50, 0.95],
            "ml_only": [0.10, 0.20, 0.30, ml_score.ensemble_score, 0.91],
            "full_argos": [0.10, 0.20, 0.30, 0.94, 0.98],
        },
        threshold=0.74,
    )

    for result in ablation_results:
        print(
            f"    {result.configuration_name:<12} "
            f"precision={result.metrics.precision:.2f} "
            f"recall={result.metrics.recall:.2f} "
            f"f1={result.metrics.f1:.2f}"
        )

    print("\n" + "=" * 72)
    print("DEMO COMPLETED")
    print("=" * 72)


if __name__ == "__main__":
    main()