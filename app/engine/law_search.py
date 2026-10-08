"""Tagged provision search used when the QA index is unavailable."""
import re

from app.engine.law import get_lawbook
from app.schemas import AskResponse, AskSource

_WORDS = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOP = {"인공지능", "기본법", "법률", "관련", "대해", "대한", "무엇", "어떻게",
         "궁금", "궁금해요", "있나요", "하나요", "저희", "우리", "서비스"}
_ARTICLE = re.compile(r"제\s*(\d+)\s*조(?:의\s*(\d+))?")
_SUFFIXES = ("인가요", "인가", "하는데", "하나요", "해요", "에서", "에는", "에게",
             "으로", "와", "과", "을", "를", "은", "는", "이", "가")


def _terms(question: str) -> list[str]:
    raw = question.replace("AI", "인공지능").replace("ai", "인공지능")
    words = []
    for word in _WORDS.findall(raw):
        for suffix in _SUFFIXES:
            if word.endswith(suffix) and len(word) > len(suffix) + 1:
                word = word[:-len(suffix)]
                break
        if word not in _STOP and word not in words:
            words.append(word)
    return words


def search_law(question: str, limit: int = 5) -> AskResponse:
    law = get_lawbook()
    terms = _terms(question)
    article = _ARTICLE.search(question)
    ranked = []
    for record in law.records:
        title = f"{record['ref_label']} {record['title']}".lower()
        summary = (record.get("summary") or "").lower()
        body = (record.get("text") or "").lower()
        score = sum(7 if term.lower() in title else 5 if term.lower() in summary
                    else 2 if term.lower() in body else 0 for term in terms)
        if article and record.get("article") == int(article.group(1)):
            score += 15
            if article.group(2) and f"_{article.group(1)}-{article.group(2)}" in record["id"]:
                score += 8
        if score > 0:
            ranked.append((score, record))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    # Closely nested paragraphs can crowd out other useful laws.
    seen = set()
    selected = []
    for _, record in ranked:
        family = record["id"].split("_")[0:3]
        family_key = tuple(family)
        if family_key in seen and len(selected) >= 2:
            continue
        seen.add(family_key)
        selected.append(record)
        if len(selected) >= limit:
            break
    sources = []
    for index, record in enumerate(selected, 1):
        doc = law.source_by_id[record["doc"]]
        sources.append(AskSource(
            source_id=f"S{index}", article=record["ref_label"], content=record["text"],
            document=doc["short"], page=record.get("source_page") or 0,
            chunk_id=record["id"], source_file=doc["file"],
        ))
    if sources:
        answer = ("질문과 관련된 조문 원문을 찾았습니다. 아래 근거를 확인해 주세요. "
                  "현재 답변 생성 기능을 사용할 수 없어 조문의 적용 여부는 단정하지 않습니다.")
    else:
        answer = "입력하신 표현과 일치하는 조문을 찾지 못했습니다. 법령명이나 핵심 용어로 다시 질문해 주세요."
    return AskResponse(answer=answer, sources=sources, mode="general")
