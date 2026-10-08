# config.py — 설정값을 한 곳에 모은다 (.env에서 읽음)
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── 경로 ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"                                # 원본 PDF 6종
SOURCES_PATH = DATA_DIR / "sources.json"                  # 데이터 목록 (문서별 종류·파서·역할)
TAGGED_PATH = DATA_DIR / "tagged" / "articles.json"      # 조문 clause 태깅 (핵심 데이터)
EN_ARTICLES_PATH = DATA_DIR / "tagged" / "en_articles.json"  # 영문 조문 매핑 (ingest가 갱신)
DECOMPILED_DIR = DATA_DIR / "tagged" / "decompiled"       # 디컴파일 코드 스니펫
CHUNKS_PATH = DATA_DIR / "processed" / "chunks.json"      # 전처리 결과 (ingest가 생성)
VECTORSTORE_DIR = DATA_DIR / "vectorstore"                # Chroma 저장 위치 (ingest가 생성)
EVAL_PATH = DATA_DIR / "eval" / "cases.json"              # 평가셋
STATIC_DIR = BASE_DIR / "app" / "static"

# ── LLM (특성 추출) ───────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
# auto: API 키가 있으면 LLM, 없으면 규칙 기반(heuristic) 추출기 사용
FEATURE_EXTRACTOR = os.getenv("FEATURE_EXTRACTOR", "auto").lower()   # auto | llm | heuristic

# ── 임베딩 / Chroma ──────────────────────────────────────────
# local: API 키 없이 동작하는 글자 n-gram 해싱 임베딩 (데모·Naive 베이스라인용)
# openai: text-embedding-3-small 등
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local").lower()  # local | openai
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "law_articles")
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
BUILD_RETRIEVAL_MODE = os.getenv("BUILD_RETRIEVAL_MODE", "bm25").strip().lower()  # chroma | bm25 | hybrid

# ── /ask: Qdrant 기반 AI 기본법 QA ───────────────────────────
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()  # 비우면 WSL 로컬 Qdrant
QDRANT_PATH = DATA_DIR / "qdrant"
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "ai_basic_law_qa").strip()
QA_TOP_K = int(os.getenv("QA_TOP_K", "5"))
MONOROUTER_API_KEY = os.getenv("MONOROUTER_API_KEY", "").strip()
MONOROUTER_BASE_URL = os.getenv("MONOROUTER_BASE_URL", "https://api.monorouter.com").strip()
# 기존 LLM_MODEL=gpt-4o-mini는 이 MonoRouter의 현재 허용 목록에 없어 QA는 별도 기본값 사용.
QA_LLM_MODEL = os.getenv("QA_LLM_MODEL", "gpt-4.1").strip()
QA_EMBEDDING_PROVIDER = os.getenv("QA_EMBEDDING_PROVIDER", "monorouter" if MONOROUTER_API_KEY else "local").strip().lower()
QA_EMBEDDING_MODEL = os.getenv("QA_EMBEDDING_MODEL", "text-embedding-3-small").strip()


def use_llm() -> bool:
    """특성 추출에 LLM을 쓸지 결정"""
    if FEATURE_EXTRACTOR == "heuristic":
        return False
    if FEATURE_EXTRACTOR == "llm":
        return True
    return bool(OPENAI_API_KEY)
