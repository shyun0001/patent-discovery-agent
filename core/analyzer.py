"""TechChangeAnalyzer — 변경 섹션에서 기술적으로 유의미한 변화를 추출한다 (Stage 1)."""
from __future__ import annotations

from config import settings
from db.models import ChangedSection, TechChange
from exceptions import AnalysisError
from llm.client import LLMClient
from llm.prompts import PromptManager

NON_PATENTABLE = {"bug_fix", "refactor"}
_MAX_CHARS_PER_SECTION = 1500


class TechChangeAnalyzer:
    def __init__(self, llm_client: LLMClient | None = None, prompts: PromptManager | None = None):
        self.llm = llm_client or LLMClient()
        self.prompts = prompts or PromptManager()

    def analyze(self, sections: list[ChangedSection], diff_id: str = "") -> list[TechChange]:
        if not sections:
            raise AnalysisError("변경된 섹션이 없습니다.", "E4001")

        prompt = self.prompts.build_tech_analysis_prompt(self._build_analysis_context(sections))
        response = self.llm.call_structured(prompt, model=settings.MODEL_SECONDARY)
        changes = self._parse_llm_response(response, diff_id)
        if not changes:
            raise AnalysisError("기술적으로 유의미한 변화가 발견되지 않았습니다.", "E4001")
        return changes

    def filter_significant(
        self, changes: list[TechChange], threshold: float | None = None
    ) -> list[TechChange]:
        threshold = settings.SIGNIFICANCE_THRESHOLD if threshold is None else threshold
        return [
            change
            for change in changes
            if change.significance_score >= threshold
            and change.change_type not in NON_PATENTABLE
        ]

    # ─── 내부 ──────────────────────────────────────────
    def _build_analysis_context(self, sections: list[ChangedSection]) -> str:
        """변경된 섹션만 하나의 컨텍스트로 묶어 토큰을 절약한다."""
        blocks = []
        for section in sections:
            diff_text = section.diff_text or ""
            if len(diff_text) > _MAX_CHARS_PER_SECTION:
                diff_text = diff_text[:_MAX_CHARS_PER_SECTION] + "\n... (이하 생략)"
            blocks.append(
                f"### 섹션: {section.heading or f'#{section.section_index}'}\n"
                f"변경 유형: {section.change_type}\n"
                f"{diff_text}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _parse_llm_response(response: dict, diff_id: str) -> list[TechChange]:
        items = response.get("tech_changes") or response.get("changes") or []
        changes = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                score = float(item.get("significance_score", 0) or 0)
            except (TypeError, ValueError):
                score = 0.0
            changes.append(
                TechChange(
                    diff_id=diff_id,
                    change_type=str(item.get("change_type", "other")),
                    title=str(item.get("title", "")),
                    description=str(item.get("description", "")),
                    original_text=str(item.get("original_summary", "")),
                    changed_text=str(item.get("changed_summary", "")),
                    significance_score=max(0.0, min(1.0, score)),
                    is_patentable_candidate=bool(item.get("is_patentable_candidate", False)),
                    reasoning=str(item.get("reasoning", "")),
                )
            )
        changes.sort(key=lambda c: c.significance_score, reverse=True)
        return changes
