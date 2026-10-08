"""Qdrant 검색과 일반/서비스 QA 분리 검증 (LLM 호출은 대체)."""
import json

import pytest
from fastapi.testclient import TestClient
from qdrant_client import models

from app import config
from app.main import app
from app.rag import qa_pipeline, qdrant_store
from app.rag.qa_retriever import retrieve


@pytest.fixture(scope="module")
def qa_index(chunks, tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "QA_EMBEDDING_PROVIDER", "local")
        mp.setattr(qdrant_store, "QDRANT_PATH", tmp_path_factory.mktemp("qdrant_qa"))
        qdrant_store.client.cache_clear()
        qdrant_store.dense_query.cache_clear()
        assert qdrant_store.index_chunks(chunks["chunks"]) == 395
        yield
        qdrant_store.client().close()
        qdrant_store.client.cache_clear()
        qdrant_store.dense_query.cache_clear()


def test_definition_retrieval_contains_docling_clause(qa_index):
    hits = retrieve("고영향 인공지능이란 무엇인가요?")
    assert hits[0]["id"] == "ARTICLE_2_4"
    assert hits[0]["source_file"] == "ai_basic_act_20260721.pdf"
    assert hits[0]["source_sha256"]


def test_amended_articles_are_indexed_from_current_pdfs(qa_index):
    act, decree = qdrant_store.get_chunks(["ARTICLE_17-2_1", "DECREE_1-2"])
    assert act["source_file"] == "ai_basic_act_20260721.pdf"
    assert decree["source_file"] == "ai_basic_act_decree_20260820.pdf"
    assert "이용비용" in act["text"] or "비용" in act["text"]
    assert decree["title"] == "인공지능취약계층의 범위"


def test_local_qdrant_sparse_idf_search(qa_index):
    config = qdrant_store.client().get_collection(qdrant_store.QDRANT_COLLECTION).config
    assert config.params.sparse_vectors[qdrant_store.SPARSE].modifier == models.Modifier.IDF
    assert qdrant_store.search_sparse("채용 판단 평가", limit=3)


def test_leaf_embedding_contains_parent_definition(chunks):
    leaf = next(c for c in chunks["chunks"] if c["id"] == "ARTICLE_2_4_SA")
    assert "고영향 인공지능" in qdrant_store.dense_text(leaf)
    assert leaf["text"].startswith("채용, 대출 심사")
    assert "고영향 인공지능" not in leaf["text"]


