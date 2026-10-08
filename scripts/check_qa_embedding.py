"""Probe the configured QA embedding endpoint with one request and no retries."""

from openai import OpenAI, RateLimitError

from app.config import (MONOROUTER_API_KEY, MONOROUTER_BASE_URL, OPENAI_API_KEY,
                        QA_EMBEDDING_MODEL, QA_EMBEDDING_PROVIDER)


def main() -> None:
    if QA_EMBEDDING_PROVIDER == "local":
        print("QA 임베딩은 로컬 해싱으로 설정돼 있습니다.")
        return
    key = OPENAI_API_KEY if QA_EMBEDDING_PROVIDER == "openai" else MONOROUTER_API_KEY
    if not key:
        raise SystemExit(f"QA_EMBEDDING_PROVIDER={QA_EMBEDDING_PROVIDER}의 API 키가 없습니다.")
    kwargs = {"api_key": key, "max_retries": 0, "timeout": 15}
    if QA_EMBEDDING_PROVIDER == "monorouter":
        kwargs["base_url"] = MONOROUTER_BASE_URL
    client = OpenAI(**kwargs)
    try:
        vector = client.embeddings.create(model=QA_EMBEDDING_MODEL, input="고영향 인공지능 정의").data[0].embedding
    except RateLimitError as exc:
        raise SystemExit(f"QA 임베딩 API 제한(429): {exc}") from None
    print(f"QA 임베딩 응답 정상: {QA_EMBEDDING_PROVIDER}, {len(vector)}차원")


if __name__ == "__main__":
    main()
