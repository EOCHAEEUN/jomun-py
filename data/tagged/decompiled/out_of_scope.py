# Knowledge Base 범위 밖 → 표시만
KB = {'인공지능기본법 (2026.1.22.)'}

def check(s):
    if s.biometric or s.personal_data:
        # '위반'이라고 단정하지 않는다
        return OUT_OF_SCOPE(
          "타 법률 검토 필요할 수 있음")
