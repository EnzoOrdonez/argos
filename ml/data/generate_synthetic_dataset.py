"""Generate synthetic datasets for ARGOS Layer 2 evaluation.

Run from project root:

    python -m ml.data.generate_synthetic_dataset
"""

from __future__ import annotations

import json
from pathlib import Path


OUTPUT_DIR = Path("ml/data/synthetic")


def build_benign_rows(size: int = 100) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []

    for index in range(size):
        rows.append(
            {
                "label": 0,
                "file_write_rate": round(0.01 + (index % 5) * 0.003, 4),
                "avg_entropy": round(3.1 + (index % 7) * 0.10, 4),
                "extension_modification_ratio": round(0.02 + (index % 4) * 0.01, 4),
                "crypto_api_calls": index % 2,
                "new_outbound_connections": 1 if index % 13 == 0 else 0,
                "cpu_burst_score": round((index % 4) * 0.10, 4),
                "io_burst_score": round((index % 5) * 0.10, 4),
            }
        )

    return rows


def build_ransomware_like_rows(size: int = 30) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []

    for index in range(size):
        rows.append(
            {
                "label": 1,
                "file_write_rate": round(3.5 + (index % 5) * 0.45, 4),
                "avg_entropy": round(7.2 + (index % 6) * 0.10, 4),
                "extension_modification_ratio": round(0.70 + (index % 5) * 0.04, 4),
                "crypto_api_calls": 18 + (index % 8),
                "new_outbound_connections": 2 + (index % 4),
                "cpu_burst_score": round(5.0 + (index % 5) * 0.50, 4),
                "io_burst_score": round(6.0 + (index % 6) * 0.60, 4),
            }
        )

    return rows


def write_json(path: Path, rows: list[dict[str, float | int]]) -> None:
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    benign_rows = build_benign_rows()
    ransomware_like_rows = build_ransomware_like_rows()
    all_rows = benign_rows + ransomware_like_rows

    write_json(OUTPUT_DIR / "benign_windows.json", benign_rows)
    write_json(OUTPUT_DIR / "ransomware_like_windows.json", ransomware_like_rows)
    write_json(OUTPUT_DIR / "layer2_synthetic_dataset.json", all_rows)

    print(f"Wrote {len(benign_rows)} benign rows")
    print(f"Wrote {len(ransomware_like_rows)} ransomware-like rows")
    print(f"Wrote {len(all_rows)} total rows to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()