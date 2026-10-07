# 개인정보 보호법 제37조의2
def on_decision(d):
    if d.human_involved:
        return  # 완전 자동화 아님
    disclose(d.criteria, d.process)  # ④

# ①② 권리 주어 = 정보주체 (MAY)
def on_request(d, subject):     # ③
    if subject.refuses and d.serious:
        stop_or_rehandle_by_human(d)
    if subject.asks_explanation:
        explain(d)
