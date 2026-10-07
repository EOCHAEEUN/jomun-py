# test_rules.py — 판정 엔진·문법 파서·제재 경로 테스트 (Chroma 없이 실행됨)
#   실행:  python -m pytest -q
import json

import pytest

from app.config import EVAL_PATH
from app.engine.features import heuristic_extract
from app.engine.grammar import parse, split_clauses, tag_clause
from app.engine.penalty import chain_for
from app.engine.pipeline import run_build

DEMO = "얼굴 인식으로 면접 영상을 분석해서 지원자의 채용 점수를 추천하는 AI"


def statuses(result):
    return {it["label"]: it["status"] for it in result["items"]}


# ── 문법 파서 ────────────────────────────────────────────
def test_should_beats_must():
    # '노력하여야 한다' 안에 '하여야 한다'가 들어 있어도 SHOULD
    assert tag_clause("사전에 검ㆍ인증등을 받도록 노력하여야 한다.")["obligation"] == "SHOULD"


@pytest.mark.parametrize("text", ["검토하여야 하며,", "고지하여야 한다.", "지정하고, 신고하여야 한다."])
def test_must_endings(text):
    assert tag_clause(text)["obligation"] == "MUST"


@pytest.mark.parametrize("text", ["대통령령으로 정한다.", "대통령령으로 정하는 기준 이상인", "대통령령으로 정하는 바에 따라"])
def test_external_decree_variants(text):
    assert tag_clause(text)["external"] == "EXTERNAL_DECREE"


def test_article_33_has_two_clauses():
    text = ("인공지능사업자는 … 사전에 검토하여야 하며, 필요한 경우 과학기술정보통신부장관에게 "
            "고영향 인공지능에 해당하는지 여부의 확인을 요청할 수 있다.")
    clauses = parse(text)
    assert [c["obligation"] for c in clauses] == ["MUST", "MAY"]
    assert {c["addressee"] for c in clauses} == {"AI_BUSINESS"}   # 앞 절의 주어가 이어짐


def test_must_not_and_exception():
    assert tag_clause("목적 외의 용도로 사용하여서는 아니 된다.")["obligation"] == "MUST_NOT"
    assert "EXCEPTION" in tag_clause("다만, … 경우에는 그러하지 아니하다.")["flags"]
    assert len(split_clauses("우선 고려하여야 한다. 다만, 적합하지 아니한 경우에는 그러하지 아니하다.")) == 2


# ── 특성 추출 ────────────────────────────────────────────
def test_face_recognition_hiring_is_not_criminal():
    f = heuristic_extract(DEMO)
    assert f.purpose == "RECRUITMENT" and f.uses_biometric and f.decision_mode == "RECOMMEND"


# ── 판정 엔진 ────────────────────────────────────────────
def test_demo_case():
    s = statuses(run_build(DEMO))
    assert s["제2조4호사목"] == "MATCH"            # 바목이 아니라 사목
    assert "제2조4호바목" not in s
    assert s["제33조①"] == "REQUIRED"
    assert s["HIGH_IMPACT_AI"] == "REVIEW"
    assert s["제31조①"] == s["제34조①"] == s["제35조①"] == "CONDITIONAL"
    assert s["KB 범위 밖"] == "OUT_OF_SCOPE"


def test_answer_promotes_conditionals():
    s = statuses(run_build(DEMO, {"high_impact": "assume", "domestic_office": "yes"}))
    assert s["제31조①"] == s["제34조①"] == "REQUIRED"
    assert s["제35조①"] == "SHOULD"
    assert "제36조" not in s                       # 국내 영업소 있음 → 국내대리인 항목 없음


def test_overseas_threshold_flow():
    spec = "국내 영업소가 없는 해외 기업이 한국 이용자에게 제공하는 LLM 기반 번역 앱"
    assert statuses(run_build(spec))["제36조①"] == "REVIEW"
    assert statuses(run_build(spec, {"threshold": "yes"}))["제36조①"] == "REQUIRED"


def test_user_business_not_excluded_from_article_32():
    s = statuses(run_build("OpenAI API를 이용한 쇼핑몰 고객 상담 챗봇"))
    assert s["제32조①"] == "REVIEW"


# ── 제재 경로 ────────────────────────────────────────────
@pytest.mark.parametrize("record, kind", [
    ("ARTICLE_31_1", "DIRECT"), ("ARTICLE_36_1", "DIRECT"),
    ("ARTICLE_31_2", "INDIRECT"), ("ARTICLE_34_1", "INDIRECT"),
    ("ARTICLE_33_1_A", "NONE"), ("ARTICLE_35_1", "NONE"),
])
def test_penalty_type(record, kind):
    assert chain_for(record)["type"] == kind


# ── 평가셋 정답과 일치 ───────────────────────────────────
@pytest.mark.parametrize("case", json.loads(EVAL_PATH.read_text(encoding="utf-8")), ids=lambda c: c["id"])
def test_eval_cases(case):
    s = statuses(run_build(case["spec"]))
    for label, expected in case["gold"]["statuses"].items():
        assert s.get(label) == expected, f"{label}: {s.get(label)} != {expected}"
    for label in case["gold"].get("absent", []):
        assert label not in s
