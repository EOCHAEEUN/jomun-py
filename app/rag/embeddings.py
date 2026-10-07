# embeddings.py — Chroma 임베딩 함수
#
# local  : API 키 없이 동작하는 한글 글자 n-gram 해싱 임베딩.
#          의미 검색 성능은 낮지만, 단어가 겹치면 끌려가는 'Naive RAG'의 한계를
#          그대로 보여주는 베이스라인으로 쓰기 좋다. (예: "얼굴" → 바목)
# openai : text-embedding-3-small 등 (EMBEDDING_PROVIDER=openai)
import hashlib
import math
import re
from collections import Counter

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.utils.embedding_functions import register_embedding_function

from app.config import EMBEDDING_MODEL, EMBEDDING_PROVIDER, OPENAI_API_KEY


@register_embedding_function
class KoreanHashingEmbedding(EmbeddingFunction[Documents]):
    """글자 2·3-gram을 해싱해 고정 길이 벡터로 만든다 (L2 정규화, sublinear tf)"""

    def __init__(self, dim: int = 1024):
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        text = re.sub(r"[^0-9A-Za-z가-힣]+", " ", text.lower())
        grams: Counter = Counter()
        for token in text.split():
            padded = f" {token} "
            for n in (2, 3):
                for i in range(len(padded) - n + 1):
                    grams[padded[i:i + n]] += 1
        vec = [0.0] * self.dim
        for gram, count in grams.items():
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
            sign = 1.0 if (h >> 1) & 1 else -1.0
            vec[h % self.dim] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def __call__(self, input: Documents) -> Embeddings:
        return [self._vector(t) for t in input]

    @staticmethod
    def name() -> str:
        return "korean-hashing"

    def get_config(self) -> dict:
        return {"dim": self.dim}

    @staticmethod
    def build_from_config(config: dict) -> "KoreanHashingEmbedding":
        return KoreanHashingEmbedding(dim=config.get("dim", 1024))

    def default_space(self):
        return "cosine"


def get_embedding_function() -> EmbeddingFunction:
    if EMBEDDING_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("EMBEDDING_PROVIDER=openai 이면 .env에 OPENAI_API_KEY가 필요합니다.")
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        return OpenAIEmbeddingFunction(api_key=OPENAI_API_KEY, model_name=EMBEDDING_MODEL)
    return KoreanHashingEmbedding()
