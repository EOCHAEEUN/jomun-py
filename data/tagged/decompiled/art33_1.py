# 제33조① 한 문장, 두 절
class AIBusiness:
    def before_launch(self, s):
        # '검토하여야 하며' → MUST
        self.review_high_impact(s)
        if self.is_unsure(s):
            # '요청할 수 있다' → MAY
            self.request_confirm(MSIT)

# penalty: NONE
# (제40조①·제43조에 없음)
