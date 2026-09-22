"""ReportBuilder — 발명신고서 초안 렌더링 (LLM 사용 없음)."""
from __future__ import annotations

import io
from datetime import datetime

from config import settings
from db.models import DisclosureReport, InventionStructure, SearchQueries
from exceptions import ReportError
from patent.schemas import PriorArtSummary

_NO_PRIOR_ART = "선행기술 조사 미실시"


class ReportBuilder:
    def __init__(self, template_path=None):
        self.template_path = template_path or (settings.TEMPLATE_DIR / "disclosure_template.md")

    def build_disclosure(
        self,
        invention: InventionStructure,
        queries: SearchQueries | None = None,
        prior_art: PriorArtSummary | None = None,
        inventor_name: str = "",
        inventor_affiliation: str = "",
    ) -> DisclosureReport:
        if not invention or not invention.problem:
            raise ReportError("발명 구조 정보가 비어 있습니다.", "E5002")

        queries = queries or SearchQueries(invention_id=invention.invention_id)
        sections = {
            "title": invention.title or "(제목 없음)",
            "technical_field": invention.technical_field,
            "background_art": invention.background_art,
            "problem": invention.problem,
            "solution_means": invention.solution_means,
            "effect": invention.effect,
            "summary": invention.summary,
            "query_kr": queries.primary_kr,
            "query_en": queries.primary_en,
            "ipc_codes": ", ".join(
                f"{c.code}({c.description})" if c.description else c.code for c in queries.ipc_codes
            )
            or "-",
            "inventor_name": inventor_name,
            "inventor_affiliation": inventor_affiliation,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        sections.update(self._prior_art_fields(prior_art))

        template = self._load_template()
        try:
            markdown = template.format(**sections)
        except KeyError as exc:
            raise ReportError(f"템플릿 필드가 누락되었습니다: {exc}", "E5002") from exc

        return DisclosureReport(
            invention_id=invention.invention_id,
            report_markdown=markdown,
            sections=sections,
            prior_art_included=bool(prior_art and prior_art.patents),
        )

    def render_markdown(self, report: DisclosureReport) -> str:
        return report.report_markdown

    def render_prior_art_table(self, prior_art: PriorArtSummary, limit: int = 5) -> str:
        if not prior_art or not prior_art.patents:
            return "_검색된 선행기술이 없습니다._"

        header = (
            "| 출원번호 | 발명의 명칭 | 출원인 | 출원일 | 유사도 |\n"
            "|----------|-------------|--------|--------|--------|"
        )
        rows = []
        for patent in prior_art.patents[:limit]:
            assessment = prior_art.assessment_for(patent.application_number)
            score = f"{assessment.similarity_score:.2f}" if assessment else "-"
            title = self._cell((patent.invention_title or "")[:40])
            applicant = self._cell(patent.applicant_name)
            rows.append(
                f"| {patent.application_number} | {title} | {applicant} "
                f"| {patent.application_date} | {score} |"
            )
        return header + "\n" + "\n".join(rows)

    @staticmethod
    def _cell(text: str) -> str:
        """마크다운 표 셀 값 정리. KIPRIS는 복수 출원인을 '|'로 구분해 주므로 셀이 깨진다."""
        return (text or "").replace("|", ", ").replace("\n", " ").strip()

    def export_docx(self, report: DisclosureReport) -> bytes:
        """마크다운 초안을 간단한 DOCX로 변환 (Nice-to-Have)."""
        try:
            from docx import Document as DocxDocument
        except ImportError as exc:  # pragma: no cover
            raise ReportError(f"python-docx를 불러올 수 없습니다: {exc}", "E5001") from exc

        document = DocxDocument()
        for line in report.report_markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("### "):
                document.add_heading(stripped[4:], level=3)
            elif stripped.startswith("## "):
                document.add_heading(stripped[3:], level=2)
            elif stripped.startswith("# "):
                document.add_heading(stripped[2:], level=1)
            elif stripped:
                document.add_paragraph(stripped)

        buffer = io.BytesIO()
        document.save(buffer)
        return buffer.getvalue()

    # ─── 내부 ──────────────────────────────────────────
    def _load_template(self) -> str:
        try:
            return self.template_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ReportError(f"신고서 템플릿을 불러올 수 없습니다: {exc}", "E5001") from exc

    def _prior_art_fields(self, prior_art: PriorArtSummary | None) -> dict:
        if not prior_art or not prior_art.patents:
            return {
                "searched_db": "KIPRIS (국내 특허/실용신안)",
                "used_query": _NO_PRIOR_ART,
                "total_found": 0,
                "assessed_count": 0,
                "overall_risk": _NO_PRIOR_ART,
                "max_similarity": "-",
                "prior_art_table": "_선행기술 조사를 실시하지 않았거나 검색 결과가 없습니다._",
                "differentiating_points": "-",
            }

        differentiators = prior_art.key_differentiators or [
            a.differentiating_points for a in prior_art.assessments[:3] if a.differentiating_points
        ]
        note = " (※ 샘플 데이터)" if prior_art.is_sample else ""
        return {
            "searched_db": f"KIPRIS (국내 특허/실용신안){note}",
            "used_query": ", ".join(prior_art.used_queries) or "-",
            "total_found": prior_art.total_found,
            "assessed_count": prior_art.assessed_count,
            "overall_risk": prior_art.overall_risk,
            "max_similarity": f"{prior_art.max_similarity:.2f}",
            "prior_art_table": self.render_prior_art_table(prior_art),
            "differentiating_points": "\n".join(f"- {d}" for d in differentiators) or "-",
        }
