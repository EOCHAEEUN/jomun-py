# 조문.py — AI Legal Build Checker

> **법조문을 읽는 대신, 법 빌드를 돌립니다.**
> 개발할 AI 서비스를 한 줄로 설명하면, 인공지능기본법과 관련 법령에서 걸리는 조문을 찾아 **빌드 로그**처럼 보여주는 RAG + Rule Engine 기반 Legal Linter

![조문.py 화면](docs/screenshot.png)

- 기획·역할 문서: [최종 기획안 PDF](docs/handout/조문py_최종기획안_20261008.pdf) · [편집용 원본](docs/plan_final_20261008.md) · [3인 QA 작업명세](docs/roles_qa_3.md) · [기존 4인 기획안](docs/plan.md) · [기존 4인 역할 명세](docs/roles.md)
- 발표 참고: [개발일지](docs/presentation/개발일지_20261008.md) · [발표용 기획안](docs/presentation/발표용_기획안_20261008.md)

## AI 기본법 QA 백엔드 (`POST /ask`)

서비스 설명이 없는 법률 질문에는 조문의 의미와 개발 시 확인할 조건을 설명합니다. 서비스 설명을 주면 기존 특성 추출·Rule Engine의 사전 점검 결과를 추가해 적용 가능성을 설명합니다. 두 모드 모두 **인공지능기본법·시행령 원문**을 검색한 뒤 LLM이 답변하며, 실제 인용한 청크만 `sources`로 돌려줍니다. 서비스 설명이 없을 때는 특정 서비스의 의무를 확정하지 않습니다. 기존 화면과 `/api/build`는 그대로 사용할 수 있습니다.

```
AI 기본법·시행령 PDF → Docling 조·항·호·목 청킹 → 의미/어휘 임베딩 → Qdrant
질문 → dense + sparse 검색/RRF → 법률 용어 확장·재정렬 → 원문 + (서비스 입력 시) Rule Engine → LLM → answer + sources
```

WSL에서 이 저장소로 이동한 뒤 실행합니다.

```bash
cd /mnt/c/Users/Admin/Desktop/jomun-py
source /home/ai_fish/jomun-py/.venv/bin/activate  # 현재 작업 환경의 기존 WSL 가상환경
~/.local/bin/uv pip install -r requirements.txt
python -m scripts.ingest_qa
uvicorn app.main:app --host 127.0.0.1 --port 8003
```

`/docs`에서 API 형식을 볼 수 있습니다. `.env`의 `MONOROUTER_API_KEY`, `MONOROUTER_BASE_URL`을 사용합니다. 현재 MonoRouter에서 허용되는 QA 기본 모델은 `gpt-4.1`이며 `QA_LLM_MODEL`로 변경할 수 있습니다. QA 임베딩은 키가 있으면 `text-embedding-3-small`(`QA_EMBEDDING_PROVIDER=monorouter`), 없으면 검색 실험용 로컬 해싱(`local`)을 사용합니다. 임베딩 제공자·모델을 바꾸면 `python -m scripts.ingest_qa`를 다시 실행해야 합니다. Qdrant는 기본적으로 `data/qdrant/` 로컬 모드이며 `QDRANT_URL`로 서버에 연결할 수 있습니다. 로컬 모드에서는 한 프로세스만 저장소를 열 수 있으므로 적재·평가 명령은 API 서버를 멈춘 상태에서 실행합니다.

```bash
curl -s http://127.0.0.1:8003/ask -H 'Content-Type: application/json' \
  -d '{"question":"고영향 인공지능이란 무엇인가요?"}'

curl -s http://127.0.0.1:8003/ask -H 'Content-Type: application/json' \
  -d '{"question":"출시 전에 무엇을 확인해야 하나요?","service_description":"면접 영상을 분석해 채용 점수를 추천하는 AI"}'

curl -s http://127.0.0.1:8003/ask -H 'Content-Type: application/json' \
  -d '{"question":"고영향 AI란 무엇인가요? 내가 면접 영상을 분석해 채용 점수를 추천하는 AI 서비스를 준비하는데 해당하나요?"}'
```

응답은 `answer`, `sources`, `mode`를 포함합니다. 각 출처에는 답변의 `[S1]` 같은 표식과 연결되는 `source_id`, 조문 번호(`article`), 원문(`content`), 문서·페이지·PDF 파일명이 있습니다. 단일 `question`에서 법 개념과 내 서비스의 적용 가능성을 함께 물어도 서비스 모드로 처리하며, 개념 정의와 서비스 검토 근거를 함께 제공합니다. 서비스 설명을 별도 `service_description` 필드로 보내도 됩니다.

