"""AI 기본법 QA API."""
import logging

from fastapi import APIRouter, HTTPException

from app.rag.qa_pipeline import answer
from app.schemas import AskRequest, AskResponse

router = APIRouter(tags=["AI 기본법 QA"])
log = logging.getLogger(__name__)


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    """일반 법률 질문 또는 서비스 설명을 근거 조문과 개발 작업 언어로 답한다."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="질문을 입력해 주세요.")
    try:
        return answer(req)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("QA 답변 생성 실패")
        raise HTTPException(status_code=502, detail="근거 기반 답변을 생성하지 못했습니다. 검색·LLM 연결을 확인하세요.") from exc
