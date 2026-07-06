from __future__ import annotations

from typing import Any


class EvidenceBuilder:
    """Builds standard v2 evidence records."""

    def __init__(self) -> None:
        self._counter = 0

    def build(
        self,
        source: str,
        source_file: str,
        source_row_id: str,
        text: str,
        related_entities: list[str],
        timestamp: str = "",
        reliability: float = 0.8,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._counter += 1
        clean_related = sorted(dict.fromkeys(item for item in related_entities if item))
        if not text.strip():
            raise ValueError(f"evidence text is required for {source_file}:{source_row_id}")
        return {
            "id": f"ev_{self._counter:06d}",
            "source": source,
            "source_file": source_file,
            "source_row_id": source_row_id,
            "text": text.strip(),
            "related_entities": clean_related,
            "timestamp": timestamp,
            "reliability": float(reliability),
            "metadata": metadata or {},
        }
