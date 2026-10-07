# 제36조① + 시행령 제29조 국내대리인
def must_designate(biz):
    if biz.has_domestic_office:
        return False
    return any([
        biz.revenue >= 1_000_000_000_000,
        biz.ai_revenue >= 10_000_000_000,
        biz.daily_kr_users >= 1_000_000,
        biz.fined_under_43_1_3,
    ])  # 매출은 전년도 평균환율로 환산

# 미지정 → DIRECT (제43조①2)
