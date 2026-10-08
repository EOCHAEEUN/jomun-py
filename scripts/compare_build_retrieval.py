"""Compare /api/build's Chroma, BM25, and RRF retrieval on identical cases."""

import json
from datetime import date

from app.config import DATA_DIR, EVAL_PATH, RETRIEVAL_TOP_K
from app.rag.bm25 import get_index
from app.rag.retriever import resolve_strategy
from app.rag.store import get_collection
from scripts.evaluate import HELDOUT_PATH, K, run


def main() -> None:
    modes = ("chroma", "bm25", "hybrid")
    for mode in modes:
        if resolve_strategy(mode) != mode:
            raise SystemExit(f"{mode} 인덱스가 준비되지 않았습니다.")

    splits = {"dev": EVAL_PATH, "heldout": HELDOUT_PATH}
    results = {mode: run(splits, strategy=mode) for mode in modes}
    comparison = {
        "date": date.today().isoformat(),
        "scope": "/api/build legal-clause retrieval",
        "selection": "BM25 selected using dev only; heldout used once for verification",
        "top_k_per_query": RETRIEVAL_TOP_K,
        "hit_k_per_query": K,
        "rrf_rank_constant": 60,
        "rrf_input_depth": "max(4 * requested_k, 20)",
        "chroma_chunks": get_collection().count(),
        "bm25_searchable_chunks": len(get_index().chunks),
        "modes": {
            mode: {
                split: {
                    "summary": result["summary"],
                    "cases": {row["id"]: {
                        "gold_retrieval": row["retrieval"]["gold"],
                        "candidate_hits": row["retrieval"]["candidate_hits"],
                        "failed_checks": [c["check"] for c in row["final_checks"] if not c["ok"]],
                    } for row in result["rows"]},
                } for split, result in splits_result.items()
            } for mode, splits_result in results.items()
        },
    }
    output = DATA_DIR.parent / "docs" / "build_retrieval_compare.json"
    output.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for mode, splits_result in results.items():
        print(mode, *(f"{split}: recall={value['summary']['candidate_recall']} "
                       f"final={value['summary']['final_accuracy']}" for split, value in splits_result.items()))
    print(output)


if __name__ == "__main__":
    main()
