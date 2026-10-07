# 제2조4호 + 가이드라인 해설 2단계 판단
def review_high_impact_status(s):
    if s.domain not in HIGH_IMPACT:  # 1
        return 'NOT_HIGH_IMPACT'
    if s.decision == 'AUTOMATED':    # 2
        return 'HIGH_IMPACT'
    if s.ministry_reply == 'NOT':  # 33조
        return 'NOT_HIGH_IMPACT'
    # 해설: '인적 개입 없이' → 해당 사례
    # 역(개입 → 비해당)은 성립 X
    return 'REVIEW'  # 사람 최종 결정도
