from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evidencekg.candidate.base import RelationSpec
from evidencekg.graph.graph_store import GraphStore
from evidencekg.io import read_jsonl, write_jsonl
from evidencekg.retrieval.evidence_retriever import EvidenceRetriever


def load_relation_specs(path: str | Path) -> dict[str, RelationSpec]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    relations = payload.get("relations")
    if not isinstance(relations, list):
        raise ValueError("relation schema must contain a relations list")
    return {item["name"]: RelationSpec.from_dict(item) for item in relations}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build relation-aware evidence contexts for candidate edges.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--relation-schema", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--allow-keyword-only", action="store_true")
    parser.add_argument("--enable-dense", action="store_true")
    parser.add_argument("--bi-encoder-model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--cross-encoder-model", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    args = parser.parse_args()

    graph = GraphStore.from_dir(args.data_dir)
    relation_specs = load_relation_specs(args.relation_schema)
    retriever = EvidenceRetriever(
        enable_dense=args.enable_dense,
        bi_encoder_model=args.bi_encoder_model,
        cross_encoder_model=args.cross_encoder_model,
    )
    contexts = []
    for candidate in read_jsonl(args.candidates):
        relation_name = candidate["relation"]
        if relation_name not in relation_specs:
            raise ValueError(f"candidate references relation not in schema: {relation_name}")
        contexts.append(
            retriever.retrieve(
                candidate,
                relation_specs[relation_name],
                graph,
                top_k=args.top_k,
                allow_keyword_only=args.allow_keyword_only,
            )
        )
    write_jsonl(args.out, contexts)
    summary = {
        "context_count": len(contexts),
        "avg_supporting_evidence_count": round(
            sum(len(item["supporting_evidence_candidates"]) for item in contexts) / len(contexts), 4
        )
        if contexts
        else 0.0,
        "degraded_count": sum(1 for item in contexts if item["retrieval_metadata"].get("degraded")),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