QA 개발 질문 12개는 `data/eval/qa_golden.jsonl`에 있습니다. `python -m scripts.evaluate_qa`는 같은 질문에서 dense → sparse → hybrid(RRF) → 다중 질의 → 규칙 재정렬의 Hit@3/5, MRR을 따로 기록합니다. `--stages sparse --output docs/sparse_check.json`처럼 일부 단계만 실행할 수 있고, `--answers`를 붙이면 LLM 답변과 인용 조문을 저장해 사람이 검토할 수 있습니다. IDF 적용 전 개정판 395개 청크의 개발용 결과는 dense Hit@3 **0.833**, MRR **0.653**; hybrid·재정렬 Hit@3 **1.000**, MRR **0.917**입니다. 기존 벡터에 IDF만 적용한 sparse 검색은 같은 12문항에서 Hit@3 **0.750→1.000**, MRR **0.618→0.667**이었습니다(`docs/qa_sparse_before_20261008.json`, `docs/qa_sparse_after_idf_20261008.json`). 이 질문들은 재정렬 개발에 사용됐으므로 독립 성능으로 해석하지 않습니다. 맥락을 붙인 새 dense 임베딩과 전체 단계별 점수는 재적재 후 다시 측정해야 합니다.

새 적재는 IDF를 자동 적용합니다. 기존 QA 컬렉션은 API 서버를 멈춘 상태에서 `python -m scripts.enable_qa_idf`로 벡터 재생성 없이 IDF만 켤 수 있습니다. 목(目) 청크의 상위 호 문장을 dense 임베딩에 반영하려면 `python -m scripts.ingest_qa`로 전체 QA 컬렉션을 재적재해야 합니다. 원격 임베딩 API 상태는 `python -m scripts.check_qa_embedding`으로 먼저 확인할 수 있습니다.

- **법률 자문이 아닙니다.** 아래 데이터 6종 안에서만 판정하는 사전 점검 도구입니다.

---

## 데이터 범위 (6종으로 고정)

| 문서 | 근거 | 조문.py에서 하는 일 |
| --- | --- | --- |
| 인공지능기본법 | 법률 제21311호, 2026.7.21. 시행 | 핵심. 조문 태깅·판정 기준 |
| 인공지능기본법 시행령 | 대통령령 제36580호, 2026.8.20. 시행 | 법률이 "대통령령으로 정한다"고 비워 둔 기준을 채움 (국내대리인 기준, 10²⁶ FLOPs, 고지·표시 방법, 5년 보관 등) |
| 고영향 AI 판단 가이드라인 해설 | 법무법인 태평양 뉴스레터, 2025.9.29. (2차 자료) | PDF 원문을 Docling으로 청킹·임베딩해 별도 검색 가능하게 하고, 판정 후보에는 검수한 요약 9개를 사용. 화면의 요약은 "요약 · 원문 아님"으로 표시 |
| 개인정보 보호법 | 법률 제21445호, 2026.9.11. 시행 | 제37조의2 자동화된 결정, 제23조 민감정보 |
| 신용정보법 | 법률 제21445호(타법개정), 2026.9.11. 시행 | 제2조제14호 자동화평가, 제36조의2 설명·이의제기 |
| 인공지능기본법 영문본 | 국가법령정보센터 영문 번역 (참고용) | INSPECT 원문 탭에 English 병기 |

사용 중인 문서 목록은 `data/sources.json`입니다. 현재 국문 기본법은 **제21311호**, 시행령은 **제36580호**이고, `data/raw/`의 `ai_basic_act_20260721.pdf`와 `ai_basic_act_decree_20260820.pdf`를 Docling 입력으로 사용합니다. 이전 PDF 두 개도 비교용으로 남아 있지만 적재 대상은 아닙니다. 시행일 기준 법제처 API JSON은 `data/reference/law_api/`에 버전 대조용으로 보관하며 임베딩하지 않습니다. 이 6종 밖의 규정(장관 고시, 정부가 발표한 고영향 AI 판단 가이드라인 원문 — 위 BKL 해설과는 별개 —, 개인정보 보호법 시행령 등)이 필요한 판단은 `◈ EXTERNAL`로 표시하고 판정하지 않습니다.

