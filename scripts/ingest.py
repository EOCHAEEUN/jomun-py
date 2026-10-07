# ingest.py — 법령 PDF → 전처리·청킹 → Chroma 적재
#
# 실행:  python -m scripts.ingest
from collections import Counter

from app.config import CHUNKS_PATH, EMBEDDING_PROVIDER, VECTORSTORE_DIR
from app.rag import preprocess
from app.rag.store import build_collection


def main():
    chunks = preprocess.run()
    print(f"[1/2] 전처리 완료: 청크 {len(chunks)}개 → {CHUNKS_PATH.relative_to(CHUNKS_PATH.parents[2])}")
    tagged = sum(1 for c in chunks if c["tagged"])
    print(f"      태깅 레코드 메타데이터 {tagged}개 / Clause Parser 자동 태깅 {len(chunks) - tagged}개")
    print("      수범자 분포:", dict(Counter(c["addressee"] for c in chunks)))

    count = build_collection(chunks)
    print(f"[2/2] Chroma 적재 완료: {count}개 (임베딩: {EMBEDDING_PROVIDER}) → {VECTORSTORE_DIR.name}/")


if __name__ == "__main__":
    main()
