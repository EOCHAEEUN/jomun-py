# features.py — 서비스 설명 → 사실 특성(ServiceFeatures)
#
# LLM은 '판정'하지 않고 '추출'만 한다. API 키가 없거나 LLM 호출이 실패하면
# 키워드 규칙 기반 추출기(heuristic)로 대체한다.
import logging
import re

from app.config import LLM_MODEL, use_llm
from app.engine.prompts import FEATURE_SYSTEM_PROMPT
from app.schemas import ServiceFeatures

log = logging.getLogger(__name__)

# 목적(purpose) 키워드 — 위에서부터 먼저 걸리는 것이 우선
PURPOSE_RULES: list[tuple[str, list[str]]] = [
    ("DEFENSE", ["국방", "군사", "국가안보", "무기체계", "군 작전"]),
    ("CRIMINAL_INVESTIGATION", ["범죄 수사", "수사", "용의자", "피의자", "체포", "경찰", "수배"]),
    ("STUDENT_ASSESSMENT", ["학생 평가", "학생 성적", "성적", "학업 평가", "수행평가", "채점"]),
    ("RECRUITMENT", ["채용", "면접", "지원자", "입사", "구직", "이력서", "서류 심사", "인재 선발"]),
    ("LENDING", ["대출", "여신", "신용평가", "신용 평가", "신용점수", "보험 심사"]),
    ("MEDICAL_DEVICE", ["의료기기", "디지털의료기기", "진단 보조", "의료 영상", "판독"]),
    ("HEALTHCARE", ["진료", "환자", "병원", "의료", "헬스케어", "처방"]),
    ("ENERGY", ["전력", "에너지", "발전소", "전력망", "가스 공급"]),
    ("DRINKING_WATER", ["먹는물", "정수장", "수돗물", "정수 처리"]),
    ("NUCLEAR", ["원자력", "원전", "핵물질"]),
    ("TRANSPORT", ["자율주행", "교통", "신호 제어", "철도", "항공 관제"]),
    ("PUBLIC_SERVICE_DECISION", ["복지 수급", "수급 자격", "자격 확인", "공공서비스", "과세", "비용징수", "행정 처분"]),
    ("RECOMMENDATION", ["영화 추천", "콘텐츠 추천", "상품 추천", "음악 추천", "맞춤 추천", "추천 시스템"]),
    ("CONTENT_GENERATION", ["이미지 생성", "마케팅 이미지", "영상 생성", "글 작성", "카피 작성", "음성 합성"]),
    ("CUSTOMER_SERVICE", ["상담", "고객센터", "고객 응대", "챗봇"]),
]
SCHOOL_LEVEL = ["초등", "초·중", "중등", "중학", "고등학", "고교", "유치원", "유아"]  # 대학은 차목 아님
RIGHTS_PURPOSES = {
    "RECRUITMENT", "LENDING", "CRIMINAL_INVESTIGATION", "HEALTHCARE", "MEDICAL_DEVICE", "ENERGY",
    "DRINKING_WATER", "NUCLEAR", "TRANSPORT", "PUBLIC_SERVICE_DECISION", "STUDENT_ASSESSMENT",
}

GENERATIVE = ["생성형", "생성", "LLM", "GPT", "챗봇", "합성", "만들어 주", "작성해 주", "제작"]
REALISTIC = ["딥페이크", "가상 인물", "가상 인간", "디지털 휴먼", "실제와 구분", "실사", "합성 영상",
             "보이스 클로닝", "음성 복제", "목소리 복제", "AI 아바타"]
# "실제 사람 목소리처럼", "실제와 구분하기 어려운" 처럼 단어 목록에 없는 표현
REALISTIC_RE = re.compile(r"(실제|진짜|실존)\s*(사람|인물)[^.,]{0,8}?(처럼|같은|같이)|구분하기\s*어려|구별하기\s*어려|구별이\s*안")
MEDIA = ["이미지", "영상", "음성", "사진", "목소리", "음향", "그림"]
BIOMETRIC = ["얼굴", "안면", "지문", "홍채", "정맥", "생체", "음성 인식", "목소리로 본인"]
PERSONAL_DATA = ["개인정보", "위치정보", "건강정보", "주민등록"]
AUTOMATED = re.compile(r"자동(으로|적으로)?\s*(결정|승인|거절|탈락|평가|선발|채점|판단|심사|제어|배정|판독|산출|진단|분류|조절)")
# '자동'이라는 말 없이 사람의 개입이 없다고 밝힌 구조 ("의료진 개입 없이", "사람 검토 없이", "스스로 결정")
NO_HUMAN = re.compile(
    r"(사람|인간|담당자|직원|전문가|의료진|의사|교사|심사역|심사자|운전자|기관사|관리자|상담원)\s*(의)?\s*"
    r"(개입|검토|확인|관여|판단|조작)\s*(이|을|를)?\s*없이"
    r"|스스로\s*(결정|판단|제어|운행|운전|조절)")
