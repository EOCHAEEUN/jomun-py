# rules.py — Rule Engine: 특성(ServiceFeatures) → 빌드 로그 항목
#
# 원칙
#   1. 조건이 확정되지 않은 의무는 REQUIRED가 아니라 CONDITIONAL로 둔다.
#   2. 데이터만으로 단정할 수 없으면 REVIEW로 두고 되묻는다. 확률을 지어내지 않는다.
#   3. 주어가 사업자가 아닌 조문은 사업자 의무로 쓰지 않는다.
#      국가기관등·장관이 주어 → OPPORTUNITY / 정부 권한 안내, 정보주체가 주어(권리) → '요구가 오면 대응'.
#   4. Knowledge Base(데이터 6종) 밖의 규정은 판정하지 않고 범위 밖이라고 표시만 한다.
#
# 데이터 6종: 인공지능기본법(국문·영문), 시행령, 고영향 AI 판단 가이드라인 해설, 개인정보 보호법, 신용정보법
#   - 시행령: 법률이 "대통령령으로 정한다"고 비워 둔 기준 → EXTERNAL 항목을 수치로 해소
#   - 가이드라인 해설: 2차 자료. 판정 근거로 인용하되 '해설'임을 표시
#   - 개인정보 보호법·신용정보법: "사람이 개입하느냐"로 갈리는 연결 조문만 판정
from dataclasses import dataclass, field

from app.schemas import ServiceFeatures

# 고영향 AI 영역 (제2조제4호 가~차목)
DOMAIN_BY_PURPOSE = {
    "ENERGY": "GA", "DRINKING_WATER": "NA", "HEALTHCARE": "DA", "MEDICAL_DEVICE": "RA",
    "NUCLEAR": "MA", "RECRUITMENT": "SA", "LENDING": "SA", "TRANSPORT": "A",
    "PUBLIC_SERVICE_DECISION": "JA", "STUDENT_ASSESSMENT": "CHA",
}
MOK_KO = {"GA": "가", "NA": "나", "DA": "다", "RA": "라", "MA": "마", "BA": "바",
          "SA": "사", "A": "아", "JA": "자", "CHA": "차", "KA": "카"}
DOMAIN_SUMMARY = {
    "GA": "에너지 공급 영역 관련성", "NA": "먹는물 생산 공정 관련성", "DA": "보건의료 제공 영역 관련성",
    "RA": "의료기기 개발·이용 관련성", "MA": "원자력시설 관리 관련성",
    "BA": "범죄 수사용 생체인식정보 분석 관련성", "A": "교통수단·체계 운영 관련성",
    "JA": "국가기관등 의사결정 관련성", "CHA": "학생 평가 관련성",
}
# 가이드라인 해설의 영역별 '해당 사례' 레코드
GUIDE_EXAMPLE = {
    "RECRUITMENT": "BKL_RECRUIT", "LENDING": "BKL_LENDING", "STUDENT_ASSESSMENT": "BKL_EDU",
    "CRIMINAL_INVESTIGATION": "BKL_CRIME", "HEALTHCARE": "BKL_MEDICAL", "MEDICAL_DEVICE": "BKL_MEDICAL",
    "PUBLIC_SERVICE_DECISION": "BKL_PUBLIC", "TRANSPORT": "BKL_TRANSPORT",
}
# 개인에 대한 결정을 내리는 목적 → 개인정보 보호법 제37조의2(자동화된 결정) 검토 대상
INDIVIDUAL_DECISION_PURPOSES = {"RECRUITMENT", "LENDING", "STUDENT_ASSESSMENT", "PUBLIC_SERVICE_DECISION"}
DOMAIN_AREA = {
    "GA": "에너지 공급", "NA": "먹는물 생산", "DA": "보건의료 제공", "RA": "의료기기", "MA": "원자력시설·핵물질",
    "BA": "범죄 수사·체포용 생체인식정보 분석", "SA": "채용·대출 심사 등 권리·의무 판단", "A": "교통수단·교통체계",
    "JA": "국가기관등의 자격 확인·결정", "CHA": "유아·초·중등 학생 평가", "KA": "대통령령으로 정하는 영역",
}
PURPOSE_KO = {
    "RECRUITMENT": "채용", "LENDING": "대출·신용 심사", "CRIMINAL_INVESTIGATION": "범죄 수사", "HEALTHCARE": "보건의료",
    "MEDICAL_DEVICE": "의료기기", "ENERGY": "에너지", "DRINKING_WATER": "먹는물", "NUCLEAR": "원자력",
    "TRANSPORT": "교통", "PUBLIC_SERVICE_DECISION": "공공서비스 결정", "STUDENT_ASSESSMENT": "학생 평가",
    "DEFENSE": "국방", "RECOMMENDATION": "일반 추천", "CONTENT_GENERATION": "콘텐츠 생성",
    "CUSTOMER_SERVICE": "상담", "OTHER": "기타",
}
IF_HIGH_IMPACT = "IF HIGH_IMPACT_AI"
IF_AUTOMATED = "IF 완전히 자동화된 결정"

# RAG 검색과 상관없이 항상 확인하는 기본 규칙 (적용 범위 · 모든 AI 제공자의 사전 검토 · 고영향 판정 결과)
BASELINE_KEYS = {"scope_exclusion", "scope_territorial", "art33_1", "high_impact"}

