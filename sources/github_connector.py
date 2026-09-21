"""GitHubConnector — REST API v3로 커밋/파일을 가져온다."""
from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass

import requests

from config import settings
from exceptions import SourceError
from sources.base import Revision, SourceConnector

_REPO_URL = re.compile(r"github\.com[/:]([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$")
_SLUG = re.compile(r"^([\w.\-]+)/([\w.\-]+)$")


@dataclass
class RepoInfo:
    owner: str
    repo: str
    default_branch: str = "main"
    html_url: str = ""

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


class GitHubConnector(SourceConnector):
    source_type = "github"

    def __init__(self, token: str | None = None):
        super().__init__()
        self.token = token if token is not None else settings.GITHUB_TOKEN
        self.owner = ""
        self.repo = ""
        self.default_branch = "main"
        self.session = requests.Session()
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers.update(headers)

    # ─── 인증 / 연결 ───────────────────────────────────
    def authenticate(self) -> bool:
        if not self.token:
            raise SourceError(
                "GitHub 토큰이 설정되지 않았습니다. .env의 GITHUB_TOKEN을 확인해주세요.", "E0001"
            )
        return True

    @staticmethod
    def _parse_repo_url(url_or_slug: str) -> tuple[str, str]:
        text = (url_or_slug or "").strip().rstrip("/")
        match = _REPO_URL.search(text) or _SLUG.match(text)
        if not match:
            raise SourceError(
                "저장소 형식을 인식할 수 없습니다. 'owner/repo' 또는 GitHub URL을 입력해주세요.", "E0003"
            )
        return match.group(1), match.group(2)

    def connect(self, repo_url_or_slug: str) -> RepoInfo:
        self.authenticate()
        self.owner, self.repo = self._parse_repo_url(repo_url_or_slug)
        data = self._get(f"/repos/{self.owner}/{self.repo}")
        self.default_branch = data.get("default_branch", "main")
        return RepoInfo(
            owner=self.owner,
            repo=self.repo,
            default_branch=self.default_branch,
            html_url=data.get("html_url", ""),
        )

    # ─── HTTP ──────────────────────────────────────────
    def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{settings.GITHUB_API_BASE}{path}"
        last_error = None
        for attempt in range(3):
            try:
                response = self.session.get(url, params=params, timeout=15)
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue

            if response.status_code == 200:
                return response.json()
            if response.status_code == 401:
                raise SourceError(
                    "GitHub 인증에 실패했습니다. 토큰 권한(repo 읽기)을 확인해주세요.", "E0002"
                )
            if response.status_code == 404:
                raise SourceError("해당 저장소/파일을 찾을 수 없습니다.", "E0003")
            if response.status_code == 409:
                # GitHub은 커밋이 하나도 없는 저장소에 409를 돌려준다.
                raise SourceError(
                    "저장소가 비어 있습니다. 분석할 문서를 먼저 커밋해주세요.", "E0003"
                )
            if response.status_code == 403:
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining == "0":
                    reset = response.headers.get("X-RateLimit-Reset", "")
                    raise SourceError(
                        f"GitHub API 호출 한도를 초과했습니다. (reset: {reset})", "E0004"
                    )
                raise SourceError("GitHub 접근 권한이 없습니다.", "E0002")
            if 500 <= response.status_code < 600:
                last_error = f"HTTP {response.status_code}"
                time.sleep(2**attempt)
                continue
            raise SourceError(f"GitHub 호출 실패 (HTTP {response.status_code})", "E0006")

        raise SourceError(f"GitHub 호출에 실패했습니다: {last_error}", "E0006")

    # ─── 목록 조회 ─────────────────────────────────────
    def list_targets(self, ref: str | None = None) -> list[str]:
        """분석 가능한 확장자의 파일 경로 목록."""
        ref = ref or self.default_branch
        data = self._get(
            f"/repos/{self.owner}/{self.repo}/git/trees/{ref}", {"recursive": "1"}
        )
        tree = data.get("tree", []) if isinstance(data, dict) else []
        return sorted(
            item["path"]
            for item in tree
            if item.get("type") == "blob" and self.is_supported(item.get("path", ""))
        )

    def list_files(self, ref: str | None = None) -> list[str]:
        return self.list_targets(ref)

    def list_revisions(self, target: str, per_page: int = 30) -> list[Revision]:
        """특정 파일의 커밋 목록 (최신순)."""
        commits = self._get(
            f"/repos/{self.owner}/{self.repo}/commits",
            {"path": target, "per_page": per_page},
        )
        revisions = []
        for commit in commits or []:
            sha = commit.get("sha", "")
            detail = commit.get("commit", {})
            message = (detail.get("message") or "").splitlines()[0]
            author = (detail.get("author") or {}).get("name", "")
            date = (detail.get("author") or {}).get("date", "")
            revisions.append(
                Revision(
                    ref=sha,
                    label=message,
                    path=target,
                    author=author,
                    modified_at=date,
                    url=f"https://github.com/{self.owner}/{self.repo}/blob/{sha}/{target}",
                )
            )
        return revisions

    def list_commits(self, target: str, per_page: int = 30) -> list[Revision]:
        return self.list_revisions(target, per_page)

    # ─── 다운로드 ──────────────────────────────────────
    def fetch_content(self, target: str, ref: str) -> bytes:
        cached = self._read_cache(target, ref)
        if cached is not None:
            return cached

        payload = self._get(
            f"/repos/{self.owner}/{self.repo}/contents/{target}", {"ref": ref}
        )
        data = self._decode_content(payload)
        self._write_cache(target, ref, data)
        return data

    def fetch_file(self, path: str, ref: str) -> bytes:
        return self.fetch_content(path, ref)

    def _decode_content(self, payload: dict) -> bytes:
        encoding = payload.get("encoding")
        content = payload.get("content")
        if encoding == "base64" and content:
            return base64.b64decode(content)

        # 1MB 초과 파일은 content가 비어 오므로 download_url로 재요청한다.
        download_url = payload.get("download_url")
        if download_url:
            try:
                response = self.session.get(download_url, timeout=30)
                response.raise_for_status()
                return response.content
            except requests.RequestException as exc:
                raise SourceError(f"파일 다운로드에 실패했습니다: {exc}", "E0006") from exc
        raise SourceError("파일 내용을 가져오지 못했습니다.", "E0006")

    # ─── 부가 ──────────────────────────────────────────
    def get_rate_limit(self) -> dict:
        try:
            data = self._get("/rate_limit")
            core = data.get("resources", {}).get("core", {})
            return {
                "limit": core.get("limit", 0),
                "remaining": core.get("remaining", 0),
                "reset": core.get("reset", 0),
            }
        except SourceError:
            return {"limit": 0, "remaining": 0, "reset": 0}

    def source_url(self, target: str, ref: str) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/blob/{ref}/{target}"