HUMAN_FINAL = ["최종 결정은 사람", "사람이 최종", "담당자가 최종", "인사담당자가 결정", "사람이 결정"]
RECOMMEND = ["추천", "보조", "참고", "제안", "도와", "지원하는", "지원해"]
# overseas = '국내에 주소·영업소가 없는 사업자' (제36조). '해외'라는 말만으로는 단정하지 않는다.
#   확정 문구가 있을 때만 True, 해외·외국 언급만 있으면 None으로 두고 되묻는다.
OVERSEAS_CONFIRMED = re.compile(
    r"(국내|한국)\s*(에|내)?\s*(는|에는)?\s*(주소|법인|영업소|지사|사무소)[^.,]{0,12}?(없|두지\s*않)")
OVERSEAS_MENTION = ["해외", "국외", "외국 기업", "외국계", "미국 법인", "글로벌 본사", "미국 본사"]
OVERSEAS_NO = ["국내 기업", "국내 법인", "한국 회사", "국내 스타트업"]
USER_BUSINESS = ["API", "GPT", "외부 모델", "외부 LLM", "OpenAI", "오픈AI", "Claude", "Gemini", "LLM API"]
DEVELOPER = ["자체 모델", "직접 학습", "사전학습", "파운데이션 모델 개발", "모델을 개발", "자체 개발한 모델"]
PUBLIC_TARGET = ["공공기관", "지자체", "정부 납품", "조달", "관공서", "공공 납품"]
SME = ["스타트업", "중소기업", "소상공인", "벤처"]
# 시행령 제23조④2호: 사업자의 내부 업무 용도로만 사용
INTERNAL_ONLY = re.compile(r"(내부\s*업무|사내|내부\s*(직원|임직원))[^.,]{0,10}?(으로만|에만|만\s*(사용|쓰|이용)|전용)")
# 시행령 제29조① 기준과 비교할 수치 (판정은 Rule Engine이 한다)
DAILY_USERS = re.compile(
    r"(?:일평균|하루|1일\s*평균|일일|일간)\s*(?:국내\s*)?(?:이용자|사용자)\s*(?:수)?\s*(?:는|가|이)?\s*(?:약|대략)?\s*"
    r"([\d,]+(?:\.\d+)?)\s*(만)?\s*명")
REVENUE = re.compile(r"매출(?:액)?\s*(?:은|이|는)?\s*(?:약|대략)?\s*([\d,]+(?:\.\d+)?)\s*(조|억|만)?\s*원")
UNIT = {None: 1, "": 1, "만": 10**4, "억": 10**8, "조": 10**12}


def _amount(num: str, unit: str | None) -> int:
    return int(float(num.replace(",", "")) * UNIT[unit])


def _hit(text: str, words: list[str]) -> str | None:
    for w in words:
        if w.lower() in text.lower():
            return w
    return None


