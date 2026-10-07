# 제16조③ 국가기관등 AI 우선 고려
def procure(need):
    if not suitable_for_ai(need):
        return default(need)  # 단서: 예외
    # MUST (주어: 국가기관등)
    prefer(EXTERNAL('대통령령 범위'))
