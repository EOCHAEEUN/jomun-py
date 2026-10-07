# 제30조③ 사전 검·인증
@requires(HIGH_IMPACT)
def before_launch(s):
    # '받도록 노력하여야 한다'
    should(get_certified(s))

# penalty: NONE
# 받으면 → 제30조④ 공공 우선 고려
