# preprocess.py — Docling으로 PDF 6종을 읽고 조문·페이지 단위로 청킹
#
# 데이터 목록은 data/sources.json 에 있다. 문서 종류(parser)에 따라 다르게 자른다.
#   ko_law     : 국가법령정보센터 국문 PDF (법률·시행령) → 조·항·호·목 트리
#   en_law     : 국가법령정보센터 영문 번역 PDF → Article·paragraph 단위
#   commentary_pdf : 해설 PDF → Docling 문서 요소를 페이지별로 묶어 인덱싱
#
# 공통 처리
#   1. 머리말("법제처 N 국가법령정보센터", 문서 제목)과 개정 표시(<개정 …>, [본조신설 …])를 제거한다.
#   2. 줄바꿈으로 잘린 단어를 문서 전체 통계로 판단해 이어 붙인다. ("원\n자력" → "원자력")
#   3. 같은 조문이 두 번 나오면(시행 예정 개정본) 앞의 현행본만 쓴다.
#   4. 태깅 JSON(articles.json)에 있는 레코드는 그 메타데이터를, 없으면 grammar.py로 자동 태깅한다.
import json
import re
import hashlib
from collections import Counter
from functools import lru_cache
from pathlib import Path

from docling.chunking import HierarchicalChunker
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import NativePdfPipelineOptions
from docling.document_converter import DocumentConverter, NativePdfFormatOption

from app.config import CHUNKS_PATH, EN_ARTICLES_PATH, RAW_DIR, SOURCES_PATH
from app.engine.grammar import parse as parse_clauses
from app.engine.law import get_lawbook

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
MOK_CODE = {"가": "GA", "나": "NA", "다": "DA", "라": "RA", "마": "MA", "바": "BA", "사": "SA",
            "아": "A", "자": "JA", "차": "CHA", "카": "KA", "타": "TA", "파": "PA", "하": "HA"}
MOK_ORDER = "가나다라마바사아자차카타파하"
MAX_CHUNK_CHARS = 450

RE_HEADER = re.compile(r"^법제처\s+\d+\s+국가법령정보센")
RE_BRACKET_NOTE = re.compile(r"^\[[^\]]*(개정|신설|삭제|이동|시행일|종전|제목)[^\]]*\](\s*제\d+조\S*)?$")
RE_ANNOTATION = re.compile(r"<(개정|신설|삭제|\d{4}\.)[^>]*>|\[(제목개정|본조신설|전문개정)[^\]]*\]")
RE_OPEN_NOTE = re.compile(r"<(개|신|삭|\d)[^>]*$")   # "<개" 에서 줄이 끊기는 경우도 있음
RE_DELETED_TEXT = re.compile(r"^삭제\s*(<[^>]*>)?$")
RE_CHAPTER = re.compile(r"^제\d+(장|절)(의\d+)?\s+\S")
RE_ARTICLE = re.compile(r"^제(\d+)조(?:의(\d+))?\(([^)]+)\)\s*(.*)$")
RE_DELETED_ARTICLE = re.compile(r"^제(\d+)조(?:의(\d+))?\s+삭제")
RE_PARAGRAPH = re.compile(rf"^([{CIRCLED}])\s*(.*)$")
RE_ITEM = re.compile(r"^(\d+)(?:의(\d+))?\.\s+(\S.*)$")
RE_MOK = re.compile(r"^([가-하])\.\s+(\S.*)$")

RE_EN_ARTICLE = re.compile(r"^Article (\d+)(?:-(\d+))? \(([^)]+)\)\s*(.*)$")
RE_EN_ARTICLE_OPEN = re.compile(r"^Article (\d+)(?:-(\d+))? \(([^)]+)$")   # 제목이 다음 줄로 넘어감
RE_EN_PARAGRAPH = re.compile(r"^\((\d+)\)\s+(.*)$")
RE_EN_ITEM = re.compile(r"^(\d+)\.\s+(.*)$")
RE_EN_NOISE = re.compile(r"^(?:법제처$|국가법령정보센(?:터)?$|\d+$|터$|「FRAMEWORK|FOUNDATION FOR TRUST」$|CHAPTER [IVX]+)")
RE_PARTICLE_HEAD = re.compile(r"^(은|는|이|가|을|를|의|에|와|과|로|도)(\s|$)")


def load_sources() -> list[dict]:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


