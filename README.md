# 🔬 Patent Discovery Agent

연구 산출물(GitHub 커밋, 연구보고서, PT 등)의 **버전 간 변화**를 분석해 잠재 발명을 찾아내고,
**KIPRIS 선행기술 검색**까지 이어 **발명신고서 초안**을 자동 생성하는 AI Agent입니다.

```
GitHub 커밋 / Drive 리비전 2개 선택
        ↓  (자동 수집 — 수동 업로드 없음)
    텍스트 추출 → Diff 생성 (로컬, 무료)
        ↓
    기술 변화 분석 (LLM)
        ↓
    발명 포인트 도출 · 과제/수단/효과 구조화 (LLM)
        ↓
    KIPRIS 선행기술 검색 (무료 API) → 유사도·차별점 평가 (LLM)
        ↓
    발명신고서 초안 (.md / .docx)
```

## 특징

- **문서 입력은 연동만**: GitHub REST API v3, Google Drive API v3. 수동 파일 업로드는 제공하지 않습니다.
- **지원 포맷**: `.md`, `.txt`, `.pdf`, `.pptx`, `.docx` (DOCX는 문단과 표를 함께 읽습니다)
- **선행기술 검색은 국내 한정**: KIPRIS Plus OpenAPI(특허/실용신안). USPTO·Google Patents 등 해외 DB는 조회하지 않습니다(영문 검색어는 신고서 참고용).
- **비용 최소화**: Diff는 로컬 `difflib`, 소스 파일·LLM 응답·KIPRIS 응답을 모두 SQLite/파일로 캐싱합니다. 같은 입력을 재분석하면 API 호출이 발생하지 않습니다.
- **데모 안전장치**: KIPRIS Service Key가 없으면 샘플 XML로 동작하는 오프라인 모드로 자동 전환되며, 화면에 "샘플 데이터" 배지가 표시됩니다.

## 설치

```bash
pip install -r requirements.txt
cp .env.example .env     # Windows: copy .env.example .env
python -m db.init_db
```

## 환경변수 (.env)

| 키 | 설명 |
|----|------|
| `OPENAI_API_KEY` | LLM 호출용 (필수) |
| `GITHUB_TOKEN` | repo 읽기 권한이 있는 Personal Access Token |
| `GDRIVE_CREDENTIALS_PATH` | 서비스 계정 키 또는 OAuth 클라이언트 시크릿 경로 |
| `KIPRIS_SERVICE_KEY` | KIPRIS Plus Service Key (없으면 오프라인 모드) |
| `KIPRIS_MAX_RESULTS` | 유사도 평가 대상 상위 N건 (기본 10) |
| `KIPRIS_OFFLINE` | `true`면 실제 호출 없이 샘플 응답 사용 |

### 키 발급 방법

- **GitHub PAT**: Settings → Developer settings → Personal access tokens → `repo` (private) 또는 `public_repo` 권한으로 생성
- **Google Drive**: Google Cloud Console에서 프로젝트 생성 → Drive API 사용 설정 → 서비스 계정 키(JSON) 발급 후 `data/credentials/service_account.json`에 저장 → 분석할 Drive 폴더를 서비스 계정 이메일과 공유
- **KIPRIS**: [plus.kipris.or.kr](https://plus.kipris.or.kr) 회원가입 → 특허/실용신안 검색 서비스 신청 → 발급된 Service Key 사용 (무료, 일일 호출 한도 있음)

> ⚠️ 오퍼레이션명·응답 필드명은 KIPRIS Plus 계정 발급 시 제공되는 API 명세서 기준으로 확인하세요.
> 응답 매핑은 `patent/kipris_client.py`의 `_normalize_item()` 한 곳에만 있으므로, 다를 경우 여기만 수정하면 됩니다.

## 실행

```bash
streamlit run app.py
```

홈에서 프로젝트를 만든 뒤, 좌측 페이지를 순서대로 진행합니다.

| 페이지 | 하는 일 |
|--------|---------|
| 1 🔗 Source | GitHub 저장소 연결 → 파일·커밋 선택, 또는 Drive 폴더 → 파일·리비전 선택 |
| 2 🔍 Diff | 변경률·변경 섹션·unified diff 확인 |
| 3 🧠 Analysis | AI가 분류한 기술 변화 중 발명 후보 선택 |
| 4 💡 Invention | 과제/수단/효과 구조화 + KIPRIS 검색어·IPC 코드 생성 |
| 5 🇰🇷 PriorArt | KIPRIS 검색 결과, 유사도·중복/차별점, 종합 위험도 |
| 6 📋 Report | 선행기술 조사 결과가 포함된 신고서 초안 편집·다운로드 |

## 데모 시나리오

1. 데모 저장소에 `tests/fixtures/sample_v1.md`를 커밋한 뒤, `sample_v2.md` 내용으로 수정해 두 번째 커밋을 만듭니다.
2. 1 🔗 Source에서 저장소를 연결하고 해당 파일의 커밋 2개를 선택 → "가져와서 비교 시작".
3. 3 🧠 Analysis에서 `algorithm` 유형의 변화(옵티마이저 교체 + 코사인 어닐링)를 선택 → 발명 포인트 도출.
4. 5 🇰🇷 PriorArt에서 KIPRIS 검색 → 유사도 0.7 내외의 선행문헌과 차별점 확인.
5. 6 📋 Report에서 신고서 초안을 확인하고 `.md`로 다운로드.

## 테스트

```bash
pytest tests -q                    # 전체 (외부 API·LLM 호출 없음)
pytest tests/test_kipris.py -v     # KIPRIS XML 파싱·캐시·오프라인 모드
pytest tests/test_sources.py -v    # GitHub/Drive 커넥터 (API 모킹)
pytest tests/test_pipeline.py -v   # 수집→신고서 전체 파이프라인
pytest tests/test_pages.py -v      # Streamlit 페이지 스모크
```

## 구조

```
app.py                  Streamlit 엔트리포인트 (프로젝트 선택·진행 현황)
ui_state.py             세션 상태 및 에러 표시 헬퍼
pages/                  6개 페이지 (Source → Diff → Analysis → Invention → PriorArt → Report)
sources/                GitHubConnector, GDriveConnector (SourceConnector 추상화)
patent/                 KiprisClient, 특허 데이터 모델
core/                   parser, differ, analyzer, inventor, searcher, prior_art, reporter, pipeline
llm/                    LLMClient(캐싱·재시도), PromptManager(5개 프롬프트)
db/                     SQLite 스키마·모델·CRUD
templates/              발명신고서 양식
tests/                  단위·파이프라인·페이지 테스트 + fixtures
```

설계 문서: [docs/implementation_plan.md](docs/implementation_plan.md) (범위·아키텍처·데이터모델·태스크),
[docs/implementation_detail.md](docs/implementation_detail.md) (API 스키마·프롬프트 전략·예외·비용·테스트)

## 참고

- 생성되는 발명신고서는 **AI 초안**이며, 선행기술 조사 결과는 KIPRIS 키워드 검색 기반입니다. 정식 선행기술조사나 변리사 검토를 대체하지 않습니다.
- `data/` 디렉터리(로컬 DB, 캐시, 인증 토큰)와 `.env`는 `.gitignore` 대상입니다.
