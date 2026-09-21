import base64
import json

import pytest

from exceptions import SourceError
from sources.github_connector import GitHubConnector


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None, content=b""):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("acme-lab/model-compression", ("acme-lab", "model-compression")),
        ("https://github.com/acme-lab/model-compression", ("acme-lab", "model-compression")),
        ("https://github.com/acme-lab/model-compression.git", ("acme-lab", "model-compression")),
    ],
)
def test_parse_repo_url_accepts_both_forms(value, expected):
    assert GitHubConnector._parse_repo_url(value) == expected


def test_parse_repo_url_rejects_garbage():
    with pytest.raises(SourceError) as exc:
        GitHubConnector._parse_repo_url("not a repo")
    assert exc.value.error_code == "E0003"


def test_list_commits_maps_revisions(monkeypatch):
    connector = GitHubConnector(token="ghp_dummy")
    connector.owner, connector.repo = "acme-lab", "model-compression"
    payload = [
        {
            "sha": "a" * 40,
            "commit": {
                "message": "feat: AdamW 도입\n\n본문",
                "author": {"name": "hyeonjin", "date": "2026-09-19T11:20:00Z"},
            },
        }
    ]
    monkeypatch.setattr(connector, "_get", lambda *a, **k: payload)

    revisions = connector.list_commits("docs/report.md")
    assert revisions[0].ref == "a" * 40
    assert revisions[0].label == "feat: AdamW 도입"  # 첫 줄만
    assert revisions[0].author == "hyeonjin"
    assert "blob" in revisions[0].url


def test_list_files_filters_supported_extensions(monkeypatch):
    connector = GitHubConnector(token="ghp_dummy")
    connector.owner, connector.repo = "acme-lab", "repo"
    tree = {
        "tree": [
            {"path": "docs/report.md", "type": "blob"},
            {"path": "src/main.py", "type": "blob"},
            {"path": "slides/deck.pptx", "type": "blob"},
            {"path": "docs", "type": "tree"},
        ]
    }
    monkeypatch.setattr(connector, "_get", lambda *a, **k: tree)

    assert connector.list_files() == ["docs/report.md", "slides/deck.pptx"]


def test_fetch_content_decodes_base64_and_caches(monkeypatch):
    connector = GitHubConnector(token="ghp_dummy")
    connector.owner, connector.repo = "acme-lab", "repo"
    body = "# 보고서".encode("utf-8")
    payload = {"encoding": "base64", "content": base64.b64encode(body).decode()}
    calls = []

    def fake_get(path, params=None):
        calls.append(path)
        return payload

    monkeypatch.setattr(connector, "_get", fake_get)

    assert connector.fetch_content("docs/report.md", "sha123456789") == body
    assert connector.fetch_content("docs/report.md", "sha123456789") == body
    assert len(calls) == 1  # 두 번째는 로컬 캐시


def test_authenticate_without_token_raises_e0001():
    with pytest.raises(SourceError) as exc:
        GitHubConnector(token="").authenticate()
    assert exc.value.error_code == "E0001"


@pytest.mark.parametrize(
    "status,headers,code",
    [
        (401, {}, "E0002"),
        (404, {}, "E0003"),
        (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"}, "E0004"),
        (409, {}, "E0003"),  # 커밋이 없는 빈 저장소
    ],
)
def test_http_errors_map_to_source_errors(monkeypatch, status, headers, code):
    connector = GitHubConnector(token="ghp_dummy")
    monkeypatch.setattr(
        connector.session, "get", lambda *a, **k: FakeResponse(status_code=status, headers=headers)
    )
    with pytest.raises(SourceError) as exc:
        connector._get("/repos/x/y")
    assert exc.value.error_code == code


def test_gdrive_export_map_marks_native_docs():
    from sources.gdrive_connector import _EXPORT_MAP

    assert "application/vnd.google-apps.presentation" in _EXPORT_MAP
    assert _EXPORT_MAP["application/vnd.google-apps.document"][0] == "text/plain"
