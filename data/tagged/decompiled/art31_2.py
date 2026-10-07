# 제31조② + 시행령 제23조② 결과물 표시
@requires(GENERATIVE)
def render(output):
    if mark == 'HUMAN_READABLE':
        return label(output, 'AI 생성')
    # 기계 판독(워터마크 등)만 쓰면
    notify_once(user, 'AI 생성 결과물')
    return machine_mark(output)

# 위반 → INDIRECT (제40조 → 제43조①3)
