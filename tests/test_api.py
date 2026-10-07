# test_api.py — FastAPI 엔드포인트 테스트 (TestClient)
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import DEMO

client = TestClient(app)
ITEM_KEYS = {"key", "doc", "doc_short", "status", "label", "summary", "obligation", "condition", "notes",
             "externals", "records", "chain", "decompiled", "checklist", "question", "baseline", "found_by",
             "rejected"}
STATUSES = {"MATCH", "REQUIRED", "CONDITIONAL", "SHOULD", "REVIEW", "OPPORTUNITY", "INFO", "OUT_OF_SCOPE"}


def test_index_serves_the_ui():
    res = client.get("/")
    assert res.status_code == 200 and "조문" in res.text


def test_sources_lists_six_documents():
    res = client.get("/api/sources")
    assert res.status_code == 200
    assert {s["id"] for s in res.json()} == {"AIACT", "DECREE", "AIACT_EN", "BKL", "PIPA", "CREDIT"}


def test_examples_come_from_the_dev_set():
    ex = client.get("/api/examples").json()
    assert len(ex) >= 10 and {"id", "name", "spec"} <= set(ex[0])


def test_build_returns_build_log(chroma):
    res = client.post("/api/build", json={"spec": DEMO})
    assert res.status_code == 200
    body = res.json()
    assert {"items", "summary", "todo", "pending_questions", "rag", "features", "mode", "sources"} <= set(body)
    assert body["items"] and all(ITEM_KEYS <= set(i) for i in body["items"])
    assert all(i["status"] in STATUSES for i in body["items"])
    assert body["rag"]["mode"] == "chroma"
    assert "high_impact" in body["pending_questions"]


def test_answers_change_the_build(chroma):
    before = client.post("/api/build", json={"spec": DEMO}).json()
    after = client.post("/api/build", json={"spec": DEMO, "answers": {"high_impact": "assume"}}).json()
    status = lambda body, key: next(i["status"] for i in body["items"] if i["key"] == key)  # noqa: E731
    assert status(before, "art34_1") == "CONDITIONAL" and status(after, "art34_1") == "REQUIRED"


@pytest.mark.parametrize("payload", [{"spec": "   "}, {"spec": "가" * 501}, {}])
def test_invalid_spec_is_rejected(payload):
    assert client.post("/api/build", json=payload).status_code == 422


def test_article_lookup():
    assert client.get("/api/articles/ARTICLE_33_1_A").json()["obligation"] == "MUST"
    assert client.get("/api/articles/NOPE").status_code == 404
