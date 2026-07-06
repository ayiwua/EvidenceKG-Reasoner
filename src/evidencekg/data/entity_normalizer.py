from __future__ import annotations

import re


TOKEN_RE = re.compile(r"[^a-z0-9]+")


class EntityNormalizer:
    """Stable entity id normalization for v2 dataset construction."""

    PREFIX_BY_TYPE = {
        "application": "app",
        "asset": "asset",
        "alert": "alert",
        "domain": "domain",
        "host": "host",
        "ip": "ip",
        "port": "port",
        "service": "svc",
        "team": "team",
        "ticket": "ticket",
    }

    def normalize_token(self, value: str) -> str:
        text = str(value or "").strip().lower()
        if not text:
            raise ValueError("cannot normalize empty entity value")
        text = TOKEN_RE.sub("_", text).strip("_")
        if not text:
            raise ValueError(f"cannot normalize entity value: {value!r}")
        return text

    def entity_id(self, entity_type: str, value: str) -> str:
        prefix = self.PREFIX_BY_TYPE.get(entity_type, self.normalize_token(entity_type))
        token = self.normalize_token(value)
        if token.startswith(prefix + "_"):
            return token
        return f"{prefix}_{token}"

    def ip_id(self, value: str) -> str:
        return self.entity_id("ip", value)

    def port_id(self, value: str) -> str:
        port = str(value or "").strip()
        if not port:
            raise ValueError("port value is required")
        return self.entity_id("port", port)
