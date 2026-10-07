# rules.py — Rule Engine: 특성(ServiceFeatures) → 빌드 로그 항목
#
# 원칙
#   1. 조건이 확정되지 않은 의무는 REQUIRED가 아니라 CONDITIONAL로 둔다.
#   2. 법률 본문만으로 단정할 수 없으면 REVIEW로 두고 되묻는다. 확률을 지어내지 않는다.
#   3. 주어가 사업자가 아닌 조문(국가기관등·장관)은 의무가 아니라 OPPORTUNITY / REGULATORY_RISK로 바꿔 보여준다.
#   4. Knowledge Base 밖의 법률은 판정하지 않고 OUT_OF_SCOPE로 표시만 한다.
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
IF_HIGH_IMPACT = "IF HIGH_IMPACT_AI"

# ── 되묻기 질문 ───────────────────────────────────────────────
Q_HIGH_IMPACT = {
    "id": "high_impact",
    "text": "AI 결과는 실제 판단·평가에 어떻게 쓰이나요?",
    "help": "제2조제4호사목은 '판단 또는 평가'를 기준으로 합니다. 추천만 하는 구조는 법률 본문만으로 단정하기 어려워요.",
    "options": [
        {"value": "automated", "label": "AI 결과가 그대로 판단·평가로 쓰여요"},
        {"value": "human_final", "label": "사람이 최종 결정하고 AI는 참고용이에요"},
        {"value": "assume", "label": "고영향 AI로 보고 대비할게요"},
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
    "text": "이용자 수·매출액이 대통령령으로 정하는 기준에 해당하나요?",
    "help": "기준 수치는 법률 본문에 없고 대통령령에 위임돼 있어요 (EXTERNAL).",
    "options": [
        {"value": "yes", "label": "해당해요"},
        {"value": "no", "label": "해당하지 않아요"},
        {"value": "unknown", "label": "모르겠어요"},
    ],
}
Q_COMPUTE = {
    "id": "compute",
    "text": "학습 누적 연산량이 대통령령 기준 이상인 모델을 제공하나요?",
    "help": "외부 모델을 이용하는 경우에도 자동으로 제외하지 않아요. 모델 제공자와 시스템 구조를 확인해 주세요.",
    "options": [
        {"value": "yes", "label": "예"},
        {"value": "no", "label": "아니요"},
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
    externals: list[str] = field(default_factory=list)  # 하위 규정 의존 (EXTERNAL)
    decompiled: str | None = None
    checklist: list[str] = field(default_factory=list)  # 이 조문의 구현 체크리스트
    todo: dict | None = None                            # 전체 '적용 사항 체크리스트'에 들어갈 항목
    question: dict | None = None
    penalty_from: str | None = None                     # 근거 체인을 그릴 레코드


def match_domain(f: ServiceFeatures) -> str | None:
    if f.purpose == "CRIMINAL_INVESTIGATION":
        return "BA" if f.uses_biometric else None   # 바목은 생체인식정보 분석·활용일 때만
    return DOMAIN_BY_PURPOSE.get(f.purpose or "")


def resolve_high_impact(f: ServiceFeatures, domain: str | None, answers: dict) -> tuple[bool | None, str]:
    """고영향 AI 여부: True / False / None(REVIEW)"""
    if domain is None:
        return False, "제2조제4호 가~차목 영역에 해당하지 않음"
    if f.affects_rights is False:
        return False, "권리·안전에 중대한 영향 우려가 없다고 확인됨"
    choice = answers.get("high_impact")
    if choice == "assume":
        return True, "고영향 AI로 보고 대비하기로 선택함"
    if choice == "automated" or f.decision_mode == "AUTOMATED":
        return True, "AI 결과가 그대로 판단·평가로 쓰임"
    if f.decision_mode == "HUMAN_FINAL":
        return None, "사람이 최종 결정하는 구조 — 법률 본문만으로 단정 불가"
    if f.decision_mode == "RECOMMEND":
        return None, "AI가 추천·보조하는 구조 — '판단 또는 평가' 해당 여부 추가 검토 필요"
    return None, "AI 결과가 결정에 쓰이는 방식에 대한 정보가 없음"


def _with_answer(question: dict, answers: dict) -> dict:
    return {**question, "answer": answers.get(question["id"])}


def evaluate(f: ServiceFeatures, answers: dict | None = None) -> list[RuleItem]:
    answers = answers or {}
    items: list[RuleItem] = []

    # ── STEP 0. Scope Check (제4조) ──────────────────────────
    if f.defense_only:
        items.append(RuleItem(
            key="scope_exclusion", status="REVIEW", label="제4조②",
            summary="국방·국가안보 목적 전용 — 적용 제외 가능성",
            records=["ARTICLE_4_2"], notes=["국방·국가안보 목적으로'만' 개발·이용되는 AI 중 대통령령으로 정하는 것은 적용 제외"],
            externals=["대통령령: 적용 제외 대상 인공지능"], decompiled="art4_scope.py",
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

    # ── STEP 1. 고영향 AI 영역 매칭 (제2조제4호) ─────────────────
    domain = match_domain(f)
    hi, hi_reason = resolve_high_impact(f, domain, answers)
    if domain:
        ko = MOK_KO[domain]
        summary = DOMAIN_SUMMARY.get(domain) or (
            "대출 심사 판단·평가 관련성" if f.purpose == "LENDING" else "채용 판단·평가 관련성")
        notes = ["고영향 AI 정의 = 중대한 영향 우려 AND 가~카목 영역 (제2조제4호)"]
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
        records=["ARTICLE_33_1_A", "ARTICLE_33_1_B"],
        notes=["한 문장에 두 절: '검토하여야 하며'(MUST) + '요청할 수 있다'(MAY)",
               "MUST이지만 제재 조항 없음 (penalty: NONE)"],
        decompiled="art33_1.py", penalty_from="ARTICLE_33_1_A",
        checklist=["가~카목 영역 해당 여부 검토 결과를 기록으로 남기기",
                   "AI 결과가 결정에 쓰이는 방식(자동 / 추천 / 사람 최종) 문서화",
                   "판단이 어려우면 과기부 장관에게 확인 요청 검토 (제33조① 후단)"],
        todo={"title": "고영향 AI 해당 여부 검토", "desc": "제33조에 따라 고영향 AI 기준에 해당하는지 사전 검토"},
    ))

    # ── STEP 3. 고영향 여부 판정 결과 ─────────────────────────────
    if hi is None:
        items.append(RuleItem(
            key="high_impact", status="REVIEW", label="HIGH_IMPACT_AI",
            summary={"RECOMMEND": "추천이 판단·평가에 해당하는지 추가 검토",
                     "HUMAN_FINAL": "사람 최종 결정 구조 — 가이드라인 확인 필요"}.get(
                f.decision_mode or "", "고영향 AI 해당 여부 추가 검토"),
            records=["ARTICLE_2_4", "ARTICLE_33_3", "ARTICLE_33_1_B"],
            notes=[hi_reason, "고영향 여부가 확정되면 CONDITIONAL 항목이 REQUIRED / SHOULD로 바뀝니다"],
            externals=["제33조③ 고영향 AI 기준·예시 가이드라인"],
            decompiled="high_impact_review.py",
            question=_with_answer(Q_HIGH_IMPACT, answers),
        ))
    elif hi:
        items.append(RuleItem(
            key="high_impact", status="MATCH", label="HIGH_IMPACT_AI",
            summary="고영향 AI로 판정", records=["ARTICLE_2_4"], notes=[hi_reason],
            decompiled="high_impact_review.py",
            question=_with_answer(Q_HIGH_IMPACT, answers) if "high_impact" in answers else None,
        ))
    else:
        items.append(RuleItem(
            key="high_impact", status="INFO", label="HIGH_IMPACT_AI",
            summary="가~차목 영역 미해당 · 카목(대통령령) 확인",
            records=["ARTICLE_2_4", "ARTICLE_2_4_KA"], notes=[hi_reason],
            externals=["카목: 대통령령으로 정하는 영역"], decompiled="not_high_impact.py",
        ))

    # ── STEP 4. 제31조 투명성 ────────────────────────────────────
    if hi or f.generative:
        why = "고영향 AI" if hi else "생성형 AI"
        items.append(RuleItem(
            key="art31_1", status="REQUIRED", label="제31조①", obligation="MUST",
            summary=f"AI 기반 서비스 사전 고지 ({why})", records=["ARTICLE_31_1", "ARTICLE_31_4"],
            notes=["고영향 AI 또는 생성형 AI 제공 시 적용", "직접 과태료 대상 (제43조①1호)"],
            externals=["제31조④ 고지 방법·예외 (대통령령)"], decompiled="art31_1.py",
            penalty_from="ARTICLE_31_1",
            checklist=["서비스 이용 전에 AI 기반 운용 사실을 고지하는 화면·문구 마련",
                       "고지 시점이 '사전'인지 확인 (가입·첫 이용 단계)",
                       "고지 방법·예외는 대통령령(제31조④) 확인"],
            todo={"title": "AI 사용 사전고지 검토", "desc": "제31조에 따른 이용자 대상 사전고지 방법 검토"},
        ))
    elif hi is None:
        items.append(RuleItem(
            key="art31_1", status="CONDITIONAL", label="제31조①", obligation="MUST",
            condition=IF_HIGH_IMPACT, summary="AI 기반 서비스 사전 고지",
            records=["ARTICLE_31_1", "ARTICLE_31_4"],
            notes=["고영향 AI로 확정되면 REQUIRED", "직접 과태료 대상 (제43조①1호)"],
            externals=["제31조④ 고지 방법·예외 (대통령령)"], decompiled="art31_1.py",
            penalty_from="ARTICLE_31_1",
            checklist=["서비스 이용 전에 AI 기반 운용 사실을 고지하는 화면·문구 마련",
                       "고지 방법·예외는 대통령령(제31조④) 확인"],
            todo={"title": "AI 사용 사전고지 검토", "desc": "제31조에 따른 이용자 대상 사전고지 방법 검토"},
        ))

    if f.generative:
        items.append(RuleItem(
            key="art31_2", status="REQUIRED", label="제31조②", obligation="MUST",
            summary="생성형 AI 결과물 표시", records=["ARTICLE_31_2", "ARTICLE_31_4"],
            notes=["MUST이지만 직접 과태료가 아니라 제40조 사실조사 → 시정명령 경로 (INDIRECT)"],
            externals=["제31조④ 표시 방법·예외 (대통령령)"], decompiled="art31_2.py",
            penalty_from="ARTICLE_31_2",
            checklist=["결과물에 생성형 AI로 생성되었다는 표시 넣기", "다운로드·공유 시에도 표시가 유지되는지 확인"],
            todo={"title": "생성형 결과물 표시 설계", "desc": "제31조②에 따른 AI 생성 결과물 표시 방식 설계"},
        ))
    if f.realistic_synthetic_media:
        items.append(RuleItem(
            key="art31_3", status="REQUIRED", label="제31조③", obligation="MUST",
            summary="실제와 구분 어려운 결과물 AI 생성 고지·표시",
            records=["ARTICLE_31_3_A", "ARTICLE_31_3_B"],
            notes=["예술적·창의적 표현물은 향유를 저해하지 않는 방식 허용 (후단 MAY)"],
            decompiled="art31_3.py", penalty_from="ARTICLE_31_3_A",
            checklist=["이용자가 '명확하게 인식'할 수 있는 고지·표시 방식 정하기",
                       "예술적 표현물이면 전시·향유를 해치지 않는 방식 검토"],
            todo={"title": "딥페이크성 결과물 고지", "desc": "제31조③에 따른 AI 생성 사실 고지·표시 방식 검토"},
        ))
    elif f.generative and f.realistic_synthetic_media is None:
        items.append(RuleItem(
            key="art31_3", status="CONDITIONAL", label="제31조③", obligation="MUST",
            condition="IF 실제와 구분 어려운 결과물", summary="AI 생성 사실 고지·표시",
            records=["ARTICLE_31_3_A", "ARTICLE_31_3_B"],
            notes=["실사 수준의 음향·이미지·영상을 제공하면 REQUIRED"],
            decompiled="art31_3.py", penalty_from="ARTICLE_31_3_A",
        ))

    # ── STEP 5. 제32조 — 이용사업자라도 자동 제외하지 않음 ─────────
    if f.business_type or f.generative:
        choice = answers.get("compute")
        if choice == "yes":
            items.append(RuleItem(
                key="art32_1", status="REQUIRED", label="제32조①", obligation="MUST",
                summary="고연산 AI 안전성 확보 · 결과 제출",
                records=["ARTICLE_32_1", "ARTICLE_32_2", "ARTICLE_32_3"],
                externals=["제32조③ 이행 방식 (장관 고시)"], decompiled="art32_1.py",
                penalty_from="ARTICLE_32_1", question=_with_answer(Q_COMPUTE, answers),
                checklist=["수명주기 전반의 위험 식별·평가·완화", "안전사고 모니터링·대응 체계 구축",
                           "이행 결과를 과기부에 제출"],
                todo={"title": "고연산 AI 안전성 조치", "desc": "제32조에 따른 위험관리·결과 제출 준비"},
            ))
        elif choice != "no":
            notes = ["학습 누적 연산량 기준은 법률 본문에 없음 → 대통령령 확인 필요"]
            if f.business_type == "USER_BUSINESS":
                notes.append("외부 모델을 이용하더라도 자동 제외하지 않음 — 모델 제공자·시스템 구조 확인")
            items.append(RuleItem(
                key="art32_1", status="REVIEW", label="제32조①", obligation="MUST",
                summary="학습 누적 연산량 기준(대통령령) 확인 필요",
                records=["ARTICLE_32_1", "ARTICLE_32_2"], notes=notes,
                externals=["대통령령: 학습 누적 연산량 기준"], decompiled="art32_1.py",
                penalty_from="ARTICLE_32_1", question=_with_answer(Q_COMPUTE, answers),
            ))

    # ── STEP 6. 고영향 AI 책무 (제34·35·30조) ─────────────────────
    if hi is not False:
        status = "REQUIRED" if hi else "CONDITIONAL"
        items.append(RuleItem(
            key="art34_1", status=status, label="제34조①", obligation="MUST",
            condition=None if hi else IF_HIGH_IMPACT, summary="안전성·신뢰성 조치",
            records=["ARTICLE_34_1", "ARTICLE_34_2", "ARTICLE_34_3"],
            notes=["1~5호 + 6호(위원회 심의·의결 사항) + ②장관 고시까지 확인해야 함",
                   "③ 다른 법령상 준하는 조치를 이행했으면 이행한 것으로 봄 (TREAT_AS)",
                   "위반 시 제40조 사실조사 → 시정명령 → 불이행 시 과태료 (INDIRECT)"],
            externals=["대통령령: 조치 이행 방법", "6호: 위원회 심의·의결 사항", "② 장관 고시"],
            decompiled="art34_1.py", penalty_from="ARTICLE_34_1",
            checklist=["1호 위험관리방안 수립·운영", "2호 결과·주요 기준·학습데이터 개요 설명 방안",
                       "3호 이용자 보호 방안", "4호 사람의 관리·감독 체계",
                       "5호 조치 내용 확인 문서 작성·보관", "6호 위원회 심의·의결 사항 확인 (EXTERNAL)"],
            todo={"title": "위험관리방안 준비", "desc": "제34조에 따른 안전성·신뢰성 확보 조치 계획 수립"},
        ))
        items.append(RuleItem(
            key="art35_1", status="SHOULD" if hi else "CONDITIONAL", label="제35조①", obligation="SHOULD",
            condition=None if hi else IF_HIGH_IMPACT, summary="기본권 영향평가 노력",
            records=["ARTICLE_35_1", "ARTICLE_35_3"],
            notes=["노력의무(SHOULD) — 직접 제재 없음", "실시하면 공공기관 도입 시 우선 고려 (제35조②)"],
            externals=["제35조③ 영향평가 내용·방법 (대통령령)"], decompiled="art35_1.py",
            penalty_from="ARTICLE_35_1",
            checklist=["영향받는 자(지원자 등)의 기본권 영향 식별", "평가 결과와 완화 조치 기록"],
            todo={"title": "영향평가 필요성 검토", "desc": "제35조에 따른 기본권 영향평가 실시 필요성 검토"},
        ))
        items.append(RuleItem(
            key="art30_3", status="SHOULD" if hi else "CONDITIONAL", label="제30조③", obligation="SHOULD",
            condition=None if hi else IF_HIGH_IMPACT, summary="사전 검·인증 노력",
            records=["ARTICLE_30_3"], notes=["노력의무(SHOULD) — 직접 제재 없음",
                                              "받으면 공공기관 이용 시 우선 고려 (제30조④)"],
            decompiled="art30_3.py", penalty_from="ARTICLE_30_3",
            todo={"title": "검·인증 추진 여부 검토", "desc": "제30조③에 따른 사전 검·인증 추진 여부 검토"},
        ))
        items.append(RuleItem(
            key="opp_public", status="OPPORTUNITY", label="제30조④",
            summary="공공기관 도입 검토 시 우선 고려 요소",
            records=["ARTICLE_30_4", "ARTICLE_35_2"],
            notes=["주어가 사업자가 아니라 국가기관등 → 사업자에게는 의무가 아니라 기회 신호",
                   "검·인증(제30조④)·영향평가(제35조②)를 갖추면 우선 고려 대상"],
            decompiled="opportunity_public.py",
        ))
        if f.sme:
            items.append(RuleItem(
                key="opp_sme", status="OPPORTUNITY", label="제17조③",
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
            externals=["대통령령: 우선 고려 대상 인공지능제품·서비스"], decompiled="art16_3.py",
        ))

    # ── STEP 7. 제36조 국내대리인 ─────────────────────────────────
    if f.overseas is None:
        items.append(RuleItem(
            key="art36_1", status="REVIEW", label="제36조", obligation="MUST",
            summary="국내 주소·영업소 여부 정보 필요", records=["ARTICLE_36_1", "ARTICLE_36_2"],
            notes=["국내에 주소·영업소가 없는 사업자 + 이용자 수·매출액 기준 해당 시 지정 의무"],
            decompiled="art36_1.py", penalty_from="ARTICLE_36_1",
            question=_with_answer(Q_DOMESTIC, answers),
        ))
    elif f.overseas:
        choice = answers.get("threshold")
        common = dict(label="제36조①", obligation="MUST", records=["ARTICLE_36_1", "ARTICLE_36_3"],
                      decompiled="art36_1.py", penalty_from="ARTICLE_36_1",
                      question=_with_answer(Q_THRESHOLD, answers))
        if choice == "yes":
            items.append(RuleItem(
                key="art36_1", status="REQUIRED", summary="국내대리인 서면 지정·신고",
                notes=["미지정 시 직접 과태료 (제43조①2호)", "③ 대리인의 위반은 사업자의 행위로 봄 (TREAT_AS)"],
                checklist=["국내에 주소·영업소가 있는 대리인 선정", "서면 지정 후 과기부 신고"],
                todo={"title": "국내대리인 지정", "desc": "제36조에 따른 국내대리인 서면 지정·신고"},
                **common))
        elif choice == "no":
            items.append(RuleItem(key="art36_1", status="INFO", summary="기준 미해당 — 지정 의무 없음",
                                  notes=["기준 수치가 바뀌면 다시 확인"], **common))
        else:
            items.append(RuleItem(
                key="art36_1", status="REVIEW", summary="이용자 수·매출액 기준(대통령령) 확인 필요",
                notes=["국내 주소·영업소 없음 확인됨", "기준 수치는 대통령령에 위임 (EXTERNAL)"],
                externals=["대통령령: 이용자 수·매출액 기준"], **common))

    # ── STEP 8. Knowledge Base 범위 밖 ───────────────────────────
    if f.uses_biometric or f.handles_personal_data:
        what = "얼굴정보 등 생체정보 처리" if f.uses_biometric else "개인정보 처리"
        items.append(RuleItem(
            key="out_of_scope", status="OUT_OF_SCOPE", label="KB 범위 밖",
            summary=f"{what} — 타 법률 검토 필요할 수 있음",
            notes=["현재 분석 범위: 인공지능기본법",
                   "다른 법률 위반 여부는 판정하지 않음 ('위반'으로 단정하지 않음)"],
            decompiled="out_of_scope.py",
        ))
    return items
