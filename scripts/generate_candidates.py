from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidencekg.candidate.multi_route_generator import MultiRouteCandidateGenerator
from evidencekg.graph.graph_store import GraphStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate v2 candidate edges with multi-route recall.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--relation-schema", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    graph = GraphStore.from_dir(args.data_dir)
    candidates = MultiRouteCandidateGenerator(args.relation_schema).write(graph, args.out)
    summary = {
        "candidate_count": len(candidates),
        "candidate_count_by_relation": {},
    }
    for candidate in candidates:
        relation = candidate["relation"]
        summary["candidate_count_by_relation"][relation] = summary["candidate_count_by_relation"].get(relation, 0) + 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
