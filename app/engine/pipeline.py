# pipeline.py — SPEC → 특성 추출 → RAG 후보 검색 → Rule Engine 검증 → Penalty Graph → BUILD LOG
#
#   RAG는 '어떤 조문이 걸릴 수 있는지' 후보를 찾고,
#   Rule Engine은 그 후보 조문이 실제 서비스 조건에 적용되는지 검증한다.
#   제4조(적용 범위)·제33조①(사전 검토)·고영향 판정 결과는 검색 결과와 상관없이 항상 확인한다(기본 규칙).
#   Chroma가 비어 있으면 '규칙만' 모드로 동작한다.
import logging
import time

from app.config import EMBEDDING_PROVIDER, RETRIEVAL_TOP_K
from app.engine.features import apply_answers, extract
from app.engine.law import get_lawbook, read_decompiled
from app.engine.penalty import chain_for
from app.engine.rules import RuleItem, evaluate
from app.rag.retriever import Retrieval, retrieve_candidates
from app.schemas import ServiceFeatures

log = logging.getLogger(__name__)

SUMMARY_ORDER = ["REQUIRED", "REVIEW", "CONDITIONAL", "SHOULD", "OPPORTUNITY", "OUT_OF_SCOPE"]


def _item_to_dict(item: RuleItem, rag: Retrieval) -> dict:
    law = get_lawbook()
    return {
        "key": item.key,
        "doc": item.doc,
        "doc_short": law.source_by_id[item.doc]["short"],
        "status": item.status,
        "label": item.label,
        "summary": item.summary,
        "obligation": item.obligation,
        "condition": item.condition,
        "notes": item.notes,
        "externals": item.externals,
        "records": [law.public_record(r) for r in item.records],
        "chain": chain_for(item.penalty_from),
        "decompiled": {"filename": item.decompiled, "code": read_decompiled(item.decompiled)}
        if item.decompiled else None,
        "checklist": item.checklist,
        "question": item.question,
        # 이 항목을 빌드 로그에 올린 경로: RAG 검색 / 참조 확장 / 기본 규칙
        "baseline": item.baseline,
        "found_by": rag.found_by(item.records) if rag.candidates is not None else [],
        "rejected": item.rejected,
    }


def _rag_info(rag: Retrieval, items: list[RuleItem]) -> dict:
    law = get_lawbook()
    top = sorted(rag.hits.items(), key=lambda kv: -kv[1]["score"])
    used = {r for i in items for r in i.records}
    return {
        "mode": "chroma" if rag.candidates is not None else "rules-only",
        "embedding": EMBEDDING_PROVIDER if rag.candidates is not None else None,
        "top_k": RETRIEVAL_TOP_K,
        "queries": [{"label": q["label"], "text": q["text"],
                     "hits": [{"id": h, "ref_label": rag.hits[h]["ref_label"], "doc_short": rag.hits[h]["doc_short"]}
                              for h in q.get("hits", [])]}
                    for q in rag.queries],
        "n_hits": len(rag.hits),
        "n_expanded": len(rag.expanded),
        "n_candidates": len(rag.candidates or ()),
        "n_used": len(used & (rag.candidates or set())),
        "rejected": [r for i in items for r in i.rejected],
        # 화면의 'RAG 검색 근거' 칩: 검색으로 직접 찾은 조문 (점수 순)
        "top": [{"id": rid, "ref_label": h["ref_label"], "doc_short": h["doc_short"], "score": h["score"],
                 "title": law.by_id.get(rid, {}).get("summary") or "", "query": h["query"], "used": rid in used}
                for rid, h in top[:12]],
    }


def run_build(spec: str, answers: dict | None = None, use_rag: bool = True,
              extracted: tuple[ServiceFeatures, str] | None = None) -> dict:
    """extracted: 미리 뽑은 (특성, 추출기 이름). 평가에서 같은 특성으로 여러 단계를 비교할 때 쓴다"""
    started = time.perf_counter()
    answers = answers or {}

    features, extractor = extracted or extract(spec)
    features = apply_answers(features, answers)
    rag = retrieve_candidates(spec, features) if use_rag else Retrieval(mode="off")
    items = evaluate(features, answers, candidates=rag.candidates)

    counts = {s: sum(1 for i in items if i.status == s) for s in SUMMARY_ORDER}
    summary_text = " · ".join(f"{n} {s.lower().replace('_', ' ')}" for s, n in counts.items() if n)

    todo, seen = [], set()
    for i in items:
        if i.todo and i.todo["title"] not in seen:
            seen.add(i.todo["title"])
            todo.append({"key": i.key, "status": i.status, **i.todo})

    rag_info = _rag_info(rag, items)
    return {
        "spec": spec,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "mode": {"feature_extractor": extractor,
                 "retriever": f"chroma ({EMBEDDING_PROVIDER})" if rag_info["mode"] == "chroma" else "rules-only"},
        "features": features.model_dump(),
        "items": [_item_to_dict(i, rag) for i in items],
        "summary": {"counts": counts, "text": summary_text},
        "todo": todo,
        "pending_questions": [i.question["id"] for i in items if i.question and not i.question.get("answer")],
        "rag": rag_info,
        "sources": [{k: s[k] for k in ("id", "short", "title", "kind", "authority", "effective")}
                    for s in get_lawbook().sources],
    }