# ── 되묻기 질문 ───────────────────────────────────────────────
Q_HIGH_IMPACT = {
    "id": "high_impact",
    "text": "AI 결과는 실제 판단·평가에 어떻게 쓰이나요?",
    "help": "가이드라인 해설은 채용에서 '실질적인 인사권자의 개입 없이' 지원자를 탈락시키는 경우를 해당 사례로 들어요. "
            "그렇다고 사람이 검토하면 고영향이 아니라고 정한 것은 아니에요. 확신이 없으면 과기부에 해당 여부 확인을 "
            "요청할 수 있어요 (제33조①, 시행령 제25조: 30일 이내 회신).",
    "options": [
        {"value": "automated", "label": "AI 결과가 그대로 판단·평가로 쓰여요"},
        {"value": "human_final", "label": "사람이 실질적으로 검토해 최종 결정해요"},
        {"value": "assume", "label": "고영향 AI로 보고 대비할게요"},
        {"value": "confirmed_no", "label": "과기부 확인 결과 해당하지 않는다고 회신받았어요"},
    ],
}
Q_DOMESTIC = {
    "id": "domestic_office",
    "text": "국내에 주소 또는 영업소가 있나요?",
    "help": "제36조 국내대리인 지정 의무는 국내에 주소·영업소가 없는 사업자에게만 적용돼요.",
    "options": [
        {"value": "yes", "label": "예"},
        {"value": "no", "label": "아니요"},
        {"value": "unknown", "label": "모르겠어요"},
    ],
}
Q_THRESHOLD = {
    "id": "threshold",
    "text": "아래 중 하나라도 해당하나요?",
    "help": "시행령 제29조①: 전년도 매출 1조원 이상 · AI 서비스 부문 매출 100억원 이상 · "
            "직전 3개월 국내 일평균 이용자 100만명 이상 · 시정명령 불이행으로 과태료를 받은 적 있음",
    "options": [
        {"value": "yes", "label": "하나 이상 해당해요"},
        {"value": "no", "label": "모두 해당하지 않아요"},
        {"value": "unknown", "label": "모르겠어요"},
    ],
}
Q_COMPUTE = {
    "id": "compute",
    "text": "시행령 제24조의 3요건을 모두 충족하는 AI 시스템을 제공하나요?",
    "help": "① 학습 누적 연산량 10²⁶ FLOPs 이상 ② 최첨단 기술 적용 ③ 생명·신체·기본권에 광범위하고 중대한 위험. "
            "외부 모델을 쓰더라도 자동으로 제외하지 않아요.",
    "options": [
        {"value": "yes", "label": "모두 충족해요"},
        {"value": "no", "label": "충족하지 않아요"},
        {"value": "unknown", "label": "모르겠어요"},
    ],
}


@dataclass
class RuleItem:
    key: str
    status: str                 # MATCH | REQUIRED | CONDITIONAL | SHOULD | REVIEW | OPPORTUNITY | INFO | OUT_OF_SCOPE
    label: str                  # 빌드 로그의 조문 표시 (예: 제33조①)
    summary: str
    records: list[str] = field(default_factory=list)   # 원문으로 보여줄 레코드 (첫 번째가 대표)
    obligation: str | None = None
    condition: str | None = None
    notes: list[str] = field(default_factory=list)      # 판정 근거
    externals: list[str] = field(default_factory=list)  # 아직 남은 하위 규정 의존 (EXTERNAL)
    decompiled: str | None = None
    checklist: list[str] = field(default_factory=list)  # 이 조문의 구현 체크리스트
    todo: dict | None = None                            # 전체 '적용 사항 체크리스트'에 들어갈 항목
    question: dict | None = None
    penalty_from: str | None = None                     # 근거 체인을 그릴 레코드
    doc: str = "AIACT"                                  # 근거 문서 (sources.json id)
    rejected: list[dict] = field(default_factory=list)  # RAG 후보였지만 규칙 검증에서 기각된 조문
    baseline: bool = False                              # 검색과 상관없이 항상 확인하는 기본 규칙인가


def match_domain(f: ServiceFeatures) -> str | None:
    if f.purpose == "CRIMINAL_INVESTIGATION":
        return "BA" if f.uses_biometric else None   # 바목은 생체인식정보 분석·활용일 때만
    return DOMAIN_BY_PURPOSE.get(f.purpose or "")


def reject_reason(mok: str, f: ServiceFeatures) -> str:
    """RAG가 찾은 제2조제4호 ○목 후보를 규칙이 기각한 이유"""
    if mok == "KA":
        return "카목은 대통령령으로 정하는 영역 — 시행령에 별도 규정이 없어 판정 대상이 아님"
    if mok == "BA" and f.purpose == "CRIMINAL_INVESTIGATION":
        return "범죄 수사 목적이지만 생체인식정보를 분석·활용하지 않음"
    if mok == "BA" and f.uses_biometric:
        return "생체정보를 쓰지만 목적이 범죄 수사·체포가 아님"
    if mok == "CHA" and f.purpose == "OTHER":
        return "유아·초·중등 학생 평가가 아님"
    purpose = PURPOSE_KO.get(f.purpose or "OTHER", "기타")
    return f"서비스 목적({purpose})이 {MOK_KO[mok]}목 영역({DOMAIN_AREA[mok]})과 다름"


def check_domain(f: ServiceFeatures, candidates: set[str] | None) -> tuple[str | None, str | None, list[dict]]:
    """RAG 후보 중 제2조제4호 ○목을 규칙으로 검증한다.

    반환: (확정 영역, 검색 누락 영역, 기각된 후보)
      - 후보가 None(규칙만 모드)이면 특성만으로 영역을 정한다.
      - 특성은 영역을 가리키는데 그 ○목 조문이 후보에 없으면 '검색 누락' → 단정하지 않고 REVIEW.
    """
    wanted = match_domain(f)
    if candidates is None:
        return wanted, None, []
    rejected = [
        {"id": f"ARTICLE_2_4_{mok}", "label": f"제2조4호{ko}목", "reason": reject_reason(mok, f)}
        for mok, ko in MOK_KO.items()
        if f"ARTICLE_2_4_{mok}" in candidates and mok != wanted
    ]
    if wanted and f"ARTICLE_2_4_{wanted}" not in candidates:
        return None, wanted, rejected
    return wanted, None, rejected


