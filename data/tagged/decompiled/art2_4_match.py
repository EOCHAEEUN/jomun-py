# 제2조4호: 영향 우려 AND 가~카목 영역
HIGH_IMPACT = {
    '가': 'ENERGY',   '나': 'WATER',
    '다': 'HEALTH',   '라': 'MED_DEVICE',
    '마': 'NUCLEAR',  '바': 'CRIME_BIO',
    '사': 'RIGHTS',   '아': 'TRANSPORT',
    '자': 'PUBLIC',   '차': 'STUDENT',
}  # 카목 → EXTERNAL (대통령령)

def match_domain(s):
    if s.purpose in ('HIRE', 'LOAN'):
        return '사'  # 판단·평가
    if s.biometric and s.crime_probe:
        return '바'  # 수사·체포 목적만
    return DOMAIN.get(s.purpose)
