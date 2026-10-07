# test_rules.py — 판정 엔진·문법 파서·제재 경로 테스트
#   검색 없이 '규칙만' 모드로 돌린다 (Chroma 상태와 무관하게 같은 결과). RAG 연결은 test_rag.py.
#   실행:  python -m pytest -q
import json

import pytest

from app.config import EVAL_PATH
from app.engine.features import heuristic_extract
from app.engine.grammar import parse, split_clauses, tag_clause
from app.engine.penalty import chain_for
from app.engine.pipeline import run_build
from app.engine.rules import BASELINE_KEYS, IF_HIGH_IMPACT, evaluate

DEMO = "얼굴 인식으로 면접 영상을 분석해서 지원자의 채용 점수를 추천하는 AI"


def build(spec, answers=None):
    return run_build(spec, answers, use_rag=False)


def statuses(result):
    return {it["label"]: it["status"] for it in result["items"]}


# ── 문법 파서 ────────────────────────────────────────────
def test_should_beats_must():
    # '노력하여야 한다' 안에 '하여야 한다'가 들어 있어도 SHOULD
    assert tag_clause("사전에 검ㆍ인증등을 받도록 노력하여야 한다.")["obligation"] == "SHOULD"


@pytest.mark.parametrize("text", ["검토하여야 하며,", "고지하여야 한다.", "지정하고, 신고하여야 한다.",
                                  "사전에 고지해야 한다.", "다음 사항이 포함되어야 한다."])   # 아래 둘은 시행령 문체
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


def test_decree_style_should_and_may():
    assert tag_clause("협력하도록 노력해야 한다.")["obligation"] == "SHOULD"
    assert tag_clause("전부 또는 일부를 적용하지 않을 수 있다.")["obligation"] == "MAY"


def test_must_not_and_exception():
    assert tag_clause("목적 외의 용도로 사용하여서는 아니 된다.")["obligation"] == "MUST_NOT"
    assert "EXCEPTION" in tag_clause("다만, … 경우에는 그러하지 아니하다.")["flags"]
    assert len(split_clauses("우선 고려하여야 한다. 다만, 적합하지 아니한 경우에는 그러하지 아니하다.")) == 2


# ── 특성 추출 ────────────────────────────────────────────
def test_face_recognition_hiring_is_not_criminal():
    f = heuristic_extract(DEMO)
    assert f.purpose == "RECRUITMENT" and f.uses_biometric and f.decision_mode == "RECOMMEND"


@pytest.mark.parametrize("spec", ["국내 영업소가 없는 해외 기업의 번역 앱", "국내에 지사를 두지 않은 외국계 챗봇",
                                  "국내 법인 없이 운영하는 AI 서비스"])
def test_overseas_only_when_no_domestic_office_is_stated(spec):
    assert heuristic_extract(spec).overseas is True


@pytest.mark.parametrize("spec", ["해외 기업이 만든 AI 번역 앱", "글로벌 본사가 운영하는 추천 서비스", "국외 사용자도 쓰는 챗봇"])
def test_overseas_mention_alone_is_unknown(spec):
    # '해외'라는 말만으로는 국내 영업소가 없다고 단정하지 않는다 → None (제36조 되묻기)
    f = heuristic_extract(spec)
    assert f.overseas is None
    assert any("미확정" in e for e in f.evidence)
    s = statuses(build(spec))
    assert s["제36조"] == "REVIEW" and "제4조①" not in s


# ── 판정 엔진 ────────────────────────────────────────────
def test_demo_case():
    s = statuses(build(DEMO))
    assert s["제2조4호사목"] == "MATCH"            # 바목이 아니라 사목
    assert "제2조4호바목" not in s
    assert s["제33조①"] == "REQUIRED"
    assert s["HIGH_IMPACT_AI"] == "REVIEW"
    assert s["제31조①"] == s["제34조①"] == s["제35조①"] == "CONDITIONAL"
    assert s["제37조의2"] == "CONDITIONAL"          # 개인정보 보호법 — 완전 자동화 여부에 따라
    assert s["제23조"] == "CONDITIONAL"             # 개인정보 보호법 — 민감정보 범위는 KB 밖


