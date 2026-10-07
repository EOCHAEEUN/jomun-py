# 신용정보법 제36조의2 자동화평가
# 제2조14호: 종사자 관여 없이 컴퓨터로만
# ①② 권리 주어 = 신용정보주체 (MAY)
def on_request(subject, req):  # 사업자
    if refusal_reason(req):    # ③ MAY
        return reject(req)
    if req == 'EXPLAIN':       # ①
        return explain(result, criteria,
                       base_data)
    if req in ('CORRECT', 'RECALC'):  # ②
        return handle(req)
