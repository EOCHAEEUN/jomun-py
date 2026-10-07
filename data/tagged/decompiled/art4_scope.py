# 제4조 적용범위 — 판정보다 먼저
def check_scope(s):
    if s.defense_only:            # ②
        return EXCLUDED_IF(DECREE)
    if s.overseas and s.kr_users:  # ①
        return IN_SCOPE  # 역외 적용
    return IN_SCOPE