# ── 공통: 줄 읽기·줄 이어 붙이기 ─────────────────────────────
@lru_cache(maxsize=1)
def _converter() -> DocumentConverter:
    # 원문 텍스트가 포함된 PDF 6개: OCR 모델 없이 Docling의 native PDF 파서 사용.
    options = NativePdfPipelineOptions()
    return DocumentConverter(format_options={InputFormat.PDF: NativePdfFormatOption(pipeline_options=options)})


@lru_cache(maxsize=6)
def _convert(path: Path):
    result = _converter().convert(path)
    if result.status != ConversionStatus.SUCCESS:
        raise RuntimeError(f"Docling PDF 변환 실패: {path} ({result.status})")
    return result.document


def _pdf_lines(path) -> list[tuple[int, str]]:
    out = []
    for item, _ in _convert(Path(path)).iterate_items(with_groups=False):
        if not getattr(item, "prov", None) or not getattr(item, "text", None):
            continue
        page_no = item.prov[0].page_no
        for raw in item.text.splitlines():
            line = raw.strip()
            if line:
                out.append((page_no, line))
    return out


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
        if prev.endswith(("ㆍ", "(", "「", "-")) or nxt.startswith(("ㆍ", ")", ",", ".", "」")):
            return prev + nxt
        if RE_PARTICLE_HEAD.match(nxt):   # "처분\n은 제외" 처럼 조사가 줄 머리로 넘어온 경우
            return prev + nxt
        pair = prev[-1] + nxt[0]
        return prev + nxt if inside[pair] > between[pair] else prev + " " + nxt

    return join


# ── 국문 법령 (법률·시행령) ────────────────────────────────
def _ko_body_lines(path, title: str) -> list[tuple[int, str]]:
    """제1장부터 부칙 전까지, 머리말·개정 표시를 뺀 본문 줄"""
    lines, started, in_note = [], False, False
    for page, line in _pdf_lines(path):
        if (RE_HEADER.match(line) or line in ("법제처", "국가법령정보센터", "국가법령정보센", "터", title)
                or line.isdigit() or RE_BRACKET_NOTE.match(line)):
            continue
        if in_note:                       # 두 줄에 걸친 <개정 …, … > 의 뒷부분
            if ">" not in line:
                continue
            line, in_note = line.split(">", 1)[1].strip(), False
            if not line:
                continue
        if line.startswith("제1장"):
            started = True
        if started and line.startswith("부칙"):
            break
        if not started:
            continue
        cleaned = RE_ANNOTATION.sub("", line)
        if (m := RE_OPEN_NOTE.search(cleaned)):   # 줄 끝에서 닫히지 않은 <개정 …
            cleaned, in_note = cleaned[:m.start()], True
        cleaned = cleaned.strip()
        if cleaned:
            lines.append((page, cleaned))
    return lines


def parse_ko_law(path, title: str) -> list[dict]:
    """PDF → 조문 트리 [{num, sub, title, chapter, page, paragraphs:[{num, text, items:[{num, text, moks}]}]}]"""
    lines = _ko_body_lines(path, title)
    join = _make_joiner(lines)
    articles: list[dict] = []
    chapter, cur, skipping, last_key = "", None, False, (0, 0)

    def new_paragraph(art, num, text, page):
        para = {"num": num, "text": text, "page": page, "items": []}
        art["paragraphs"].append(para)
        return para

    for page, line in lines:
        if RE_CHAPTER.match(line):
            chapter, cur, skipping = line, None, False
            continue
        if RE_DELETED_ARTICLE.match(line):
            cur, skipping = None, True
            continue
        if (m := RE_ARTICLE.match(line)):
            key = (int(m.group(1)), int(m.group(2) or 0))
            if key == last_key:          # 같은 조문 재등장 = 시행 예정 개정본 → 현행본만 사용
                cur, skipping = None, True
                continue
            if key > last_key:
                last_key, skipping = key, False
                art = {"num": key[0], "sub": key[1] or None, "title": m.group(3),
                       "chapter": chapter, "page": page, "paragraphs": []}
                articles.append(art)
                rest = m.group(4)
                if (pm := RE_PARAGRAPH.match(rest)):
                    cur = new_paragraph(art, CIRCLED.index(pm.group(1)) + 1, pm.group(2), page)
                else:
                    cur = new_paragraph(art, None, rest, page)
                continue
            # key < last_key: 줄 머리에 걸린 조문 인용 → 본문으로 취급
        if skipping or not articles:
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

    # '② 삭제'처럼 내용 없는 항·호 정리
    for art in articles:
        art["paragraphs"] = [p for p in art["paragraphs"] if not RE_DELETED_TEXT.match(p["text"]) or p["items"]]
        for p in art["paragraphs"]:
            p["items"] = [i for i in p["items"] if not RE_DELETED_TEXT.match(i["text"])]
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


