"""앱 전역 설정 — .env 로드 및 상수 정의."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ─── 경로 ──────────────────────────────────────────────
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "patent_agent.db"
FETCH_CACHE_DIR = DATA_DIR / "fetched"
CREDENTIALS_DIR = DATA_DIR / "credentials"
TEMPLATE_DIR = BASE_DIR / "templates"
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"

# ─── LLM ───────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_PRIMARY = os.getenv("OPENAI_MODEL_PRIMARY", "gpt-4o")
MODEL_SECONDARY = os.getenv("OPENAI_MODEL_SECONDARY", "gpt-4o-mini")
LLM_MAX_RETRIES = 3
LLM_TIMEOUT = 60

# ─── GitHub ────────────────────────────────────────────
GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_DEFAULT_REPO = os.getenv("GITHUB_DEFAULT_REPO", "")

# ─── Google Drive ──────────────────────────────────────
GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# API 키 모드: 링크 공개된 파일만 접근 가능 (폴더 탐색·리비전 조회는 불가)
GDRIVE_API_KEY = os.getenv("GDRIVE_API_KEY", "")
GDRIVE_CREDENTIALS_PATH = BASE_DIR / os.getenv(
    "GDRIVE_CREDENTIALS_PATH", "data/credentials/service_account.json"
)
GDRIVE_TOKEN_PATH = BASE_DIR / os.getenv(
    "GDRIVE_TOKEN_PATH", "data/credentials/token.json"
)
GDRIVE_DEFAULT_FOLDER_ID = os.getenv("GDRIVE_DEFAULT_FOLDER_ID", "")

# ─── KIPRIS ────────────────────────────────────────────
# NOTE: 서비스명/오퍼레이션명은 KIPRIS Plus 명세서 기준으로 확정할 것.
#       응답 필드 매핑은 KiprisClient._normalize_item() 한 곳에만 둔다.
# 실측 확인 (2026-09): 서비스 경로는 patUtiModInfoSearchSevice — "Utili"가 아니라 "Uti"
KIPRIS_API_BASE = "https://plus.kipris.or.kr/kipo-api/kipi"
KIPRIS_SERVICE = "patUtiModInfoSearchSevice"
KIPRIS_SERVICE_KEY = os.getenv("KIPRIS_SERVICE_KEY", "")
KIPRIS_MAX_RESULTS = _int(os.getenv("KIPRIS_MAX_RESULTS"), 10)
KIPRIS_OFFLINE = _bool(os.getenv("KIPRIS_OFFLINE"), False)
KIPRIS_TIMEOUT = 10
KIPRIS_MAX_RETRIES = 3
# 발급 키의 총 호출 한도 — 사이드바 경고 기준으로만 사용한다
KIPRIS_CALL_BUDGET = _int(os.getenv("KIPRIS_CALL_BUDGET"), 1000)
# 실측 확인: khome/search/detail.do 는 404, kpat 서지 프레임이 정상 응답
KIPRIS_DETAIL_URL = "http://kpat.kipris.or.kr/kpat/biblioa.do?method=biblioFrame&applno={app_no}"

# ─── 공통 ──────────────────────────────────────────────
SUPPORTED_EXT = {".md", ".txt", ".pdf", ".pptx", ".docx"}
SIGNIFICANCE_THRESHOLD = 0.5
SIMILARITY_HIGH = 0.8
SIMILARITY_MEDIUM = 0.5


def ensure_dirs() -> None:
    """런타임 디렉터리 생성 (gitignore 대상)."""
    for path in (DATA_DIR, FETCH_CACHE_DIR, CREDENTIALS_DIR):
        path.mkdir(parents=True, exist_ok=True)
