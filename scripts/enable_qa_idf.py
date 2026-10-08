"""Enable Qdrant sparse IDF on the existing QA index without an embedding API call.

Run while the local Qdrant database is not in use by the API server:
    python -m scripts.enable_qa_idf
"""

from app.rag.qdrant_store import QDRANT_COLLECTION, count, enable_sparse_idf


def main() -> None:
    changed = enable_sparse_idf()
    print(f"Qdrant {QDRANT_COLLECTION}: {count()} points, IDF {'enabled' if changed else 'already enabled'}")


if __name__ == "__main__":
    main()
