# store.py — Chroma 벡터 DB 적재·검색
import logging
from functools import lru_cache

import chromadb

from app.config import COLLECTION_NAME, EMBEDDING_PROVIDER, VECTORSTORE_DIR
from app.rag.embeddings import get_embedding_function

log = logging.getLogger(__name__)
META_KEYS = ["ref_label", "title", "chapter", "article", "paragraph", "page", "tagged",
             "addressee", "obligation", "external", "flags", "status_rule", "penalty_type"]


def _client() -> chromadb.ClientAPI:
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(VECTORSTORE_DIR))


def build_collection(chunks: list[dict]) -> int:
    """청크를 새로 적재한다 (기존 컬렉션은 지우고 다시 만든다)"""
    client = _client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    col = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine", "embedding_provider": EMBEDDING_PROVIDER},
    )
    metadatas = []
    for c in chunks:
        meta = {k: c.get(k) for k in META_KEYS}
        # Chroma 메타데이터는 str/int/float/bool만 허용 → None은 빈 값으로
        metadatas.append({k: ("" if v is None else v) for k, v in meta.items()})
    col.add(
        ids=[c["id"] for c in chunks],
        # 제목·조문 번호를 같이 넣으면 검색이 조금 더 안정적이다
        documents=[f"[{c['ref_label']} {c['title']}] {c['text']}" for c in chunks],
        metadatas=metadatas,
    )
    get_collection.cache_clear()
    return col.count()


@lru_cache
def get_collection():
    """적재된 컬렉션 (없으면 None)"""
    try:
        col = _client().get_collection(COLLECTION_NAME, embedding_function=get_embedding_function())
        return col if col.count() > 0 else None
    except Exception as e:
        log.info("Chroma 컬렉션 없음 — `python -m scripts.ingest`로 먼저 적재하세요 (%s)", e)
        return None


def search(query: str, k: int = 5, where: dict | None = None) -> list[dict]:
    col = get_collection()
    if col is None:
        return []
    res = col.query(query_texts=[query], n_results=k, where=where)
    hits = []
    for i, cid in enumerate(res["ids"][0]):
        meta = res["metadatas"][0][i]
        hits.append({
            "id": cid,
            "ref_label": meta.get("ref_label"),
            "title": meta.get("title"),
            "addressee": meta.get("addressee"),
            "obligation": meta.get("obligation"),
            "score": round(1 - res["distances"][0][i], 3),   # cosine 유사도
            "snippet": res["documents"][0][i][:120],
        })
    return hits
