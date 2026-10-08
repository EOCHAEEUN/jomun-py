"""정식 BM25 vs 현재 sparse(어절+음절 bigram · log TF · L2 · Qdrant IDF) — 같은 청크 · 같은 질문으로 비교.

실행: python -m scripts.compare_bm25            (먼저 python -m scripts.ingest_qa)
결과: docs/bm25_compare.json + 표 출력

비교 행 (sparse 단독 / dense와 RRF로 합친 hybrid)
  current        지금 Qdrant sparse (어절 + 음절 2-gram, IDF는 Qdrant Modifier.IDF)
  bm25_word      Okapi BM25 (k1=1.2, b=0.75) · 공백 어절 토큰 — '그냥 BM25'
  bm25_bigram    Okapi BM25 · 지금과 같은 어절 + 음절 2-gram 토큰
  bm25_kiwi      Okapi BM25 · Kiwi 형태소 (kiwipiepy가 설치돼 있을 때만)
hybrid는 모든 행을 같은 방식(Qdrant dense 상위 50 + sparse 상위 50, RRF k=60)으로 앱에서 합쳐 공정하게 비교한다.
"""
import json
import math
import re
import shutil
import time
from collections import Counter
from datetime import date
from pathlib import Path

from openai import RateLimitError

from app.config import BASE_DIR, DATA_DIR, QA_EMBEDDING_PROVIDER, QDRANT_COLLECTION
from app.rag import qdrant_store
from scripts.compare_vectordb import _metrics, _points, _qdrant_client, _rank

GOLD = DATA_DIR / "eval" / "qa_golden.jsonl"
OUTPUT = BASE_DIR / "docs" / "bm25_compare.json"
_WORD = re.compile(r"[가-힣A-Za-z0-9]+")
K, DEPTH, RRF_K = 5, 50, 60


def tok_word(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def tok_bigram(text: str) -> list[str]:
    return list(qdrant_store._terms(text).elements())


def tok_kiwi():
    try:
        from kiwipiepy import Kiwi
    except ImportError:
        return None
    kiwi = Kiwi()
    keep = ("NN", "VV", "VA", "XR", "SL", "SN", "MA")      # 명사·동사·형용사 어간·어근·외국어·숫자·부사
    return lambda text: [t.form for t in kiwi.tokenize(text.lower()) if t.tag.startswith(keep)]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = sum(self.len) / len(docs)
        df = Counter(t for d in self.tf for t in d)
        n = len(docs)
        self.idf = {t: math.log((n - f + 0.5) / (f + 0.5) + 1) for t, f in df.items()}

    def top(self, query: list[str], k: int) -> list[int]:
        scores = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in set(query):
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            scores.append(s)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [i for i in order[:k] if scores[i] > 0]


def _embed(question: str) -> list[float]:
    """질문 임베딩 — MonoRouter 분당 요청 한도에 걸리면 기다렸다 다시 시도한다."""
    for attempt in range(4):
        try:
            vec = qdrant_store.dense_query(question)
            if QA_EMBEDDING_PROVIDER != "local":
                time.sleep(2.5)
            return vec
        except RateLimitError:
            if attempt == 3:
                raise
            time.sleep(30)


def rrf(*rankings: list[str], k: int = RRF_K) -> list[str]:
    score: Counter = Counter()
    for ranking in rankings:
        for rank, cid in enumerate(ranking, 1):
            score[cid] += 1 / (k + rank)
    return [cid for cid, _ in score.most_common()]


def run(output: Path = OUTPUT) -> dict:
    cases = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    qclient, tmp = _qdrant_client()
    try:
        qdrant_store.client = lambda: qclient
        points = _points(qclient)
        ids = [p.payload["id"] for p in points]
        # 인덱싱할 때 sparse에 넣은 글과 같은 글 (qdrant_store.index_chunks의 lexical_text)
        texts = [f"{p.payload['doc_short']} {p.payload['ref_label']} {p.payload['title']} {p.payload['text']}" for p in points]
        tokenizers = {"bm25_word": tok_word, "bm25_bigram": tok_bigram}
        if (kiwi := tok_kiwi()):
            tokenizers["bm25_kiwi"] = kiwi
        indexes = {name: BM25([fn(t) for t in texts]) for name, fn in tokenizers.items()}

        rows = []
        for index, case in enumerate(cases, 1):
            q, gold = case["question"], case["gold_ids"]
            dense = [p.payload["id"] for p in qclient.query_points(
                QDRANT_COLLECTION, query=_embed(q), using=qdrant_store.DENSE,
                limit=DEPTH, with_payload=True).points]
            sparse = {"current": [h["id"] for h in qdrant_store.search_sparse(q, limit=DEPTH)]}
            for name, bm in indexes.items():
                sparse[name] = [ids[i] for i in bm.top(tokenizers[name](q), DEPTH)]
            got = {f"{name}_sparse": lst[:K] for name, lst in sparse.items()}
            got.update({f"{name}_hybrid": rrf(dense, lst)[:K] for name, lst in sparse.items()})
            got["dense"] = dense[:K]
            rows.append({"id": case["id"], "question": q, "gold_ids": gold,
                         "ranks": {k: _rank(v, gold) for k, v in got.items()}, "top5": got})
            print(f"{index}/{len(cases)} {case['id']}", flush=True)
    finally:
        qclient.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    names = list(rows[0]["ranks"])
    result = {
        "meta": {"date": date.today().isoformat(), "questions": len(rows), "chunks": len(points),
                 "bm25": {"k1": 1.2, "b": 0.75}, "hybrid": f"Qdrant dense 상위 {DEPTH} + sparse 상위 {DEPTH}, RRF k={RRF_K}",
                 "kiwi": "bm25_kiwi" in indexes},
        "rows": {n: _metrics([r["ranks"][n] for r in rows]) for n in names},
        "cases": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    res = run()
    print(f"\n질문 {res['meta']['questions']}개 · 청크 {res['meta']['chunks']}개 · Kiwi {'사용' if res['meta']['kiwi'] else '미설치'}")
    print(f"{'방식':<22}{'Hit@1':>7}{'Hit@3':>7}{'Hit@5':>7}{'MRR':>7}")
    for name, m in res["rows"].items():
        print(f"{name:<22}{m['hit@1']:>7}{m['hit@3']:>7}{m['hit@5']:>7}{m['mrr']:>7}")


if __name__ == "__main__":
    main()
