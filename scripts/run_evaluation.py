from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidencekg.eval.evaluator import Evaluator
from evidencekg.io import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate EvidenceKG predictions.")
    parser.add_argument("--predicted", required=True)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--verified")
    args = parser.parse_args()

    report = Evaluator().evaluate(args.predicted, args.gold, args.verified)
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
