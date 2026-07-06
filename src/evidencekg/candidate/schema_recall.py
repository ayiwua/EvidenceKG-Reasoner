from __future__ import annotations

from evidencekg.candidate.base import RecallHit
from evidencekg.graph.graph_store import GraphStore


class SchemaTypeRecall:
    source = "schema_type"

    def score(self, head: str, tail: str, graph: GraphStore) -> RecallHit:
        head_type = (graph.get_entity(head) or {}).get("type", "")
        tail_type = (graph.get_entity(tail) or {}).get("type", "")
        return RecallHit(0.05, self.source, {"head_type": head_type, "tail_type": tail_type})
