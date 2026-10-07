# 개인정보 보호법 제23조 민감정보
def process(face_video):
    if is_sensitive(face_video):  # 범위는
        # 개보법 시행령 (KB 밖) → EXTERNAL
        if not separate_consent:
            raise MustNot('제23조①')
    return use(face_video)
