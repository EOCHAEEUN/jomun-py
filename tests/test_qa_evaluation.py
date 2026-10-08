"""The answer evaluation uses the same service context as /ask."""
import json

from app.schemas import AskResponse, AskSource, ServiceFeatures
from scripts import evaluate_qa


def test_service_context_is_searched_and_sent_to_answer(tmp_path, monkeypatch):
    gold = tmp_path / "gold.jsonl"
    gold.write_text(json.dumps({
        "id": "service", "question": "무슨 법을 봐야 하나요?",
        "service_description": "지원자 채용 점수를 추천하는 AI", "gold_ids": ["ARTICLE_2_4_SA"],
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    seen = {}

    def fake_retrieve(query, features=None, limit=5):
        seen["query"] = query
        seen["features"] = features
        return [{"id": "ARTICLE_2_4_SA"}]

    def fake_answer(req):
        seen["service"] = req.service_description
        return AskResponse(answer="채용 영역을 검토합니다. [S1]", sources=[
            AskSource(source_id="S1", article="제2조제4호사목", content="채용", document="인공지능기본법",
                      page=1, chunk_id="ARTICLE_2_4_SA", source_file="law.pdf")], mode="service")

    monkeypatch.setattr(evaluate_qa, "ready", lambda: True)
    monkeypatch.setattr(evaluate_qa, "retrieve", fake_retrieve)
    monkeypatch.setattr(evaluate_qa, "extract", lambda _spec: (ServiceFeatures(purpose="RECRUITMENT"), []))
    monkeypatch.setattr(evaluate_qa, "apply_answers", lambda features, _answers: features)
    monkeypatch.setattr("app.rag.qa_pipeline.answer", fake_answer)

    result = evaluate_qa.run(with_answers=True, output=tmp_path / "result.json",
                             stages=("hybrid_rerank",), gold=gold)
    assert seen["service"] == "지원자 채용 점수를 추천하는 AI"
    assert seen["service"] in seen["query"]
    assert seen["features"].purpose == "RECRUITMENT"
    assert result["hybrid_rerank"]["hit@3"] == 1.0
    assert result["cases"][0]["cited_gold"] is True


def test_unanswerable_question_is_not_search_hit_denominator():
    rows = [{"gold_ids": [], "ids": ["OTHER"]},
            {"gold_ids": ["ARTICLE_1"], "ids": ["ARTICLE_1"]},
            {"gold_ids": ["ARTICLE_2", "ARTICLE_3"], "ids": ["ARTICLE_2"]}]
    metrics = evaluate_qa.rank_metrics(rows, "ids")
    assert metrics["hit@3"] == 1.0
    assert metrics["all_gold@5"] == 0.5
