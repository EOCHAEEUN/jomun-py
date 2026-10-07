# 제35조① + 시행령 제28조 영향평가
@requires(HIGH_IMPACT)
def assess(s, by=SELF or THIRD_PARTY):
    should(include(
        affected_people, rights_types,
        social_economic_impact, usage,
        metrics_and_method,
        mitigation_and_recovery,
        improvement_plan,
    ))  # 7개 항목, SHOULD
# 하면 → 제35조② 공공 우선 고려
