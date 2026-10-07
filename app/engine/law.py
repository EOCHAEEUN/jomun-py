# law.py — 태깅 JSON(articles.json)과 데이터 목록(sources.json)을 읽어 조문 레코드를 꺼내 쓰는 도우미
import json
from functools import lru_cache

from app.config import DECOMPILED_DIR, EN_ARTICLES_PATH, SOURCES_PATH, TAGGED_PATH

ADDRESSEE_KO = {
    "AI_BUSINESS": "인공지능사업자",
    "GOVERNMENT": "정부·과기부 장관",
    "PUBLIC_AGENCY": "국가기관등",
    "COMMITTEE": "위원회",
    "DATA_HANDLER": "개인정보처리자",
    "DATA_SUBJECT": "정보주체",
    "CREDIT_EVALUATOR": "개인신용평가회사등",
    "OTHER": "정의·기타",
}


class LawBook:
    def __init__(self, path=TAGGED_PATH):
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.records: list[dict] = doc["records"]
        self.by_id = {r["id"]: r for r in self.records}
        self.sources: list[dict] = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        self.source_by_id = {s["id"]: s for s in self.sources}
        self.law = self.source_by_id["AIACT"]           # 핵심 법률 (하위 호환)
        self.en = json.loads(EN_ARTICLES_PATH.read_text(encoding="utf-8")) if EN_ARTICLES_PATH.exists() else {}

    def get(self, record_id: str) -> dict:
        return self.by_id[record_id]

    def children(self, record_id: str) -> list[dict]:
        """한 단계 아래 레코드 (제34조① → ①1호~6호, 제2조제4호 → 가~카목)"""
        depth = record_id.count("_") + 1
        return [r for r in self.records
                if r["id"].startswith(record_id + "_") and r["id"].count("_") == depth]

    @staticmethod
    def marker(child: dict) -> str:
        return f"{child['clause'] or child['item']}."

    def original_text(self, record_ids: list[str]) -> str:
        """원문 텍스트 (항 본문 + 딸린 호·목) — 평가·디버깅용"""
        blocks = []
        for rid in record_ids:
            r = self.by_id[rid]
            lines = [f"[{self.source_by_id[r['doc']]['short']} {r['ref_label']}] {r['text']}"]
            for child in self.children(rid):
                lines.append(f"  {self.marker(child)} {child['text']}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def english(self, record_id: str) -> dict | None:
        """인공지능기본법 레코드의 영문 번역 (ARTICLE_31_1 → Article 31(1))"""
        if self.by_id[record_id]["doc"] != "AIACT":
            return None
        key = record_id
        while key and key not in self.en:      # ARTICLE_2_4_SA → ARTICLE_2_4 → …
            key = key.rsplit("_", 1)[0] if "_" in key else ""
            if key == "ARTICLE":
                return None
        return self.en.get(key)

    def public_record(self, record_id: str) -> dict:
        r = self.by_id[record_id]
        src = self.source_by_id[r["doc"]]
        return {
            "id": r["id"],
            "doc": r["doc"],
            "doc_short": src["short"],
            "doc_kind": src["kind"],
            "verbatim": r.get("verbatim", True),
            "ref_label": r["ref_label"],
            "title": r["title"],
            "text": r["text"],
            "summary": r["summary"],
            "addressee": r["addressee"],
            "addressee_ko": ADDRESSEE_KO.get(r["addressee"], r["addressee"]),
            "obligation": r["obligation"],
            "flags": r["flags"],
            "external_dependency": r["external_dependency"],
            "penalty": r["penalty"],
            "source_page": r["source_page"],
            "children": [{"marker": self.marker(c), "id": c["id"], "text": c["text"]}
                         for c in self.children(record_id)],
            "en": self.english(record_id),
        }


@lru_cache
def get_lawbook() -> LawBook:
    return LawBook()


@lru_cache
def read_decompiled(filename: str) -> str:
    path = DECOMPILED_DIR / filename
    return path.read_text(encoding="utf-8") if path.exists() else ""
