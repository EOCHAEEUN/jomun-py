"""Refresh manually tagged AI Act/Decree page numbers from their Docling PDFs.

Run after changing the active PDFs in data/sources.json:
    python -m scripts.sync_tagged_pages
"""

import json

from app.config import RAW_DIR, TAGGED_PATH
from app.rag.preprocess import MOK_CODE, load_sources, parse_ko_law


def main() -> None:
    pages = {}
    for src in load_sources():
        if src["id"] not in {"AIACT", "DECREE"}:
            continue
        for art in parse_ko_law(RAW_DIR / src["file"], src["title"]):
            base = f"{src['prefix']}_{art['num']}" + (f"-{art['sub']}" if art["sub"] else "")
            pages[base] = art["page"]
            for para in art["paragraphs"]:
                pid = base + (f"_{para['num']}" if para["num"] else "")
                pages[pid] = para["page"]
                for item in para["items"]:
                    iid = f"{pid}_{item['num']}"
                    pages[iid] = item["page"]
                    for mok in item["moks"]:
                        pages[f"{iid}_{MOK_CODE[mok['ko']]}"] = mok["page"]

    data = json.loads(TAGGED_PATH.read_text(encoding="utf-8"))
    changed = 0
    missing = []
    for record in data["records"]:
        if record["doc"] not in {"AIACT", "DECREE"}:
            continue
        rid = record["id"]
        lookup = rid.rsplit("_", 1)[0] if record.get("clause") in {"A", "B"} else rid
        page = pages.get(lookup)
        if page is None:
            missing.append(rid)
            continue
        if record.get("source_page") != page:
            record["source_page"] = page
            changed += 1
    if missing:
        raise ValueError(f"PDF에서 찾지 못한 태깅 조문: {missing}")
    TAGGED_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"태깅 원문 페이지 갱신: {changed}개")


if __name__ == "__main__":
    main()
