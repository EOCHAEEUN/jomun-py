# penalty.py — Penalty · Reference Graph
#
# MUST라고 해서 곧바로 과태료가 붙는 것은 아니다.
#   DIRECT   : 제31조①, 제36조① → 제43조① 직접 과태료
#   INDIRECT : 제31조②③, 제32조①②, 제34조① → 제40조① 사실조사 → 제40조③ 시정명령 → 불이행 시 제43조①3
#   NONE     : 제33조①, 제35조① 등 — 제재 조항 없음
from app.engine.law import get_lawbook


def chain_for(record_id: str | None) -> dict | None:
    """INSPECT 화면의 '근거 체인'에 그릴 노드 목록"""
    if not record_id:
        return None
    law = get_lawbook()
    rec = law.get(record_id)
    penalty = rec.get("penalty")
    if not penalty:
        return None

    head = {"ref": rec["ref_label"], "label": rec["obligation"] or "-", "kind": "obligation"}
    ptype = penalty["type"]
    if ptype == "NONE":
        return {"type": "NONE", "nodes": [
            head,
            {"ref": None, "label": "제재 조항 없음 (제40조①·제43조 미열거)", "kind": "none"},
        ]}

    amount = penalty.get("max_amount_krw")
    fine_label = f"과태료 {amount // 10_000:,}만원 이하" if amount else "과태료"
    if ptype == "DIRECT":
        fine = law.get(penalty["ref"])
        return {"type": "DIRECT", "nodes": [
            head,
            {"ref": None, "label": "위반 (미이행)", "kind": "event"},
            {"ref": fine["ref_label"], "label": fine_label, "kind": "fine"},
        ]}

    # INDIRECT
    return {"type": "INDIRECT", "nodes": [
        head,
        {"ref": None, "label": "위반 의심 · 신고 · 민원", "kind": "event"},
        {"ref": "제40조①", "label": "자료 제출 · 사실조사", "kind": "gov"},
        {"ref": "제40조③", "label": "중지 · 시정명령", "kind": "gov"},
        {"ref": None, "label": "명령 불이행", "kind": "event"},
        {"ref": "제43조①3호", "label": fine_label, "kind": "fine"},
    ]}
