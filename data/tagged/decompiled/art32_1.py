# 제32조 + 시행령 제24조 고성능 AI
def in_scope(sys):
    return all([             # 3요건 모두
        sys.flops >= 10**26,  # 누적 연산량
        sys.is_frontier,      # 최첨단
        sys.broad_risk,       # 광범위 위험
    ])

if in_scope(system):
    mitigate_lifecycle_risks()  # ①1
    monitor_incidents()         # ①2
    submit_results(MSIT)        # ②
# 이용사업자라도 자동 제외 안 함
