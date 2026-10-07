# 제36조① 국내대리인
LIMIT = EXTERNAL('대통령령: 이용자·매출')

def comply(biz):
    if biz.has_domestic_office:
        return
    if biz.users_or_revenue >= LIMIT:
        designate(agent)  # MUST, 서면
        report_to(MSIT)   # MUST

# 미지정 → DIRECT (제43조①2)
# ③ 대리인 위반 → TREAT_AS(사업자)
