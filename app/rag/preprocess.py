# preprocess.py — 법령 PDF → 조·항·호·목 구조 → clause 청크
#
# 1. 머리말·꼬리말("법제처 N 국가법령정보센터")과 개정 표시(<개정 …>, [본조신설 …])를 제거한다.
# 2. 줄바꿈으로 잘린 단어를 이어 붙인다. ("관\n련" → "관련", "또는\n서비스" → "또는 서비스")
# 3. 조 → 항 → 호 → 목 트리로 파싱하고, 길이에 따라 항/호/목 단위로 청크를 만든다.
# 4. 태깅 JSON(articles.json)에 있는 레코드는 그 메타데이터를, 없으면 grammar.py로 자동 태깅한다.
import json
import re
from collections import Counter

from pypdf import PdfReader

from app.config import CHUNKS_PATH, RAW_PDF
from app.engine.grammar import parse as parse_clauses
from app.engine.law import get_lawbook

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
MOK_CODE = {"가": "GA", "나": "NA", "다": "DA", "라": "RA", "마": "MA", "바": "BA", "사": "SA",
            "아": "A", "자": "JA", "차": "CHA", "카": "KA", "타": "TA", "파": "PA", "하": "HA"}
MAX_CHUNK_CHARS = 450

RE_NOISE_LINE = re.compile(
    r"^(법제처\s+\d+\s+국가법령정보센터|인공지능 발전과 신뢰 기반 조성 등에 관한 기본법|\[시행일:.*|\[(제목개정|본조신설)[^\]]*\])$")
RE_ANNOTATION = re.compile(r"<(개정|신설)[^>]*>|\[(제목개정|본조신설)[^\]]*\]")
RE_CHAPTER = re.compile(r"^제\d+(장|절)\s+\S")
RE_ARTICLE = re.compile(r"^제(\d+)조(?:의(\d+))?\(([^)]+)\)\s*(.*)$")
RE_PARAGRAPH = re.compile(rf"^([{CIRCLED}])\s*(.*)$")
RE_ITEM = re.compile(r"^(\d+)(?:의(\d+))?\.\s+(\S.*)$")
RE_MOK = re.compile(r"^([가-하])\.\s+(\S.*)$")
MOK_ORDER = "가나다라마바사아자차카타파하"
RE_TOKEN = re.compile(r"[가-힣A-Za-z0-9ㆍ]+")


def _read_lines(pdf_path=RAW_PDF) -> list[tuple[int, str]]:
    """(페이지, 줄) 목록 — 제1장부터 부칙 전까지만"""
    reader = PdfReader(str(pdf_path))
    lines, started = [], False
    for page_no, page in enumerate(reader.pages, start=1):
        for raw in (page.extract_text() or "").splitlines():
            line = raw.strip()
            if not line or RE_NOISE_LINE.match(line):
                continue
            if line.startswith("제1장"):
                started = True
            if line.startswith("부칙"):
                return lines
            if started:
                lines.append((page_no, RE_ANNOTATION.sub("", line).strip()))
    return lines


def _make_joiner(lines: list[tuple[int, str]]):
    """줄 경계의 두 글자가 '단어 안'에서 더 자주 붙어 나오는지, '단어 사이'에서 더 자주
    나오는지 문서 전체 통계로 판단해 이어 붙인다. (원|자력 → 붙임, 또는|서비스 → 띄움)"""
    inside: Counter = Counter()    # 한 단어 안에서 이웃한 두 글자
    between: Counter = Counter()   # 띄어쓰기를 사이에 둔 두 글자
    for _, line in lines:
        tokens = line.split()
        for tok in tokens:
            inside.update(tok[i:i + 2] for i in range(len(tok) - 1))
        for a, b in zip(tokens, tokens[1:]):
            between[a[-1] + b[0]] += 1

    def join(prev: str, nxt: str) -> str:
        if not prev:
            return nxt
        if prev.endswith(("ㆍ", "(", "「")) or nxt.startswith(("ㆍ", ")", ",", ".", "」")):
            return prev + nxt
        pair = prev[-1] + nxt[0]
        return prev + nxt if inside[pair] > between[pair] else prev + " " + nxt

    return join


def parse_law(pdf_path=RAW_PDF) -> list[dict]:
    """PDF → 조문 트리"""
    lines = _read_lines(pdf_path)
    join = _make_joiner(lines)
    articles: list[dict] = []
    chapter = ""
    cur = None  # 현재 텍스트를 이어 붙일 노드 (dict with 'text')

    def new_paragraph(art, num, text, page):
        para = {"num": num, "text": text, "page": page, "items": []}
        art["paragraphs"].append(para)
        return para

    for page, line in lines:
        if RE_CHAPTER.match(line):
            chapter = line
            cur = None
            continue
        if (m := RE_ARTICLE.match(line)):
            art = {"num": int(m.group(1)), "sub": int(m.group(2)) if m.group(2) else None,
                   "title": m.group(3), "chapter": chapter, "page": page, "paragraphs": []}
            articles.append(art)
            rest = m.group(4)
            if (pm := RE_PARAGRAPH.match(rest)):
                cur = new_paragraph(art, CIRCLED.index(pm.group(1)) + 1, pm.group(2), page)
            else:
                cur = new_paragraph(art, None, rest, page)
            continue
        if not articles:
            continue
        art = articles[-1]
        if (m := RE_PARAGRAPH.match(line)):
            cur = new_paragraph(art, CIRCLED.index(m.group(1)) + 1, m.group(2), page)
        elif (m := RE_ITEM.match(line)):
            num = m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
            item = {"num": num, "text": m.group(3), "page": page, "moks": []}
            art["paragraphs"][-1]["items"].append(item)
            cur = item
        elif (m := RE_MOK.match(line)) and art["paragraphs"][-1]["items"] and _next_mok(art, m.group(1)):
            mok = {"ko": m.group(1), "text": m.group(2), "page": page}
            art["paragraphs"][-1]["items"][-1]["moks"].append(mok)
            cur = mok
        elif cur is not None:
            cur["text"] = join(cur["text"], line)
    return articles


