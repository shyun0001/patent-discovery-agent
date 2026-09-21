"""InventionExtractor — 기술 변화에서 발명 포인트를 도출하고 구조화한다 (Stage 2)."""
from __future__ import annotations

from config import settings
from db.models import (
    InventionPoint,
    InventionStructure,
    PatentabilityScore,
    TechChange,
)
from exceptions import AnalysisError
from llm.client import LLMClient
from llm.prompts import PromptManager


class InventionExtractor:
    def __init__(self, llm_client: LLMClient | None = None, prompts: PromptManager | None = None):
        self.llm = llm_client or LLMClient()
        self.prompts = prompts or PromptManager()

    def extract_invention_points(self, tech_changes: list[TechChange]) -> list[InventionPoint]:
        if not tech_changes:
            raise AnalysisError("발명 포인트 도출에 사용할 기술 변화가 없습니다.", "E4002")

        payload = [
            {
                "title": change.title,
                "change_type": change.change_type,
                "description": change.description,
                "original": change.original_text,
                "changed": change.changed_text,
                "significance_score": change.significance_score,
            }
            for change in tech_changes
        ]
        prompt = self.prompts.build_invention_extract_prompt(payload)
        response = self.llm.call_structured(prompt, model=settings.MODEL_PRIMARY, temperature=0.3)

        title_to_id = {change.title: change.id for change in tech_changes}
        points = []
        for item in response.get("invention_points", []):
            if not isinstance(item, dict):
                continue
            source_titles = item.get("source_change_titles") or []
            points.append(
                InventionPoint(
                    title=str(item.get("title", "")).strip(),
                    summary=str(item.get("summary", "")).strip(),
                    source_change_ids=[
                        title_to_id[t] for t in source_titles if t in title_to_id
                    ]
                    or [c.id for c in tech_changes],
                    confidence_score=self._score(item.get("confidence_score")),
                )
            )
        if not points:
            raise AnalysisError("발명 포인트를 도출하지 못했습니다.", "E4002")
        return points

    def structure_invention(self, point: InventionPoint) -> InventionStructure:
        payload = {
            "title": point.title,
            "summary": point.summary,
            "confidence_score": point.confidence_score,
        }
        prompt = self.prompts.build_invention_structure_prompt(payload)
        response = self.llm.call_structured(prompt, model=settings.MODEL_PRIMARY, temperature=0.3)

        required = ("problem", "solution_means", "effect")
        if not all(str(response.get(field, "")).strip() for field in required):
            raise AnalysisError("발명 구조화 결과에 필수 항목이 누락되었습니다.", "E4003")

        return InventionStructure(
            invention_id=point.id,
            title=point.title,
            summary=point.summary,
            technical_field=str(response.get("technical_field", "")),
            background_art=str(response.get("background_art", "")),
            problem=str(response.get("problem", "")),
            solution_means=str(response.get("solution_means", "")),
            effect=str(response.get("effect", "")),
            patentability=self._assess_patentability(response.get("patentability") or {}),
        )

    # ─── 내부 ──────────────────────────────────────────
    @staticmethod
    def _assess_patentability(raw: dict) -> PatentabilityScore:
        def pick(key: str) -> tuple[str, str]:
            value = raw.get(key)
            if isinstance(value, dict):
                return str(value.get("level", "")), str(value.get("reasoning", ""))
            return str(value or ""), ""

        novelty, novelty_reason = pick("novelty")
        step, step_reason = pick("inventive_step")
        industrial, industrial_reason = pick("industrial_applicability")
        return PatentabilityScore(
            novelty=novelty,
            novelty_reasoning=novelty_reason,
            inventive_step=step,
            inventive_step_reasoning=step_reason,
            industrial_applicability=industrial,
            industrial_applicability_reasoning=industrial_reason,
        )

    @staticmethod
    def _score(value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
