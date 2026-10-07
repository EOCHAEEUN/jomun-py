# pipeline.py — SPEC → 특성 추출 → Scope → RAG 검색 → Rule Engine → Penalty Graph → BUILD LOG
import logging
import time

from app.config import EMBEDDING_PROVIDER, RETRIEVAL_TOP_K
from app.engine.features import apply_answers, extract
from app.engine.law import get_lawbook, read_decompiled
from app.engine.penalty import chain_for
from app.engine.rules import RuleItem, evaluate

log = logging.getLogger(__name__)

SUMMARY_ORDER = ["REQUIRED", "REVIEW", "CONDITIONAL", "SHOULD", "OPPORTUNITY", "OUT_OF_SCOPE"]


def _retrieve(spec: str) -> tuple[list[dict], str]:
    """Chroma 검색 (적재 전이면 건너뜀). 판정에는 쓰지 않고 근거 표시용으로만 쓴다."""
    try:
        from app.rag.store import search
        hits = search(spec, k=RETRIEVAL_TOP_K,
                      where={"addressee": {"$in": ["AI_BUSINESS", "OTHER", "PUBLIC_AGENCY"]}})
        return hits, (f"chroma ({EMBEDDING_PROVIDER})" if hits else "off")
    except Exception as e:  # chromadb 미설치·DB 손상 등
        log.warning("검색 건너뜀: %s", e)
        return [], "off"


def _item_to_dict(item: RuleItem) -> dict:
    law = get_lawbook()
    return {
        "key": item.key,
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
    }


def run_build(spec: str, answers: dict | None = None) -> dict:
    started = time.perf_counter()
    answers = answers or {}

    features, extractor = extract(spec)
    features = apply_answers(features, answers)
    items = evaluate(features, answers)
    retrieved, retriever = _retrieve(spec)

    counts = {s: sum(1 for i in items if i.status == s) for s in SUMMARY_ORDER}
    summary_text = " · ".join(f"{n} {s.lower().replace('_', ' ')}" for s, n in counts.items() if n)

    todo, seen = [], set()
    for i in items:
        if i.todo and i.todo["title"] not in seen:
            seen.add(i.todo["title"])
            todo.append({"key": i.key, "status": i.status, **i.todo})

    return {
        "spec": spec,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "mode": {"feature_extractor": extractor, "retriever": retriever},
        "features": features.model_dump(),
        "items": [_item_to_dict(i) for i in items],
        "summary": {"counts": counts, "text": summary_text},
        "todo": todo,
        "pending_questions": [i.question["id"] for i in items if i.question and not i.question.get("answer")],
        "retrieved": retrieved,
        "law": get_lawbook().law,
    }
