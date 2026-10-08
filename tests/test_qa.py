"""Qdrant 검색과 일반/서비스 QA 분리 검증 (LLM 호출은 대체)."""
import pytest
from fastapi.testclient import TestClient

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
        assert qdrant_store.index_chunks(chunks["chunks"]) == 362
        yield
        qdrant_store.client().close()
        qdrant_store.client.cache_clear()
        qdrant_store.dense_query.cache_clear()


def test_definition_retrieval_contains_docling_clause(qa_index):
    hits = retrieve("고영향 인공지능이란 무엇인가요?")
    assert hits[0]["id"] == "ARTICLE_2_4"
    assert hits[0]["source_file"] == "ai_basic_act_20260122.pdf"
    assert hits[0]["source_sha256"]


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
