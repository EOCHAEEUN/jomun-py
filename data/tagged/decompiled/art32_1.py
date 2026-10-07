# 제32조 고연산 AI 안전성
LIMIT = EXTERNAL('대통령령: 연산량')

def comply(system):
    if system.compute < LIMIT:
        return  # 기준 미정 → REVIEW
    mitigate_lifecycle_risks()  # ①1
    monitor_incidents()         # ①2
    submit_results(MSIT)        # ②

# 이용사업자라도 자동 제외 안 함
