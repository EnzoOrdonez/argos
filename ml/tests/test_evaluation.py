from ml.evaluation.ablation import run_ablation_study
from ml.evaluation.metrics import (
    best_threshold_by_f1,
    evaluate_binary_detection,
    predict_labels,
    sweep_thresholds,
)
from ml.evaluation.mitre import build_mitre_coverage_report


def test_predict_labels_uses_threshold():
    scores = [0.10, 0.50, 0.74, 0.90]

    assert predict_labels(scores, threshold=0.74) == [0, 0, 1, 1]


def test_evaluate_binary_detection_returns_expected_metrics():
    y_true = [0, 0, 1, 1]
    y_score = [0.10, 0.20, 0.82, 0.95]

    metrics = evaluate_binary_detection(y_true, y_score, threshold=0.74)

    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1 == 1.0
    assert metrics.accuracy == 1.0
    assert metrics.true_positives == 2
    assert metrics.false_positives == 0
    assert metrics.true_negatives == 2
    assert metrics.false_negatives == 0


def test_sweep_thresholds_and_best_threshold_by_f1():
    y_true = [0, 0, 1, 1]
    y_score = [0.10, 0.20, 0.82, 0.95]

    results = sweep_thresholds(y_true, y_score, thresholds=[0.40, 0.74, 0.90])
    best = best_threshold_by_f1(results)

    assert len(results) == 3
    assert best.f1 == 1.0


def test_build_mitre_coverage_report():
    report = build_mitre_coverage_report(
        {
            "CU-01": {"T1486", "T1490", "T1083"},
            "CU-03": {"T1486", "T1562"},
        }
    )

    assert report.total_count == 6
    assert report.covered_count == 4
    assert report.coverage_ratio == 0.6667

    covered_ids = {
        technique.technique_id
        for technique in report.techniques
        if technique.covered
    }

    assert covered_ids == {"T1486", "T1490", "T1083", "T1562"}


def test_run_ablation_study():
    y_true = [0, 0, 1, 1]

    results = run_ablation_study(
        y_true,
        {
            "rules_only": [0.10, 0.20, 0.30, 0.95],
            "ml_only": [0.20, 0.30, 0.82, 0.90],
            "full_argos": [0.10, 0.20, 0.92, 0.98],
        },
        threshold=0.74,
    )

    assert len(results) == 3

    by_name = {result.configuration_name: result for result in results}

    assert by_name["rules_only"].metrics.recall == 0.5
    assert by_name["ml_only"].metrics.recall == 1.0
    assert by_name["full_argos"].metrics.f1 == 1.0
