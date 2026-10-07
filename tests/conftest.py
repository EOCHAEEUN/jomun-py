# 프로젝트 루트를 import 경로에 추가 (python -m pytest 로 실행)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
