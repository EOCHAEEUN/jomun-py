# 공통 설정 (python -m pytest 로 실행)
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEMO = "얼굴 인식으로 면접 영상을 분석해서 지원자의 채용 점수를 추천하는 AI"


@pytest.fixture(scope="session")
def chunks():
    """PDF → 청크 (파일을 쓰지 않는 build_all 사용 — data/processed, en_articles.json을 건드리지 않음)"""
    from app.rag import preprocess
    built, en_map = preprocess.build_all()
    return {"chunks": built, "en_map": en_map}


@pytest.fixture(scope="session")
def chroma(chunks, tmp_path_factory):
    """임시 폴더에 Chroma를 새로 적재한다 (로컬 data/vectorstore 상태와 무관)

    chromadb가 설치되지 않은 환경에서는 이 fixture를 쓰는 테스트만 건너뛴다 (CI는 requirements.txt로 설치)."""
    pytest.importorskip("chromadb")
    from app.rag import store
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(store, "VECTORSTORE_DIR", tmp_path_factory.mktemp("vectorstore"))
        store.get_collection.cache_clear()
        count = store.build_collection(chunks["chunks"])
        yield count
        store.get_collection.cache_clear()
