"""E2E — 가짜 커넥터 + Mock LLM + KIPRIS 오프라인 모드로 전체 파이프라인을 돌린다."""
import pytest

from core.pipeline import PipelineOrchestrator
from db import repository
from exceptions import SourceError
from patent.kipris_client import KiprisClient
from sources.base import Revision, SourceConnector
from tests.conftest import FIXTURES, FakeLLM
from tests.test_analyzer import (
    INVENTION_RESPONSE,
    QUERY_RESPONSE,
    SIMILARITY_RESPONSE,
    STRUCTURE_RESPONSE,
    TECH_RESPONSE,
)


class FakeGitHubConnector(SourceConnector):
    """GitHub 커넥터 대역 — 커밋 2개와 파일 내용을 fixture에서 돌려준다."""

    source_type = "github"

    def __init__(self):
        super().__init__()
        self.fetch_calls = []
        self.contents = {
            "sha_v1": (FIXTURES / "sample_v1.md").read_bytes(),
            "sha_v2": (FIXTURES / "sample_v2.md").read_bytes(),
        }

    def authenticate(self) -> bool:
        return True

    def list_targets(self):
        return ["docs/research_report.md"]

    def list_revisions(self, target):
        return [
            Revision(ref="sha_v2", label="feat: AdamW 도입", path=target),
            Revision(ref="sha_v1", label="docs: 초안 작성", path=target),
        ]

    def fetch_content(self, target, ref):
        self.fetch_calls.append((target, ref))
        if ref not in self.contents:
            raise SourceError("해당 리비전을 찾을 수 없습니다.", "E0003")
        return self.contents[ref]

    def source_url(self, target, ref):
        return f"https://github.com/acme-lab/repo/blob/{ref}/{target}"


@pytest.fixture
def orchestrator():
    llm = FakeLLM(
        {
            "기술 특허 전문 분석가": TECH_RESPONSE,
            "잠재적 발명 포인트를 도출": INVENTION_RESPONSE,
            "핵심 구성요소로 구조화": STRUCTURE_RESPONSE,
            "선행기술 검색 전략": QUERY_RESPONSE,
            "선행기술 조사 전문가": SIMILARITY_RESPONSE,
        }
    )
    pipeline = PipelineOrchestrator(llm_client=llm)
    # KIPRIS는 Service Key 없이 오프라인(샘플) 모드로 동작시킨다.
    pipeline.prior_art.kipris = KiprisClient(service_key="", offline=True)
    return pipeline


OLD = {"source_path": "docs/research_report.md", "source_ref": "sha_v1", "filename": "research_report.md"}
NEW = {"source_path": "docs/research_report.md", "source_ref": "sha_v2", "filename": "research_report.md"}


def test_full_pipeline_github_to_report(orchestrator):
    connector = FakeGitHubConnector()
    result = orchestrator.run_full_pipeline(connector, OLD, NEW, project_id="proj_test")

    # 수집
    assert len(result.documents) == 2
    assert result.documents[0].source.source_ref == "sha_v1"
    assert result.documents[1].version == 2

    # Diff
    assert result.diff.change_ratio > 0
    assert result.diff.changed_sections

    # 분석 → 발명 → 검색어
    assert result.tech_changes and result.tech_changes[0].change_type == "algorithm"
    assert result.inventions[0].title.startswith("도메인 특화")
    assert result.queries[0].primary_kr

    # 선행기술 (샘플 데이터)
    prior_art = result.prior_art[0]
    assert prior_art.total_found == 37
    assert len(prior_art.patents) == 3
    assert prior_art.is_sample is True
    assert prior_art.overall_risk == "MEDIUM"

    # 신고서
    report = result.reports[0]
    assert "## 9. 선행기술 조사 결과" in report.report_markdown
    assert "1020210012345" in report.report_markdown
    assert "샘플 데이터" in report.report_markdown
    assert report.prior_art_included is True


def test_same_revision_is_reused_from_db(orchestrator):
    connector = FakeGitHubConnector()
    orchestrator.import_document(connector, OLD["source_path"], "sha_v1", "research_report.md")
    assert len(connector.fetch_calls) == 1

    # 두 번째 호출은 DB에 저장된 문서를 재사용 → API/캐시 접근 없음
    document = orchestrator.import_document(
        connector, OLD["source_path"], "sha_v1", "research_report.md"
    )
    assert len(connector.fetch_calls) == 1
    assert document.content.startswith("# 모바일 경량 모델")
    assert document.sections


def test_pipeline_persists_records(orchestrator):
    connector = FakeGitHubConnector()
    result = orchestrator.run_full_pipeline(connector, OLD, NEW, project_id="proj_test")

    stored = repository.get_documents_by_project("proj_test")
    assert len(stored) == 2

    prior_art_rows = repository.get_prior_art_results(result.queries[0].id)
    assert len(prior_art_rows) == 3
    assert prior_art_rows[0].application_number == "1020210012345"


def test_unknown_revision_raises_source_error(orchestrator):
    connector = FakeGitHubConnector()
    with pytest.raises(SourceError) as exc:
        orchestrator.import_document(connector, "docs/research_report.md", "sha_missing", "x.md")
    assert exc.value.error_code == "E0003"
