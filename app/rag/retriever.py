# retriever.py — RAG 후보 조문 검색
#
#   서비스 설명 + 추출된 특성
#     → ① 쿼리 만들기: 원문 그대로(naive) + 특성을 법률 용어로 바꾼 쿼리(feature-enriched)
#     → ② BM25 기본 검색: 쿼리마다 top-k, 문서·수범자 필터 (Chroma·RRF 선택 가능)
#     → ③ 참조 그래프 확장: 찾은 조문의 상위 조문, refs, '고영향이면 적용되는 조문'
#     → 후보 집합 (Rule Engine이 이 후보들의 적용 조건을 검증한다)
#
# 선택한 검색 인덱스가 없으면 파이프라인은 '규칙만' 모드로 동작한다.
import logging
from dataclasses import dataclass, field

from app.config import BUILD_RETRIEVAL_MODE, RETRIEVAL_TOP_K
from app.engine.law import get_lawbook
from app.rag.bm25 import EXCLUDED_ADDRESSEES, SEARCHABLE_DOCS, get_index, search as bm25_search
from app.schemas import ServiceFeatures

log = logging.getLogger(__name__)

# 검색 대상: 판정에 쓰는 문서만 (영문 번역은 화면 병기용이라 제외)
SEARCH_FILTER = {"$and": [
    {"doc": {"$in": list(SEARCHABLE_DOCS)}},
    {"kind": {"$ne": "COMMENTARY_PDF"}},
    {"addressee": {"$nin": list(EXCLUDED_ADDRESSEES)}},
]}

# 특성 → 법률 용어 쿼리 (서비스 설명의 일상어를 법조문의 단어로 옮긴다)
PURPOSE_QUERY = {
    "RECRUITMENT": "채용 지원자 판단 평가 개인의 권리 의무 관계 중대한 영향 고영향 인공지능 영역",
    "LENDING": "대출 심사 신용 평가 개인의 권리 의무 관계 판단 고영향 인공지능 영역",
    "STUDENT_ASSESSMENT": "유아교육 초등교육 중등교육 학생 평가 고영향 인공지능 영역",
    "HEALTHCARE": "보건의료 제공 이용체계 진료 고영향 인공지능 영역",
    "MEDICAL_DEVICE": "의료기기 디지털의료기기 개발 이용 진단 고영향 인공지능 영역",
    "ENERGY": "에너지 공급 전력 고영향 인공지능 영역",
    "DRINKING_WATER": "먹는물 생산 공정 고영향 인공지능 영역",
    "NUCLEAR": "핵물질 원자력시설 안전한 관리 운영 고영향 인공지능 영역",
    "TRANSPORT": "교통수단 교통시설 교통체계 주요한 작동 운영 고영향 인공지능 영역",
    "PUBLIC_SERVICE_DECISION": "공공서비스 자격 확인 결정 비용징수 국가기관등 의사결정 고영향 인공지능 영역",
    "CRIMINAL_INVESTIGATION": "범죄 수사 체포 업무 생체인식정보 분석 활용 고영향 인공지능 영역",
    "DEFENSE": "국방 국가안보 목적 개발 이용 인공지능 적용 제외",
}
INDIVIDUAL_DECISION_PURPOSES = {"RECRUITMENT", "LENDING", "STUDENT_ASSESSMENT", "PUBLIC_SERVICE_DECISION"}


@dataclass
class Retrieval:
    mode: str                                        # chroma | off
    queries: list[dict] = field(default_factory=list)  # [{label, text, hits:[id]}]
    hits: dict = field(default_factory=dict)           # 검색으로 직접 찾은 id → {score, query, ref_label, doc_short}
    expanded: dict = field(default_factory=dict)       # 확장으로 추가된 id → 출발 id
    candidates: set | None = None                      # hits ∪ expanded (None = 규칙만 모드)

    def found_by(self, record_ids: list[str]) -> list[dict]:
        """이 항목의 근거 조문 중 RAG가 찾은 것과 그 경로"""
        out, law = [], get_lawbook()
        for rid in record_ids:
            rec = law.by_id.get(rid, {})
            title = rec.get("summary") or rec.get("title") or ""
            if rid in self.hits:
                h = self.hits[rid]
                out.append({"id": rid, "how": "search", "ref_label": h["ref_label"], "doc_short": h["doc_short"],
                            "title": title, "score": h["score"], "query": h["query"]})
            elif rid in self.expanded:
                src = self.expanded[rid]
                src_label = self.hits[src]["ref_label"] if src in self.hits else law.by_id[src]["ref_label"]
                out.append({"id": rid, "how": "expand", "ref_label": rec.get("ref_label", rid),
                            "doc_short": law.source_by_id[rec["doc"]]["short"] if rec else "", "title": title,
                            "from": src_label})
        return out


