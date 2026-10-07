# 제30조④·제35조② 주어 = 국가기관등
def agency_procurement(products):
    return sorted(products, key=lambda p:(
        p.certified,       # 제30조④
        p.impact_assessed, # 제35조②
    ), reverse=True)

# 사업자 관점: 의무가 아니라
# '우선 고려 요소' (OPPORTUNITY)
