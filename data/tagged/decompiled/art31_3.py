# 제31조③ 실제와 구분 어려운 결과물
@requires(REALISTIC_SYNTHETIC)
def deliver(media):
    if media.is_artistic:  # 후단 MAY
        return soft_label(media)
    # 명확히 인식 가능하게 → MUST
    return clear_label(media, 'AI 생성')

# penalty: INDIRECT (제40조 경유)
