# main.py — FastAPI 진입점 (화면 + API)
#
# 실행:  python run.py   또는   uvicorn app.main:app --reload
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import (EMBEDDING_PROVIDER, EVAL_PATH, QA_EMBEDDING_MODEL,
                        QA_EMBEDDING_PROVIDER, STATIC_DIR, use_llm)
from app.engine.law import get_lawbook
from app.engine.pipeline import run_build
from app.schemas import AskRequest, AskResponse, BuildRequest
from app.routers.ask import router as ask_router

app = FastAPI(title="조문.py — AI Legal Build Checker", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(ask_router)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    from app.rag.store import get_collection
    from app.rag import qdrant_store
    col = get_collection()
    return {
        "status": "ok",
        "feature_extractor": "llm" if use_llm() else "heuristic",
        "vectorstore": {"ready": col is not None, "count": col.count() if col else 0,
                        "embedding": EMBEDDING_PROVIDER},
        "qa_vectorstore": {"ready": qdrant_store.ready(), "count": qdrant_store.count(),
                           "embedding": QA_EMBEDDING_PROVIDER, "model": QA_EMBEDDING_MODEL},
        "sources": get_lawbook().sources,
    }


@app.get("/api/sources")
def sources():
    """데이터 6종 목록"""
    return get_lawbook().sources


@app.get("/api/examples")
def examples():
    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    return [{"id": c["id"], "name": c["name"], "spec": c["spec"]} for c in cases]


@app.post("/api/build")
def build(req: BuildRequest):
    spec = req.spec.strip()
    if not spec:
        raise HTTPException(status_code=422, detail="서비스 설명을 입력해 주세요.")
    return run_build(spec, req.answers)


@app.get("/api/graph")
def graph():
    """법령 라이브러리 관계도 — 태깅 레코드에서 만든 조문 관계 (노드·엣지)"""
    from app.engine.graph import build_graph
    return build_graph()


@app.post("/api/law-search", response_model=AskResponse)
def law_search(req: AskRequest):
    """QA 인덱스가 없을 때 태깅된 조문 원문에서 관련 근거를 찾는다."""
    from app.engine.law_search import search_law
    return search_law(req.question.strip())


@app.get("/api/articles")
def articles():
    law = get_lawbook()
    return [{"id": r["id"], "ref_label": r["ref_label"], "title": r["title"], "summary": r["summary"],
             "addressee": r["addressee"], "obligation": r["obligation"]} for r in law.records]


@app.get("/api/articles/{record_id}")
def article(record_id: str):
    law = get_lawbook()
    if record_id not in law.by_id:
        raise HTTPException(status_code=404, detail="없는 조문입니다.")
    return law.by_id[record_id]
