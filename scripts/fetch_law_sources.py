"""Fetch pinned, currently effective AI Basic Act sources from law.go.kr.

API JSON is kept as a version/structure reference. Official PDFs remain the
inputs to Docling and the QA/Chroma ingestion pipelines.

Run: LAW_GO_KR_OC=<your OC> python -m scripts.fetch_law_sources
"""

import hashlib
import io
import json
import os
from pathlib import Path

import requests
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
API_DIR = ROOT / "data" / "reference" / "law_api"
API_URL = "https://www.law.go.kr/DRF/lawService.do"
PDF_URL = "https://www.law.go.kr/LSW/lsPdfPrint.do"

# MST is the lsiSeq for the promulgated law. `law` for 282791 labels the Act
# 2026-01-22; `eflaw` by ID returns its 2026-07-21 effective text.
SOURCES = (
    {
        "name": "ai_basic_law",
        "id": "014820",
        "mst": "282791",
        "number": "21311",
        "effective": "20260721",
        "title": "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법",
        "pdf": "ai_basic_act_20260721.pdf",
        "must_contain": "제17조의2",
    },
    {
        "name": "ai_basic_law_decree",
        "id": "015032",
        "mst": "288781",
        "number": "36580",
        "effective": "20260820",
        "title": "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법 시행령",
        "pdf": "ai_basic_act_decree_20260820.pdf",
        "must_contain": "제1조의2",
    },
)


def fetch_json(session: requests.Session, source: dict, oc: str) -> dict:
    response = session.get(API_URL, params={"OC": oc, "target": "eflaw", "ID": source["id"],
                                            "type": "JSON"}, timeout=45)
    response.raise_for_status()
    data = response.json()
    law = data.get("법령")
    info = law.get("기본정보", {}) if isinstance(law, dict) else {}
    expected = {"법령명_한글": source["title"], "공포번호": source["number"],
                "시행일자": source["effective"], "법령ID": source["id"]}
    mismatches = {key: (info.get(key), value) for key, value in expected.items()
                  if str(info.get(key)) != value}
    if mismatches or not law.get("조문") or source["must_contain"] not in json.dumps(law, ensure_ascii=False):
        raise ValueError(f"예상한 현행 법령과 API 응답이 다릅니다: {source['name']} {mismatches}")
    return data


def fetch_pdf(session: requests.Session, source: dict) -> bytes:
    response = session.get(PDF_URL, params={"lsiSeq": source["mst"],
                                            "efYd": source["effective"], "efGubun": "Y",
                                            "joAllCheck": "Y", "joEfOutPutYn": "on",
                                            "ancYnChk": "0", "bylChaChk": "N",
                                            "mokChaChk": "N"}, timeout=90)
    response.raise_for_status()
    payload = response.content
    if not payload.startswith(b"%PDF-"):
        raise ValueError(f"PDF가 아닌 응답입니다: {source['name']}")
    pdf = PdfReader(io.BytesIO(payload))
    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    compact = "".join(text.split())
    if (source["title"].replace(" ", "") not in compact
            or source["number"] not in compact
            or source["must_contain"] not in compact):
        raise ValueError(f"PDF의 법령명·번호·개정 조문을 확인할 수 없습니다: {source['name']}")
    return payload


def main() -> None:
    oc = os.getenv("LAW_GO_KR_OC", "").strip()
    if not oc:
        raise SystemExit("LAW_GO_KR_OC를 설정한 뒤 실행하세요.")

    # Validate both responses before replacing any pinned source file.
    with requests.Session() as session:
        fetched = [(source, fetch_json(session, source, oc), fetch_pdf(session, source))
                   for source in SOURCES]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    API_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source, data, pdf in fetched:
        json_path = API_DIR / f"{source['name']}.json"
        pdf_path = RAW_DIR / source["pdf"]
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pdf_path.write_bytes(pdf)
        manifest.append({"name": source["name"], "law_id": source["id"], "mst": source["mst"],
                         "number": source["number"], "effective": source["effective"],
                         "api_json": str(json_path.relative_to(ROOT)).replace("\\", "/"),
                         "pdf": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
                         "pdf_sha256": hashlib.sha256(pdf).hexdigest()})
        print(f"{source['name']}: {json_path.relative_to(ROOT)} + {pdf_path.relative_to(ROOT)}")
    (API_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")


if __name__ == "__main__":
    main()