def _next_mok(art: dict, ko: str) -> bool:
    """'다.'처럼 줄바꿈으로 잘린 문장 끝을 목으로 오인하지 않도록 순서를 확인"""
    moks = art["paragraphs"][-1]["items"][-1]["moks"]
    expected = MOK_ORDER[len(moks)] if len(moks) < len(MOK_ORDER) else ""
    return ko == expected


def _render_item(item: dict) -> str:
    lines = [f"{item['num']}. {item['text']}"]
    lines += [f"  {m['ko']}. {m['text']}" for m in item["moks"]]
    return "\n".join(lines)


def build_chunks(articles: list[dict]) -> list[dict]:
    chunks: list[dict] = []

    def add(cid, ref_label, text, art, para, page, lead=""):
        # lead: 호·목 청크가 주어·의무 강도를 물려받는 항 본문 (자동 태깅에 사용)
        chunks.append({"id": cid, "ref_label": ref_label, "text": text.strip(), "article": art["num"],
                       "article_sub": art["sub"], "paragraph": para, "title": art["title"],
                       "chapter": art["chapter"], "page": page, "lead": lead})

    for art in articles:
        base = f"ARTICLE_{art['num']}" + (f"-{art['sub']}" if art["sub"] else "")
        art_label = f"제{art['num']}조" + (f"의{art['sub']}" if art["sub"] else "")
        for para in art["paragraphs"]:
            pnum = para["num"]
            pid = base + (f"_{pnum}" if pnum else "")
            plabel = art_label + (CIRCLED[pnum - 1] if pnum else "")
            whole = "\n".join([para["text"]] + [_render_item(i) for i in para["items"]])
            if len(whole) <= MAX_CHUNK_CHARS or not para["items"]:
                add(pid, plabel, whole, art, pnum, para["page"])
                continue
            if para["text"]:
                add(pid, plabel, para["text"], art, pnum, para["page"])
            for item in para["items"]:
                iid, ilabel = f"{pid}_{item['num']}", f"{plabel}{'' if pnum else '제'}{item['num']}호"
                rendered = _render_item(item)
                if item["moks"] and len(rendered) > MAX_CHUNK_CHARS:
                    add(iid, ilabel, item["text"], art, pnum, item["page"], para["text"])
                    for mok in item["moks"]:
                        add(f"{iid}_{MOK_CODE[mok['ko']]}", f"{plabel}{item['num']}호{mok['ko']}목",
                            mok["text"], art, pnum, mok["page"], para["text"])
                else:
                    add(iid, ilabel, rendered, art, pnum, item["page"], para["text"])
    return chunks


def attach_metadata(chunks: list[dict]) -> list[dict]:
    """태깅 레코드가 있으면 그 메타데이터를, 없으면 Clause Parser로 자동 태깅"""
    law = get_lawbook()
    clause_records: dict[str, list[dict]] = {}
    for r in law.records:
        if r["clause"] in ("A", "B"):
            clause_records.setdefault(r["id"].rsplit("_", 1)[0], []).append(r)

    out = []
    for c in chunks:
        # 제33조①처럼 한 항이 절(A/B)로 태깅돼 있으면 절 단위 청크로 교체
        if c["id"] in clause_records:
            for r in clause_records[c["id"]]:
                out.append({**c, "id": r["id"], "ref_label": r["ref_label"], "text": r["text"],
                            **_meta_from_record(r)})
            continue
        if c["id"] in law.by_id:
            out.append({**c, **_meta_from_record(law.by_id[c["id"]])})
        else:
            out.append({**c, **_meta_auto(c["lead"] or c["text"])})
    return out


def _meta_from_record(r: dict) -> dict:
    return {
        "tagged": True,
        "addressee": r["addressee"],
        "obligation": r["obligation"] or "",
        "external": (r["external_dependency"] or {}).get("type", ""),
        "flags": ",".join(r["flags"]),
        "status_rule": r["status_rule"] or "",
        "penalty_type": (r["penalty"] or {}).get("type", ""),
    }


def _meta_auto(text: str) -> dict:
    clauses = parse_clauses(text.split("\n")[0])
    rank = {"MUST_NOT": 4, "MUST": 3, "SHOULD": 2, "MAY": 1, None: 0}
    best = max(clauses, key=lambda c: rank[c["obligation"]]) if clauses else {}
    return {
        "tagged": False,
        "addressee": clauses[0]["addressee"] if clauses else "OTHER",
        "obligation": best.get("obligation") or "",
        "external": next((c["external"] for c in clauses if c["external"]), "") or "",
        "flags": ",".join(sorted({f for c in clauses for f in c["flags"]})),
        "status_rule": "",
        "penalty_type": "",
    }


def run(pdf_path=RAW_PDF, out_path=CHUNKS_PATH) -> list[dict]:
    chunks = attach_metadata(build_chunks(parse_law(pdf_path)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    return chunks
