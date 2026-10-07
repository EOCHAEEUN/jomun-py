# 제34조① 고영향 AI 사업자 책무
class HighImpactAIProvider(ABC):
    @abstractmethod
    def risk_management(self): ...  # 1
    @abstractmethod
    def explain(self, out): ...     # 2
    @abstractmethod
    def protect_users(self): ...    # 3
    @abstractmethod
    def human_oversight(self): ...  # 4
    @abstractmethod
    def keep_documents(self): ...   # 5

    item6 = EXTERNAL('위원회 의결')
    detail = EXTERNAL('② 장관 고시')

# ③ 타 법령상 준하는 조치 이행
#   → TREAT_AS(SATISFIED)
