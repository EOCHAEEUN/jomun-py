"""Search ranking and fusion checks for the build retriever."""

import json

from app.config import DATA_DIR
from app.engine.features import heuristic_extract
from app.rag.bm25 import BM25Index, tokenize
from app.rag.retriever import _rrf, retrieve_candidates


def _chunk(cid, text, **overrides):
    return {"id": cid, "doc": "AIACT", "kind": "LAW", "addressee": "BUSINESS",
            "doc_short": "인공지능기본법", "ref_label": "제2조", "title": "정의", "text": text, **overrides}


def test_bm25_ranks_legal_words_and_excludes_unsearchable_chunks():
    index = BM25Index([
        _chunk("MATCH", "고영향 인공지능 채용 평가"),
        _chunk("OTHER", "인공지능 기술 개발"),
        _chunk("ENGLISH", "고영향 인공지능 채용 평가", doc="AIACT_EN"),
    ])
    assert len(index.chunks) == 2
    assert index.search("채용 평가")[0]["id"] == "MATCH"
    assert "g2:채용" in tokenize("채용을 평가해요")


def test_rrf_rewards_agreement_without_mixing_raw_scores():
    dense = [{"id": "A", "score": 0.9}, {"id": "B", "score": 0.8}]
    sparse = [{"id": "B", "score": 15.0}, {"id": "C", "score": 13.0}]
    assert [hit["id"] for hit in _rrf(dense, sparse, 3)] == ["B", "A", "C"]


def test_bm25_recovers_heldout_energy_clause():
    case = next(case for case in json.loads((DATA_DIR / "eval" / "heldout_cases.json").read_text(encoding="utf-8"))
                if case["id"] == "H02")
    rag = retrieve_candidates(case["spec"], heuristic_extract(case["spec"]), strategy="bm25")
    assert rag.mode == "bm25"
    assert "ARTICLE_2_4_GA" in rag.candidates
