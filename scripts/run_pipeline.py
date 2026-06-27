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
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=None,
        help="Limit candidates entering evidence retrieval and reasoning. Candidate generation remains full.",
    )
    parser.add_argument(
        "--candidate-offset",
        type=int,
        default=0,
        help="Skip this many generated candidates before evidence retrieval and reasoning.",
    )
    parser.add_argument(
        "--disable-verifier",
        action="store_true",
        help="Ablation only: write raw reasoner outputs without verifier filtering.",
    )
    parser.add_argument(
        "--debug-timing",
        action="store_true",
        help="Print detailed timing logs and write timing_report.jsonl.",
    )
    parser.add_argument(
        "--llm-timeout-seconds",
        type=float,
        default=None,
        help="Override llm.timeout_seconds. Use 0 to disable the HTTP timeout for one-shot latency measurement.",
    )
    parser.add_argument(
        "--llm-max-retries",
        type=int,
        default=None,
        help="Override llm.max_retries. Use 0 to send exactly one provider request.",
    )
    parser.add_argument(
        "--enable-writeback",
        action="store_true",
        help="Write verified accepted edges to pending_edges.jsonl or triples.enriched.jsonl.",
    )
    parser.add_argument(
        "--writeback-mode",
        default="pending",
        choices=["pending", "approved"],
        help="pending writes pending_edges.jsonl; approved writes triples.enriched.jsonl.",
    )
    args = parser.parse_args()

    result = PipelineRunner().run(
        args.config,
        args.data_dir,
        args.output_dir,
        stage=args.stage,
        max_candidates=args.max_candidates,
        candidate_offset=args.candidate_offset,
        disable_verifier=args.disable_verifier,
        debug_timing=args.debug_timing,
        llm_timeout_seconds=args.llm_timeout_seconds,
        llm_max_retries=args.llm_max_retries,
        enable_writeback=args.enable_writeback,
        writeback_mode=args.writeback_mode,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