def build_ko_chunks(articles: list[dict], src: dict) -> list[dict]:
    chunks: list[dict] = []

    def add(cid, ref_label, text, art, para, page, lead=""):
        # lead: 호·목 청크가 주어·의무 강도를 물려받는 항 본문 (자동 태깅에 사용)
        chunks.append({"id": cid, "doc": src["id"], "doc_short": src["short"], "kind": src["kind"],
                       "ref_label": ref_label, "text": text.strip(), "article": art["num"],
                       "article_sub": art["sub"], "paragraph": para, "title": art["title"],
                       "chapter": art["chapter"], "page": page, "lead": lead})

    for art in articles:
        base = f"{src['prefix']}_{art['num']}" + (f"-{art['sub']}" if art["sub"] else "")
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
                            mok["text"], art, pnum, mok["page"], f"{para['text']} {item['text']}")
                else:
                    add(iid, ilabel, rendered, art, pnum, item["page"], para["text"])
    return chunks


# ── 영문 번역본 ─────────────────────────────────────────────
def parse_en_law(path) -> list[dict]:
    """Article 단위 → paragraph (n) 단위. 제2조는 호(1., 2., …) 단위로 한 번 더 나눈다."""
    articles, cur_art, started, title_open = [], None, False, False
    for page, line in _pdf_lines(path):
        if RE_EN_NOISE.match(line):
            continue
        if not started and line.startswith("Article 1 ("):
            started = True
        if not started:
            continue
        if title_open:                    # 이전 줄에서 이어지는 제목 "… artificial\nintelligence) (1) …"
            head, _, rest = line.partition(")")
            cur_art["title"] += " " + head.strip()
            cur_art["lines"] = [rest.strip()]
            title_open = False
            continue
        m, mo = RE_EN_ARTICLE.match(line), RE_EN_ARTICLE_OPEN.match(line)
        if m or mo:
            g = m or mo
            cur_art = {"num": int(g.group(1)), "sub": int(g.group(2)) if g.group(2) else None,
                       "title": g.group(3), "page": page, "lines": [m.group(4) if m else ""]}
            articles.append(cur_art)
            title_open = mo is not None and m is None
        elif cur_art is not None:
            cur_art["lines"].append(line)

    for art in articles:
        cur = {"para": None, "item": None, "text": ""}
        units = [cur]
        for line in art.pop("lines"):           # 첫 줄은 Article 머리 줄의 나머지 ("(1) An …")
            pm, im = RE_EN_PARAGRAPH.match(line), RE_EN_ITEM.match(line)
            if pm:
                cur = {"para": int(pm.group(1)), "item": None, "text": pm.group(2)}
                units.append(cur)
            elif im and art["num"] == 2:
                cur = {"para": None, "item": int(im.group(1)), "text": f"{im.group(1)}. {im.group(2)}"}
                units.append(cur)
            else:
                cur["text"] = (cur["text"] + " " + line).strip()
        art["units"] = [u for u in units if u["text"].strip()]
    return articles


def build_en_chunks(articles: list[dict], src: dict) -> list[dict]:
    chunks = []
    for art in articles:
        base = f"{src['prefix']}_{art['num']}" + (f"-{art['sub']}" if art["sub"] else "")
        label = f"Article {art['num']}" + (f"-{art['sub']}" if art["sub"] else "")
        for u in art["units"]:
            cid = base + (f"_{u['para']}" if u["para"] else "") + (f"_{u['item']}" if u["item"] else "")
            ref = label + (f"({u['para']})" if u["para"] else "") + (f" item {u['item']}" if u["item"] else "")
            chunks.append({"id": cid, "doc": src["id"], "doc_short": src["short"], "kind": src["kind"],
                           "ref_label": ref, "text": u["text"], "article": art["num"],
                           "article_sub": art["sub"], "paragraph": u["para"], "title": art["title"],
                           "chapter": "", "page": art["page"], "lead": ""})
    return chunks


def en_lookup(chunks: list[dict]) -> dict:
    """국문 레코드 id(ARTICLE_31_1, ARTICLE_2_4) → 영문 텍스트"""
    out = {}
    for c in chunks:
        key = c["id"].replace("EN_", "ARTICLE_", 1)
        out[key] = {"ref": c["ref_label"], "title": c["title"], "text": c["text"]}
    return out


