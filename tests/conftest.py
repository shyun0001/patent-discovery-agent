"""테스트 공통 픽스처 — DB는 임시 파일로 격리한다."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"

__all__ = ["ROOT", "FIXTURES", "FakeLLM"]


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """모든 테스트가 자신만의 SQLite 파일을 쓰도록 강제한다."""
    from config import settings
    from db import repository

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "FETCH_CACHE_DIR", tmp_path / "fetched")
    monkeypatch.setattr(settings, "CREDENTIALS_DIR", tmp_path / "credentials")
    monkeypatch.setattr(repository, "_initialized", False)
    yield db_path


@pytest.fixture
def sample_docs():
    from core.parser import DocumentParser

    parser = DocumentParser()
    old = parser.parse((FIXTURES / "sample_v1.md").read_bytes(), "sample_v1.md")
    new = parser.parse((FIXTURES / "sample_v2.md").read_bytes(), "sample_v2.md")
    return old, new


class FakeLLM:
    """LLMClient 대역 — 프롬프트 내용으로 태스크를 구분해 고정 응답을 돌려준다."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.calls = []
        self.last_call_cached = False

    def call_structured(self, prompt, model=None, temperature=0.1):
        self.calls.append(prompt)
        for key, value in self.responses.items():
            if key in prompt:
                return value
        return {}

    text_response = ""

    def call(self, prompt, model=None, temperature=0.1):
        self.calls.append(prompt)
        return self.text_response
