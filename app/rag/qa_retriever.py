"""AI 기본법 QA 검색: 다중 쿼리 → Qdrant hybrid RRF → 어휘·조문 재정렬."""
import re

from app.config import QA_TOP_K
from app.engine.features import heuristic_extract
from app.rag.qdrant_store import search_hybrid
from app.rag.retriever import PURPOSE_QUERY
from app.schemas import ServiceFeatures

_ARTICLE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")
_WORDS = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOP = {"인공지능", "서비스", "우리", "대한", "관련", "어떻게", "무엇", "있나요", "하나요", "경우", "법률"}
_DEFINITION = re.compile(r"([가-힣 ]{2,20}?)(?:이란|란|의 뜻|의 정의|란 무엇)")
_DEFINED_TERM = re.compile(r'["“]([^"”]{2,30})["”]이란')
_DOMAIN_ID = {"RECRUITMENT": "ARTICLE_2_4_SA", "LENDING": "ARTICLE_2_4_SA",
              "HEALTHCARE": "ARTICLE_2_4_DA", "MEDICAL_DEVICE": "ARTICLE_2_4_RA",
              "ENERGY": "ARTICLE_2_4_GA", "DRINKING_WATER": "ARTICLE_2_4_NA",
              "NUCLEAR": "ARTICLE_2_4_MA", "TRANSPORT": "ARTICLE_2_4_A",
              "PUBLIC_SERVICE_DECISION": "ARTICLE_2_4_JA", "STUDENT_ASSESSMENT": "ARTICLE_2_4_CHA"}


def rerank(question: str, hits: list[dict], limit: int = QA_TOP_K) -> list[dict]:
    """조문 번호 일치와 질문 핵심어의 본문 포함 여부로 RRF 후보를 다시 정렬한다."""
    terms = {t.lower() for t in _WORDS.findall(question)} - _STOP
    article = _ARTICLE.search(question)
    definition = _DEFINITION.search(question)
    term = definition.group(1).strip() if definition else ""
    asks_definition = bool(definition or re.search(r"정의|뜻|무엇인가", question))
    f = heuristic_extract(question)
    domain_id = _DOMAIN_ID.get(f.purpose or "")
    if f.purpose == "CRIMINAL_INVESTIGATION" and f.uses_biometric:
        domain_id = "ARTICLE_2_4_BA"
    wanted = int(article.group(1)) if article else None
    sub = int(article.group(2)) if article and article.group(2) else None
    for hit in hits:
        body = f"{hit.get('title', '')} {hit.get('text', '')}".lower()
        coverage = sum(1 for term in terms if term in body) / max(len(terms), 1)
        exact = 1.0 if wanted is not None and hit.get("article") == wanted and (
            sub is None or hit.get("article_sub") == sub) else 0.0
        defined = _DEFINED_TERM.search(hit.get("text", ""))
        definition_match = 1.0 if asks_definition and defined and (
            defined.group(1) in question or (term and term in defined.group(1))) else 0.0
        domain_match = 1.0 if "고영향" in question and domain_id == hit["id"] else 0.0
        hit["rerank_score"] = (hit.get("fusion_score", hit.get("score", 0.0))
                               + 0.14 * coverage + 0.28 * exact + 0.35 * definition_match
                               + 0.08 * domain_match)
    return sorted(hits, key=lambda h: (-h["rerank_score"], h["id"]))[:limit]


def retrieve(question: str, features: ServiceFeatures | None = None, limit: int = QA_TOP_K) -> list[dict]:
    queries = [question]
    # 일반 질문에서도 법률 용어로 확장해 영역 조문의 검색 누락을 줄인다.
    query_features = features or heuristic_extract(question)
    if query_features.purpose in PURPOSE_QUERY:
        queries.append(PURPOSE_QUERY[query_features.purpose])
    if features and features.generative:
        queries.append("생성형 인공지능 결과물 사전 고지 표시 인공지능기본법")

    by_id: dict[str, dict] = {}
    for query in queries:
        for rank, hit in enumerate(search_hybrid(query, limit=max(limit * 10, 50)), start=1):
            cid = hit["id"]
            if cid not in by_id:
                by_id[cid] = {**hit, "fusion_score": 0.0}
            by_id[cid]["fusion_score"] += 1.0 / (60 + rank)
    return rerank(question, list(by_id.values()), limit=limit)
