from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidencekg.data.redocred_adapter import run_adapter


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic processed JSONL from raw Re-DocRED.")
    parser.add_argument("--train-file")
    parser.add_argument("--dev-file")
    parser.add_argument("--test-file")
    parser.add_argument("--split", choices=("train", "dev", "test"))
    parser.add_argument("--output-dir", default="data/redocred_processed")
    parser.add_argument("--max-docs", type=_positive_int)
    parser.add_argument("--source-name", default="Re-DocRED")
    parser.add_argument("--strict", choices=("true", "false"), default="true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = run_adapter(
        output_dir=args.output_dir,
        train_file=args.train_file,
        dev_file=args.dev_file,
        test_file=args.test_file,
        split=args.split,
        max_docs=args.max_docs,
        source_name=args.source_name,
        strict=args.strict == "true",
        relation_metadata_path=ROOT / "resources" / "redocred_relations.jsonl",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
