# graph.py — 태깅 레코드(articles.json)로 조문 관계도를 만든다 (법령 라이브러리 화면용)
#
# 노드: 조문(provision) + 수범자(actor) · 적용 조건(condition) · 위임(delegation) · 정의 용어(term) · 외부 법률(extlaw)
# 엣지 (근거)
#   PART_OF     하위 조문 → 상위 조문                         ID 계층
#   REFERS      조문 → 참조 조문                               태깅 refs + 법률 본문의 "제N조제M항"
#   IMPLEMENTS  시행령 → 법률 조문                             시행령 본문의 "법 제N조제M항"
#   EXPLAINS    해설 요약 → 법률 조문                          태깅 domain + 본문의 "법 제N조"
#   SANCTION    의무 조문 → 제재 조문 (경로 순서대로)          태깅 penalty.path
#   APPLIES_TO  의무 조문 → 수범자                             태깅 addressee
#   REQUIRES    조문 → 적용 조건                               태깅 condition
#   DELEGATES   조문 → 대통령령·고시·가이드라인·위원회        태깅 external_dependency · external_effect
#   CITES       조문 → 「외부 법률」                           본문 정규식
#   DEFINES     정의 조문 → 용어 / USES_TERM  조문 → 용어      “용어”이란 · (이하 “용어”라 한다)
# 임베딩 유사도처럼 추정한 관계는 넣지 않는다. 판정 근거와 같은 데이터만 쓴다.
import re
from collections import Counter
from functools import lru_cache

from app.engine.law import ADDRESSEE_KO, get_lawbook

CONDITION_KO = {
    "IF_HIGH_IMPACT_AI": "고영향 AI인 경우",
    "IS_GENERATIVE_AI": "생성형 AI인 경우",
    "COMPUTE_ABOVE_THRESHOLD": "학습 연산량 기준 이상",
    "PROVIDES_REALISTIC_SYNTHETIC_MEDIA": "실제와 구분 어려운 결과물",
    "IF_FULLY_AUTOMATED_DECISION": "완전히 자동화된 결정",
    "IS_SME": "중소기업 등",
    "IS_ARTISTIC_EXPRESSION": "예술·창작 표현물",
    "PROVIDES_AI_OR_AI_SERVICE": "AI 제품·서비스 제공",
    "IF_NEEDED": "필요한 경우",
    "NO_DOMESTIC_OFFICE": "국내 주소·영업소 없음",
    "MEETS_USER_OR_REVENUE_THRESHOLD": "이용자·매출 기준 충족",
    "IF_REQUESTING_CONFIRMATION": "확인을 요청하는 경우",
    "IF_ASSESSING": "영향평가를 하는 경우",
}
DELEGATION_KO = {
    "PRESIDENTIAL_DECREE": "대통령령에 위임",
    "NOTICE": "장관 고시 (데이터 범위 밖)",
    "GUIDELINE": "가이드라인 (데이터 범위 밖)",
    "COMMITTEE": "위원회 심의",
}
MOK_IDS = {"GA", "NA", "DA", "RA", "MA", "BA", "SA", "A", "JA", "CHA", "KA"}
PAIR_PRIORITY = ["SANCTION", "IMPLEMENTS", "EXPLAINS", "PART_OF", "REFERS"]   # 조문↔조문 관계의 우선순위

RE_LAW_REF = re.compile(r"법\s*제(\d+)조(?:의(\d+))?(?:\s*제(\d+)항)?(?:\s*제(\d+)호)?")
RE_SELF_REF = re.compile(r"제(\d+)조(?:의(\d+))?(?:제(\d+)항)?(?:제(\d+)호)?")
RE_EXT_LAW = re.compile(r"「([^」]+)」")
RE_DEFINE = re.compile(r"[“\"]([^”\"]{2,20})[”\"](?:이란|란)")
RE_DEFINE_HEREAFTER = re.compile(r"이하\s*[“\"]([^”\"]{2,20})[”\"](?:이|이라|라)\s*한다")


def _resolve(by_id: dict, prefix: str, art: str, sub: str | None, para: str | None, item: str | None) -> str | None:
    """'제34조제1항제2호' → 데이터에 있는 가장 구체적인 레코드 ID"""
    base = f"{prefix}_{art}" + (f"-{sub}" if sub else "")
    candidates = []
    if para and item:
        candidates.append(f"{base}_{para}_{item}")
    if para:
        candidates += [f"{base}_{para}", f"{base}_{para}_A"]
    if item and not para:
        candidates.append(f"{base}_{item}")
    candidates.append(base)
    for cid in candidates:
        if cid in by_id:
            return cid
    # '법 제33조'처럼 조만 적었으면 데이터 순서상 첫 조문(보통 ①)으로
    return next((rid for rid in by_id if rid.startswith(base + "_")), None)


def _parent(by_id: dict, rid: str) -> str | None:
    key = rid
    while "_" in key:
        key = key.rsplit("_", 1)[0]
        if key in by_id:
            return key
    return None


