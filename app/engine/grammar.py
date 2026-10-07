# grammar.py — Clause Parser: 법률 문법 → 개발 언어
#
# 두 개의 축을 분리한다.
#   obligation : 누가 무엇을 해야 하는가      (MUST / MUST_NOT / SHOULD / MAY)
#   external   : 판단에 하위 규정이 필요한가   (EXTERNAL_DECREE / EXTERNAL_NOTICE)
# 문자열 순서에 의존하지 않도록 정규식 + 우선순위로 매칭한다.
import re

# (패턴, 태그, 축, 우선순위) — 같은 축에서는 우선순위가 높은 태그 하나만 채택
# 주의 1: '한다'의 첫 글자는 '하'가 아니라 '한'이다. 어간을 '하'로만 잡으면
#         '하여야 한다'를 놓치므로 (한|하)로 둘 다 잡는다. ('정한다/정하는', '된다/되는'도 같음)
# 주의 2: 법률은 '하여야 한다', 시행령은 '해야 한다', '포함되어야 한다'처럼 어미가 다르다.
#         '-어야/-여야/-해야' 를 모두 MUST로 잡는다.
LEGAL_PATTERNS = [
    (r"노력(하여|해)야\s*(한|하)",                 "SHOULD",          "obligation", 100),
    (r"(하여서는|해서는)\s*(아니|안)\s*(된|되)",       "MUST_NOT",        "obligation", 100),
    (r"(어|여|해)야\s*(한|하)",                    "MUST",            "obligation", 90),
    (r"(할|을)\s*수\s*있",                        "MAY",             "obligation", 80),
    (r"대통령령으로\s*정(한|하)",                    "EXTERNAL_DECREE", "external",   100),
    (r"고시(한|하)",                              "EXTERNAL_NOTICE", "external",   80),
    (r"그러하지\s*아니(한|하)",                      "EXCEPTION",       "flag",       100),
    (r"(것|자|행위)으?로\s*본다",                    "TREAT_AS",        "flag",       90),
]

# 한 문장 안에 의무 강도가 둘 이상일 때 절(clause)로 나눈다 (예: 제33조① "검토하여야 하며, … 요청할 수 있다")
_CLAUSE_SPLIT = re.compile(r"(?<=하며),\s*|(?<=하고),\s*|(?<=있고),\s*|\s+(?=다만,)|\s+(?=이 경우)")

# 주어(수범자) — 문장 머리의 "법 제31조제1항에 따라" 같은 인용구는 떼고 본다
_LEAD_REF = re.compile(r"^(법\s*)?제\d+조(의\d+)?(제\d+항)?(제\d+호)?\s*(에\s*따라|에서|에 따른)?\s*")
_ADDRESSEE_RULES = [
    (r"^(인공지능사업자|인공지능개발사업자|인공지능이용사업자|국내대리인)", "AI_BUSINESS"),
    (r"^개인정보처리자", "DATA_HANDLER"),
    (r"^(정보주체|개인인 신용정보주체|신용정보주체)", "DATA_SUBJECT"),
    (r"^개인신용평가회사", "CREDIT_EVALUATOR"),
    (r"^(과학기술정보통신부장관|정부|국가 및 지방자치단체|국가는|지방자치단체|중앙행정기관의 장|보호위원회|금융위원회)",
     "GOVERNMENT"),
    (r"^국가기관등", "PUBLIC_AGENCY"),
    (r"^위원회", "COMMITTEE"),
]


def split_clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE_SPLIT.split(text) if c.strip()]


def tag_clause(text: str) -> dict:
    """절 하나에 의무 강도·외부 의존·플래그를 붙인다"""
    best: dict[str, tuple[int, str]] = {}
    flags: list[str] = []
    for pattern, tag, axis, priority in LEGAL_PATTERNS:
        if not re.search(pattern, text):
            continue
        if axis == "flag":
            flags.append(tag)
        elif axis not in best or priority > best[axis][0]:
            best[axis] = (priority, tag)
    return {
        "obligation": best.get("obligation", (0, None))[1],
        "external": best.get("external", (0, None))[1],
        "flags": flags,
    }


def guess_addressee(text: str, default: str = "OTHER") -> str:
    """절의 주어(수범자) 추정 — '이 법은', '그 밖에' 등은 default"""
    stripped = re.sub(r"^[①-⑳]\s*", "", text.strip())
    stripped = _LEAD_REF.sub("", stripped)
    for pattern, addressee in _ADDRESSEE_RULES:
        if re.search(pattern, stripped):
            return addressee
    return default


def parse(text: str) -> list[dict]:
    """문장 → 절 단위 태그 목록. 앞 절의 주어는 뒤 절로 이어진다."""
    result, addressee = [], None
    for clause in split_clauses(text):
        guessed = guess_addressee(clause, default="")
        addressee = guessed or addressee or "OTHER"
        result.append({"text": clause, "addressee": addressee, **tag_clause(clause)})
    return result
