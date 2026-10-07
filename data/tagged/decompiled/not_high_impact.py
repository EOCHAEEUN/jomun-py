# 제2조4호 가~차목 미해당
def review_high_impact_status(s):
    if s.domain not in HIGH_IMPACT:
        # 카목: 대통령령으로 정하는 영역
        return 'NOT_HIGH_IMPACT'

# 그래도 제33조① 사전 검토(MUST)는 남음
