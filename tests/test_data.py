# test_data.py — 태깅 데이터가 원문 PDF와 글자 단위로 일치하는지 확인 (공백 무시)
#   실행:  python -m pytest -q
import re
from functools import lru_cache

import pytest
from pypdf import PdfReader

from app.config import RAW_DIR
from app.engine.law import get_lawbook

norm = lambda s: re.sub(r"\s+", "", s)  # noqa: E731


@lru_cache
def full_text(doc: str) -> str:
    src = get_lawbook().source_by_id[doc]
    text = "".join(p.extract_text() or "" for p in PdfReader(str(RAW_DIR / src["file"])).pages)
    text = re.sub(r"법제처\s*\d+\s*국가법령정보센터", "", text).replace(src["title"], "")
    return norm(re.sub(r"<(개정|신설|삭제)[^>]*>", "", text))


VERBATIM = [r for r in get_lawbook().records if r.get("verbatim", True)]


@pytest.mark.parametrize("record", VERBATIM, ids=lambda r: r["id"])
def test_record_matches_pdf(record):
    assert norm(record["text"]) in full_text(record["doc"])


def test_commentary_is_marked_as_summary():
    # 가이드라인 해설은 2차 자료 요약 — 원문 인용으로 취급하지 않는다
    bkl = [r for r in get_lawbook().records if r["doc"] == "BKL"]
    assert bkl and all(r["verbatim"] is False for r in bkl)


def test_every_record_points_to_a_known_source():
    known = set(get_lawbook().source_by_id)
    assert {r["doc"] for r in get_lawbook().records} <= known
