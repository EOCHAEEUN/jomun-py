"""AI 기본법 PDF → Docling → 구조 청크 → Qdrant hybrid QA 인덱스.

실행: python -m scripts.ingest_qa
"""
from collections import Counter

from app.rag.preprocess import build_all, load_sources
from app.rag.qdrant_store import QA_DOCS, index_chunks


def main() -> None:
    sources = [src for src in load_sources() if src["id"] in QA_DOCS]
    chunks, _ = build_all(sources)
    count = index_chunks(chunks)
    print(f"Docling 청크: {dict(Counter(c['doc_short'] for c in chunks))}")
    print(f"Qdrant QA 적재 완료: {count}개")


if __name__ == "__main__":
    main()
