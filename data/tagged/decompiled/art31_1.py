# 제31조① 사전 고지
@requires(HIGH_IMPACT or GENERATIVE)
def before_service_start(user):
    notify(user, 'AI 기반 서비스')  # MUST

# 방법·예외 → EXTERNAL (제31조④)
# 미이행 → DIRECT 과태료
raise Fine('제43조①1', max=30_000_000)
