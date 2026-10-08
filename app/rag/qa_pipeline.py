"""근거 조문만을 이용하는 /ask 답변 파이프라인."""
import json
import logging
import re

from app.config import (MONOROUTER_API_KEY, MONOROUTER_BASE_URL, QA_LLM_MODEL,
                        QA_TOP_K)
from app.engine.features import apply_answers, extract
from app.engine.rules import evaluate
from app.rag import qdrant_store
from app.rag.qa_retriever import retrieve
from app.schemas import AskRequest, AskResponse, AskSource, ServiceFeatures

log = logging.getLogger(__name__)
_SERVICE_CUE = re.compile(
    r"(?:우리|저희|제|내)(?:가|는|의)?\s*(?:회사|팀|서비스|앱|플랫폼|AI|인공지능|시스템|만드는|개발하는).{0,30}"
)
_SERVICE_NARRATIVE = re.compile(
    r"(?:내가|나는|제가|저는|우리는|저희는).{0,120}?(?:서비스|앱|플랫폼|AI|인공지능|시스템).{0,80}?(?:준비|개발|만들|기획|운영|출시|제공)"
)
_DEFINITION_CUE = re.compile(r"(?:뭔가요|뭔지|뭐야|무엇|정의|뜻|의미)")
_VALID_STATUSES = {"MATCH", "REQUIRED", "REVIEW", "CONDITIONAL", "SHOULD"}


def _display_ref(ref: str) -> str:
    return re.sub(r"(제\d+조(?:의\d+)?)(\d+호)", r"\1제\2", ref)

SYSTEM = """당신은 인공지능기본법 QA 도우미다. 제공된 원문 근거와 서비스 점검 결과만 사용한다.
법률 문구를 개발자가 이해할 수 있는 담백한 한국어로 설명한다. 코드를 꾸며내지 않는다.
답변은 '조문의 의미'와 '개발 시 확인할 조건 또는 작업'을 짧게 구분한다.
법 개념과 자신의 서비스 적용 여부를 함께 물으면 두 질문 모두 답한다. 먼저 개념을 설명하고, 이어서 서비스의 확인된 사실과 아직 확인할 조건을 설명한다.
일반 질문에는 구체적인 서비스 사실이 없으므로 어떤 서비스의 의무가 확정됐다고 말하지 않는다.
서비스 설명이 있어도 REVIEW·CONDITIONAL을 확정 의무로 바꾸지 않는다.
근거가 없는 내용은 추측하지 말고 확인할 수 없다고 말한다.
조문이 '노력하여야 한다'고 쓰면 '노력의무'라고 정확히 설명한다. '의무가 아니다'라고 단정하지 않는다.
각 사실 설명 문장이나 짧은 문단 끝에는 이를 뒷받침하는 [S번호]를 넣는다.
반드시 JSON 객체 하나만 출력한다: {"answer":"한국어 답변. 근거마다 [S1]처럼 표기", "used_source_ids":["S1"]}.
used_source_ids는 실제 답변에 인용한 근거 ID만 넣는다. 원문에 없는 사실을 단정하지 않는다."""


def _service_text(req: AskRequest) -> str | None:
    if req.service_description and req.service_description.strip():
        return req.service_description.strip()
    # RFP의 question 단일 필드로 우리 서비스를 설명한 경우에도 서비스 모드로 처리한다.
    matches = [match for pattern in (_SERVICE_CUE, _SERVICE_NARRATIVE)
               if (match := pattern.search(req.question))]
    return req.question[min(match.start() for match in matches):].strip() if matches else None


def _definition_ids(question: str) -> list[str]:
    """복합 질문에서 정의를 요구한 조문을 적용성 근거와 함께 제공한다."""
    if "고영향" in question and _DEFINITION_CUE.search(question):
        return ["ARTICLE_2_4"]
    return []


def _legal_question_before_service(question: str, service: str | None) -> str:
    """한 입력창에서 서비스 설명 앞에 적힌 별도 법률 질문을 분리한다."""
    if not service or service not in question:
        return ""
    return question.split(service, 1)[0].strip(" \t\n.,?!:;。？")


def _rule_context(spec: str, answers: dict[str, str]) -> tuple[list[dict], list[str], ServiceFeatures]:
    features, _ = extract(spec)
    features = apply_answers(features, answers)
    items = [i for i in evaluate(features, answers, candidates=None)
             if i.doc == "AIACT" and i.status in _VALID_STATUSES]
    ids = []
    for item in items:
        ids.extend(rid for rid in item.records if rid.startswith("ARTICLE_") and rid not in ids)
    # 해당 서비스와 관련된 판정 근거를 Qdrant 원문에서 다시 조회한다.
    facts = [{"status": i.status, "article": i.label, "summary": i.summary,
              "condition": i.condition, "checklist": i.checklist[:3],
              "record_ids": [rid for rid in i.records if rid.startswith("ARTICLE_")]}
             for i in items[:8]]
    return facts, ids[:12], features


