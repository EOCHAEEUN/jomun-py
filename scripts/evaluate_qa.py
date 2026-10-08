"""QA 골든셋의 dense 기준선과 hybrid+reranking 검색 성능 비교.

실행: python -m scripts.evaluate_qa [--answers]
--answers는 실제 LLM 답변과 인용 조문을 저장하고 사람이 정확성·근거 충실성을 검토할 수 있게 한다.
"""
import argparse
import json
from pathlib import Path

from app.config import DATA_DIR
from app.rag.qa_retriever import retrieve
from app.rag.qdrant_store import ready, search_dense
from app.schemas import AskRequest

GOLD = DATA_DIR / "eval" / "qa_golden.jsonl"
OUTPUT = DATA_DIR / "eval" / "qa_results.json"


def rank_metrics(rows: list[dict], key: str, k: int = 5) -> dict:
    ranks = []
    for row in rows:
        rank = next((i for i, cid in enumerate(row[key], 1) if cid in row["gold_ids"]), None)
        ranks.append(rank)
    n = len(ranks) or 1
    return {"hit@3": round(sum(r is not None and r <= 3 for r in ranks) / n, 3),
            f"hit@{k}": round(sum(r is not None and r <= k for r in ranks) / n, 3),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 3)}


def run(with_answers: bool = False) -> dict:
    if not ready():
        raise RuntimeError("먼저 `python -m scripts.ingest_qa`를 실행하세요.")
    cases = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for case in cases:
        question = case["question"]
        row = {**case,
               "dense_ids": [h["id"] for h in search_dense(question, limit=5)],
               "hybrid_rerank_ids": [h["id"] for h in retrieve(question, limit=5)]}
        if with_answers:
            from app.rag.qa_pipeline import answer
            result = answer(AskRequest(question=question))
            row["answer"] = result.answer
            row["cited_ids"] = [s.chunk_id for s in result.sources]
            row["cited_gold"] = bool(set(row["cited_ids"]) & set(case["gold_ids"]))
            row["human_review"] = {"correctness": None, "relevance": None,
                                    "groundedness": None, "hallucination": None}
        rows.append(row)
    result = {"count": len(rows), "dense": rank_metrics(rows, "dense_ids"),
              "hybrid_rerank": rank_metrics(rows, "hybrid_rerank_ids"), "cases": rows}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", action="store_true", help="LLM 답변 및 출처를 생성해 수동 평가용으로 저장")
    args = parser.parse_args()
    result = run(args.answers)
    print(json.dumps({k: result[k] for k in ("count", "dense", "hybrid_rerank")}, ensure_ascii=False, indent=2))
    print(f"상세: {OUTPUT}")


if __name__ == "__main__":
    main()
