import networkx as nx

from evidencekg.graph.graph_store import GraphStore


def test_graph_store_uses_multidigraph_and_indexes_records():
    graph = GraphStore.from_dir("data/sample")

    assert isinstance(graph.graph, nx.MultiDiGraph)
    assert len(graph.entities) == 76
    assert len(graph.triples) == 131
    assert len(graph.evidence) == 42
    assert graph.get_entity("ip_001")["type"] == "ip"
    assert graph.get_triple("t_021")["relation"] == "exposes_service"
    assert graph.get_evidence("ev_001")["evidence_id"] == "ev_001"


def test_graph_store_practical_interfaces():
    graph = GraphStore.from_dir("data/sample")

    assert graph.iter_entities_by_type(["ip"])[0]["type"] == "ip"
    assert graph.iter_triples()
    assert graph.get_triples_between("ip_001", "service_payment_api")
    assert graph.get_triples_for_entities(["ip_001", "team_payment"])
    assert graph.get_evidence_for_triple("t_021")[0]["evidence_id"] == "ev_023"
    assert "service_payment_api" in graph.get_neighbors("ip_001")
    assert "port_443" in graph.get_neighbors("service_payment_api")
    assert graph.find_paths("ip_001", "team_payment", max_hops=3, max_paths=5)
