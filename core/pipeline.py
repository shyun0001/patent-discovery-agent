"""PipelineOrchestrator — 소스 수집부터 신고서까지의 서비스 레이어.

Streamlit 페이지는 이 클래스만 호출한다 (향후 FastAPI 전환 시 그대로 엔드포인트가 됨).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import settings
from core.analyzer import TechChangeAnalyzer
from core.differ import DiffEngine
from core.inventor import InventionExtractor
from core.parser import DocumentParser
from core.prior_art import PriorArtAnalyzer
from core.reporter import ReportBuilder
from core.searcher import SearchQueryGenerator
from db import repository
from db.models import (
    DiffResult,
    DisclosureReport,
    Document,
    InventionPoint,
    InventionStructure,
    SearchQueries,
    SourceRef,
    TechChange,
)
from llm.client import LLMClient
from patent.schemas import PriorArtSummary
from sources.base import SourceConnector


@dataclass
class PipelineResult:
    project_id: str = ""
    sources: list[SourceRef] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    diff: DiffResult | None = None
    tech_changes: list[TechChange] = field(default_factory=list)
    inventions: list[InventionPoint] = field(default_factory=list)
    structures: list[InventionStructure] = field(default_factory=list)
    queries: list[SearchQueries] = field(default_factory=list)
    prior_art: list[PriorArtSummary] = field(default_factory=list)
    reports: list[DisclosureReport] = field(default_factory=list)


class PipelineOrchestrator:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()
        self.parser = DocumentParser()
        self.differ = DiffEngine()
        self.analyzer = TechChangeAnalyzer(self.llm)
        self.inventor = InventionExtractor(self.llm)
        self.searcher = SearchQueryGenerator(self.llm)
        self.prior_art = PriorArtAnalyzer(llm_client=self.llm)
        self.reporter = ReportBuilder()

    # ─── A6: 문서 수집 ─────────────────────────────────
    def import_document(
        self,
        connector: SourceConnector,
        source_path: str,
        source_ref: str,
        filename: str,
        project_id: str = "",
        version: int = 1,
        connection_id: str = "",
    ) -> Document:
        """소스에서 파일을 가져와 파싱한다. 동일 리비전은 DB에서 재사용한다."""
        existing = repository.get_document_by_source(
            connector.source_type, source_path, source_ref
        )
        if existing and existing.content:
            existing.sections = self.parser.split_sections(existing.content)
            existing.version = version
            return existing

        data = connector.fetch_content(source_path, source_ref)
        source = SourceRef(
            source_type=connector.source_type,
            source_path=source_path,
            source_ref=source_ref,
            source_url=connector.source_url(source_path, source_ref),
            connection_id=connection_id,
        )
        document = self.parser.parse(
            data, filename, source=source, project_id=project_id, version=version
        )
        repository.save_document(document)
        return document

    def import_documents(
        self, connector: SourceConnector, old: dict, new: dict, project_id: str = "", connection_id: str = ""
    ) -> tuple[Document, Document]:
        doc_old = self.import_document(
            connector,
            old["source_path"],
            old["source_ref"],
            old.get("filename") or old["source_path"],
            project_id=project_id,
            version=1,
            connection_id=connection_id,
        )
        doc_new = self.import_document(
            connector,
            new["source_path"],
            new["source_ref"],
            new.get("filename") or new["source_path"],
            project_id=project_id,
            version=2,
            connection_id=connection_id,
        )
        return doc_old, doc_new

    # ─── A7: Diff ──────────────────────────────────────
    def run_diff(self, doc_old: Document, doc_new: Document) -> DiffResult:
        diff = self.differ.compute_diff(doc_old, doc_new)
        repository.save_diff_result(diff)
        return diff

    # ─── A8: 기술 변화 분석 ────────────────────────────
    def analyze_changes(self, diff: DiffResult, threshold: float | None = None) -> list[TechChange]:
        changes = self.analyzer.analyze(diff.changed_sections, diff_id=diff.id)
        for change in changes:
            repository.save_tech_change(change)
        return self.analyzer.filter_significant(changes, threshold)

    # ─── A9/A10: 발명 도출 & 구조화 ────────────────────
    def extract_inventions(self, changes: list[TechChange]) -> list[InventionPoint]:
        points = self.inventor.extract_invention_points(changes)
        for point in points:
            repository.save_invention_point(point)
        return points

    def structure_invention(self, point: InventionPoint) -> InventionStructure:
        structure = self.inventor.structure_invention(point)
        repository.save_invention_structure(structure)
        return structure

    # ─── A11: 검색어 ───────────────────────────────────
    def generate_queries(self, structure: InventionStructure) -> SearchQueries:
        queries = self.searcher.generate_queries(structure)
        repository.save_search_query(queries)
        return queries

    # ─── A12/A13: 선행기술 ─────────────────────────────
    def search_prior_art(
        self,
        structure: InventionStructure,
        queries: SearchQueries | str,
        max_results: int | None = None,
        query_id: str = "",
    ) -> PriorArtSummary:
        summary = self.prior_art.run(structure, queries, max_results=max_results)
        if summary.patents:
            repository.save_prior_art_results(
                query_id or getattr(queries, "id", ""), structure.invention_id, summary.patents
            )
        for assessment in summary.assessments:
            repository.save_similarity_assessment(assessment, structure.invention_id)
        return summary

    # ─── A14: 신고서 ───────────────────────────────────
    def build_report(
        self,
        structure: InventionStructure,
        queries: SearchQueries | None = None,
        prior_art: PriorArtSummary | None = None,
        inventor_name: str = "",
        inventor_affiliation: str = "",
    ) -> DisclosureReport:
        report = self.reporter.build_disclosure(
            structure,
            queries,
            prior_art,
            inventor_name=inventor_name,
            inventor_affiliation=inventor_affiliation,
        )
        repository.save_disclosure_report(report)
        return report

    # ─── 전체 실행 ─────────────────────────────────────
    def run_full_pipeline(
        self,
        connector: SourceConnector,
        old: dict,
        new: dict,
        project_id: str = "",
        connection_id: str = "",
    ) -> PipelineResult:
        result = PipelineResult(project_id=project_id)

        doc_old, doc_new = self.import_documents(
            connector, old, new, project_id=project_id, connection_id=connection_id
        )
        result.documents = [doc_old, doc_new]
        result.sources = [doc_old.source, doc_new.source]

        result.diff = self.run_diff(doc_old, doc_new)
        result.tech_changes = self.analyze_changes(result.diff)
        result.inventions = self.extract_inventions(result.tech_changes)

        for point in result.inventions:
            structure = self.structure_invention(point)
            queries = self.generate_queries(structure)
            prior_art = self.search_prior_art(
                structure, queries, max_results=settings.KIPRIS_MAX_RESULTS, query_id=queries.id
            )
            report = self.build_report(structure, queries, prior_art)
            result.structures.append(structure)
            result.queries.append(queries)
            result.prior_art.append(prior_art)
            result.reports.append(report)

        return result
