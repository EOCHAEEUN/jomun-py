"""Chroma vs Qdrant — 같은 청크 · 같은 벡터 · 같은 질문으로 '벡터 DB만' 바꿨을 때와 검색 방식을 바꿨을 때를 나눠 비교.

실행: python -m scripts.compare_vectordb            (먼저 python -m scripts.ingest_qa)
결과: docs/vectordb_compare.json + 표 출력

비교 행
  chroma_hash    Chroma · 로컬 해싱 임베딩 (지금 /api/build와 같은 임베딩)        — 임베딩 효과
  chroma_dense   Chroma · Qdrant에 저장된 것과 같은 OpenAI 임베딩 벡터            — DB만 바꾼 효과
  qdrant_dense   Qdrant · 같은 벡터
  qdrant_sparse / qdrant_hybrid / qdrant_multi / qdrant_rerank   Qdrant 단계별 (Chroma 로컬은 sparse 인덱스 미지원)
질문 임베딩은 질문당 한 번만 만들고 모든 dense 행이 같이 쓴다. 지연 시간은 임베딩을 뺀 DB 검색만 잰다.
"""
import argparse
import json
import shutil
import statistics
import tempfile
import time
from datetime import date
from pathlib import Path

import chromadb
from qdrant_client import QdrantClient, models

from app.config import BASE_DIR, DATA_DIR, QA_EMBEDDING_MODEL, QA_EMBEDDING_PROVIDER, QDRANT_COLLECTION, QDRANT_PATH, QDRANT_URL
from app.rag import qdrant_store
from app.rag.embeddings import KoreanHashingEmbedding

GOLD = DATA_DIR / "eval" / "qa_golden.jsonl"
OUTPUT = BASE_DIR / "docs" / "vectordb_compare.json"
K = 5
ROWS = {
    "chroma_hash": "Chroma · 로컬 해싱 임베딩",
    "chroma_dense": "Chroma · OpenAI 임베딩 (같은 벡터)",
    "qdrant_dense": "Qdrant · OpenAI 임베딩 (같은 벡터)",
    "qdrant_sparse": "Qdrant · sparse (어휘)",
    "qdrant_hybrid": "Qdrant · hybrid (dense+sparse RRF)",
    "qdrant_multi": "Qdrant · hybrid + 다중 쿼리",
    "qdrant_rerank": "Qdrant · hybrid + 다중 쿼리 + 재정렬",
}
HNSW = {"space": "cosine", "ef_construction": 400, "ef_search": 400, "max_neighbors": 32}


def _qdrant_client() -> tuple[QdrantClient, Path | None]:
    """서버가 로컬 Qdrant 폴더를 잠그고 있어도 읽을 수 있게 임시 복사본을 연다."""
    if QDRANT_URL:
        return QdrantClient(url=QDRANT_URL, timeout=30), None
    tmp = Path(tempfile.mkdtemp(prefix="qdrant-compare-"))
    shutil.copytree(QDRANT_PATH, tmp / "qdrant", ignore=shutil.ignore_patterns(".lock"))
    return QdrantClient(path=str(tmp / "qdrant")), tmp


def _points(client: QdrantClient) -> list:
    points, offset = [], None
    while True:
        batch, offset = client.scroll(QDRANT_COLLECTION, limit=256, offset=offset, with_payload=True, with_vectors=True)
        points += batch
        if offset is None:
            return points


def _chroma(points: list, hash_embed: KoreanHashingEmbedding):
    client = chromadb.EphemeralClient()
    dense = client.create_collection("compare_dense", configuration={"hnsw": HNSW})
    hashed = client.create_collection("compare_hash", configuration={"hnsw": HNSW})
    ids = [p.payload["id"] for p in points]
    texts = [qdrant_store.dense_text(p.payload) for p in points]
    for start in range(0, len(points), 128):
        sl = slice(start, start + 128)
        dense.add(ids=ids[sl], embeddings=[p.vector[qdrant_store.DENSE] for p in points[sl]])
        hashed.add(ids=ids[sl], embeddings=hash_embed(texts[sl]))
    return dense, hashed


def _rank(ids: list[str], gold: list[str]) -> int | None:
    return next((i for i, cid in enumerate(ids, 1) if cid in gold), None)


def _metrics(ranks: list[int | None]) -> dict:
    n = len(ranks) or 1
    hit = lambda k: round(sum(r is not None and r <= k for r in ranks) / n, 3)  # noqa: E731
    return {"hit@1": hit(1), "hit@3": hit(3), "hit@5": hit(5), "mrr": round(sum(1 / r for r in ranks if r) / n, 3)}


