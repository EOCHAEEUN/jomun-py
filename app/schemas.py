# schemas.py — API 입출력과 서비스 특성(feature) 스키마
from typing import Literal, Optional

from pydantic import BaseModel, Field

Purpose = Literal[
    "RECRUITMENT",              # 채용
    "LENDING",                  # 대출·신용 심사
    "CRIMINAL_INVESTIGATION",   # 범죄 수사·체포
    "HEALTHCARE",               # 보건의료 제공
    "MEDICAL_DEVICE",           # 의료기기·디지털의료기기
    "ENERGY",                   # 에너지 공급
    "DRINKING_WATER",           # 먹는물 생산
    "NUCLEAR",                  # 원자력
    "TRANSPORT",                # 교통
    "PUBLIC_SERVICE_DECISION",  # 국가기관등의 자격 확인·결정·비용징수
    "STUDENT_ASSESSMENT",       # 유아·초·중등 학생 평가
    "DEFENSE",                  # 국방·국가안보
    "RECOMMENDATION",           # 일반 추천 (영화·상품 등)
    "CONTENT_GENERATION",       # 콘텐츠 생성
    "CUSTOMER_SERVICE",         # 상담·고객응대
    "OTHER",
]


class ServiceFeatures(BaseModel):
    """서비스 설명에서 뽑은 '사실 특성'. 법률 판단(고영향 여부 등)은 여기서 하지 않는다."""

    purpose: Optional[Purpose] = Field(None, description="AI가 활용되는 주된 목적·영역")
    uses_biometric: Optional[bool] = Field(None, description="얼굴·지문·홍채·정맥·목소리 등 생체정보를 다루는가")
    generative: Optional[bool] = Field(None, description="글·이미지·소리·영상 등 결과물을 생성하는가")
    realistic_synthetic_media: Optional[bool] = Field(
        None, description="실제와 구분하기 어려운 가상의 음향·이미지·영상(딥페이크 등)을 제공하는가")
    affects_rights: Optional[bool] = Field(None, description="개인의 권리·의무, 생명·신체 안전에 영향을 주는 판단에 쓰이는가")
    decision_mode: Optional[Literal["AUTOMATED", "RECOMMEND", "HUMAN_FINAL"]] = Field(
        None, description="AI 결과가 그대로 결정(AUTOMATED)인지, 추천·보조(RECOMMEND)인지, 사람이 최종 결정(HUMAN_FINAL)인지")
    overseas: Optional[bool] = Field(None, description="국내에 주소 또는 영업소가 없는 사업자인가 (True=없음)")
    defense_only: Optional[bool] = Field(None, description="국방·국가안보 목적으로만 개발·이용되는가")
    business_type: Optional[Literal["DEVELOPER", "USER_BUSINESS"]] = Field(
        None, description="모델을 직접 개발(DEVELOPER)하는지, 외부 모델을 이용(USER_BUSINESS)하는지")
    public_sector_target: Optional[bool] = Field(None, description="공공기관·지자체 납품을 고려하는가")
    sme: Optional[bool] = Field(None, description="스타트업·중소기업·소상공인인가")
    handles_personal_data: Optional[bool] = Field(None, description="개인정보를 처리하는가")
    internal_only: Optional[bool] = Field(None, description="사업자의 내부 업무 용도로만 쓰는가 (외부 이용자에게 제공하지 않음)")
    domestic_daily_users: Optional[int] = Field(None, description="설명에 적힌 국내 1일 평균 이용자 수 (명)")
    annual_revenue_krw: Optional[int] = Field(None, description="설명에 적힌 전년도(연) 매출액 (원)")
    evidence: list[str] = Field(default_factory=list, description="각 특성을 뽑은 근거 문구")


class BuildRequest(BaseModel):
    spec: str = Field(..., max_length=500, description="서비스 설명")
    # 되묻기 질문에 대한 답 (예: {"high_impact": "assume", "domestic_office": "yes"})
    answers: dict[str, str] = Field(default_factory=dict)


class AskRequest(BaseModel):
    """일반 질문 또는 명시적인 서비스 설명을 곁들인 질문."""

    question: str = Field(..., min_length=2, max_length=1000)
    service_description: Optional[str] = Field(None, max_length=1000)
    answers: dict[str, str] = Field(default_factory=dict)


class AskSource(BaseModel):
    source_id: str
    article: str
    content: str
    document: str
    page: int
    chunk_id: str
    source_file: str


class AskResponse(BaseModel):
    answer: str
    sources: list[AskSource]
    mode: Literal["general", "service"]