def decision_mode(f: ServiceFeatures, answers: dict) -> str | None:
    """되묻기 답변이 있으면 그것을, 없으면 추출된 특성을 쓴다"""
    return {"automated": "AUTOMATED", "human_final": "HUMAN_FINAL"}.get(answers.get("high_impact"), f.decision_mode)


def resolve_high_impact(f: ServiceFeatures, domain: str | None, answers: dict,
                        gap: str | None = None) -> tuple[bool | None, str]:
    """고영향 AI 여부: True / False / None(REVIEW)

    사람이 최종 결정해도 False로 내리지 않는다.
      해설: '실질적인 인사권자의 개입 없이' 탈락시키는 경우가 해당 사례다.
      → 그 역('사람이 개입하면 해당하지 않는다')은 해설도 법 본문(제2조제4호 '판단 또는 평가')도 말하지 않는다.
    False가 되는 길은 영역 미해당, 중대한 영향 없음 확인, 과기부 확인 회신(제33조①·시행령 제25조)뿐이다.
    """
    ans = answers.get("high_impact")
    if domain is None and not gap:
        return False, "제2조제4호 가~차목 영역에 해당하지 않음"
    if ans == "confirmed_no":
        return False, "과기부 확인 요청(제33조①) 결과 고영향 AI에 해당하지 않는다고 회신받음"
    if ans == "assume":
        return True, "고영향 AI로 보고 대비하기로 선택함"
    if gap:   # 특성은 영역을 가리키지만 검색이 그 ○목 조문을 찾지 못함
        return None, (f"서비스 특성은 {MOK_KO[gap]}목({DOMAIN_AREA[gap]})을 가리키지만 "
                      f"RAG 후보에 {MOK_KO[gap]}목 조문이 없어 영역을 확정하지 않음 (검색 누락 가능성)")
    if f.affects_rights is False:
        return False, "권리·안전에 중대한 영향 우려가 없다고 확인됨"
    mode = decision_mode(f, answers)
    if mode == "AUTOMATED":
        return True, "AI 결과가 사람의 실질적 검토 없이 그대로 판단·평가로 쓰임"
    if mode == "HUMAN_FINAL":
        return None, ("사람이 실질적으로 검토해 최종 결정 — 해설의 해당 사례(인적 개입 없는 판단)와는 다르지만, "
                      "사람이 개입한다는 이유만으로 고영향이 아니라고 단정할 수 없음")
    if mode == "RECOMMEND":
        return None, "AI가 추천·보조하는 구조 — 결과가 판단·평가에 어떻게 쓰이는지 확인 필요"
    return None, "AI 결과가 결정에 쓰이는 방식에 대한 정보가 없음"


def _with_answer(question: dict, answers: dict) -> dict:
    return {**question, "answer": answers.get(question["id"])}


def evaluate(f: ServiceFeatures, answers: dict | None = None,
             candidates: set[str] | None = None) -> list[RuleItem]:
    """특성 + 되묻기 답변 → 빌드 로그 항목

    candidates: RAG가 찾은 후보 조문 id 집합. 주어지면 규칙은 이 후보 조문들의 적용 조건만 검증한다
                (기본 규칙 BASELINE_KEYS는 예외). None이면 '규칙만' 모드 — 검색 없이 모든 규칙을 평가한다.
    """
    items = _evaluate(f, answers or {}, candidates)
    for i in items:
        # 국내 주소·영업소 여부(제36조 되묻기)도 적용 범위 확인이라 기본 규칙으로 둔다
        i.baseline = i.key in BASELINE_KEYS or (i.key == "art36_1" and f.overseas is None)
    if candidates is None:
        return items
    return [i for i in items if i.baseline or set(i.records) & candidates]