법령 원본을 다시 받으려면 WSL에서 `LAW_GO_KR_OC`를 설정한 뒤 아래 순서로 실행합니다. API 동기화 스크립트는 예상 법령번호와 시행일이 다르면 저장을 중단합니다. Qdrant 로컬 모드에서는 서버를 멈춘 상태에서 재적재·평가합니다.

```bash
export LAW_GO_KR_OC=your_oc
python -m scripts.fetch_law_sources
python -m scripts.sync_tagged_pages
python -m scripts.ingest_qa
python -m scripts.ingest
python -m scripts.evaluate_qa
```

**같은 질문, 법마다 다른 답.** "사람이 실질적으로 개입하는가"는 세 법의 판단에 모두 영향을 주지만, 작동 방식이 다릅니다.

| 법 | 정의 | 사람이 실질적으로 최종 결정하면 |
| --- | --- | --- |
| 개인정보 보호법 제37조의2 | "완전히 자동화된 시스템"으로 한 결정 | 정의상 대상 아님 → `INFO` |
| 신용정보법 제2조제14호 · 제36조의2 | "종사자가 평가 업무에 관여하지 아니하고" | 정의상 자동화평가 아님 → `INFO` |
| 인공지능기본법 제2조제4호 | 영역 안에서 "판단 또는 평가"에 쓰이는 AI | 본문에 사람 개입 제외 규정이 없음 → `REVIEW` 유지, 제33조① 확인 요청 안내 |

가이드라인 해설은 "실질적인 인사권자의 개입 **없이**" 탈락시키는 경우를 해당 사례로 들 뿐, 사람이 개입하면 고영향이 아니라고 정하지 않았습니다. "개입 없음 → 해당 사례"에서 "개입 있음 → 비해당"은 따라 나오지 않으므로, 고영향 영역과 관련성이 확인된 서비스에서는 ‘사람이 최종 결정한다’는 사실만으로 `INFO`로 내리지 않습니다. 비해당을 확정하려면 제33조① 확인 요청에 따른 비해당 회신 등 명확한 근거가 필요합니다. 같은 문장을 법마다 다르게 읽어야 하므로 LLM 한 번으로 뭉뚱그려 판단하지 않습니다.

---

## 빠른 시작

Python 3.10 이상이 필요합니다 (CI는 3.11).

```bash
# 1. 가상환경 만들고 켜기
python -m venv venv
venv\Scripts\activate          # Windows CMD
# source venv/bin/activate     # Mac / Linux

# 2. 패키지 설치
pip install -r requirements.txt

# 3. (선택) 환경 변수 — API 키가 없어도 동작합니다
copy .env.example .env         # Windows
# cp .env.example .env         # Mac / Linux

# 4. PDF 6종 → Docling 변환·청킹 → Chroma 임베딩 (안 하면 '규칙만 모드')
python -m scripts.ingest

# 5. 서버 실행 → 브라우저에서 http://127.0.0.1:8000
python run.py
```

API 키가 없으면 키워드 규칙 기반 추출기와 로컬 해싱 임베딩으로 동작합니다. `.env`에 `OPENAI_API_KEY`를 넣으면 서비스 특성 추출에 LLM(LangChain + OpenAI)을 씁니다. 적재를 건너뛰면 검색 없이 규칙만으로 판정하고, 화면 상단 상태에 `규칙만 모드`라고 표시합니다.

적재는 원본 PDF를 바꾸지 않습니다. Docling의 native PDF 파서로 여섯 파일의 텍스트와 페이지를 읽고, 법령은 조·항·호·목 단위로, 영문본은 Article 단위로 나눕니다. BKL 해설은 PDF 원문 청크 11개와 판정용 요약 9개를 별도 ID로 저장합니다. 결과는 `data/processed/chunks.json`과 `data/vectorstore/`에 생성되며, 각 청크에는 원본 파일명과 SHA-256 해시가 남습니다. 기본 임베딩은 로컬 해싱이고 `EMBEDDING_PROVIDER=openai`를 설정하면 OpenAI 임베딩을 사용합니다.

---

## 화면 구성

