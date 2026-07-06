from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidencekg.writeback import ReviewApplier


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply review decisions to pending edges.")
    parser.add_argument("--triples", required=True)
    parser.add_argument("--pending", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = ReviewApplier().apply(args.triples, args.pending, args.review, args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