def _llm_json(question: str, service: str | None, facts: list[dict], sources: list[dict]) -> dict:
    if not MONOROUTER_API_KEY:
        raise RuntimeError("MONOROUTER_API_KEY가 설정되지 않았습니다.")
    from langchain_core.messages import HumanMessage, SystemMessage

    context = "\n\n".join(
        f"[S{n}] {s['doc_short']} {_display_ref(s['ref_label'])} (p.{s['page']})\n{s['text']}"
        for n, s in enumerate(sources, 1)
    )
    content = (f"질문: {question}\n\n"
               f"서비스 설명: {service or '(없음)'}\n\n"
               f"서비스 점검 결과(사전 검토, 법적 확정 아님): {json.dumps(facts, ensure_ascii=False)}\n\n"
               f"원문 근거:\n{context}\n\n"
               "위 근거 안에서만 답하고, 서비스 정보가 없으면 해당 서비스 의무를 판정하지 마세요.")
    if QA_LLM_MODEL.startswith("claude-"):
        from langchain_anthropic import ChatAnthropic
        base = MONOROUTER_BASE_URL.rstrip("/")
        if "/api/monorouter/v1" in base and not base.endswith("/anthropic"):
            base += "/anthropic"
        llm = ChatAnthropic(model=QA_LLM_MODEL, anthropic_api_url=base,
                            anthropic_api_key=MONOROUTER_API_KEY, temperature=0,
                            max_tokens=1000, timeout=45, max_retries=1)
    else:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=QA_LLM_MODEL, base_url=MONOROUTER_BASE_URL,
                         api_key=MONOROUTER_API_KEY, temperature=0,
                         max_tokens=1000, timeout=45, max_retries=1)
    result = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=content)])
    raw = result.content if isinstance(result.content, str) else "".join(
        block.get("text", "") for block in result.content if isinstance(block, dict))
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(raw)


def answer(req: AskRequest) -> AskResponse:
    if not qdrant_store.ready():
        raise RuntimeError("Qdrant QA 인덱스가 없습니다. `python -m scripts.ingest_qa`를 실행하세요.")
    service = _service_text(req)
    facts, rule_ids, features = _rule_context(service, req.answers) if service else ([], [], None)
    question = req.question.strip()
    search_text = question if not service or service in question else f"{question} {service}"
    hits = retrieve(search_text,
                    features=features, limit=QA_TOP_K)
    legal_question = _legal_question_before_service(question, service)
    legal_ids = [hit["id"] for hit in qdrant_store.search_sparse(legal_question, limit=2)] if legal_question else []
    context_ids = _definition_ids(question) + legal_ids + rule_ids
    if context_ids:
        present = {h["id"] for h in hits}
        for chunk in qdrant_store.get_chunks(context_ids):
            if chunk["id"] not in present:
                hits.append(chunk)
                present.add(chunk["id"])
            if len(hits) >= QA_TOP_K + 6:
                break
    if not hits:
        return AskResponse(answer="검색된 인공지능기본법 근거가 없어 답변할 수 없습니다.", sources=[],
                           mode="service" if service else "general")
    visible_ids = {h["id"] for h in hits}
    facts = [f for f in facts if any(rid in visible_ids for rid in f["record_ids"])]
    generated = _llm_json(question, service, facts, hits)
    text = str(generated.get("answer", "")).strip()
    cited = {f"S{n}" for n in re.findall(r"\[S(\d+)\]", text)}
    valid = {f"S{n}" for n in range(1, len(hits) + 1)}
    if not text or not cited or not cited <= valid:
        return AskResponse(answer="제공된 조문만으로 답변을 확인할 수 없습니다. 질문을 더 구체적으로 입력해 주세요.",
                           sources=[], mode="service" if service else "general")
    sources = [AskSource(source_id=f"S{n}", article=_display_ref(h["ref_label"]), content=h["text"], document=h["doc_short"],
                         page=h["page"], chunk_id=h["id"], source_file=h["source_file"])
               for n, h in enumerate(hits, 1) if f"S{n}" in cited]
    return AskResponse(answer=text, sources=sources, mode="service" if service else "general")