| 영역 | 하는 일 |
| --- | --- |
| **01 서비스 설명** | 서비스 설명 입력, `예시 불러오기`(dev 평가셋 11개 순환), `법령 점검` (Ctrl+Enter). 아래에 실제 AI 사용 방식 고지 |
| **02 점검 결과** | 조문 번호와 한 줄 설명 중심 목록. 판정 상태는 `의무`, `검토 필요`, `조건부 의무` 등 일반 텍스트로 표시하고, 확인할 사항으로 이동할 수 있음 |
| **03 적용 가이드** | 판정 조건·설계 질문·구현 작업을 먼저 보고, 아래에서 조문 원문·적용 이유·해설 요약·English 병기를 확인. `작업 체크리스트`에서 전체 작업을 확인하고 검색·제재 경로는 `판단 과정 자세히`에서 확인 |
| 적용 사항 체크리스트 | 빌드 결과 전체에서 할 일 모음 (체크 상태는 브라우저에 저장) |
| 사이드바 `법령 라이브러리` | 데이터 범위 6종 목록 |

### 판정 상태

| 상태 | 의미 |
| --- | --- |
| `MATCH` | 서비스 특성이 조문의 정의·영역과 일치 |
| `REQUIRED` | 조건이 확정된 사업자 의무 (MUST) |
| `CONDITIONAL` | 조건이 확정되면 적용되는 의무 (예: `IF HIGH_IMPACT_AI →`, `IF 완전히 자동화된 결정 →`) |
| `SHOULD` | 노력의무 |
| `REVIEW` | 데이터만으로 단정 불가 → 되묻기 질문 |
| `OPPORTUNITY` | 공공기관 도입 검토 시 우선 고려 요소, 받을 수 있는 지원 (고영향 미확정이면 `IF HIGH_IMPACT_AI →` 조건부) |
| `INFO` | 참고 (해당하지 않는 이유 포함) |

**보조 표식** — 판정 상태와 별도로 항목에 붙는 표시입니다.

| 표식 | 의미 |
| --- | --- |
| `◈ EXTERNAL` | 장관 고시·다른 법의 시행령 등 데이터 6종 밖의 규정이 있어야 확정됨 |
| `IF … →` | 조건부 항목의 조건 (`IF HIGH_IMPACT_AI`, `IF 정보주체가 거부·설명 요구` 등) |
| 수범자 칩 | 조문의 주어. 정보주체의 권리(MAY)는 사업자 의무로 쓰지 않고 "요구가 오면 대응"으로 바꿔 보여준다 |
| `penalty` | 제재 경로 DIRECT / INDIRECT / NONE |

### 데모 3장면

1. **바목 함정** — "얼굴 인식 채용 AI"에서 RAG는 생체정보 쿼리로 바목도 후보로 가져오지만, 규칙이 "생체정보를 쓰지만 목적이 범죄 수사·체포가 아님"으로 기각하고 채용(사목)으로 판정한다. `적용 가이드`의 `판단 과정 자세히`에서 검색 경로와 기각 이유를 확인할 수 있다.
2. **같은 답, 법마다 다른 판단** — HIGH_IMPACT_AI의 질문에 "사람이 실질적으로 검토해 최종 결정해요"를 고르면 개인정보 보호법 제37조의2는 `INFO`(완전히 자동화된 결정 아님)로 바뀌지만, AI기본법 고영향은 `REVIEW`로 남고 제34조① 등은 `CONDITIONAL`로 유지된다. 고영향 영역과 관련성이 확인된 경우, 비해당을 확정하려면 제33조① 확인 요청에 따른 비해당 회신 등 명확한 근거가 필요하다.
3. **시행령이 채운 숫자** — 해외 기업 예시에서 제36조 질문에 시행령 제29조 기준(매출 1조·AI 매출 100억·이용자 100만)이 그대로 나온다.

---

## 동작 방식

```
SERVICE SPEC
   ↓  ① 특성 추출 (LLM 또는 규칙) — 판정하지 않고 사실만 뽑는다
   ↓  ② RAG 후보 검색 — 설명 그대로(naive) + 특성을 법률 용어로 바꾼 쿼리, 쿼리마다 Chroma top-5
   │                   → 참조 그래프 1단계 확장 (상위 조문 · refs · 고영향이면 적용되는 조문)
   ↓  ③ Rule Engine 검증 — 후보 조문마다 적용 조건 확인 → MATCH / REQUIRED / CONDITIONAL / REVIEW …
   │                   후보에 없는 조문은 판정하지 않는다 · 맞지 않는 후보는 이유와 함께 기각
   │   기본 규칙 — 제4조(적용 범위) · 제33조①(사전 검토) · 고영향 판정 결과는 검색과 상관없이 항상 확인
   ↓  ④ Penalty · Reference Graph — DIRECT / INDIRECT / NONE
 점검 결과 → 적용 가이드 (적용과 근거 │ 작업 체크리스트)
```