def test_answer_promotes_conditionals():
    s = statuses(build(DEMO, {"high_impact": "assume", "domestic_office": "yes"}))
    assert s["제31조①"] == s["제34조①"] == "REQUIRED"
    assert s["제35조①"] == "SHOULD"
    assert "제36조" not in s                       # 국내 영업소 있음 → 국내대리인 항목 없음


def test_human_final_is_read_differently_by_each_law():
    # 같은 답(사람이 실질적으로 최종 결정)이 법마다 다르게 작동한다
    s = statuses(build(DEMO, {"high_impact": "human_final"}))
    assert s["제37조의2"] == "INFO"                 # 개인정보 보호법: 완전히 자동화된 결정이 아님 (정의상)
    assert s["HIGH_IMPACT_AI"] == "REVIEW"          # AI기본법: 사람 개입만으로 제외된다고 단정할 수 없음
    assert s["제34조①"] == "CONDITIONAL"            # → 고영향 책무는 조건부로 남는다
    assert s["제33조①"] == "REQUIRED"


def test_human_final_lending_clears_credit_law_only():
    spec = "AI가 대출 신청자의 신용을 평가하고 심사역이 최종 결정하는 서비스"
    s = statuses(build(spec, {"high_impact": "human_final"}))
    assert s["제36조의2"] == "INFO"                  # 신용정보법: 종사자 관여 → 자동화평가 아님
    assert s["HIGH_IMPACT_AI"] == "REVIEW"


def test_only_ministry_confirmation_clears_high_impact():
    s = statuses(build(DEMO, {"high_impact": "confirmed_no"}))
    assert s["HIGH_IMPACT_AI"] == "INFO"            # 제33조① 확인 요청 → 비해당 회신
    assert "제34조①" not in s and "제31조①" not in s
    assert s["제33조①"] == "REQUIRED"


def test_automated_decision_splits_disclosure_and_response():
    # 제37조의2: ④ 공개는 자동화된 결정을 하면 바로 의무, ③ 대응은 정보주체가 요구할 때
    items = {i["key"]: i for i in build("초·중등 학생 수행평가 답안을 자동으로 채점하는 AI")["items"]}
    assert items["pipa_37_2"]["status"] == "REQUIRED" and items["pipa_37_2"]["records"][0]["id"] == "PIPA_37-2_4"
    assert items["pipa_37_2_3"]["status"] == "CONDITIONAL"
    assert items["pipa_37_2_3"]["condition"] == "IF 정보주체가 거부·설명 요구"


def test_credit_rights_are_not_business_obligations():
    # 신용정보법 제36조의2의 MAY는 정보주체의 권리 → 사업자 의무(MAY/MUST)로 표시하지 않는다
    item = next(i for i in build("은행 대출 승인 여부를 판단하는 AI")["items"] if i["key"] == "credit_36_2")
    assert item["status"] == "CONDITIONAL" and item["obligation"] is None
    assert "정보주체 요구" in item["condition"]


def test_decree_values_reach_the_build_log():
    result = build("국내 영업소가 없는 해외 기업이 한국 이용자에게 제공하는 LLM 기반 번역 앱")
    agent = next(i for i in result["items"] if i["key"] == "art36_1")
    assert any(r["id"] == "DECREE_29_1" for r in agent["records"])
    assert "100만" in agent["question"]["help"]
    assert not agent["externals"]                    # 시행령으로 해소 → EXTERNAL 없음


def test_overseas_threshold_flow():
    spec = "국내 영업소가 없는 해외 기업이 한국 이용자에게 제공하는 LLM 기반 번역 앱"
    assert statuses(build(spec))["제36조①"] == "REVIEW"
    assert statuses(build(spec, {"threshold": "yes"}))["제36조①"] == "REQUIRED"


