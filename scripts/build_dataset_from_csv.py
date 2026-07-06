from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidencekg.data.dataset_builder import DatasetBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build v2 EvidenceKG JSONL dataset from CSV files.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    summary = DatasetBuilder(args.manifest, args.raw_dir, args.out_dir).build()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
