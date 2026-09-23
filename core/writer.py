"""DisclosureWriter — 발명신고서 본문을 LLM이 직접 작성한다.

프롬프트(llm/disclosure_prompt.py)의 [입력자료] 4개 항목을 실제 데이터로 채운다.
근거 추적성이 프롬프트의 핵심 요구사항이므로, 파일 경로·커밋 SHA·출원번호 같은
확인 가능한 식별정보를 함께 전달하여 LLM이 근거 위치를 지어내지 않게 한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import settings
from db.models import DiffResult, Document, InventionStructure, SearchQueries
from exceptions import LLMError
from llm.client import LLMClient
from llm.disclosure_prompt import DISCLOSURE_REPORT_PROMPT
from patent.schemas import PriorArtSummary

_SECTION_CHAR_LIMIT = 1800
_ABSTRACT_LIMIT = 600


@dataclass
class DisclosureDraft:
    markdown: str
    model: str = ""
    cached: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.markdown.strip()


class DisclosureWriter:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or LLMClient()

    def write(
        self,
        invention: InventionStructure,
        queries: SearchQueries | None = None,
        prior_art: PriorArtSummary | None = None,
        documents: list[Document] | None = None,
        diff: DiffResult | None = None,
        extra_instruction: str = "",
    ) -> DisclosureDraft:
        prompt = DISCLOSURE_REPORT_PROMPT.format(
            invention_title=invention.title or "(명칭 미정)",
            research_material=self._research_material(invention, diff),
            source_identifiers=self._source_identifiers(documents, diff),
            prior_art_result=self._prior_art_result(prior_art, queries),
            extra_instruction=extra_instruction.strip() or "없음",
        )
        model = settings.MODEL_REPORT
        markdown = self.llm.call(prompt, model=model, temperature=0.2)
        if not markdown.strip():
            raise LLMError("발명신고서 본문이 비어 있습니다.", "E3003")
        return DisclosureDraft(
            markdown=markdown.strip(), model=model, cached=self.llm.last_call_cached
        )

    # ─── 입력자료 구성 ─────────────────────────────────
    @staticmethod
    def _evidence_labels(
        documents: list[Document] | None, diff: DiffResult | None
    ) -> list[tuple[str, str]]:
        """근거 식별자 목록. LLM이 이 라벨만 인용하도록 해 위조를 막는다."""
        labels: list[tuple[str, str]] = []
        path = ""
        ref_old = ref_new = ""
        for document in documents or []:
            source = document.source
            if not source:
                continue
            path = source.source_path or document.filename
            if document.version == 1:
                ref_old = (source.source_ref or "")[:12]
            else:
                ref_new = (source.source_ref or "")[:12]

        for index, section in enumerate(diff.changed_sections if diff else [], start=1):
            heading = section.heading or f"섹션 #{section.section_index}"
            where = f"`{path}` 문서구간 \"{heading}\"" if path else f'문서구간 "{heading}"'
            if section.change_type == "added" and ref_new:
                where += f", 커밋 `{ref_new}`에서 추가"
            elif ref_old and ref_new:
                where += f", 커밋 `{ref_old}` → `{ref_new}` 변경"
            labels.append((f"E{index}", where))
        return labels

    def _research_material(self, invention: InventionStructure, diff: DiffResult | None) -> str:
        """발명후보 정보 + 실제 연구자료의 변경 내용 (근거 식별자 포함)."""
        blocks = [
            "## 발명후보 정보 (버전 비교로 도출됨)",
            f"- 기술분야: {invention.technical_field or '미확인'}",
            f"- 요약: {invention.summary or '미확인'}",
            f"- 배경기술: {invention.background_art or '미확인'}",
            f"- 기술적 과제: {invention.problem or '미확인'}",
            f"- 해결수단: {invention.solution_means or '미확인'}",
            f"- 효과: {invention.effect or '미확인'}",
        ]

        if diff and diff.changed_sections:
            blocks.append(
                f"\n## 연구자료 변경 내용 (변경률 {diff.change_ratio:.1%}, "
                f"변경 섹션 {len(diff.changed_sections)}개)"
            )
            for index, section in enumerate(diff.changed_sections, start=1):
                heading = section.heading or f"섹션 #{section.section_index}"
                blocks.append(f"\n### [E{index}] {heading} ({section.change_type})")
                if section.new_content:
                    blocks.append("[변경 후 원문]")
                    blocks.append(section.new_content[:_SECTION_CHAR_LIMIT])
                if section.old_content:
                    blocks.append("[변경 전 원문]")
                    blocks.append(section.old_content[:_SECTION_CHAR_LIMIT])
        return "\n".join(blocks)

    def _source_identifiers(
        self, documents: list[Document] | None, diff: DiffResult | None
    ) -> str:
        """근거로 인용할 수 있는 확인 가능한 위치만 제공한다."""
        lines = []
        for document in documents or []:
            source = document.source
            label = "변경 전 버전" if document.version == 1 else "변경 후 버전"
            if source:
                lines.append(
                    f"- {label}: 파일 `{source.source_path}`, "
                    f"{source.source_type} 리비전 `{(source.source_ref or '')[:12]}`"
                    + (f", 원문 링크 {source.source_url}" if source.source_url else "")
                )
            else:
                lines.append(f"- {label}: 파일 `{document.filename}`")

        labels = self._evidence_labels(documents, diff)
        if labels:
            lines.append("")
            lines.append("근거 식별자 (연구자료 각 구간에 부여된 번호):")
            for label, where in labels:
                lines.append(f"- [{label}] {where}")

        if not lines:
            return "제공된 식별정보 없음 (근거 위치를 알 수 없으면 '근거 위치 미확인'으로 표시할 것)"

        lines.append("")
        lines.append(
            "표의 '입력 근거' 열과 청구항 근거에는 위 식별자를 `[E1] 문서구간명` 형식으로 인용할 것. "
            "목록에 없는 파일명·페이지·커밋을 새로 만들어 인용하지 말고, "
            "해당 구성의 근거를 특정할 수 없을 때만 '근거 위치 미확인'으로 표시할 것."
        )
        return "\n".join(lines)

    @staticmethod
    def _prior_art_result(
        prior_art: PriorArtSummary | None, queries: SearchQueries | None
    ) -> str:
        if not prior_art or not prior_art.patents:
            return "선행기술 조사 미실시 또는 검색 결과 없음 (8항은 작성하지 말 것)"

        lines = [
            f"- 조사 DB: KIPRIS 국내 특허/실용신안"
            + (" (샘플 데이터)" if prior_art.is_sample else ""),
            f"- 사용 검색어: {', '.join(prior_art.used_queries) or '미기록'}",
            f"- 검색 건수: {prior_art.total_found}건 중 상위 {prior_art.assessed_count}건 분석",
            f"- 최고 유사도: {prior_art.max_similarity:.2f} (종합 위험도 {prior_art.overall_risk})",
        ]
        if queries and queries.ipc_codes:
            lines.append(
                "- 추천 IPC: " + ", ".join(code.code for code in queries.ipc_codes)
            )

        lines.append("\n### 검색된 선행문헌")
        for patent in prior_art.patents:
            assessment = prior_art.assessment_for(patent.application_number)
            lines.append(
                f"\n- 출원번호 {patent.application_number} / {patent.invention_title}"
            )
            lines.append(
                f"  - 출원인: {patent.applicant_name or '미확인'}, "
                f"출원일: {patent.application_date or '미확인'}, "
                f"상태: {patent.register_status or '미확인'}"
            )
            if patent.ipc_codes:
                lines.append(f"  - IPC: {', '.join(patent.ipc_codes)}")
            if patent.abstract:
                lines.append(f"  - 초록: {patent.abstract[:_ABSTRACT_LIMIT]}")
            if assessment:
                lines.append(
                    f"  - 유사도 {assessment.similarity_score:.2f} ({assessment.risk_level})"
                )
                if assessment.overlapping_points:
                    lines.append(f"  - 중복 우려: {assessment.overlapping_points}")
                if assessment.differentiating_points:
                    lines.append(f"  - 차별점 후보: {assessment.differentiating_points}")
        return "\n".join(lines)
