# test_rag.py — RAG 후보 검색 → Rule Engine 검증 연결 테스트
#   임시 폴더에 Chroma를 새로 적재해서 돌린다 (conftest.chroma). 로컬 임베딩 기준.
import json

import pytest

pytest.importorskip("chromadb")   # chromadb가 없으면 이 파일만 건너뛴다 (CI는 requirements.txt로 설치)

from app.config import EMBEDDING_PROVIDER, EVAL_PATH, use_llm  # noqa: E402
from app.engine.features import heuristic_extract  # noqa: E402
from app.engine.pipeline import run_build  # noqa: E402
from app.rag import store  # noqa: E402
from app.rag.retriever import SEARCH_FILTER, build_queries, retrieve_candidates  # noqa: E402
from tests.conftest import DEMO  # noqa: E402

pytestmark = pytest.mark.skipif(EMBEDDING_PROVIDER != "local", reason="스냅샷·검색 기대값은 로컬 임베딩 기준")


def by_key(result):
    return {i["key"]: i for i in result["items"]}


def test_ingest_loads_all_chunks(chroma, chunks):
    assert chroma == len(chunks["chunks"]) > 1000


def test_search_excludes_english_and_government_clauses(chroma):
    hits = store.search("고영향 인공지능 사업자 책무", k=10, where=SEARCH_FILTER)
    assert hits and all(h["doc"] != "AIACT_EN" for h in hits)
    assert all(h["kind"] != "COMMENTARY_PDF" for h in hits)
    assert all(h["addressee"] not in ("GOVERNMENT", "COMMITTEE") for h in hits)


def test_original_commentary_pdf_is_embedded_and_searchable(chroma, chunks):
    original = [c for c in chunks["chunks"] if c["kind"] == "COMMENTARY_PDF"]
    hits = store.search("실질적인 인사권자의 개입 없이 지원자를 탈락", k=3,
                        where={"kind": "COMMENTARY_PDF"})
    assert hits and all(h["id"].startswith("BKL_P") for h in hits)
    assert all(h["source_sha256"] == original[0]["source_sha256"] for h in hits)
    assert any(h["page"] in (3, 4) for h in hits)


def test_feature_queries_use_legal_vocabulary():
    labels = [q["label"] for q in build_queries(DEMO, heuristic_extract(DEMO))]
    assert labels[0].startswith("서비스 설명")                       # naive 쿼리도 항상 함께
    assert {"활용 영역: RECRUITMENT", "생체정보", "자동화된 결정"} <= set(labels)


def test_enriched_retrieval_finds_the_domain_article(chroma):
    rag = retrieve_candidates(DEMO, heuristic_extract(DEMO))
    assert rag.mode == "chroma"
    assert "ARTICLE_2_4_SA" in rag.hits                               # 사목을 '검색'으로 찾는다
    assert "ARTICLE_34_1" in rag.expanded                             # 고영향이면 적용되는 조문은 참조 확장으로
    assert rag.candidates == set(rag.hits) | set(rag.expanded)


def test_pipeline_uses_rag_candidates(chroma):
    result = run_build(DEMO)
    items = by_key(result)
    assert result["rag"]["mode"] == "chroma" and result["rag"]["n_candidates"] > 0
    assert items["art2_4"]["label"] == "제2조4호사목" and items["art2_4"]["status"] == "MATCH"
    # 사목은 RAG 검색이 찾았고, 규칙이 검증했다
    assert any(f["how"] == "search" and f["id"] == "ARTICLE_2_4_SA" for f in items["art2_4"]["found_by"])
    # 검색이 함께 가져온 바목은 규칙이 이유와 함께 기각한다
    assert any(r["label"] == "제2조4호바목" for r in result["rag"]["rejected"])
    # 기본 규칙은 검색과 무관하게 표시된다
    assert items["art33_1"]["baseline"] and items["high_impact"]["baseline"]
    # 기본 규칙이 아닌 항목은 모두 RAG 후보에서 왔다
    assert all(i["found_by"] for i in result["items"] if not i["baseline"])


def test_rules_only_fallback_when_vectorstore_is_empty(monkeypatch):
    monkeypatch.setattr(store, "get_collection", lambda: None)
    result = run_build(DEMO)
    assert result["rag"]["mode"] == "rules-only" and result["rag"]["n_candidates"] == 0
    assert by_key(result)["art2_4"]["status"] == "MATCH"              # 규칙만으로도 판정은 된다
    assert all(not i["found_by"] for i in result["items"])


@pytest.mark.parametrize("case", json.loads(EVAL_PATH.read_text(encoding="utf-8")), ids=lambda c: c["id"])
def test_dev_cases_with_rag(chroma, case):
    s = {it["label"]: it["status"] for it in run_build(case["spec"])["items"]}
    for label, expected in case["gold"]["statuses"].items():
        assert s.get(label) == expected, f"{label}: {s.get(label)} != {expected}"
    for label in case["gold"].get("absent", []):
        assert label not in s


@pytest.mark.skipif(use_llm(), reason="스냅샷은 규칙 기반(heuristic) 특성 추출 기준")
def test_evaluation_matches_committed_snapshot(chroma):
    # 평가 결과가 바뀌면 docs/eval_snapshot.json도 같이 갱신해야 한다 (python -m scripts.evaluate --snapshot)
    from scripts.evaluate import HELDOUT_PATH, HELDOUT_V2_PATH, SNAPSHOT_PATH, run
    snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    results = run({"dev": EVAL_PATH, "heldout": HELDOUT_PATH, "heldout_v2": HELDOUT_V2_PATH})
    for split, res in results.items():
        assert res["summary"] == snap[split]["summary"], split
        failed = {r["id"]: [c["check"] for c in r["final_checks"] if not c["ok"]] for r in res["rows"]}
        assert failed == snap[split]["cases"], split
