from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import yaml

from evidencekg.data.entity_normalizer import EntityNormalizer
from evidencekg.data.evidence_builder import EvidenceBuilder
from evidencekg.io import write_jsonl


class DatasetBuilder:
    """Build v2 standard JSONL files from enterprise asset CSV tables."""

    REQUIRED_TABLES = {
        "teams": ["team_id", "team_name", "department", "oncall_email"],
        "assets": ["asset_id", "asset_type", "ip", "hostname", "env", "region"],
        "services": ["service_id", "service_name", "app_name", "owner_team", "host_ip", "port"],
        "dns_records": ["domain", "record_type", "value", "source", "timestamp"],
        "tickets": [
            "ticket_id",
            "title",
            "description",
            "related_service",
            "related_ip",
            "assigned_team",
            "timestamp",
        ],
        "alerts": [
            "alert_id",
            "title",
            "description",
            "related_service",
            "related_ip",
            "assigned_team",
            "severity",
            "timestamp",
        ],
        "service_dependencies": ["source_service", "target_service", "evidence_source", "timestamp"],
    }

    def __init__(self, manifest_path: str | Path, raw_dir: str | Path, out_dir: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        self.raw_dir = Path(raw_dir)
        self.out_dir = Path(out_dir)
        self.normalizer = EntityNormalizer()
        self.evidence_builder = EvidenceBuilder()
        self.entities: dict[str, dict[str, Any]] = {}
        self.triples: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        self.gold_hidden_edges: list[dict[str, Any]] = []
        self._triple_counter = 0
        self._team_lookup: dict[str, str] = {}
        self._service_lookup: dict[str, str] = {}
        self._ip_lookup: dict[str, str] = {}

    def build(self) -> dict[str, int]:
        manifest = self._load_manifest()
        tables = {name: self._read_table(name, spec) for name, spec in manifest["tables"].items()}

        self._build_teams(tables["teams"])
        self._build_assets(tables["assets"])
        self._build_services(tables["services"])
        self._build_dns_records(tables["dns_records"])
        self._build_tickets(tables["tickets"])
        self._build_alerts(tables["alerts"])
        self._build_service_dependencies(tables["service_dependencies"])

        self._write_outputs()
        return {
            "entity_count": len(self.entities),
            "triple_count": len(self.triples),
            "evidence_count": len(self.evidence),
            "gold_hidden_edge_count": len(self.gold_hidden_edges),
        }

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"manifest not found: {self.manifest_path}")
        manifest = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8")) or {}
        tables = manifest.get("tables")
        if not isinstance(tables, dict):
            raise ValueError("dataset manifest must contain a tables mapping")
        missing = sorted(set(self.REQUIRED_TABLES) - set(tables))
        if missing:
            raise ValueError(f"dataset manifest missing tables: {missing}")
        return manifest

    def _read_table(self, table_name: str, spec: dict[str, Any]) -> list[dict[str, str]]:
        file_name = spec.get("file")
        if not file_name:
            raise ValueError(f"table {table_name} missing file")
        path = self.raw_dir / file_name
        if not path.exists():
            raise FileNotFoundError(f"raw CSV not found for table {table_name}: {path}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            missing = [col for col in self.REQUIRED_TABLES[table_name] if col not in fieldnames]
            if missing:
                raise ValueError(f"{path} missing required columns: {missing}")
            return [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    def _build_teams(self, rows: list[dict[str, str]]) -> None:
        for row in rows:
            entity_id = self.normalizer.entity_id("team", row["team_id"] or row["team_name"])
            self._add_entity(
                entity_id,
                "team",
                row["team_name"],
                aliases=[row["team_id"]],
                properties={"department": row["department"], "oncall_email": row["oncall_email"]},
            )
            for key in [row["team_id"], row["team_name"]]:
                if key:
                    self._team_lookup[self.normalizer.normalize_token(key)] = entity_id

    def _build_assets(self, rows: list[dict[str, str]]) -> None:
        for row in rows:
            ip_id = self.normalizer.ip_id(row["ip"])
            host_id = self.normalizer.entity_id("host", row["hostname"])
            self._ip_lookup[row["ip"]] = ip_id
            self._add_entity(
                ip_id,
                "ip",
                row["ip"],
                aliases=[],
                properties={"asset_id": row["asset_id"], "env": row["env"], "region": row["region"]},
            )
            self._add_entity(
                host_id,
                "host",
                row["hostname"],
                aliases=[row["asset_id"]],
                properties={"asset_type": row["asset_type"], "env": row["env"], "region": row["region"]},
            )
            self._add_triple(host_id, "has_ip", ip_id, "assets.csv", row["asset_id"], 0.95)

    def _build_services(self, rows: list[dict[str, str]]) -> None:
        for row in rows:
            service_id = self.normalizer.entity_id("service", row["service_id"] or row["service_name"])
            app_id = self.normalizer.entity_id("application", row["app_name"])
            ip_id = self._require_ip(row["host_ip"])
            port_id = self.normalizer.port_id(row["port"])
            team_id = self._require_team(row["owner_team"])
            self._service_lookup[self.normalizer.normalize_token(row["service_id"])] = service_id
            self._service_lookup[self.normalizer.normalize_token(row["service_name"])] = service_id
            self._add_entity(
                service_id,
                "service",
                row["service_name"],
                aliases=[row["service_id"]],
                properties={"app_name": row["app_name"], "port": row["port"]},
            )
            self._add_entity(app_id, "application", row["app_name"], aliases=[], properties={})
            self._add_entity(port_id, "port", row["port"], aliases=[f"{row['port']}/tcp"], properties={"protocol": "tcp"})
            self._add_triple(service_id, "belongs_to_application", app_id, "services.csv", row["service_id"], 0.9)
            self._add_triple(service_id, "runs_on", ip_id, "services.csv", row["service_id"], 0.92)
            self._add_triple(service_id, "uses_port", port_id, "services.csv", row["service_id"], 0.88)
            self._add_gold(service_id, "owned_by", team_id, "services.csv", row["service_id"], "evaluation_gold")

    def _build_dns_records(self, rows: list[dict[str, str]]) -> None:
        for index, row in enumerate(rows, start=1):
            domain_id = self.normalizer.entity_id("domain", row["domain"])
            self._add_entity(
                domain_id,
                "domain",
                row["domain"],
                aliases=[],
                properties={"record_type": row["record_type"], "source": row["source"]},
            )
            if row["value"] in self._ip_lookup:
                self._add_triple(domain_id, "resolves_to", self._ip_lookup[row["value"]], "dns_records.csv", row["domain"], 0.9)
            self._add_evidence(
                "dns",
                "dns_records.csv",
                row["domain"],
                f"DNS {row['record_type']} record maps {row['domain']} to {row['value']}.",
                [domain_id, self._ip_lookup.get(row["value"], "")],
                row["timestamp"],
                0.82,
                {"row_index": index, "source": row["source"]},
            )

    def _build_tickets(self, rows: list[dict[str, str]]) -> None:
        for row in rows:
            ticket_id = self.normalizer.entity_id("ticket", row["ticket_id"])
            service_id = self._require_service(row["related_service"])
            ip_id = self._require_ip(row["related_ip"])
            team_id = self._require_team(row["assigned_team"])
            self._add_entity(ticket_id, "ticket", row["ticket_id"], aliases=[], properties={"title": row["title"]})
            self._add_triple(ticket_id, "mentions", service_id, "tickets.csv", row["ticket_id"], 0.8)
            self._add_triple(ticket_id, "mentions", ip_id, "tickets.csv", row["ticket_id"], 0.8)
            self._add_triple(ticket_id, "assigned_to", team_id, "tickets.csv", row["ticket_id"], 0.85)
            self._add_evidence(
                "ticket",
                "tickets.csv",
                row["ticket_id"],
                f"{row['title']} {row['description']}",
                [ticket_id, service_id, ip_id, team_id],
                row["timestamp"],
                0.86,
                {},
            )

    def _build_alerts(self, rows: list[dict[str, str]]) -> None:
        for row in rows:
            alert_id = self.normalizer.entity_id("alert", row["alert_id"])
            service_id = self._require_service(row["related_service"])
            ip_id = self._require_ip(row["related_ip"])
            team_id = self._require_team(row["assigned_team"])
            self._add_entity(alert_id, "alert", row["alert_id"], aliases=[], properties={"severity": row["severity"]})
            self._add_triple(alert_id, "alerts_on", service_id, "alerts.csv", row["alert_id"], 0.82)
            self._add_triple(alert_id, "alerts_on", ip_id, "alerts.csv", row["alert_id"], 0.78)
            self._add_triple(alert_id, "routed_to", team_id, "alerts.csv", row["alert_id"], 0.84)
            self._add_evidence(
                "alert",
                "alerts.csv",
                row["alert_id"],
                f"{row['title']} {row['description']} Severity {row['severity']}.",
                [alert_id, service_id, ip_id, team_id],
                row["timestamp"],
                0.8,
                {"severity": row["severity"]},
            )

    def _build_service_dependencies(self, rows: list[dict[str, str]]) -> None:
        for index, row in enumerate(rows, start=1):
            source_id = self._require_service(row["source_service"])
            target_id = self._require_service(row["target_service"])
            row_id = f"dep_{index:03d}"
            self._add_gold(source_id, "depends_on", target_id, "service_dependencies.csv", row_id, "evaluation_gold")
            self._add_evidence(
                "service_dependency",
                "service_dependencies.csv",
                row_id,
                f"{row['source_service']} depends on {row['target_service']} according to {row['evidence_source']}.",
                [source_id, target_id],
                row["timestamp"],
                0.84,
                {"evidence_source": row["evidence_source"]},
            )

    def _add_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        aliases: list[str],
        properties: dict[str, Any],
    ) -> None:
        if entity_id in self.entities:
            existing = self.entities[entity_id]
            existing["aliases"] = sorted(set(existing.get("aliases", [])) | {item for item in aliases if item})
            existing["properties"].update({key: value for key, value in properties.items() if value != ""})
            return
        self.entities[entity_id] = {
            "id": entity_id,
            "type": entity_type,
            "name": name,
            "aliases": sorted(item for item in aliases if item),
            "properties": {key: value for key, value in properties.items() if value != ""},
        }

    def _add_triple(
        self,
        head: str,
        relation: str,
        tail: str,
        source: str,
        source_row_id: str,
        confidence: float,
        properties: dict[str, Any] | None = None,
    ) -> None:
        self._triple_counter += 1
        self.triples.append(
            {
                "id": f"triple_{self._triple_counter:06d}",
                "head": head,
                "relation": relation,
                "tail": tail,
                "source": source,
                "source_row_id": source_row_id,
                "confidence": confidence,
                "properties": properties or {},
            }
        )

    def _add_gold(self, head: str, relation: str, tail: str, source: str, source_row_id: str, hide_reason: str) -> None:
        self.gold_hidden_edges.append(
            {
                "head": head,
                "relation": relation,
                "tail": tail,
                "source": source,
                "source_row_id": source_row_id,
                "hide_reason": hide_reason,
            }
        )

    def _add_evidence(
        self,
        source: str,
        source_file: str,
        source_row_id: str,
        text: str,
        related_entities: list[str],
        timestamp: str,
        reliability: float,
        metadata: dict[str, Any],
    ) -> None:
        self.evidence.append(
            self.evidence_builder.build(
                source=source,
                source_file=source_file,
                source_row_id=source_row_id,
                text=text,
                related_entities=related_entities,
                timestamp=timestamp,
                reliability=reliability,
                metadata=metadata,
            )
        )

    def _require_team(self, value: str) -> str:
        key = self.normalizer.normalize_token(value)
        if key not in self._team_lookup:
            raise ValueError(f"unknown team reference: {value}")
        return self._team_lookup[key]

    def _require_service(self, value: str) -> str:
        key = self.normalizer.normalize_token(value)
        if key not in self._service_lookup:
            raise ValueError(f"unknown service reference: {value}")
        return self._service_lookup[key]

    def _require_ip(self, value: str) -> str:
        if value not in self._ip_lookup:
            raise ValueError(f"unknown ip reference: {value}")
        return self._ip_lookup[value]

    def _write_outputs(self) -> None:
        triples_as_keys = {(item["head"], item["relation"], item["tail"]) for item in self.triples}
        leaked_gold = [
            item for item in self.gold_hidden_edges if (item["head"], item["relation"], item["tail"]) in triples_as_keys
        ]
        if leaked_gold:
            raise ValueError(f"hidden gold edges leaked into triples: {leaked_gold[:3]}")
        write_jsonl(self.out_dir / "entities.jsonl", sorted(self.entities.values(), key=lambda item: item["id"]))
        write_jsonl(self.out_dir / "triples.jsonl", self.triples)
        write_jsonl(self.out_dir / "evidence.jsonl", self.evidence)
        write_jsonl(self.out_dir / "gold_hidden_edges.jsonl", self.gold_hidden_edges)
