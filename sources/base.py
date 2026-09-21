"""SourceConnector — 문서 소스 커넥터의 공통 인터페이스.

MVP의 문서 입력 경로는 GitHub 연동과 Google Drive 연동 두 가지뿐이다.
수동 파일 업로드(file_uploader)는 구현하지 않는다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from config import settings
from utils import file_utils


@dataclass
class Revision:
    """비교 대상이 되는 한 시점 (GitHub 커밋 / Drive 리비전)."""

    ref: str
    label: str = ""
    path: str = ""
    author: str = ""
    modified_at: str = ""
    url: str = ""
    extra: dict = field(default_factory=dict)

    def display(self) -> str:
        head = f"{self.ref[:8]} · " if self.ref else ""
        date = f" ({self.modified_at[:10]})" if self.modified_at else ""
        return f"{head}{self.label}{date}"


@dataclass
class DriveFile:
    file_id: str
    name: str
    mime_type: str = ""
    modified_at: str = ""
    web_view_link: str = ""
    export_required: bool = False


class SourceConnector(ABC):
    """모든 커넥터는 리비전 목록 조회와 콘텐츠 다운로드를 제공한다."""

    source_type: str = ""

    def __init__(self):
        settings.ensure_dirs()

    @abstractmethod
    def authenticate(self) -> bool:
        ...

    @abstractmethod
    def list_targets(self) -> list:
        """분석 대상 후보 목록 (GitHub: 파일 경로 / Drive: 파일 목록)."""

    @abstractmethod
    def list_revisions(self, target: str) -> list[Revision]:
        ...

    @abstractmethod
    def fetch_content(self, target: str, ref: str) -> bytes:
        ...

    # ─── 캐시 공통 ─────────────────────────────────────
    def _cache_path(self, target: str, ref: str):
        return file_utils.cache_path(self.source_type, ref, target)

    def _read_cache(self, target: str, ref: str) -> bytes | None:
        return file_utils.read_cache(self._cache_path(target, ref))

    def _write_cache(self, target: str, ref: str, data: bytes) -> None:
        file_utils.write_cache(self._cache_path(target, ref), data)

    @staticmethod
    def is_supported(filename: str) -> bool:
        return file_utils.is_supported(filename)
