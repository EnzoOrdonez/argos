"""Console demo for ARGOS Layer 2.

This script demonstrates the Layer 2 MVP flow:

1. Build benign synthetic windows.
2. Train Isolation Forest + One-Class SVM.
3. Score a ransomware-like synthetic activity window.
4. Convert MLScore into a SOAR-compatible RoutingSignal.
5. Route the signal through the SOAR tier router.
6. Print evaluation metrics, threshold sweep, MITRE coverage and ablation.

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
from soar.response.forensics.collector import collect_forensic_bundle
from soar.response.forensics.velociraptor_collector import collect_with_velociraptor


def build_benign_windows(size: int = 100) -> list[MLFeatures]:
    """Create synthetic benign activity windows for demo training."""
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
    """Create one synthetic ransomware-like activity window."""
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
    """Safely format enum-like tier values."""
    return getattr(tier, "name", str(tier))


def main() -> None:
    print("=" * 78)
    print("ARGOS LAYER 2 MVP DEMO")
    print("Isolation Forest + One-Class SVM + SOAR Routing")
    print("=" * 78)

    print("\n[1] Building benign synthetic training windows...")
    benign_windows = build_benign_windows(size=100)
    print(f"    Benign windows generated: {len(benign_windows)}")

    print("\n[2] Training Layer 2 anomaly ensemble...")
    model = Layer2AnomalyEnsemble().fit(benign_windows)
    print(f"    Model version: {model.model_version}")

    print("\n[3] Scoring ransomware-like synthetic activity window...")
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

    print(f"    Alert ID        : {alert.alert_id}")
    print(f"    Source layer    : {alert.source_layer}")
    print(f"    Host ID         : {alert.host_id}")
    print(f"    Severity score  : {alert.severity_score}")
    print(f"    Severity label  : {alert.severity_label}")
    print(f"    Triggering rule : {alert.triggering_rule}")
    print(f"    MITRE technique : {alert.technique_mitre}")

    print("\n[5] Routing through SOAR tier router...")
    signal = ml_score_to_routing_signal(ml_score)
    tier = route(signal)
    tier_name = format_tier(tier)

    print(f"    SOAR tier decision: {tier_name}")

    if tier_name == "T2":
        print("    Result: Human-in-the-loop approval required.")
    elif tier_name == "T0":
        print("    Result: Automatic response allowed.")
    else:
        print("    Result: Lower-priority triage path.")

    print("\n[5.1] Creating lightweight forensic evidence bundle...")

    forensic_result = collect_forensic_bundle(
        incident_id="INC-DEMO-L2-001",
        ml_score=ml_score,
        tier=tier_name,
        normalized_alert=alert,
        decision_metadata={
            "source": "ml.demo.run_layer2_demo",
            "reason": "Layer 2 anomaly score routed by SOAR tier router",
            "ensemble_score": ml_score.ensemble_score,
        },
        monitored_dirs=["ml"],
        output_root="evidence",
    )

    print(f"    Evidence directory : {forensic_result.evidence_dir}")
    print(f"    Evidence ID        : {forensic_result.manifest.evidence_id}")
    print(f"    Artifacts captured : {len(forensic_result.manifest.artifacts)}")

    print("\n[5.2] Preparing Velociraptor forensic collection request...")

    try:
        velociraptor_result = collect_with_velociraptor(
    incident_id="INC-DEMO-L2-001",
    host_id=ml_score.host_id,
    host_map_path="config/velociraptor_hosts.json",
    api_config_path="config/api.config.yaml",
    velociraptor_binary="C:/Velociraptor/velociraptor.exe",
    output_root="evidence",
    artifacts=["Generic.Client.Info"],
    dry_run=False,
)

        print(f"    Velociraptor client ID : {velociraptor_result.client_id}")
        print(f"    Collection status      : {velociraptor_result.status}")
        print(f"    Artifacts requested    : {len(velociraptor_result.artifacts)}")
        print(f"    Output directory       : {velociraptor_result.output_dir}")

    except Exception as error:
        print("    Velociraptor collection request was skipped.")
        print(f"    Reason: {error}")

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

    print("\n[7] Threshold sweep for MVP calibration...")
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

    for technique in mitre_report.techniques:
        status = "covered" if technique.covered else "not covered"
        cases = ", ".join(technique.supporting_cases) or "-"
        print(
            f"    {technique.technique_id} | "
            f"{technique.name} | "
            f"{status} | "
            f"cases={cases}"
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

    print("\n" + "=" * 78)
    print("DEMO COMPLETED")
    print("=" * 78)


if __name__ == "__main__":
    main()
