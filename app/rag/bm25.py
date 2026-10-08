"""Local BM25 search over the same legal clauses used by /api/build."""

import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from app.config import CHUNKS_PATH


SEARCHABLE_DOCS = ("AIACT", "DECREE", "PIPA", "CREDIT", "BKL")
EXCLUDED_ADDRESSEES = ("GOVERNMENT", "COMMITTEE")
_WORDS = re.compile(r"[가-힣A-Za-z0-9]+")


def is_searchable(chunk: dict) -> bool:
    return (chunk.get("doc") in SEARCHABLE_DOCS
            and chunk.get("kind") != "COMMENTARY_PDF"
            and chunk.get("addressee") not in EXCLUDED_ADDRESSEES)


def tokenize(value: str) -> list[str]:
    """Keep exact words and Korean character n-grams for inflected legal terms."""
    terms = []
    for match in _WORDS.finditer(value.lower()):
        word = match.group()
        terms.append("w:" + word)
        if any("가" <= char <= "힣" for char in word):
            for n in (2, 3):
                terms.extend(f"g{n}:{word[i:i+n]}" for i in range(len(word) - n + 1))
    return terms


class BM25Index:
    def __init__(self, chunks: list[dict], k1: float = 1.2, b: float = 0.75):
        self.chunks = [chunk for chunk in chunks if is_searchable(chunk)]
        self.k1, self.b = k1, b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths = []
        for index, chunk in enumerate(self.chunks):
            # Mirror the text that Chroma embeds during ingest.
            value = f"[{chunk['doc_short']} {chunk['ref_label']} {chunk['title']}] {chunk['text']}"
            counts = Counter(tokenize(value))
            self.lengths.append(sum(counts.values()))
            for term, count in counts.items():
                self.postings[term].append((index, count))
        self.average_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0

    def search(self, query: str, k: int = 5) -> list[dict]:
        if k <= 0 or not self.chunks:
            return []
        scores: dict[int, float] = defaultdict(float)
        n_docs = len(self.chunks)
        for term in set(tokenize(query)):
            postings = self.postings.get(term, ())
            if not postings:
                continue
            idf = math.log1p((n_docs - len(postings) + 0.5) / (len(postings) + 0.5))
            for index, freq in postings:
                norm = self.k1 * (1 - self.b + self.b * self.lengths[index] / self.average_length)
                scores[index] += idf * freq * (self.k1 + 1) / (freq + norm)
        ranked = sorted(scores, key=lambda index: (-scores[index], self.chunks[index]["id"]))[:k]
        return [{**self.chunks[index], "score": round(scores[index], 6),
                 "snippet": self.chunks[index]["text"][:120]} for index in ranked]


@lru_cache(maxsize=2)
def _load_index(path: str, mtime_ns: int, size: int) -> BM25Index:
    del mtime_ns, size
    return BM25Index(json.loads(Path(path).read_text(encoding="utf-8")))


def get_index() -> BM25Index | None:
    if not CHUNKS_PATH.exists():
        return None
    stat = CHUNKS_PATH.stat()
    return _load_index(str(CHUNKS_PATH), stat.st_mtime_ns, stat.st_size)


def search(query: str, k: int = 5) -> list[dict]:
    index = get_index()
    return index.search(query, k) if index else []
