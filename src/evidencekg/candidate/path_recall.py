from __future__ import annotations

from evidencekg.candidate.base import RecallHit, RelationSpec
from evidencekg.graph.graph_store import GraphStore


class PathRecall:
    source = "path_rule"

    def score(self, head: str, tail: str, relation: RelationSpec, graph: GraphStore) -> RecallHit | None:
        path = graph.get_shortest_path(head, tail, max_depth=3)
        if not path:
            return None
        path_len = len(path) - 1
        score = 0.45 if path_len <= 2 else 0.25
        return RecallHit(score, self.source, {"shortest_path_len": path_len, "shortest_path": path})
