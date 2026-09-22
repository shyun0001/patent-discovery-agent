"""DisclosureElaborator — 발명신고서 상세 항목 생성 (구성요소·동작·실시예·청구항 초안).

구조화(Stage 2) 결과를 실무 발명신고서 수준으로 확장한다. LLM 1회 호출로 전체 항목을
한 번에 생성하여 비용을 억제하고, 실패하면 기본 항목만으로 신고서를 만들 수 있도록
빈 결과를 돌려준다(파이프라인을 중단시키지 않는다).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import settings
from db.models import InventionStructure
from exceptions import LLMError
from llm.client import LLMClient
from llm.prompts import PromptManager
from patent.schemas import PriorArtSummary


@dataclass
class Component:
    name: str
    function: str = ""
    detail: str = ""


@dataclass
class DisclosureDetail:
    """신고서 확장 항목. 비어 있어도 신고서는 생성된다."""

    title_en: str = ""
    purpose: str = ""
    components: list[Component] = field(default_factory=list)
    operation: list[str] = field(default_factory=list)
    embodiment: str = ""
    claim_independent: str = ""
    claims_dependent: list[str] = field(default_factory=list)
    applications: list[str] = field(default_factory=list)
    open_issues: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.components or self.claim_independent or self.purpose)


class DisclosureElaborator:
    def __init__(self, llm_client: LLMClient | None = None, prompts: PromptManager | None = None):
        self.llm = llm_client or LLMClient()
        self.prompts = prompts or PromptManager()

    def elaborate(
        self, invention: InventionStructure, prior_art: PriorArtSummary | None = None
    ) -> DisclosureDetail:
        payload = {
            "title": invention.title,
            "technical_field": invention.technical_field,
            "background_art": invention.background_art,
            "problem": invention.problem,
            "solution_means": invention.solution_means,
            "effect": invention.effect,
        }
        prompt = self.prompts.build_disclosure_detail_prompt(
            payload, self._prior_art_context(prior_art)
        )

        try:
            response = self.llm.call_structured(
                prompt, model=settings.MODEL_SECONDARY, temperature=0.3
            )
        except LLMError:
            # 상세화는 부가 항목이므로 실패해도 기본 신고서는 생성한다.
            return DisclosureDetail()

        claims = response.get("claims") or {}
        return DisclosureDetail(
            title_en=str(response.get("title_en", "")).strip(),
            purpose=str(response.get("purpose", "")).strip(),
            components=self._components(response.get("components")),
            operation=self._lines(response.get("operation")),
            embodiment=str(response.get("embodiment", "")).strip(),
            claim_independent=str(claims.get("independent", "")).strip(),
            claims_dependent=self._lines(claims.get("dependent")),
            applications=self._lines(response.get("applications")),
            open_issues=self._lines(response.get("open_issues")),
        )

    # ─── 내부 ──────────────────────────────────────────
    @staticmethod
    def _prior_art_context(prior_art: PriorArtSummary | None) -> dict:
        """차별점 서술에 필요한 최소 정보만 전달한다 (토큰 절약)."""
        if not prior_art or not prior_art.patents:
            return {"searched": False}
        return {
            "searched": True,
            "overall_risk": prior_art.overall_risk,
            "max_similarity": prior_art.max_similarity,
            "key_differentiators": prior_art.key_differentiators[:3],
            "closest": [
                {
                    "application_number": item.application_number,
                    "invention_title": item.invention_title,
                }
                for item in prior_art.patents[:3]
            ],
        }

    @staticmethod
    def _components(raw) -> list[Component]:
        components = []
        for item in raw or []:
            if isinstance(item, dict) and str(item.get("name", "")).strip():
                components.append(
                    Component(
                        name=str(item["name"]).strip(),
                        function=str(item.get("function", "")).strip(),
                        detail=str(item.get("detail", "")).strip(),
                    )
                )
            elif isinstance(item, str) and item.strip():
                components.append(Component(name=item.strip()))
        return components

    @staticmethod
    def _lines(raw) -> list[str]:
        if isinstance(raw, str):
            raw = [raw]
        return [str(item).strip() for item in (raw or []) if str(item).strip()]
