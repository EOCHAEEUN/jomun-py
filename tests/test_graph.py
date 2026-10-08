# test_graph.py — 법령 라이브러리 관계도 (/api/graph)가 태깅 데이터의 관계를 그대로 담는지
from fastapi.testclient import TestClient

from app.engine.graph import build_graph
from app.engine.law import get_lawbook
from app.main import app


def _edges(graph, kind):
    return {(e["source"], e["target"]) for e in graph["edges"] if e["type"] == kind}


def test_every_tagged_record_is_a_node_and_no_edge_dangles():
    g = build_graph()
    ids = {n["id"] for n in g["nodes"]}
    assert {r["id"] for r in get_lawbook().records} <= ids
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    assert g["stats"]["edges"] == len(g["edges"])


def test_decree_implements_the_law_article_it_cites():
    implements = _edges(build_graph(), "IMPLEMENTS")
    assert ("DECREE_23_1", "ARTICLE_31_1") in implements      # "법 제31조제1항에 따라"
    assert ("DECREE_29_1", "ARTICLE_36_1") in implements      # 국내대리인 기준


def test_sanction_path_follows_tagged_penalty():
    sanction = _edges(build_graph(), "SANCTION")
    assert ("ARTICLE_31_1", "ARTICLE_43_1_1") in sanction
    assert ("ARTICLE_36_1", "ARTICLE_43_1_2") in sanction


def test_commentary_summaries_explain_their_domain():
    explains = _edges(build_graph(), "EXPLAINS")
    assert ("BKL_RECRUIT", "ARTICLE_2_4_SA") in explains
    assert ("BKL_TWO_STEP", "ARTICLE_2_4") in explains


def test_one_relation_per_article_pair():
    g = build_graph()
    pair_types = {}
    for e in g["edges"]:
        if e["type"] in ("SANCTION", "IMPLEMENTS", "EXPLAINS", "PART_OF", "REFERS"):
            pair_types.setdefault(tuple(sorted((e["source"], e["target"]))), set()).add(e["type"])
    assert all(len(t) == 1 for t in pair_types.values())


def test_external_laws_are_cited_not_judged():
    g = build_graph()
    assert ("ARTICLE_2_4_A", "EXTLAW:교통안전법") in _edges(g, "CITES")
    assert all(n["kind"] != "provision" or n["doc"] in {"AIACT", "DECREE", "BKL", "PIPA", "CREDIT"} for n in g["nodes"])


def test_graph_endpoint():
    res = TestClient(app).get("/api/graph")
    assert res.status_code == 200
    body = res.json()
    assert {"nodes", "edges", "docs", "stats"} <= set(body)
    assert body["stats"]["provisions"] == len(get_lawbook().records)
