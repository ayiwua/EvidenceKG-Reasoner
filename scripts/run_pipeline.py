from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidencekg.pipeline.runner import PipelineRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run EvidenceKG mock pipeline.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--stage", default="all", choices=["all", "candidates"])
    args = parser.parse_args()

    result = PipelineRunner().run(args.config, args.data_dir, args.output_dir, stage=args.stage)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