@lru_cache
def build_graph() -> dict:
    law = get_lawbook()
    by_id = law.by_id
    nodes: dict[str, dict] = {}
    edges: dict[tuple, dict] = {}

    def edge(src: str, dst: str, kind: str, via: str, **extra):
        if src == dst or src not in nodes or dst not in nodes:
            return
        edges.setdefault((src, dst, kind), {"source": src, "target": dst, "type": kind, "via": via, **extra})

    def entity(nid: str, kind: str, label: str) -> str:
        nodes.setdefault(nid, {"id": nid, "kind": kind, "label": label})
        return nid

    for r in law.records:
        src = law.source_by_id[r["doc"]]
        nodes[r["id"]] = {
            "id": r["id"], "kind": "provision", "doc": r["doc"], "doc_short": src["short"],
            "label": r["ref_label"], "title": r["title"], "summary": r["summary"], "text": r["text"],
            "page": r.get("source_page"), "verbatim": r.get("verbatim", True),
            "obligation": r.get("obligation"), "addressee": r["addressee"],
            "addressee_ko": ADDRESSEE_KO.get(r["addressee"], r["addressee"]),
            "penalty": (r.get("penalty") or {}).get("type"),
        }

    defined: dict[str, str] = {}   # 용어 → 정의한 조문
    for r in law.records:
        rid, text, doc = r["id"], r["text"], r["doc"]
        if (parent := _parent(by_id, rid)):
            edge(rid, parent, "PART_OF", "ID 계층")

        penalty = r.get("penalty") or {}
        path = [p for p in penalty.get("path") or [] if p in by_id]
        for a, b in zip([rid] + path, path):
            edge(a, b, "SANCTION", "태깅 penalty", penalty=penalty.get("type"))
        for ref in r.get("refs") or []:
            if ref not in path:
                edge(rid, ref, "REFERS", "태깅 refs")

        if doc == "AIACT":
            for m in RE_SELF_REF.finditer(text):
                if text[max(0, m.start() - 2):m.start()].strip().endswith(("」", "법")):
                    continue
                target = _resolve(by_id, "ARTICLE", *m.groups())
                if target and target not in path:
                    edge(rid, target, "REFERS", "원문 \"제N조\"")
        if doc in ("DECREE", "BKL"):
            for m in RE_LAW_REF.finditer(text):
                target = _resolve(by_id, "ARTICLE", *m.groups())
                if target:
                    edge(rid, target, "IMPLEMENTS" if doc == "DECREE" else "EXPLAINS", "원문 \"법 제N조\"")
        if doc == "BKL":
            domain = r.get("domain")
            target = f"ARTICLE_2_4_{domain}" if domain in MOK_IDS else ("ARTICLE_2_4" if rid == "BKL_TWO_STEP" else None)
            if target in by_id:
                edge(rid, target, "EXPLAINS", "태깅 domain")

        if r.get("obligation") and r["addressee"] != "OTHER":
            actor = entity(f"ACTOR:{r['addressee']}", "actor", ADDRESSEE_KO.get(r["addressee"], r["addressee"]))
            edge(rid, actor, "APPLIES_TO", "태깅 addressee")
        for cond in r.get("condition") or []:
            if cond == "OR":
                continue
            node = entity(f"COND:{cond}", "condition", CONDITION_KO.get(cond, cond))
            edge(rid, node, "REQUIRES", "태깅 condition")
        for dep in (r.get("external_dependency"), r.get("external_effect")):
            if dep and dep.get("type") in DELEGATION_KO:
                node = entity(f"DELEGATE:{dep['type']}", "delegation", DELEGATION_KO[dep["type"]])
                edge(rid, node, "DELEGATES", "태깅 external_dependency")
        for name in RE_EXT_LAW.findall(text):
            node = entity(f"EXTLAW:{name}", "extlaw", f"「{name}」")
            edge(rid, node, "CITES", "원문 「법명」")
        for term in RE_DEFINE.findall(text) + RE_DEFINE_HEREAFTER.findall(text):
            defined.setdefault(term, rid)

    for term, rid in defined.items():
        node = entity(f"TERM:{term}", "term", term)
        edge(rid, node, "DEFINES", "원문 정의 문장")
        for r in law.records:
            if r["id"] != rid and term in r["text"]:
                edge(r["id"], node, "USES_TERM", "원문 용어 사용")

    # 같은 두 조문 사이에는 가장 구체적인 관계 하나만 남긴다 (예: 시행령 구체화 > 단순 참조)
    best: dict[tuple, str] = {}
    for (src, dst, kind) in edges:
        if kind in PAIR_PRIORITY:
            pair = tuple(sorted((src, dst)))
            if pair not in best or PAIR_PRIORITY.index(kind) < PAIR_PRIORITY.index(best[pair]):
                best[pair] = kind
    for key in [k for k in edges if k[2] in PAIR_PRIORITY and best[tuple(sorted(k[:2]))] != k[2]]:
        del edges[key]
    used ={e["source"] for e in edges.values()} | {e["target"] for e in edges.values()}
    node_list = [n for n in nodes.values() if n["kind"] == "provision" or n["id"] in used]

    docs = Counter(n["doc"] for n in node_list if n["kind"] == "provision")
    return {
        "nodes": node_list,
        "edges": list(edges.values()),
        "docs": [{"id": s["id"], "short": s["short"], "title": s["title"], "kind": s["kind"],
                  "authority": s["authority"], "effective": s["effective"], "role": s["role"],
                  "count": docs.get(s["id"], 0)} for s in law.sources],
        "stats": {"provisions": sum(docs.values()), "entities": len(node_list) - sum(docs.values()),
                  "edges": len(edges), "by_type": dict(Counter(e["type"] for e in edges.values()))},
    }