def test_user_business_not_excluded_from_article_32():
    s = statuses(build("OpenAI API를 이용한 쇼핑몰 고객 상담 챗봇"))
    assert s["제32조①"] == "REVIEW"


def test_opportunity_is_conditional_until_high_impact_is_confirmed():
    pending = {i["key"]: i for i in build(DEMO)["items"]}
    assert pending["opp_public"]["status"] == "OPPORTUNITY"
    assert pending["opp_public"]["condition"] == IF_HIGH_IMPACT          # 고영향 미확정 → 조건부 기회
    confirmed = {i["key"]: i for i in build(DEMO, {"high_impact": "assume"})["items"]}
    assert confirmed["opp_public"]["condition"] is None


# ── RAG 후보 검증 (후보 집합을 직접 넣어 Chroma 없이 확인) ──────────────
def keys(items):
    return {i.key for i in items}


def test_rules_verify_only_retrieved_candidates():
    f = heuristic_extract(DEMO)
    full = evaluate(f, {})                                 # 규칙만 모드
    gated = evaluate(f, {}, candidates={"ARTICLE_2_4_SA", "PIPA_37-2_1"})
    assert keys(gated) < keys(full)
    assert {"art2_4", "pipa_37_2"} <= keys(gated)           # 후보에 있는 조문만 검증해서 올린다
    assert not keys(gated) & {"art34_1", "pipa_23"}          # 후보에 없으면 판정하지 않는다


def test_baseline_rules_survive_empty_retrieval():
    # 검색이 아무것도 못 찾아도 제33조①·고영향 판정·적용 범위 질문은 남는다
    items = evaluate(heuristic_extract(DEMO), {}, candidates=set())
    assert BASELINE_KEYS - {"scope_exclusion", "scope_territorial"} <= keys(items)
    assert all(i.baseline for i in items)


def test_retrieval_gap_becomes_review_not_silent_pass():
    # 특성은 사목을 가리키는데 검색이 사목 조문을 못 찾으면, '해당 없음'이 아니라 REVIEW
    items = {i.key: i for i in evaluate(heuristic_extract("AI가 서류를 보고 채용 지원자를 자동으로 탈락시키는 시스템"), {},
                                        candidates={"ARTICLE_33_1_A"})}
    assert "art2_4" not in items
    assert items["high_impact"].status == "REVIEW"
    assert "검색 누락" in items["high_impact"].summary


def test_wrong_domain_candidates_are_rejected_with_reason():
    items = {i.key: i for i in evaluate(heuristic_extract(DEMO), {},
                                        candidates={"ARTICLE_2_4_SA", "ARTICLE_2_4_BA", "ARTICLE_2_4_KA"})}
    rejected = {r["label"]: r["reason"] for r in items["high_impact"].rejected}
    assert set(rejected) == {"제2조4호바목", "제2조4호카목"}
    assert "범죄 수사" in rejected["제2조4호바목"]
    assert items["art2_4"].label == "제2조4호사목"


# ── 제재 경로 ────────────────────────────────────────────
@pytest.mark.parametrize("record, kind", [
    ("ARTICLE_31_1", "DIRECT"), ("ARTICLE_36_1", "DIRECT"),
    ("ARTICLE_31_2", "INDIRECT"), ("ARTICLE_34_1", "INDIRECT"),
    ("ARTICLE_33_1_A", "NONE"), ("ARTICLE_35_1", "NONE"),
])
def test_penalty_type(record, kind):
    assert chain_for(record)["type"] == kind


# ── 개발용 평가셋(dev) 정답과 일치 — held-out은 테스트로 고정하지 않는다 ──
@pytest.mark.parametrize("case", json.loads(EVAL_PATH.read_text(encoding="utf-8")), ids=lambda c: c["id"])
def test_dev_cases_rules_only(case):
    s = statuses(build(case["spec"]))
    for label, expected in case["gold"]["statuses"].items():
        assert s.get(label) == expected, f"{label}: {s.get(label)} != {expected}"
    for label in case["gold"].get("absent", []):
        assert label not in s