def build_queries(spec: str, f: ServiceFeatures) -> list[dict]:
    """서비스 설명 그대로의 쿼리 + 특성별 법률 용어 쿼리"""
    q = [{"label": "서비스 설명 (naive)", "text": spec}]
    if f.purpose in PURPOSE_QUERY:
        q.append({"label": f"활용 영역: {f.purpose}", "text": PURPOSE_QUERY[f.purpose]})
    if f.uses_biometric:
        q.append({"label": "생체정보", "text": "얼굴 지문 생체인식정보 민감정보 처리 제한 별도 동의"})
    if f.generative:
        q.append({"label": "생성형 AI", "text": "생성형 인공지능 결과물 생성 사실 표시 제품 서비스 사전 고지"})
        if f.realistic_synthetic_media is not False:
            q.append({"label": "실제와 구분 어려운 결과물",
                      "text": "실제와 구분하기 어려운 가상의 음향 이미지 영상 결과물 고지 표시"})
    if f.generative or f.business_type:
        q.append({"label": "학습 연산량·안전성", "text": "학습에 사용된 누적 연산량 기준 인공지능시스템 안전성 확보 위험관리체계"})
    if f.overseas:
        q.append({"label": "국외 사업자", "text": "국외 행위 국내 시장 이용자 영향 국내에 주소 영업소 없는 인공지능사업자 국내대리인 지정"})
    if f.purpose in INDIVIDUAL_DECISION_PURPOSES:
        q.append({"label": "자동화된 결정", "text": "완전히 자동화된 시스템 개인정보 처리 결정 거부 설명 요구 기준 절차 공개"})
    if f.purpose == "LENDING":
        q.append({"label": "자동화평가", "text": "자동화평가 개인신용평가 결과 주요 기준 기초정보 설명 요구 이의제기"})
    if f.public_sector_target:
        q.append({"label": "공공 조달", "text": "국가기관등 제품 서비스 구매 용역 발주 인공지능제품 우선 고려"})
    if f.sme:
        q.append({"label": "중소기업 지원", "text": "중소기업등 조치 이행 영향평가 지원"})
    return q


def _expand(hits: dict) -> dict:
    """참조 그래프 1단계 확장: 상위 조문 · refs · 고영향 조건 조문"""
    law = get_lawbook()
    high_impact_dependents = [r["id"] for r in law.records if "IF_HIGH_IMPACT_AI" in r["condition"]]
    expanded: dict[str, str] = {}

    def add(rid, src):
        if rid in law.by_id and rid not in hits and rid not in expanded:
            expanded[rid] = src

    for hid in list(hits):
        # 상위 조문 (ARTICLE_2_4_SA → ARTICLE_2_4)
        parent = hid.rsplit("_", 1)[0]
        add(parent, hid)
        rec = law.by_id.get(hid)
        if rec:
            for ref in rec["refs"]:
                add(ref, hid)
        # 고영향 영역(제2조제4호 ○목)이 후보면 '고영향이면 적용되는 조문'도 후보로
        if hid.startswith("ARTICLE_2_4_") and hid != "ARTICLE_2_4_KA":
            for dep in high_impact_dependents:
                add(dep, hid)
    return expanded


def resolve_strategy(strategy: str | None = None) -> str:
    """Return the available search mode, falling back when one index is missing."""
    requested = strategy or BUILD_RETRIEVAL_MODE
    if requested not in {"chroma", "bm25", "hybrid"}:
        raise ValueError(f"Unknown build retrieval mode: {requested}")
    dense_ready = sparse_ready = False
    if requested in {"chroma", "hybrid"}:
        try:
            from app.rag.store import get_collection
            dense_ready = get_collection() is not None
        except Exception as exc:
            log.warning("Chroma 검색 불가: %s", exc)
    if requested in {"bm25", "hybrid"}:
        try:
            sparse_ready = get_index() is not None
        except Exception as exc:
            log.warning("BM25 검색 불가: %s", exc)
    if requested == "hybrid":
        return "hybrid" if dense_ready and sparse_ready else "chroma" if dense_ready else "bm25" if sparse_ready else "off"
    return requested if (dense_ready if requested == "chroma" else sparse_ready) else "off"


def _rrf(dense: list[dict], sparse: list[dict], k: int) -> list[dict]:
    """Reciprocal rank fusion; raw cosine and BM25 scores are incomparable."""
    fused: dict[str, dict] = {}
    for hits in (dense, sparse):
        for rank, hit in enumerate(hits, start=1):
            entry = fused.setdefault(hit["id"], {**hit, "score": 0.0})
            entry["score"] += 1 / (60 + rank)
    return sorted(fused.values(), key=lambda hit: (-hit["score"], hit["id"]))[:k]


def search_candidates(query: str, k: int, strategy: str) -> list[dict]:
    if strategy == "bm25":
        return bm25_search(query, k=k)
    if strategy == "off":
        return []
    from app.rag.store import search as chroma_search
    if strategy == "chroma":
        return chroma_search(query, k=k, where=SEARCH_FILTER)
    if strategy == "hybrid":
        depth = max(k * 4, 20)
        return _rrf(chroma_search(query, k=depth, where=SEARCH_FILTER), bm25_search(query, k=depth), k)
    raise ValueError(f"Unknown search mode: {strategy}")


def retrieve_candidates(spec: str, f: ServiceFeatures, k: int = RETRIEVAL_TOP_K,
                        strategy: str | None = None) -> Retrieval:
    mode = resolve_strategy(strategy)
    if mode == "off":
        return Retrieval(mode="off")

    queries, hits = build_queries(spec, f), {}
    for q in queries:
        found = search_candidates(q["text"], k=k, strategy=mode)
        q["hits"] = [h["id"] for h in found]
        for h in found:
            if h["id"] not in hits or h["score"] > hits[h["id"]]["score"]:
                hits[h["id"]] = {"score": h["score"], "query": q["label"], "ref_label": h["ref_label"],
                                 "doc_short": h["doc_short"]}
    expanded = _expand(hits)
    return Retrieval(mode=mode, queries=queries, hits=hits, expanded=expanded,
                     candidates=set(hits) | set(expanded))
