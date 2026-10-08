from fastapi.testclient import TestClient

from app.engine.law_search import search_law
from app.main import app


def test_law_search_returns_source_text_for_notice_question():
    answer = search_law("생성형 AI의 고지 의무가 무엇인가요?")
    assert answer.sources
    assert any("제31조" in source.article for source in answer.sources)
    assert all(source.content and source.source_file for source in answer.sources)
    assert "적용 여부는 단정하지 않습니다" in answer.answer


def test_law_search_endpoint_has_ask_response_shape():
    response = TestClient(app).post("/api/law-search", json={"question": "고영향 인공지능의 정의는 무엇인가요?"})
    assert response.status_code == 200
    body = response.json()
    assert body["sources"][0]["chunk_id"] == "ARTICLE_2_4"
    assert body["sources"][0]["document"] == "인공지능기본법"