핵심 설계
- **LLM은 서비스 특성만 추출하고, Chroma는 후보 조문을 찾고, Rule Engine이 적용 여부를 판정한다.** 문법 파서와 정적 템플릿이 법률 문법을 개발자 언어로 변환한다. LLM 기반 쉬운 말 표현은 Plain 모드에서 확장한다.
- **RAG는 후보를 찾고, 규칙은 검증한다.** 검색이 놓친 조문은 빌드 로그에 오르지 않는다. 그래서 검색 성능이 최종 결과에 그대로 드러나고, 평가도 단계별로 따로 잰다.
- **검색 누락을 '해당 없음'으로 넘기지 않는다.** 특성은 고영향 영역(예: 사목)을 가리키는데 그 조문이 후보에 없으면 `REVIEW · 고영향 영역 조문 검색 누락`으로 올린다.
- Chroma가 비어 있으면 **규칙만 모드**로 모든 규칙을 평가한다 (평가의 ② 규칙 판정 정확도도 이 모드로 잰다).

| 컴포넌트 | 파일 |
| --- | --- |
| 서비스 특성 스키마 | `app/schemas.py` |
| 특성 추출 (LLM / 규칙) | `app/engine/features.py`, `app/engine/prompts.py` |
| Clause Parser (법률 문법 → MUST/SHOULD/MAY, EXTERNAL) | `app/engine/grammar.py` |
| Rule Engine | `app/engine/rules.py` |
| Penalty Graph | `app/engine/penalty.py` |
| 파이프라인 | `app/engine/pipeline.py` |
| RAG 후보 검색 (쿼리 생성 · 참조 확장) | `app/rag/retriever.py` |
| Docling PDF 변환·청킹 (국문 법령·영문·해설 원문) | `app/rag/preprocess.py` |
| Chroma 적재·검색, 로컬 임베딩 | `app/rag/store.py`, `app/rag/embeddings.py` |

### 핵심 데이터: `data/tagged/articles.json`

조문을 **절(clause) 단위**로 직접 태깅한 152개 레코드입니다 (인공지능기본법 66 · 시행령 59 · 신용정보법 11 · 가이드라인 해설 9 · 개인정보 보호법 7). 해설을 뺀 143개는 원문 PDF와 글자 단위로 대조하는 테스트가 있습니다. 이 JSON 하나가 Rule Engine의 근거, Chroma 메타데이터, 평가 정답지를 겸합니다.

```json
{
  "id": "DECREE_29_1",
  "doc": "DECREE",
  "ref_label": "제29조①",
  "text": "법 제36조제1항 각 호 외의 부분에서 “대통령령으로 정하는 기준에 해당하는 자”란 …",
  "summary": "국내대리인 지정 대상: 매출 1조↑ / AI 서비스 매출 100억↑ / 국내 일평균 이용자 100만↑ / 과태료 이력",
  "refs": ["ARTICLE_36_1"]
}
```

- `addressee`(수범자): 인공지능사업자 · 개인정보처리자 · 정보주체 · 개인신용평가회사등 · 정부 등. 정부가 주어인 조문을 사업자 의무로 오해하지 않게 한다.
- `obligation`과 `external_dependency`는 별개의 축: "누가 무엇을 해야 하나" vs "하위 규정이 필요한가"
- `penalty`: MUST라도 제재가 없거나(제33조①), 사실조사를 거치는 간접 제재(제34조①)일 수 있다.
- `verbatim: false`: 가이드라인 해설 요약. 원문 인용이 아님을 화면에 표시한다.

디컴파일 코드는 `data/tagged/decompiled/*.py`에 내부 참고 자료로 남아 있으며, 화면에는 표시하지 않습니다.

---

## 평가 — 검색 · 규칙 · 최종 빌드를 따로 잰다

```bash
python -m scripts.ingest                # 먼저 적재
python -m scripts.evaluate              # 결과 → data/eval/results.json
python -m scripts.evaluate --snapshot   # docs/eval_snapshot.json 갱신
```

