# 제34조① + 시행령 제27조
class HighImpactAIProvider(ABC):
    @abstractmethod
    def risk_management(self): ...  # 1
    @abstractmethod
    def explain(self, out): ...     # 2
    @abstractmethod
    def protect_users(self): ...    # 3
    @abstractmethod
    def human_oversight(self): ...  # 4

    def comply(self):
        publish(1, 2, 3, self.overseer)
        keep_documents(years=5)     # 5

# 시행령 ②③: 이용사업자는 개발사가 1~3호
# 이행 + 기능 변경 없으면 TREAT_AS(이행)