# ── 해설 자료 ───────────────────────────────────────────────
def build_commentary_chunks(path: Path, src: dict) -> list[dict]:
    """Docling 문서 요소를 페이지·길이 기준으로 묶어 해설 PDF 원문을 인덱싱한다.

    Rule Engine의 BKL_* 요약 레코드는 별도로 유지해 PDF 원문과 판단 요약을 구별한다.
    """
    chunks, current, current_page = [], [], None

    def flush():
        if not current:
            return
        page = current_page
        seq = 1 + sum(c["page"] == page for c in chunks)
        chunks.append({"id": f"BKL_P{page}_{seq}", "doc": src["id"], "doc_short": src["short"],
                       "kind": "COMMENTARY_PDF", "ref_label": f"해설 p.{page}", "text": "\n".join(current),
                       "article": 0, "article_sub": None, "paragraph": None,
                       "title": src["title"], "chapter": "", "page": page, "lead": ""})
        current.clear()

    for item in HierarchicalChunker().chunk(_convert(path)):
        text = item.text.strip()
        pages = [prov.page_no for doc_item in item.meta.doc_items for prov in doc_item.prov]
        if not text or not pages or text.isdigit():
            continue
        page = pages[0]
        if current and (page != current_page or len("\n".join(current)) + len(text) + 1 > MAX_CHUNK_CHARS):
            flush()
        current_page = page
        current.append(text)
    flush()
    return chunks


def build_commentary_summary_chunks(src: dict) -> list[dict]:
    """검수된 BKL_* 요약을 Rule Engine 후보 검색용으로 유지한다."""
    chunks = []
    for r in get_lawbook().records:
        if r["doc"] != src["id"]:
            continue
        chunks.append({"id": r["id"], "doc": src["id"], "doc_short": src["short"], "kind": src["kind"],
                       "ref_label": r["ref_label"], "text": r["text"], "article": 0,
                       "article_sub": None, "paragraph": None, "title": r["summary"], "chapter": "",
                       "page": r.get("source_page") or 0, "lead": ""})
    return chunks


# ── 메타데이터 ─────────────────────────────────────────────
def attach_metadata(chunks: list[dict]) -> list[dict]:
    """태깅 레코드가 있으면 그 메타데이터를, 없으면 Clause Parser로 자동 태깅"""
    law = get_lawbook()
    clause_records: dict[str, list[dict]] = {}
    for r in law.records:
        if r["clause"] in ("A", "B"):
            clause_records.setdefault(r["id"].rsplit("_", 1)[0], []).append(r)

    out = []
    for c in chunks:
        if c["kind"] in ("LAW_EN", "COMMENTARY"):
            out.append({**c, **_meta_blank()})
            continue
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


def _meta_blank() -> dict:
    return {"tagged": False, "addressee": "OTHER", "obligation": "", "external": "", "flags": "",
            "status_rule": "", "penalty_type": ""}


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


# ── 실행 ───────────────────────────────────────────────────
def build_all(sources: list[dict] | None = None) -> tuple[list[dict], dict]:
    """(전체 청크, 영문 조문 매핑)"""
    sources = sources or load_sources()
    chunks, en_map = [], {}
    for src in sources:
        path = RAW_DIR / src["file"]
        if not path.exists():
            raise FileNotFoundError(f"원본 PDF가 없습니다: {path}")
        start = len(chunks)
        if src["parser"] == "ko_law":
            chunks += build_ko_chunks(parse_ko_law(path, src["title"]), src)
        elif src["parser"] == "en_law":
            en_chunks = build_en_chunks(parse_en_law(path), src)
            en_map = en_lookup(en_chunks)
            chunks += en_chunks
        elif src["parser"] == "commentary_pdf":
            chunks += build_commentary_chunks(path, src)
            chunks += build_commentary_summary_chunks(src)
        else:
            raise ValueError(f"알 수 없는 PDF 파서: {src['parser']}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        for chunk in chunks[start:]:
            chunk["source_file"] = src["file"]
            chunk["source_sha256"] = digest
    return attach_metadata(chunks), en_map


def run(out_path=CHUNKS_PATH) -> list[dict]:
    chunks, en_map = build_all()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    if en_map:
        EN_ARTICLES_PATH.write_text(json.dumps(en_map, ensure_ascii=False, indent=2), encoding="utf-8")
    return chunks