| 평가셋 | 파일 | 성격 |
| --- | --- | --- |
| dev 11개 | `data/eval/cases.json` | 규칙을 만들면서 본 케이스 (바목 함정, 경찰 얼굴 인식 대조군, 생성형 표시 의무, 영화 추천 오탐 방지, 해외 기업, 국방 전용, 외부 LLM API, 사람이 최종 결정하는 채용 AI 등) |
| held-out 11개 | `data/eval/heldout_cases.json` | 엔진 수정 전에 따로 써 둔 케이스. **결과를 보고 엔진을 고치지 않는다** |

로컬 해싱 임베딩 · 규칙 기반 특성 추출 · 청크 1,736개 기준 ([상세](docs/evaluation.md), [스냅샷](docs/eval_snapshot.json)):

| 지표 | dev | held-out |
| --- | --- | --- |
| ① 검색 Hit@3 — 설명 그대로 (naive) | 0.28 | 0.07 |
| ① 검색 Hit@3 — 특성 쿼리 (enriched) | 0.83 | 0.80 |
| ② 규칙 판정 정확도 (검색 없이) | 1.00 | 0.69 |
| ③ 최종 빌드 정확도 (RAG → 규칙) | 1.00 | **0.61** |
| ③ 케이스 완전 일치 | 1.00 | 0.36 |

- **검색**: 서비스 설명을 그대로 넣으면 개인정보 보호법·신용정보법 청크에 묻혀 정답 조문을 거의 못 찾는다. 특성을 법률 용어 쿼리로 바꾸면 0.80까지 오른다.
- **dev 1.00은 실력이 아니다.** 규칙을 만들며 본 케이스라서다. 지금 실력은 held-out ③ 0.61이다.
- **held-out에서 틀린 14개 점검의 원인**: 검색 3개(에너지 영역 가목을 후보로 못 찾음), 특성 추출 8개(“판독”, “스스로 결정”, “사람 검토 없이 산출”, “실제 사람 목소리처럼” 같은 표현을 못 읽음), 규칙 범위 3개(시행령 제23조④ 내부 업무 예외, 설명 속 이용자 수를 시행령 기준과 비교). 고치면 이 held-out은 '본 데이터'가 되므로, 새 held-out을 먼저 쓰고 고친다.

이전 버전의 `rule_hit = 1.0`은 규칙이 직접 넣은 근거 레코드에 정답이 있는지 본 순환 지표라서 뺐습니다.

**평가 운영 규칙** (데이터 누수 방지)
- merge 기준은 **dev 회귀 1.0 유지**뿐입니다 (`test_rules.py`, `test_rag.py`의 dev 케이스).
- held-out은 **보고용**입니다. held-out 점수를 올리려고 규칙·쿼리·키워드를 고치지 않습니다.
- held-out 실패를 고치고 싶으면 ① 새 held-out(v2)을 먼저 쓰고 ② v1을 dev로 옮긴 뒤 ③ 고치고 ④ v2로 다시 잽니다.
- 판정 정책이 바뀌어 dev 정답을 고칠 때는 이유를 케이스의 `point`에 남깁니다 (예: dev 11 — 사람 최종 결정 시 고영향 `REVIEW` 유지).

---

## 테스트

```bash
python -m pytest -q
```

GitHub Actions(`.github/workflows/test.yml`)가 push·PR마다 Python 3.11에서 같은 명령을 돌립니다. 테스트는 임시 폴더에 Chroma를 새로 적재해서 쓰므로 `data/vectorstore`가 없어도 됩니다.

| 파일 | 내용 |
| --- | --- |
| `tests/test_data.py` | 태깅 레코드 143개가 원문 PDF와 글자 단위로 일치하는지(적재용 Docling과 별개로 pypdf로 다시 추출해 대조), 해설이 요약으로 표시되는지 |
| `tests/test_preprocess.py` | 6개 PDF 청킹, 제33조① 절 분리, 시행령 제29조 수치 보존, 줄바꿈 이어 붙이기, 개정 표시 제거, 영문 매핑, 해설 원문·요약 분리 |
| `tests/test_rules.py` | 문법 파서, 특성 추출('해외' 단독 언급은 미확정), 판정 엔진(규칙만 모드), 사람 최종 결정이 법마다 다르게 작동, 제37조의2 ④공개/③대응 분리, 신용정보법 권리를 사업자 의무로 쓰지 않음, OPPORTUNITY 조건, RAG 후보 검증(후보에 없으면 판정 안 함 · 기본 규칙 유지 · 검색 누락은 REVIEW · 영역 후보 기각 이유), 제재 경로, dev 11개 |
| `tests/test_rag.py` | 임시 Chroma 적재, 검색 필터, 특성 쿼리, 사목 검색·참조 확장, 파이프라인이 RAG 후보를 쓰는지, 규칙만 모드 폴백, dev 11개(RAG 모드), **평가 결과 = 커밋된 스냅샷** |
| `tests/test_api.py` | `/`, `/api/sources`(6종), `/api/examples`, `/api/build` 스키마·답변 반영, 잘못된 입력 422, `/api/articles/{id}` |

