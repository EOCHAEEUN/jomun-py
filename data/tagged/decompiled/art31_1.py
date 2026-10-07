# 제31조① + 시행령 제23조① 사전 고지
@requires(HIGH_IMPACT or GENERATIVE)
def before_service_start(user):
    notify(user, how=ANY_OF(
        'terms',     # 약관·계약서 기재
        'screen',    # 화면·단말기 표시
        'on_site',   # 제공 장소 게시
    ))  # MUST

# 시행령 제23조④ 예외: 명백 / 내부 업무용
raise Fine('제43조①1', max=30_000_000)
