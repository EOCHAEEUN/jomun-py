# config.py — 설정값을 한 곳에 모은다 (.env에서 읽음)
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── 경로 ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_PDF = DATA_DIR / "raw" / "ai_basic_act_20260122.pdf"
TAGGED_PATH = DATA_DIR / "tagged" / "articles.json"      # 조문 clause 태깅 (핵심 데이터)
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


def use_llm() -> bool:
    """특성 추출에 LLM을 쓸지 결정"""
    if FEATURE_EXTRACTOR == "heuristic":
        return False
    if FEATURE_EXTRACTOR == "llm":
        return True
    return bool(OPENAI_API_KEY)
