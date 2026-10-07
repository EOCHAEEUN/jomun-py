# 제4조 + 시행령 제2조 — 판정보다 먼저
def check_scope(s):
    if s.defense_only:         # 제4조②
        # 시행령 제2조: 국방부장관 등이
        # 지정한 업무'만' 수행할 때 제외
        return EXCLUDED_IF(s.designated)
    if s.overseas and s.kr_users:  # ①
        return IN_SCOPE  # 역외 적용
    return IN_SCOPE
