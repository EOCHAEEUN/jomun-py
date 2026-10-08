"""Docling 법령 청크의 QA 전용 Qdrant 인덱스.

기존 /api/build의 Chroma 인덱스와 분리한다. Qdrant는 dense 벡터와
어휘 기반 sparse 벡터를 함께 저장하고 RRF로 검색 결과를 합친다.
"""
import hashlib
import logging
import math
import re
import uuid
import atexit
from collections import Counter
from functools import lru_cache

from qdrant_client import QdrantClient, models

from app.config import (MONOROUTER_API_KEY, MONOROUTER_BASE_URL, OPENAI_API_KEY,
                        QA_EMBEDDING_MODEL, QDRANT_COLLECTION, QDRANT_PATH, QDRANT_URL)
from app.rag.embeddings import KoreanHashingEmbedding

log = logging.getLogger(__name__)
DENSE = "dense"
SPARSE = "lexical"
QA_DOCS = {"AIACT", "DECREE"}
_WORD = re.compile(r"[가-힣A-Za-z0-9]+")


def _terms(text: str) -> Counter[str]:
    """한국어 형태소 분석기 없이도 조문 용어와 인접 글자를 찾는 어휘 특성."""
    tokens = _WORD.findall(text.lower())
    terms: Counter[str] = Counter(tokens)
    for token in tokens:
        if re.search(r"[가-힣]", token):
            terms.update(token[i:i + 2] for i in range(len(token) - 1))
    return terms


def lexical_vector(text: str) -> models.SparseVector:
    terms = _terms(text)
    weights: dict[int, float] = {}
    for term, count in terms.items():
        index = int.from_bytes(hashlib.blake2b(term.encode(), digest_size=4).digest(), "big")
        weights[index] = weights.get(index, 0.0) + 1.0 + math.log(count)
    norm = math.sqrt(sum(v * v for v in weights.values())) or 1.0
    indices = sorted(weights)
    return models.SparseVector(indices=indices, values=[weights[i] / norm for i in indices])


def dense_vectors(texts: list[str]) -> list[list[float]]:
    # 키가 있으면 의미 임베딩, 없으면 재현 가능한 로컬 해싱 베이스라인.
    from app.config import QA_EMBEDDING_PROVIDER
    if QA_EMBEDDING_PROVIDER in ("openai", "monorouter"):
        key = OPENAI_API_KEY if QA_EMBEDDING_PROVIDER == "openai" else MONOROUTER_API_KEY
        if not key:
            raise RuntimeError(f"QA_EMBEDDING_PROVIDER={QA_EMBEDDING_PROVIDER}의 API 키가 없습니다.")
        from langchain_openai import OpenAIEmbeddings
        kwargs = {"model": QA_EMBEDDING_MODEL, "api_key": key}
        if QA_EMBEDDING_PROVIDER == "monorouter":
            kwargs["base_url"] = MONOROUTER_BASE_URL
        return OpenAIEmbeddings(**kwargs).embed_documents(texts)
    if QA_EMBEDDING_PROVIDER != "local":
        raise ValueError(f"지원하지 않는 QA_EMBEDDING_PROVIDER: {QA_EMBEDDING_PROVIDER}")
    embedder = KoreanHashingEmbedding()
    return embedder(texts)


@lru_cache(maxsize=256)
def dense_query(text: str) -> list[float]:
    from app.config import QA_EMBEDDING_PROVIDER
    if QA_EMBEDDING_PROVIDER in ("openai", "monorouter"):
        key = OPENAI_API_KEY if QA_EMBEDDING_PROVIDER == "openai" else MONOROUTER_API_KEY
        if not key:
            raise RuntimeError(f"QA_EMBEDDING_PROVIDER={QA_EMBEDDING_PROVIDER}의 API 키가 없습니다.")
        from langchain_openai import OpenAIEmbeddings
        kwargs = {"model": QA_EMBEDDING_MODEL, "api_key": key}
        if QA_EMBEDDING_PROVIDER == "monorouter":
            kwargs["base_url"] = MONOROUTER_BASE_URL
        return OpenAIEmbeddings(**kwargs).embed_query(text)
    if QA_EMBEDDING_PROVIDER != "local":
        raise ValueError(f"지원하지 않는 QA_EMBEDDING_PROVIDER: {QA_EMBEDDING_PROVIDER}")
    return KoreanHashingEmbedding()([text])[0]