> 참고: `한다`의 첫 글자는 `하`가 아니라 `한`이고, 시행령은 `해야 한다`·`포함되어야 한다`처럼 어미가 다릅니다. `grammar.py`는 `(어|여|해)야\s*(한|하)`로 모두 MUST로 잡습니다.

---

## API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/build` | `{"spec": "...", "answers": {"high_impact": "human_final"}}` → 빌드 결과 (`items[].found_by` · `baseline` · `rejected`, `rag` 후보 요약 포함) |
| `GET` | `/api/sources` | 데이터 6종 목록 |
| `GET` | `/api/examples` | 평가셋 예시 목록 |
| `GET` | `/api/articles` | 태깅된 조문 목록 |
| `GET` | `/api/articles/{id}` | 조문 레코드 하나 |
| `GET` | `/api/health` | 추출기·벡터DB 상태 |

`answers` 키: `high_impact`(automated / human_final / assume / confirmed_no), `domestic_office`(yes / no / unknown), `threshold`(yes / no / unknown), `compute`(yes / no / unknown)

Swagger 문서: http://127.0.0.1:8000/docs

---

## 폴더 구조

```
jomun-py/
├── run.py                    # 서버 실행
├── requirements.txt
├── .github/workflows/test.yml  # CI: pytest -q
├── .env.example
├── app/
│   ├── main.py               # FastAPI (화면 + API)
│   ├── config.py             # 설정 모음
│   ├── schemas.py            # ServiceFeatures, BuildRequest
│   ├── engine/               # 특성 추출 · 문법 파서 · Rule Engine · Penalty Graph
│   ├── rag/                  # PDF 전처리 · 임베딩 · Chroma · 후보 검색(retriever)
│   └── static/               # index.html, css, js, img, fonts
├── data/
│   ├── sources.json          # 데이터 6종 목록
│   ├── raw/                  # 원본 PDF 6종
│   ├── tagged/               # articles.json (핵심), en_articles.json, decompiled/*.py
│   └── eval/                 # cases.json (dev 11) · heldout_cases.json (held-out 11)
├── docs/                     # evaluation.md, eval_snapshot.json, screenshot.png
├── scripts/                  # ingest.py, evaluate.py
└── tests/                    # pytest (data · preprocess · rules · rag · api)
```

---

## 다음 단계 (하루 범위 밖)

- [ ] held-out v2를 먼저 쓰고 → held-out v1 실패 수정 (영역 쿼리 공통 문구, 자동 판정 표현, 시행령 제23조④ 예외)
- [ ] LLM 특성 추출기로 같은 평가표 다시 만들기
- [ ] 2차 빌드 `--validate`: 구현 상태 체크 → `ERROR` / `PASS`
- [ ] Plain 모드: 비개발자용 쉬운 설명 (LLM 표현 단계)
- [ ] 정부 가이드라인 원문·장관 고시 추가 → 남은 `EXTERNAL` 해소
- [ ] 리포트 Export

---

## 출처·라이선스

- 법령 원문(법률·시행령·영문 번역): 국가법령정보센터. 법령은 저작권법 제7조에 따라 보호받지 않는 저작물입니다.
- **가이드라인 해설 PDF는 법무법인 태평양의 2차 자료입니다.** 사용자 제공 원본을 `data/raw/`에 포함해 Docling으로 청킹·임베딩합니다. Rule Engine의 `BKL_*` 레코드 9개는 팀이 작성한 요약(`verbatim: false`)으로 원문 청크와 구별하며, 화면에도 요약임을 표시합니다.
- 글꼴: [Pretendard](https://github.com/orioncactus/pretendard) (SIL Open Font License 1.1, `app/static/fonts/Pretendard-LICENSE.txt`)
- `app/static/img/`의 일러스트·로고: UI 시안 이미지에서 잘라낸 임시 이미지입니다. 원본 일러스트로 교체하세요.