def heuristic_extract(spec: str) -> ServiceFeatures:
    f = ServiceFeatures()
    ev = f.evidence

    for purpose, words in PURPOSE_RULES:
        w = _hit(spec, words)
        if not w:
            continue
        if purpose == "STUDENT_ASSESSMENT" and not _hit(spec, SCHOOL_LEVEL):
            continue  # 대학 평가 등은 차목(유아·초·중등) 아님
        f.purpose = purpose
        ev.append(f"purpose={purpose} ← '{w}'")
        break
    if f.purpose is None:
        f.purpose = "OTHER"

    if f.purpose == "DEFENSE" and re.search(r"(국방|군사|안보)[^.]*?(으로만|만\s|전용|만을)", spec):
        f.defense_only = True
        ev.append("defense_only ← '목적으로만/전용'")

    if (w := _hit(spec, BIOMETRIC)):
        f.uses_biometric = True
        ev.append(f"uses_biometric ← '{w}'")
    else:
        f.uses_biometric = False

    if (w := _hit(spec, GENERATIVE)):
        f.generative = True
        ev.append(f"generative ← '{w}'")
    else:
        f.generative = False

    if (w := _hit(spec, REALISTIC)) or (m := REALISTIC_RE.search(spec)):
        f.realistic_synthetic_media = True
        ev.append(f"realistic_synthetic_media ← '{w or m.group(0)}'")
    elif f.generative and _hit(spec, MEDIA):
        f.realistic_synthetic_media = None   # 실사 수준인지 알 수 없음 → CONDITIONAL
    else:
        f.realistic_synthetic_media = False

    if f.purpose in RIGHTS_PURPOSES:
        f.affects_rights = True

    if (w := _hit(spec, HUMAN_FINAL)):
        f.decision_mode = "HUMAN_FINAL"
        ev.append(f"decision_mode=HUMAN_FINAL ← '{w}'")
    elif (m := NO_HUMAN.search(spec) or AUTOMATED.search(spec)):
        f.decision_mode = "AUTOMATED"
        ev.append(f"decision_mode=AUTOMATED ← '{m.group(0)}'")
    elif (w := _hit(spec, RECOMMEND)):
        f.decision_mode = "RECOMMEND"
        ev.append(f"decision_mode=RECOMMEND ← '{w}'")

    if (m := OVERSEAS_CONFIRMED.search(spec)):
        f.overseas = True
        ev.append(f"overseas ← '{m.group(0)}'")
    elif (w := _hit(spec, OVERSEAS_NO)):
        f.overseas = False
        ev.append(f"overseas=False ← '{w}'")
    elif (w := _hit(spec, OVERSEAS_MENTION)):
        # 해외 기업이라도 국내 법인·영업소가 있을 수 있다 → 단정하지 않고 되묻기 (None)
        ev.append(f"overseas=미확정 ← '{w}' (국내 주소·영업소 여부는 확인 질문으로)")

    if (w := _hit(spec, DEVELOPER)):
        f.business_type = "DEVELOPER"
        ev.append(f"business_type=DEVELOPER ← '{w}'")
    elif (w := _hit(spec, USER_BUSINESS)):
        f.business_type = "USER_BUSINESS"
        ev.append(f"business_type=USER_BUSINESS ← '{w}'")

    if (w := _hit(spec, PUBLIC_TARGET)):
        f.public_sector_target = True
        ev.append(f"public_sector_target ← '{w}'")
    if (w := _hit(spec, SME)):
        f.sme = True
        ev.append(f"sme ← '{w}'")
    if f.uses_biometric or _hit(spec, PERSONAL_DATA):
        f.handles_personal_data = True
    if (m := INTERNAL_ONLY.search(spec)):
        f.internal_only = True
        ev.append(f"internal_only ← '{m.group(0)}'")
    if (m := DAILY_USERS.search(spec)):
        f.domestic_daily_users = _amount(m.group(1), m.group(2))
        ev.append(f"domestic_daily_users={f.domestic_daily_users} ← '{m.group(0)}'")
    if (m := REVENUE.search(spec)):
        f.annual_revenue_krw = _amount(m.group(1), m.group(2))
        ev.append(f"annual_revenue_krw={f.annual_revenue_krw} ← '{m.group(0)}'")
    return f


def llm_extract(spec: str) -> ServiceFeatures:
    """LangChain + OpenAI 구조화 출력으로 특성 추출 (판정은 하지 않음)"""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=LLM_MODEL, temperature=0, timeout=20, max_retries=1)
    llm = llm.with_structured_output(ServiceFeatures)
    prompt = ChatPromptTemplate.from_messages([
        ("system", FEATURE_SYSTEM_PROMPT),
        ("human", "서비스 설명:\n{spec}"),
    ])
    return (prompt | llm).invoke({"spec": spec})


def extract(spec: str) -> tuple[ServiceFeatures, str]:
    """(특성, 사용한 추출기 이름)"""
    if use_llm():
        try:
            return llm_extract(spec), "llm"
        except Exception as e:  # 키 오류·네트워크 오류 등 → 규칙 기반으로 대체
            log.warning("LLM 특성 추출 실패, heuristic으로 대체: %s", e)
    return heuristic_extract(spec), "heuristic"


def apply_answers(f: ServiceFeatures, answers: dict[str, str]) -> ServiceFeatures:
    """되묻기 답변으로 특성을 확정한다"""
    f = f.model_copy(deep=True)
    domestic = answers.get("domestic_office")
    if domestic == "yes":
        f.overseas = False
    elif domestic == "no":
        f.overseas = True
    if answers.get("high_impact") == "human_final":
        f.decision_mode = "HUMAN_FINAL"
    elif answers.get("high_impact") == "automated":
        f.decision_mode = "AUTOMATED"
    return f