def test_all_retrieval_stages_are_measured(qa_index, tmp_path, monkeypatch):
    from scripts import evaluate_qa

    gold = tmp_path / "gold.jsonl"
    gold.write_text(json.dumps({"id": "definition", "question": "고영향 인공지능이란 무엇인가요?",
                                "gold_ids": ["ARTICLE_2_4"]}, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(evaluate_qa, "GOLD", gold)
    result = evaluate_qa.run(output=tmp_path / "result.json")
    assert result["count"] == 1
    assert all(stage in result and f"{stage}_ids" in result["cases"][0]
               for stage in evaluate_qa.STAGES)


def test_general_question_never_runs_service_rules(qa_index, monkeypatch):
    def forbidden(*_args):
        raise AssertionError("일반 질문에 서비스 판정이 실행됨")

    monkeypatch.setattr(qa_pipeline, "_rule_context", forbidden)
    monkeypatch.setattr(qa_pipeline, "_llm_json", lambda *_args: {
        "answer": "고영향 AI의 정의를 확인합니다. [S1]", "used_source_ids": ["S1"]})
    response = TestClient(app).post("/ask", json={"question": "고영향 인공지능이란 무엇인가요?"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "general"
    assert body["sources"][0]["source_id"] == "S1"
    assert body["sources"][0]["chunk_id"] == "ARTICLE_2_4"


def test_service_question_adds_rule_context(qa_index, monkeypatch):
    seen = {}

    def fake_llm(question, service, facts, sources):
        seen.update(service=service, facts=facts, sources=sources)
        return {"answer": "채용 영역의 판단 여부를 확인합니다. [S1]", "used_source_ids": ["S1"]}

    monkeypatch.setattr(qa_pipeline, "_llm_json", fake_llm)
    response = TestClient(app).post("/ask", json={
        "question": "출시 전에 무엇을 확인해야 하나요?",
        "service_description": "얼굴 인식으로 면접 영상을 분석해 지원자의 채용 점수를 추천하는 AI",
    })
    assert response.status_code == 200
    assert response.json()["mode"] == "service"
    assert seen["service"] and any(f["status"] == "REVIEW" for f in seen["facts"])
    assert all(s["doc"] in {"AIACT", "DECREE"} for s in seen["sources"])


def test_first_person_question_uses_service_mode(qa_index, monkeypatch):
    monkeypatch.setattr(qa_pipeline, "_llm_json", lambda *_args: {
        "answer": "서비스 조건을 확인합니다. [S1]", "used_source_ids": ["S1"]})
    response = TestClient(app).post("/ask", json={
        "question": "내 AI 서비스는 면접 영상을 분석해 채용 점수를 추천합니다. 무엇을 확인해야 하나요?"})
    assert response.status_code == 200
    assert response.json()["mode"] == "service"


def test_definition_and_service_question_in_one_input(qa_index, monkeypatch):
    monkeypatch.setattr(config, "FEATURE_EXTRACTOR", "heuristic")
    seen = {}
    sparse_search = qdrant_store.search_sparse

    def record_sparse_query(query, limit=10):
        seen["legal_query"] = query
        return sparse_search(query, limit=limit)

    def fake_llm(question, service, facts, sources):
        seen.update(question=question, service=service, facts=facts, sources=sources)
        definition = next(n for n, source in enumerate(sources, 1) if source["id"] == "ARTICLE_2_4")
        domain = next(n for n, source in enumerate(sources, 1) if source["id"] == "ARTICLE_2_4_SA")
        return {"answer": f"고영향 AI의 뜻 [S{definition}]\n채용 서비스 검토 [S{domain}]",
                "used_source_ids": [f"S{definition}", f"S{domain}"]}

    monkeypatch.setattr(qa_pipeline, "_llm_json", fake_llm)
    monkeypatch.setattr(qdrant_store, "search_sparse", record_sparse_query)
    response = TestClient(app).post("/ask", json={"question": (
        "AI 고영향이 뭔가요? 내가 면접 영상을 분석해 지원자의 채용 점수를 추천하는 "
        "AI 서비스를 준비하는데 해당하나요?")})
    assert response.status_code == 200
    assert response.json()["mode"] == "service"
    assert {source["chunk_id"] for source in response.json()["sources"]} == {
        "ARTICLE_2_4", "ARTICLE_2_4_SA"}
    assert seen["service"].startswith("내가 면접 영상을 분석해")
    assert seen["legal_query"] == "AI 고영향이 뭔가요"
    assert any("ARTICLE_2_4_SA" in fact["record_ids"] for fact in seen["facts"])


def test_unknown_citation_is_not_returned(qa_index, monkeypatch):
    monkeypatch.setattr(qa_pipeline, "_llm_json", lambda *_args: {
        "answer": "근거 없는 내용 [S99]", "used_source_ids": ["S99"]})
    response = TestClient(app).post("/ask", json={"question": "고영향 AI는 무엇인가요?"})
    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert "확인할 수 없습니다" in response.json()["answer"]


def test_missing_qdrant_returns_503(monkeypatch):
    monkeypatch.setattr(qdrant_store, "ready", lambda: False)
    response = TestClient(app).post("/ask", json={"question": "고영향 AI는 무엇인가요?"})
    assert response.status_code == 503


def test_blank_question_is_rejected():
    response = TestClient(app).post("/ask", json={"question": "  "})
    assert response.status_code == 422