def _timed(fn, reps: int) -> tuple[list[str], float]:
    times, ids = [], []
    for _ in range(reps):
        start = time.perf_counter()
        ids = fn()
        times.append((time.perf_counter() - start) * 1000)
    return ids, statistics.median(times)


def run(reps: int = 20, output: Path = OUTPUT) -> dict:
    cases = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    qclient, tmp = _qdrant_client()
    try:
        qdrant_store.client = lambda: qclient          # 단계별 검색 함수가 복사본을 쓰게 한다
        points = _points(qclient)
        hash_embed = KoreanHashingEmbedding()
        chroma_dense, chroma_hash = _chroma(points, hash_embed)
        from app.rag.qa_retriever import retrieve, retrieve_multi

        rows, latency = [], {k: [] for k in ("chroma_dense", "qdrant_dense", "chroma_hash")}
        for index, case in enumerate(cases, 1):
            q, gold = case["question"], case["gold_ids"]
            qvec = qdrant_store.dense_query(q)
            hvec = hash_embed([q])[0]
            got = {}
            got["chroma_dense"], t1 = _timed(lambda: chroma_dense.query(query_embeddings=[qvec], n_results=K)["ids"][0], reps)
            got["qdrant_dense"], t2 = _timed(lambda: [p.payload["id"] for p in qclient.query_points(
                QDRANT_COLLECTION, query=qvec, using=qdrant_store.DENSE, limit=K, with_payload=True).points], reps)
            got["chroma_hash"], t3 = _timed(lambda: chroma_hash.query(query_embeddings=[hvec], n_results=K)["ids"][0], reps)
            latency["chroma_dense"].append(t1)
            latency["qdrant_dense"].append(t2)
            latency["chroma_hash"].append(t3)
            got["qdrant_sparse"] = [h["id"] for h in qdrant_store.search_sparse(q, limit=K)]
            got["qdrant_hybrid"] = [h["id"] for h in qdrant_store.search_hybrid(q, limit=50)[:K]]
            got["qdrant_multi"] = [h["id"] for h in retrieve_multi(q, limit=K)[:K]]
            got["qdrant_rerank"] = [h["id"] for h in retrieve(q, limit=K)]
            rows.append({"id": case["id"], "question": q, "gold_ids": gold,
                         "ranks": {k: _rank(v, gold) for k, v in got.items()}, "top5": got,
                         "same_dense_top5": got["chroma_dense"] == got["qdrant_dense"]})
            print(f"{index}/{len(cases)} {case['id']}", flush=True)
    finally:
        qclient.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    result = {
        "meta": {"date": date.today().isoformat(), "questions": len(rows), "chunks": len(points), "k": K,
                 "embedding": f"{QA_EMBEDDING_PROVIDER}:{QA_EMBEDDING_MODEL}", "chromadb": chromadb.__version__,
                 "latency_reps": reps, "note": "지연 시간은 두 DB 모두 로컬 내장 모드 · 질문 임베딩 제외 · 질문별 중앙값의 평균"},
        "rows": {k: {"label": v, **_metrics([r["ranks"][k] for r in rows])} for k, v in ROWS.items()},
        "dense_agreement": {"same_top5": sum(r["same_dense_top5"] for r in rows), "of": len(rows)},
        "latency_ms": {k: round(statistics.mean(v), 2) for k, v in latency.items()},
        "chroma_local_sparse": "미지원 — chromadb 로컬 모드에서 SparseVectorIndexConfig 생성 시 "
                               "'Sparse vector indexing is not enabled in local'",
        "cases": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=20, help="지연 시간 측정 반복 횟수")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    res = run(args.reps, args.output)
    print(f"\n질문 {res['meta']['questions']}개 · 청크 {res['meta']['chunks']}개 · {res['meta']['embedding']}")
    print(f"{'방식':<36}{'Hit@1':>7}{'Hit@3':>7}{'Hit@5':>7}{'MRR':>7}")
    for row in res["rows"].values():
        print(f"{row['label']:<36}{row['hit@1']:>7}{row['hit@3']:>7}{row['hit@5']:>7}{row['mrr']:>7}")
    agree = res["dense_agreement"]
    print(f"\nChroma dense와 Qdrant dense의 상위 5개가 똑같은 질문: {agree['same_top5']}/{agree['of']}")
    print(f"DB 검색 지연(ms, 임베딩 제외): {res['latency_ms']}")
    print(f"상세: {args.output}")


if __name__ == "__main__":
    main()
