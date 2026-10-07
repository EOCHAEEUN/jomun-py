# test_preprocess.py — PDF 6종 → 청크 전처리 테스트
#   ingest와 같은 함수(build_all)를 쓰되 파일은 쓰지 않는다.
import re

from app.engine.law import get_lawbook


def by_id(chunks):
    return {c["id"]: c for c in chunks["chunks"]}


def test_all_documents_are_chunked(chunks):
    docs = {c["doc"] for c in chunks["chunks"]}
    assert docs == {"AIACT", "DECREE", "PIPA", "CREDIT", "BKL", "AIACT_EN"}


def test_chunk_ids_are_unique(chunks):
    # 개인정보 보호법처럼 시행 예정 개정본이 같은 조문으로 한 번 더 나와도 현행본 하나만 남는다
    ids = [c["id"] for c in chunks["chunks"]]
    assert len(ids) == len(set(ids))


def test_article_33_is_split_into_clauses(chunks):
    # 한 문장에 두 절: '검토하여야 하며'(MUST) + '요청할 수 있다'(MAY)
    c = by_id(chunks)
    assert "ARTICLE_33_1" not in c
    assert c["ARTICLE_33_1_A"]["obligation"] == "MUST" and c["ARTICLE_33_1_A"]["text"].endswith("하며,")
    assert c["ARTICLE_33_1_B"]["obligation"] == "MAY"


def test_decree_threshold_text_is_kept(chunks):
    # 시행령 제29조① 3호: 직전 3개월 국내 일평균 이용자 100만명 → 제36조 EXTERNAL을 수치로 해소하는 근거
    text = re.sub(r"\s+", "", by_id(chunks)["DECREE_29_1"]["text"])
    assert "1조원" in text and "100만명" in text


def test_line_breaks_inside_words_are_joined(chunks):
    texts = [c["text"] for c in chunks["chunks"] if c["kind"] in ("LAW", "DECREE")]
    assert "원자력시설" in by_id(chunks)["ARTICLE_2_4_MA"]["text"]
    assert not any("원 자력" in t for t in texts)


def test_revision_notes_and_deleted_items_are_removed(chunks):
    texts = [c["text"] for c in chunks["chunks"] if c["kind"] in ("LAW", "DECREE")]
    assert not any(re.search(r"<(개정|신설|삭제)", t) for t in texts)
    assert not any(re.fullmatch(r"\s*삭제\s*", t) for t in texts)


def test_linked_laws_keep_the_human_involvement_articles(chunks):
    c = by_id(chunks)
    assert "완전히 자동화된 시스템" in c["PIPA_37-2_1"]["text"]
    assert "관여하지 아니하고" in re.sub(r"\s+", " ", c["CREDIT_2_14"]["text"])   # 자동화평가 정의
    assert "설명하여 줄 것을 요구" in c["CREDIT_36-2_1"]["text"]


def test_commentary_indexes_team_summaries_not_original_text(chunks):
    # 해설(2차 저작물)은 원문 대신 팀이 쓴 요약 레코드만 인덱싱 → PDF 없이도(CI) 같은 인덱스
    bkl = [c for c in chunks["chunks"] if c["doc"] == "BKL"]
    law = get_lawbook()
    assert bkl and all(c["id"] in law.by_id and law.by_id[c["id"]]["verbatim"] is False for c in bkl)


def test_english_translation_is_mapped(chunks):
    en = chunks["en_map"]
    assert en["ARTICLE_4_1"]["ref"].startswith("Article 4")
    assert "Article 33" in en["ARTICLE_33_1"]["ref"]
