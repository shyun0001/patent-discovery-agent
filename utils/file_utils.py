"""파일 I/O 헬퍼 — 소스에서 가져온 파일의 로컬 캐시 관리."""
import re
from pathlib import Path

from config import settings

_UNSAFE = re.compile(r"[^\w.\-가-힣]+")


def safe_filename(name: str) -> str:
    """경로 구분자·특수문자를 제거해 캐시 파일명으로 쓸 수 있게 만든다."""
    name = name.replace("\\", "/").split("/")[-1]
    cleaned = _UNSAFE.sub("_", name).strip("_")
    return cleaned[:120] or "file"


def cache_path(source_type: str, source_ref: str, filename: str) -> Path:
    """data/fetched/{source_type}/{ref[:12]}_{filename}"""
    directory = settings.FETCH_CACHE_DIR / source_type
    directory.mkdir(parents=True, exist_ok=True)
    ref = (source_ref or "noref")[:12]
    return directory / f"{ref}_{safe_filename(filename)}"


def read_cache(path: Path) -> bytes | None:
    try:
        if path.exists() and path.stat().st_size > 0:
            return path.read_bytes()
    except OSError:
        pass
    return None


def write_cache(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError:
        # 캐시는 부가 기능이므로 실패해도 파이프라인을 막지 않는다.
        pass


def ext_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_supported(filename: str) -> bool:
    return ext_of(filename) in settings.SUPPORTED_EXT
