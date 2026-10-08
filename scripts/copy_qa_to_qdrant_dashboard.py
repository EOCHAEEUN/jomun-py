"""Copy the local QA collection to a separate Qdrant server for Web UI inspection.

The existing server collection is never overwritten. Run again with a new
``--collection`` name after re-ingesting the local QA data.
"""

import argparse

from qdrant_client import QdrantClient, models

from app.config import QDRANT_COLLECTION, QDRANT_PATH


def copy_collection(url: str, destination: str) -> int:
    local = QdrantClient(path=str(QDRANT_PATH))
    server = QdrantClient(url=url)
    try:
        if not local.collection_exists(QDRANT_COLLECTION):
            raise RuntimeError(f"로컬 컬렉션이 없습니다: {QDRANT_COLLECTION}")
        if server.collection_exists(destination):
            raise RuntimeError(f"서버 컬렉션이 이미 있습니다: {destination} (덮어쓰지 않음)")

        config = local.get_collection(QDRANT_COLLECTION).config.params
        server.create_collection(
            collection_name=destination,
            vectors_config=config.vectors,
            sparse_vectors_config=config.sparse_vectors,
        )
        offset, copied = None, 0
        while True:
            points, offset = local.scroll(
                QDRANT_COLLECTION, limit=64, offset=offset,
                with_payload=True, with_vectors=True,
            )
            if points:
                server.upsert(
                    collection_name=destination,
                    points=[models.PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points],
                    wait=True,
                )
                copied += len(points)
            if offset is None:
                break
        actual = server.count(destination, exact=True).count
        if actual != copied:
            raise RuntimeError(f"복사 개수 불일치: 보낸 점 {copied}, 서버 점 {actual}")
        return actual
    finally:
        local.close()
        server.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:6333")
    parser.add_argument("--collection", default=QDRANT_COLLECTION)
    args = parser.parse_args()
    count = copy_collection(args.url, args.collection)
    print(f"{args.collection}: {count}개 복사 완료")
    print(args.url.rstrip("/") + "/dashboard")


if __name__ == "__main__":
    main()
