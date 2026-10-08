"""QA 골든셋에서 검색 단계별 기여를 같은 질문과 Top-K로 비교.

실행: python -m scripts.evaluate_qa [--answers]
--answers는 실제 LLM 답변과 인용 조문을 저장하고 사람이 정확성·근거 충실성을 검토할 수 있게 한다.
"""
import argparse
import json
import time
from pathlib import Path

from openai import RateLimitError

from app.config import DATA_DIR, QA_EMBEDDING_PROVIDER
from app.engine.features import apply_answers, extract
from app.rag.qa_retriever import retrieve, retrieve_multi
from app.rag.qdrant_store import ready, search_dense, search_hybrid, search_sparse
from app.schemas import AskRequest

GOLD = DATA_DIR / "eval" / "qa_golden.jsonl"
OUTPUT = DATA_DIR / "eval" / "qa_results.json"
STAGES = ("dense", "sparse", "hybrid", "hybrid_multi", "hybrid_rerank")


def rank_metrics(rows: list[dict], key: str, k: int = 5) -> dict:
    # 근거가 없는 질문은 답변의 유보 능력을 평가하며 검색 Hit의 분모에서는 제외한다.
    ranks = []
    eligible = []
    for row in rows:
        if not row["gold_ids"]:
            continue
        eligible.append(row)
        rank = next((i for i, cid in enumerate(row[key], 1) if cid in row["gold_ids"]), None)
        ranks.append(rank)
    n = len(ranks) or 1
    gold_count = sum(len(set(row["gold_ids"])) for row in eligible) or 1
    return {"hit@3": round(sum(r is not None and r <= 3 for r in ranks) / n, 3),
            f"hit@{k}": round(sum(r is not None and r <= k for r in ranks) / n, 3),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 3),
            "all_gold@3": round(sum(set(row["gold_ids"]) <= set(row[key][:3]) for row in eligible) / n, 3),
            f"all_gold@{k}": round(sum(set(row["gold_ids"]) <= set(row[key][:k]) for row in eligible) / n, 3),
            f"gold_coverage@{k}": round(sum(len(set(row["gold_ids"]) & set(row[key][:k]))
                                         for row in eligible) / gold_count, 3)}


def run(with_answers: bool = False, output: Path = OUTPUT, stages: tuple[str, ...] = STAGES,
        gold: Path | None = None) -> dict:
    if not ready():
        raise RuntimeError("먼저 `python -m scripts.ingest_qa`를 실행하세요.")
    cases = [json.loads(line) for line in (gold or GOLD).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for index, case in enumerate(cases, 1):
        question = case["question"]
        service = case.get("service_description")
        search_text = question if not service or service in question else f"{question} {service}"
        features = None
        if service and ("hybrid_multi" in stages or "hybrid_rerank" in stages):
            features, _ = extract(service)
            features = apply_answers(features, case.get("answers", {}))
        for attempt in range(4):
            try:
                row = {**case}
                if "dense" in stages:
                    row["dense_ids"] = [h["id"] for h in search_dense(search_text, limit=5)]
                if "sparse" in stages:
                    row["sparse_ids"] = [h["id"] for h in search_sparse(search_text, limit=5)]
                if "hybrid" in stages:
                    # Match the per-query candidate depth used by retrieve_multi.
                    row["hybrid_ids"] = [h["id"] for h in search_hybrid(search_text, limit=50)[:5]]
                if "hybrid_multi" in stages:
                    row["hybrid_multi_ids"] = [h["id"] for h in retrieve_multi(search_text, features, limit=5)[:5]]
                if "hybrid_rerank" in stages:
                    row["hybrid_rerank_ids"] = [h["id"] for h in retrieve(search_text, features=features, limit=5)]
                break
            except RateLimitError:
                if attempt == 3:
                    raise
                time.sleep(20)
        if with_answers:
            from app.rag.qa_pipeline import answer
            result = answer(AskRequest(question=question,
                                       service_description=case.get("service_description"),
                                       answers=case.get("answers", {})))
            row["answer"] = result.answer
            row["cited_ids"] = [s.chunk_id for s in result.sources]
            row["cited_gold"] = (bool(set(row["cited_ids"]) & set(case["gold_ids"]))
                                 if case["gold_ids"] else None)
            row["human_review"] = {"correctness": None, "relevance": None,
                                    "groundedness": None, "hallucination": None,
                                    "factual_claims": None, "unsupported_claims": None}
        rows.append(row)
        print(f"검색 평가 {index}/{len(cases)}: {case['id']}", flush=True)
        if QA_EMBEDDING_PROVIDER != "local" and index < len(cases):
            time.sleep(2)
    result = {"count": len(rows), "retrieval_evaluated": sum(bool(row["gold_ids"]) for row in rows),
              **{stage: rank_metrics(rows, f"{stage}_ids") for stage in stages},
              "cases": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", action="store_true", help="LLM 답변 및 출처를 생성해 수동 평가용으로 저장")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="평가 결과 JSON 경로")
    parser.add_argument("--gold", type=Path, default=GOLD, help="질문·정답 JSONL 경로")
    parser.add_argument("--stages", default=",".join(STAGES),
                        help="쉼표로 구분한 측정 단계 (dense,sparse,hybrid,hybrid_multi,hybrid_rerank)")
    args = parser.parse_args()
    stages = tuple(dict.fromkeys(args.stages.split(",")))
    if not stages or any(stage not in STAGES for stage in stages):
        parser.error(f"--stages는 {','.join(STAGES)} 중에서 선택하세요.")
    result = run(args.answers, args.output, stages, args.gold)
    print(json.dumps({k: result[k] for k in ("count", *stages)},
                     ensure_ascii=False, indent=2))
    print(f"상세: {args.output}")


if __name__ == "__main__":
    main()
