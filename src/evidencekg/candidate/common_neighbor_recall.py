from __future__ import annotations

from evidencekg.candidate.base import RecallHit
from evidencekg.graph.graph_store import GraphStore


class CommonNeighborRecall:
    source = "common_neighbor"

    def score(self, head: str, tail: str, graph: GraphStore) -> RecallHit | None:
        common = graph.get_common_neighbors(head, tail)
        if not common:
            return None
        return RecallHit(min(0.3, 0.12 + 0.04 * len(common)), self.source, {"common_neighbor_count": len(common), "common_neighbors": common[:8]})