@lru_cache(maxsize=1)
def client() -> QdrantClient:
    if QDRANT_URL:
        return QdrantClient(url=QDRANT_URL, timeout=30)
    QDRANT_PATH.mkdir(parents=True, exist_ok=True)
    db = QdrantClient(path=str(QDRANT_PATH))
    atexit.register(db.close)
    return db


def ready() -> bool:
    try:
        return client().collection_exists(QDRANT_COLLECTION) and client().count(QDRANT_COLLECTION, exact=True).count > 0
    except Exception as exc:
        log.info("Qdrant QA 인덱스 미준비: %s", exc)
        return False


def count() -> int:
    return client().count(QDRANT_COLLECTION, exact=True).count if ready() else 0


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "jomun-py/qa/" + chunk_id))


def index_chunks(chunks: list[dict], batch_size: int = 64) -> int:
    """원본 PDF에서 변환한 AI 기본법·시행령 청크를 새 컬렉션으로 적재."""
    selected = [c for c in chunks if c["doc"] in QA_DOCS and c["text"].strip()]
    if not selected:
        raise ValueError("QA에 적재할 법률 청크가 없습니다.")
    # 외부 임베딩 호출이 실패해도 기존 컬렉션을 지우지 않도록 벡터를 먼저 준비한다.
    prepared = []
    for start in range(0, len(selected), batch_size):
        batch = selected[start:start + batch_size]
        texts = [f"{c['doc_short']} {c['ref_label']} {c['title']} {c['text']}" for c in batch]
        dense = dense_vectors(texts)
        points = []
        for c, search_text, vector in zip(batch, texts, dense):
            payload = {k: c.get(k) for k in ("id", "doc", "doc_short", "kind", "ref_label", "text",
                                              "title", "article", "article_sub", "paragraph", "page", "source_file",
                                              "source_sha256", "chapter", "lead")}
            points.append(models.PointStruct(id=point_id(c["id"]), vector={DENSE: vector,
                                                                            SPARSE: lexical_vector(search_text)},
                                             payload=payload))
        prepared.append(points)
    db = client()
    if db.collection_exists(QDRANT_COLLECTION):
        db.delete_collection(QDRANT_COLLECTION)
    db.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config={DENSE: models.VectorParams(size=len(prepared[0][0].vector[DENSE]),
                                                   distance=models.Distance.COSINE)},
        sparse_vectors_config={SPARSE: models.SparseVectorParams()},
    )
    for points in prepared:
        db.upsert(collection_name=QDRANT_COLLECTION, points=points, wait=True)
    return db.count(QDRANT_COLLECTION, exact=True).count


def _hits(points) -> list[dict]:
    return [{**(point.payload or {}), "score": float(point.score)} for point in points]


def search_dense(query: str, limit: int = 10) -> list[dict]:
    if not ready():
        return []
    result = client().query_points(collection_name=QDRANT_COLLECTION, query=dense_query(query),
                                   using=DENSE, limit=limit, with_payload=True)
    return _hits(result.points)


def search_hybrid(query: str, limit: int = 16) -> list[dict]:
    if not ready():
        return []
    result = client().query_points(
        collection_name=QDRANT_COLLECTION,
        prefetch=[models.Prefetch(query=dense_query(query), using=DENSE, limit=max(limit * 2, 20)),
                  models.Prefetch(query=lexical_vector(query), using=SPARSE, limit=max(limit * 2, 20))],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=limit, with_payload=True,
    )
    return _hits(result.points)


def get_chunks(chunk_ids: list[str]) -> list[dict]:
    if not chunk_ids or not ready():
        return []
    points = client().retrieve(collection_name=QDRANT_COLLECTION,
                               ids=[point_id(i) for i in chunk_ids], with_payload=True)
    by_id = {p.payload["id"]: p.payload for p in points if p.payload}
    return [by_id[i] for i in chunk_ids if i in by_id]