def _evaluate(f: ServiceFeatures, answers: dict, candidates: set[str] | None) -> list[RuleItem]:
    items: list[RuleItem] = []
    mode = decision_mode(f, answers)

    # ── STEP 0. Scope Check (제4조 + 시행령 제2조) ─────────────────
    if f.defense_only:
        items.append(RuleItem(
            key="scope_exclusion", status="REVIEW", label="제4조②",
            summary="국방·안보 업무'만' 수행하면 적용 제외 — 지정 업무인지 확인",
            records=["ARTICLE_4_2", "DECREE_2"],
            notes=["시행령 제2조: 국방부장관·국가정보원장·경찰청장이 지정한 업무만 수행하는 AI가 적용 제외 대상",
                   "다른 업무에도 쓰이면 적용 제외가 아님"],
            externals=["지정 업무 목록 (국방부장관·국정원장·경찰청장 지정 — KB 밖)"], decompiled="art4_scope.py",
        ))
        items.append(RuleItem(
            key="art33_1", status="CONDITIONAL", label="제33조①", obligation="MUST",
            condition="IF 적용 제외 대상이 아니면", summary="고영향 AI 해당 여부 사전 검토",
            records=["ARTICLE_33_1_A", "ARTICLE_33_1_B"], decompiled="art33_1.py",
            penalty_from="ARTICLE_33_1_A",
        ))
        return items

    if f.overseas:
        items.append(RuleItem(
            key="scope_territorial", status="MATCH", label="제4조①",
            summary="국외 사업자 · 국내 이용자 영향 시 적용",
            records=["ARTICLE_4_1"], notes=["국외에서 이루어진 행위라도 국내 시장·이용자에 영향을 미치면 이 법이 적용됨"],
            decompiled="art4_scope.py",
        ))

    # ── STEP 1. 고영향 AI 영역 매칭 (제2조제4호) — RAG 후보 ○목을 규칙으로 검증 ──
    domain, gap, rejected = check_domain(f, candidates)
    hi, hi_reason = resolve_high_impact(f, domain, answers, gap)
    rejected_notes = [f"검색 후보 기각 · {r['label']}: {r['reason']}" for r in rejected]
    guide = GUIDE_EXAMPLE.get(f.purpose or "")
    if domain:
        ko = MOK_KO[domain]
        summary = DOMAIN_SUMMARY.get(domain) or (
            "대출 심사 판단·평가 관련성" if f.purpose == "LENDING" else "채용 판단·평가 관련성")
        notes = ["고영향 AI = 1단계 영역 해당 AND 2단계 중대한 영향·위험 우려 (제2조제4호, 가이드라인 해설)"]
        if f.uses_biometric and domain != "BA":
            notes.append(f"얼굴 인식 등 생체정보를 쓰지만 목적이 범죄 수사·체포가 아니므로 바목이 아니라 {ko}목")
        items.append(RuleItem(
            key="art2_4", status="MATCH", label=f"제2조4호{ko}목", summary=summary,
            records=[f"ARTICLE_2_4_{domain}", "ARTICLE_2_4"], notes=notes, decompiled="art2_4_match.py",
        ))

    # ── STEP 2. 제33조① 사전 검토 — 모든 AI 제공자의 의무 ─────────
    items.append(RuleItem(
        key="art33_1", status="REQUIRED", label="제33조①", obligation="MUST",
        summary="고영향 AI 해당 여부 사전 검토",
        records=["ARTICLE_33_1_A", "ARTICLE_33_1_B", "DECREE_25_1"],
        notes=["한 문장에 두 절: '검토하여야 하며'(MUST) + '요청할 수 있다'(MAY)",
               "MUST이지만 제재 조항 없음 (penalty: NONE)",
               "확인 요청 시 장관은 30일 이내 회신, 30일 범위에서 1회 연장 (시행령 제25조③)"],
        decompiled="art33_1.py", penalty_from="ARTICLE_33_1_A",
        checklist=["가~카목 영역 해당 여부와 사람의 개입 방식을 검토해 기록으로 남기기",
                   "확인 요청 시: 요청서 + 서비스 개요서 · 학습용데이터 개요 · 활용 과정·결과 자료 (시행령 제25조①)",
                   "회신에 이의가 있으면 10일 이내 재확인 요청 (시행령 제25조④)"],
        todo={"title": "고영향 AI 해당 여부 검토", "desc": "제33조에 따라 고영향 AI 기준에 해당하는지 사전 검토"},
    ))

    # ── STEP 3. 고영향 여부 판정 결과 ─────────────────────────────
    hi_records = ["ARTICLE_2_4", "BKL_TWO_STEP"] + ([guide] if guide else [])
    if hi is None:
        summary = "고영향 영역 조문 검색 누락 — 해당 여부 확인" if gap else {
            "RECOMMEND": "추천이 판단·평가에 해당하는지 추가 검토",
            "HUMAN_FINAL": "사람 최종 결정 — 개입만으로 제외 단정 불가 · 확인 요청 검토",
        }.get(mode or "", "고영향 AI 해당 여부 추가 검토")
        if mode == "HUMAN_FINAL" and not gap:
            why = ["해설은 '인적 개입 없는 판단'을 해당 사례로 들 뿐, 사람이 개입하면 고영향이 아니라고 정하지 않음",
                   "같은 답이 법마다 다르게 작동: 개인정보 보호법·신용정보법은 정의상 사람이 개입하면 대상이 아니지만, "
                   "AI기본법은 본문에 그런 제외 규정이 없음",
                   "확신이 없으면 과기부 확인 요청 (제33조①, 시행령 제25조: 30일 이내 회신, 30일 범위 1회 연장)"]
        else:
            why = ["사람의 검토가 형식적이면 해설의 해당 사례에 가까워짐",
                   "확신이 없으면 과기부 확인 요청 (제33조①, 시행령 제25조: 30일 이내 회신)"]
        items.append(RuleItem(
            key="high_impact", status="REVIEW", label="HIGH_IMPACT_AI", summary=summary,
            records=hi_records + ["DECREE_25_2"],
            notes=[hi_reason] + why + ["고영향 여부가 확정되면 CONDITIONAL 항목이 REQUIRED / SHOULD로 바뀝니다"]
            + rejected_notes,
            externals=["고영향 AI 판단 가이드라인 원문 (KB에는 해설만 있음)"],
            decompiled="high_impact_review.py",
            question=_with_answer(Q_HIGH_IMPACT, answers), rejected=rejected,
        ))
    elif hi:
        items.append(RuleItem(
            key="high_impact", status="MATCH", label="HIGH_IMPACT_AI",
            summary="고영향 AI로 판정", records=hi_records, notes=[hi_reason] + rejected_notes,
            decompiled="high_impact_review.py",
            question=_with_answer(Q_HIGH_IMPACT, answers) if "high_impact" in answers else None,
            rejected=rejected,
        ))
    elif domain or gap:   # 영역은 맞지만 확인 회신 등으로 고영향이 아님이 확정됨
        confirmed = answers.get("high_impact") == "confirmed_no"
        items.append(RuleItem(
            key="high_impact", status="INFO", label="HIGH_IMPACT_AI",
            summary="과기부 확인 결과 비해당" if confirmed else "중대한 영향 우려 없음 확인",
            records=hi_records + ["DECREE_25_2"],
            notes=[hi_reason,
                   "확인 회신과 판단 근거를 제33조① 사전 검토 기록과 함께 남겨 두기",
                   "서비스 기능·활용 방식이 바뀌면 다시 검토"] + rejected_notes,
            decompiled="high_impact_review.py",
            question=_with_answer(Q_HIGH_IMPACT, answers), rejected=rejected,
        ))
    else:
        items.append(RuleItem(
            key="high_impact", status="INFO", label="HIGH_IMPACT_AI",
            summary="가~차목 영역 미해당 · 카목(대통령령) 확인",
            records=["ARTICLE_2_4", "ARTICLE_2_4_KA"], notes=[hi_reason] + rejected_notes,
            externals=["카목: 대통령령으로 정하는 영역 (시행령에 별도 규정 없음)"], decompiled="not_high_impact.py",
            rejected=rejected,
        ))

    # ── STEP 4. 제31조 투명성 (+ 시행령 제23조) ───────────────────
    notice_common = dict(
        label="제31조①", obligation="MUST", records=["ARTICLE_31_1", "DECREE_23_1", "DECREE_23_4"],
        decompiled="art31_1.py", penalty_from="ARTICLE_31_1",
        checklist=["이용 전에 고지: 약관·계약서·사용설명서 기재 / 화면·단말기 표시 / 제공 장소 게시 중 하나 (시행령 제23조①)",
                   "서비스명·화면 문구로 AI 활용이 명백하면 생략 가능한지 검토 (시행령 제23조④1호)",
                   "내부 업무용으로만 쓰면 적용 예외 (시행령 제23조④2호)"],
        todo={"title": "AI 사용 사전고지 검토", "desc": "제31조·시행령 제23조에 따른 이용자 대상 사전고지 방법 검토"},
    )
    if hi or f.generative:
        why = "고영향 AI" if hi else "생성형 AI"
        items.append(RuleItem(
            key="art31_1", status="REQUIRED", summary=f"AI 기반 서비스 사전 고지 ({why})",
            notes=["고영향 AI 또는 생성형 AI 제공 시 적용", "직접 과태료 대상 (제43조①1호)",
                   "고지 방법 4가지와 예외는 시행령 제23조에 있음"],
            externals=["시행령 제23조④3호: 장관이 고시하는 예외 (KB 밖)"], **notice_common))
    elif hi is None:
        items.append(RuleItem(
            key="art31_1", status="CONDITIONAL", condition=IF_HIGH_IMPACT, summary="AI 기반 서비스 사전 고지",
            notes=["고영향 AI로 확정되면 REQUIRED", "직접 과태료 대상 (제43조①1호)"], **notice_common))

    if f.generative:
        items.append(RuleItem(
            key="art31_2", status="REQUIRED", label="제31조②", obligation="MUST",
            summary="생성형 AI 결과물 표시", records=["ARTICLE_31_2", "DECREE_23_2"],
            notes=["표시 방법: 사람이 인식할 수 있는 방법 또는 기계가 판독할 수 있는 방법 (시행령 제23조②)",
                   "기계 판독 방식만 쓰면 생성 사실을 1회 이상 안내 문구·음성 등으로 알려야 함",
                   "MUST이지만 직접 과태료가 아니라 제40조 사실조사 → 시정명령 경로 (INDIRECT)"],
            decompiled="art31_2.py", penalty_from="ARTICLE_31_2",
            checklist=["결과물 표시 방식 선택: 사람이 인식 / 기계 판독", "기계 판독 방식이면 1회 이상 안내 문구·음성 제공",
                       "다운로드·공유 시에도 표시가 유지되는지 확인"],
            todo={"title": "생성형 결과물 표시 설계", "desc": "제31조②·시행령 제23조②에 따른 표시 방식 설계"},
        ))
    if f.realistic_synthetic_media:
        items.append(RuleItem(
            key="art31_3", status="REQUIRED", label="제31조③", obligation="MUST",
            summary="실제와 구분 어려운 결과물 AI 생성 고지·표시",
            records=["ARTICLE_31_3_A", "DECREE_23_3", "ARTICLE_31_3_B"],
            notes=["쉽게 확인할 수 있는 방법 + 주된 이용자의 나이·신체적·사회적 조건 고려 (시행령 제23조③)",
                   "예술적·창의적 표현물은 향유를 저해하지 않는 방식 허용 (후단 MAY)"],
            decompiled="art31_3.py", penalty_from="ARTICLE_31_3_A",
            checklist=["이용자가 '명확하게 인식'할 수 있는 고지·표시 방식 정하기",
                       "주 이용자층(어린이·고령자 등)에 맞는 표시인지 확인",
                       "예술적 표현물이면 전시·향유를 해치지 않는 방식 검토"],
            todo={"title": "딥페이크성 결과물 고지", "desc": "제31조③·시행령 제23조③에 따른 고지·표시 방식 검토"},
        ))
    elif f.generative and f.realistic_synthetic_media is None:
        items.append(RuleItem(
            key="art31_3", status="CONDITIONAL", label="제31조③", obligation="MUST",
            condition="IF 실제와 구분 어려운 결과물", summary="AI 생성 사실 고지·표시",
            records=["ARTICLE_31_3_A", "DECREE_23_3", "ARTICLE_31_3_B"],
            notes=["실사 수준의 음향·이미지·영상을 제공하면 REQUIRED"],
            decompiled="art31_3.py", penalty_from="ARTICLE_31_3_A",
        ))

    # ── STEP 5. 제32조 (+ 시행령 제24조) — 이용사업자라도 자동 제외하지 않음 ──
    if f.business_type or f.generative:
        choice = answers.get("compute")
        if choice == "yes":
            items.append(RuleItem(
                key="art32_1", status="REQUIRED", label="제32조①", obligation="MUST",
                summary="고성능 AI 안전성 확보 · 결과 제출",
                records=["ARTICLE_32_1", "DECREE_24_1", "ARTICLE_32_2"],
                externals=["누적 연산량 산정 방식·이행 방식 (장관 고시 — KB 밖)"], decompiled="art32_1.py",
                penalty_from="ARTICLE_32_1", question=_with_answer(Q_COMPUTE, answers),
                checklist=["수명주기 전반의 위험 식별·평가·완화", "안전사고 모니터링·대응 체계 구축",
                           "이행 결과를 과기부에 제출"],
                todo={"title": "고성능 AI 안전성 조치", "desc": "제32조에 따른 위험관리·결과 제출 준비"},
            ))
        elif choice != "no":
            notes = ["대상은 10²⁶ FLOPs 이상 · 최첨단 기술 · 광범위하고 중대한 위험 3요건을 모두 충족하는 시스템 (시행령 제24조①)"]
            if f.business_type == "USER_BUSINESS":
                notes.append("외부 모델을 이용하더라도 자동 제외하지 않음 — 모델 제공자의 연산량·시스템 구조 확인")
            items.append(RuleItem(
                key="art32_1", status="REVIEW", label="제32조①", obligation="MUST",
                summary="10²⁶ FLOPs 등 시행령 3요건 해당 여부 확인",
                records=["ARTICLE_32_1", "DECREE_24_1"], notes=notes,
                externals=["누적 연산량 산정 방식 (장관 고시 — KB 밖)"], decompiled="art32_1.py",
                penalty_from="ARTICLE_32_1", question=_with_answer(Q_COMPUTE, answers),
            ))

    # ── STEP 6. 고영향 AI 책무 (제34·35·30조 + 시행령 제27·28조) ─────
    if hi is not False:
        status = "REQUIRED" if hi else "CONDITIONAL"
        notes = ["1~5호 + 6호(위원회 심의·의결 사항) + ②장관 고시까지 확인해야 함",
                 "홈페이지 등에 위험관리·설명방안·이용자보호 주요 내용과 관리·감독자 연락처 게시 (시행령 제27조①)",
                 "조치 이행 근거 문서 5년 보관 (시행령 제27조②)",
                 "위반 시 제40조 사실조사 → 시정명령 → 불이행 시 과태료 (INDIRECT)"]
        if f.business_type == "USER_BUSINESS":
            notes.insert(1, "이용사업자: 개발사가 1~3호를 이행했고 중대한 기능 변경이 없으면 1~3호를 이행한 것으로 봄 (시행령 제27조③)")
        items.append(RuleItem(
            key="art34_1", status=status, label="제34조①", obligation="MUST",
            condition=None if hi else IF_HIGH_IMPACT, summary="안전성·신뢰성 조치 + 게시·5년 보관",
            records=["ARTICLE_34_1", "DECREE_27_1", "DECREE_27_2", "DECREE_27_3"], notes=notes,
            externals=["6호: 위원회 심의·의결 사항", "② 장관 고시 (KB 밖)"],
            decompiled="art34_1.py", penalty_from="ARTICLE_34_1",
            checklist=["1호 위험관리방안 수립·운영", "2호 결과·주요 기준·학습데이터 개요 설명 방안",
                       "3호 이용자 보호 방안", "4호 사람의 관리·감독 체계 (담당자 성명·연락처 게시)",
                       "1~4호 주요 내용 홈페이지 게시 (영업비밀 제외 가능)", "5호 근거 문서 작성 · 5년 보관",
                       "6호 위원회 심의·의결 사항 확인 (EXTERNAL)"],
            todo={"title": "위험관리방안 준비", "desc": "제34조·시행령 제27조에 따른 조치, 게시, 5년 보관 계획"},
        ))
        items.append(RuleItem(
            key="art35_1", status="SHOULD" if hi else "CONDITIONAL", label="제35조①", obligation="SHOULD",
            condition=None if hi else IF_HIGH_IMPACT, summary="기본권 영향평가 노력",
            records=["ARTICLE_35_1", "DECREE_28_1"],
            notes=["노력의무(SHOULD) — 직접 제재 없음", "실시하면 공공기관 도입 시 우선 고려 (제35조②)",
                   "직접 또는 제3자에 의뢰해 실시 가능 (시행령 제28조②)"],
            externals=["영향평가 세부 사항 (장관 고시 — KB 밖)"], decompiled="art35_1.py",
            penalty_from="ARTICLE_35_1",
            checklist=["영향받을 수 있는 개인·집단 식별", "영향받는 기본권 유형 식별",
                       "사회적·경제적 영향의 내용·범위", "사용 행태", "평가지표와 결과산출 방식",
                       "위험 예방·완화·손실 복구 방안", "개선이 필요하면 이행계획"],
            todo={"title": "영향평가 필요성 검토", "desc": "제35조·시행령 제28조 7개 항목 기준으로 실시 여부 검토"},
        ))
        items.append(RuleItem(
            key="art30_3", status="SHOULD" if hi else "CONDITIONAL", label="제30조③", obligation="SHOULD",
            condition=None if hi else IF_HIGH_IMPACT, summary="사전 검·인증 노력",
            records=["ARTICLE_30_3"], notes=["노력의무(SHOULD) — 직접 제재 없음",
                                              "받으면 공공기관 이용 시 우선 고려 (제30조④)"],
            decompiled="art30_3.py", penalty_from="ARTICLE_30_3",
            todo={"title": "검·인증 추진 여부 검토", "desc": "제30조③에 따른 사전 검·인증 추진 여부 검토"},
        ))
        # 기회 신호도 고영향 AI일 때의 이야기 → 미확정이면 조건을 붙인다
        items.append(RuleItem(
            key="opp_public", status="OPPORTUNITY", label="제30조④",
            condition=None if hi else IF_HIGH_IMPACT,
            summary="공공기관 도입 검토 시 우선 고려 요소",
            records=["ARTICLE_30_4", "ARTICLE_35_2"],
            notes=["주어가 사업자가 아니라 국가기관등 → 사업자에게는 의무가 아니라 기회 신호",
                   "검·인증(제30조④)·영향평가(제35조②)를 갖추면 우선 고려 대상"]
            + ([] if hi else ["고영향 AI로 확정될 때 의미가 있는 신호 — 지금은 조건부"]),
            decompiled="opportunity_public.py",
        ))
        if f.sme:
            items.append(RuleItem(
                key="opp_sme", status="OPPORTUNITY", label="제17조③",
                condition=None if hi else IF_HIGH_IMPACT,
                summary="중소기업등 제34조 조치·영향평가 지원 가능",
                records=["ARTICLE_17_3"], notes=["주어는 과기부 장관(MAY) — 받을 수 있는 지원"],
                decompiled="art17_3.py",
            ))
    if f.public_sector_target:
        items.append(RuleItem(
            key="opp_procurement", status="OPPORTUNITY", label="제16조③",
            summary="국가기관등 AI 제품·서비스 우선 고려",
            records=["ARTICLE_16_3_A", "ARTICLE_16_3_B"],
            notes=["우선 고려 대상 제품·서비스의 범위는 대통령령", "업무 특성상 부적합하면 예외 (단서)"],
            externals=["우선 고려 대상 인공지능제품·서비스 (시행령에 별도 규정 없음)"], decompiled="art16_3.py",
        ))

    # ── STEP 7. 제36조 국내대리인 (+ 시행령 제29조) ─────────────────
    if f.overseas is None:
        items.append(RuleItem(
            key="art36_1", status="REVIEW", label="제36조", obligation="MUST",
            summary="국내 주소·영업소 여부 정보 필요", records=["ARTICLE_36_1", "DECREE_29_1"],
            notes=["국내에 주소·영업소가 없는 사업자 + 시행령 제29조 기준 해당 시 지정 의무"],
            decompiled="art36_1.py", penalty_from="ARTICLE_36_1",
            question=_with_answer(Q_DOMESTIC, answers),
        ))
    elif f.overseas:
        choice = answers.get("threshold")
        common = dict(label="제36조①", obligation="MUST", records=["ARTICLE_36_1", "DECREE_29_1", "ARTICLE_36_3"],
                      decompiled="art36_1.py", penalty_from="ARTICLE_36_1",
                      question=_with_answer(Q_THRESHOLD, answers))
        if choice == "yes":
            items.append(RuleItem(
                key="art36_1", status="REQUIRED", summary="국내대리인 서면 지정·신고",
                notes=["시행령 제29조① 기준 중 하나 이상 해당", "미지정 시 직접 과태료 (제43조①2호)",
                       "③ 대리인의 위반은 사업자의 행위로 봄 (TREAT_AS)"],
                checklist=["국내에 주소·영업소가 있는 대리인 선정", "서면 지정 후 과기부 신고"],
                todo={"title": "국내대리인 지정", "desc": "제36조·시행령 제29조에 따른 국내대리인 서면 지정·신고"},
                **common))
        elif choice == "no":
            items.append(RuleItem(key="art36_1", status="INFO", summary="시행령 기준 미해당 — 지정 의무 없음",
                                  notes=["매출·이용자 수가 늘면 다시 확인 (매출액은 전년도 평균환율로 환산)"],
                                  **common))
        else:
            items.append(RuleItem(
                key="art36_1", status="REVIEW", summary="매출 1조·AI 매출 100억·이용자 100만 기준 확인",
                notes=["국내 주소·영업소 없음 확인됨", "시행령 제29조① 네 기준 중 하나라도 해당하면 지정 의무"],
                **common))

    # ── STEP 8. 연결 법률 — 개인정보 보호법 · 신용정보법 ───────────────
    #   같은 질문(사람이 실질적으로 개입하나)이 법마다 다르게 작동한다.
    #   두 법은 정의 자체가 '완전히 자동화된 결정' / '종사자가 관여하지 아니하고'라서 사람이 개입하면 대상이 아니다.
    #   수범자도 나눠 본다: 권리(MAY)의 주어는 정보주체 → 사업자에게는 '요구가 오면 대응'으로 바꿔 보여준다.
    if f.purpose in INDIVIDUAL_DECISION_PURPOSES:
        pipa_notes = ["대상: '완전히 자동화된 시스템'으로 개인정보를 처리해 내린 결정 (제37조의2①) — 사람이 실질적으로 개입하면 해당하지 않음"]
        if f.purpose == "PUBLIC_SERVICE_DECISION":
            pipa_notes.append("행정청의 자동적 처분(행정기본법 제20조)은 제외")
        disclose = dict(label="제37조의2", doc="PIPA", records=["PIPA_37-2_4", "PIPA_37-2_1"], decompiled="pipa_37_2.py")
        if mode == "AUTOMATED":
            items.append(RuleItem(
                key="pipa_37_2", status="REQUIRED", obligation="MUST",
                summary="자동화된 결정의 기준·절차·처리 방식 공개 (④)",
                notes=pipa_notes + ["④ 개인정보처리자의 의무 — 자동화된 결정을 하면 요구가 없어도 공개"],
                checklist=["자동화된 결정의 기준과 절차 정리", "개인정보가 처리되는 방식 정리",
                           "정보주체가 쉽게 확인할 수 있는 곳에 공개 (예: 개인정보 처리방침·서비스 화면)"],
                todo={"title": "자동화된 결정 기준 공개", "desc": "개인정보 보호법 제37조의2④ 기준·절차·처리 방식 공개"},
                **disclose))
            items.append(RuleItem(
                key="pipa_37_2_3", status="CONDITIONAL", label="제37조의2③", obligation="MUST", doc="PIPA",
                condition="IF 정보주체가 거부·설명 요구", summary="적용 중단 또는 인적 개입 재처리·설명",
                records=["PIPA_37-2_3", "PIPA_37-2_1", "PIPA_37-2_2"],
                notes=["① 거부권(권리·의무에 중대한 영향 시)과 ② 설명요구권의 주어는 정보주체 (MAY)",
                       "사업자 의무는 ③: 요구를 받으면 정당한 사유가 없는 한 적용하지 않거나 인적 개입 재처리·설명"],
                decompiled="pipa_37_2.py",
                checklist=["거부 요청 접수 창구와 처리 기한 정하기",
                           "거부 시 자동화된 결정 적용 중단 또는 사람이 다시 처리하는 절차",
                           "설명 요구 응대 자료 (결정 기준·주요 요인)", "거절할 '정당한 사유' 판단 기준 기록"],
                todo={"title": "거부·설명 요구 대응 절차", "desc": "개인정보 보호법 제37조의2③ 요구가 오면 할 조치 준비"},
            ))
        elif mode == "HUMAN_FINAL":
            items.append(RuleItem(
                key="pipa_37_2", status="INFO", summary="사람이 최종 결정 → 완전히 자동화된 결정 아님",
                notes=pipa_notes + ["사람의 검토가 형식적이면 '완전히 자동화된 결정'으로 볼 수 있으므로 검토 방식을 기록"],
                **disclose))
        else:
            items.append(RuleItem(
                key="pipa_37_2", status="CONDITIONAL", obligation="MUST", condition=IF_AUTOMATED,
                summary="자동화된 결정의 기준·절차 공개 (④)",
                notes=pipa_notes + ["완전히 자동화된 결정이면 ④ 공개(REQUIRED)와 ③ 거부·설명 요구 대응(요구가 오면)이 함께 생김",
                                    "AI기본법 고영향 판단과 같은 질문(사람이 실질적으로 개입하나)이 들어가지만, 정의가 달라 결론도 다를 수 있음"],
                checklist=["자동화된 결정의 기준·절차·처리 방식 공개 준비", "거부·설명 요구 대응 절차 준비"],
                **disclose))

    if f.purpose == "LENDING":
        credit_records = ["CREDIT_36-2_1", "CREDIT_36-2_2", "CREDIT_36-2_3", "CREDIT_2_14"]
        if mode == "HUMAN_FINAL":
            items.append(RuleItem(
                key="credit_36_2", status="INFO", label="제36조의2", doc="CREDIT",
                summary="종사자가 평가에 관여 → 자동화평가 아님", records=["CREDIT_2_14"] + credit_records[:-1],
                notes=["자동화평가 = 종사자가 평가 업무에 관여하지 않고 컴퓨터로만 처리 (제2조제14호)",
                       "종사자 관여가 형식적이면 자동화평가로 볼 수 있으므로 관여 방식을 기록"],
                decompiled="credit_36_2.py",
            ))
        else:
            items.append(RuleItem(
                key="credit_36_2", status="CONDITIONAL", label="제36조의2", doc="CREDIT",
                condition="IF 정보주체 요구" if mode == "AUTOMATED" else "IF 자동화평가 · 정보주체 요구",
                summary="자동화평가 설명·정정·재산출 요구가 오면 대응",
                records=credit_records,
                notes=["①② 설명 요구·정정·재산출 요구는 신용정보주체의 권리 (MAY, 주어 = 정보주체) — 사업자 의무 조문이 아님",
                       "사업자(개인신용평가회사등)는 요구를 받으면 대응하고, ③ 법령상 불가피·거래 곤란 등은 거절할 수 있음 (MAY)",
                       "자동화평가 = 종사자가 평가 업무에 관여하지 않고 컴퓨터로만 처리 (제2조제14호)"],
                externals=["대상 신용정보제공·이용자 범위 (신용정보법 시행령 — KB 밖)"],
                decompiled="credit_36_2.py",
                checklist=["요구 접수 창구 정하기",
                           "설명 자료: 자동화평가 여부·결과·주요 기준·기초정보 개요",
                           "정보 제출·기초정보 정정·삭제·결과 재산출 요구 처리 절차",
                           "거절 사유(③)와 통지 방식 정리"],
                todo={"title": "자동화평가 요구 대응 절차", "desc": "신용정보법 제36조의2 — 정보주체가 요구하면 할 설명·재산출 절차"},
            ))

    if f.uses_biometric:
        items.append(RuleItem(
            key="pipa_23", status="CONDITIONAL", label="제23조", obligation="MUST_NOT", doc="PIPA",
            condition="IF 민감정보 해당", summary="얼굴 등 생체정보 처리 제한 (별도 동의 등 예외)",
            records=["PIPA_23_1"],
            notes=["민감정보는 원칙적으로 처리 금지, 별도 동의·법령 근거가 있으면 예외 (단서)",
                   "생체인식정보가 민감정보에 포함되는지는 개인정보 보호법 시행령에 있음 → 이번 데이터 범위 밖"],
            externals=["민감정보 범위 (개인정보 보호법 시행령 — KB 밖)"], decompiled="pipa_23.py",
            checklist=["얼굴 영상 수집 목적·항목 정리", "다른 개인정보와 별도로 동의 받기"],
        ))
    return items
