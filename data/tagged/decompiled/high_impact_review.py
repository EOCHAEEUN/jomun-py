# 제2조4호 + 제33조① 고영향 여부 판정
def review_high_impact_status(service):
    if service.domain not in HIGH_IMPACT:
        return 'NOT_HIGH_IMPACT'
    if service.decision == 'AUTOMATED':
        return 'HIGH_IMPACT'

    # '추천'만 하고 사람이 최종 결정
    # → 법률 본문만으로 단정 불가
    return 'REVIEW'  # 제33조③ 가이드라인
