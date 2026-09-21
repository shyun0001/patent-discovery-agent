"""PriorArtAnalyzer — KIPRIS 검색(무료 API) 후 LLM으로 유사도를 평가한다 (Stage 4)."""
from __future__ import annotations

from config import settings
from db.models import InventionStructure, SearchQueries
from exceptions import KiprisError
from llm.client import LLMClient
from llm.prompts import PromptManager
from patent.kipris_client import KiprisClient
from patent.schemas import PatentDocument, PriorArtSummary, SimilarityAssessment

_ABSTRACT_LIMIT = 700


class PriorArtAnalyzer:
    def __init__(
        self,
        kipris: KiprisClient | None = None,
        llm_client: LLMClient | None = None,
        prompts: PromptManager | None = None,
    ):
        self.kipris = kipris or KiprisClient()
        self.llm = llm_client or LLMClient()
        self.prompts = prompts or PromptManager()
        self.last_used_queries: list[str] = []
        self.last_total_found = 0

    # ─── 검색 ──────────────────────────────────────────
    def search_prior_art(
        self,
        queries: SearchQueries | str,
        max_results: int | None = None,
        expand_with_secondary: bool = True,
    ) -> list[PatentDocument]:
        max_results = max_results or settings.KIPRIS_MAX_RESULTS

        if isinstance(queries, str):
            primary, secondary = queries, []
        else:
            primary, secondary = queries.primary_kr, list(queries.secondary_kr)

        used: list[str] = []
        found: list[PatentDocument] = []
        totals: list[int] = []

        if primary:
            found.extend(self.kipris.search(primary, rows=max_results))
            used.append(primary)
            totals.append(self.kipris.last_total_found)

        if expand_with_secondary and len(found) < 5:
            for query in secondary:
                found.extend(self.kipris.search(query, rows=max_results))
                used.append(query)
                totals.append(self.kipris.last_total_found)
                if len(found) >= max_results:
                    break

        results = self._dedupe_by_application_no(found)[:max_results]
        for index, item in enumerate(results, start=1):
            item.rank = index

        self.last_used_queries = used
        # 검색어별 totalCount를 더하면 중복 문헌이 이중 계산되므로 최댓값을 쓴다.
        self.last_total_found = max([*totals, len(results)])
        return results

    # ─── 평가 ──────────────────────────────────────────
    def assess_similarity(
        self, invention: InventionStructure, patents: list[PatentDocument]
    ) -> list[SimilarityAssessment]:
        if not patents:
            return []

        payload = {
            "title": invention.title,
            "technical_field": invention.technical_field,
            "problem": invention.problem,
            "solution_means": invention.solution_means,
            "effect": invention.effect,
        }
        prompt = self.prompts.build_prior_art_similarity_prompt(
            payload, self._build_abstract_context(patents)
        )
        response = self.llm.call_structured(prompt, model=settings.MODEL_SECONDARY)

        by_number = {p.application_number: p for p in patents}
        assessments = []
        for item in response.get("assessments", []):
            if not isinstance(item, dict):
                continue
            app_no = str(item.get("application_number", "")).strip()
            patent = by_number.get(app_no)
            score = self._score(item.get("similarity_score"))
            assessments.append(
                SimilarityAssessment(
                    application_number=app_no,
                    similarity_score=score,
                    risk_level=str(item.get("risk_level") or self._risk_level(score)).upper(),
                    overlapping_points=str(item.get("overlapping_points", "")),
                    differentiating_points=str(item.get("differentiating_points", "")),
                    reasoning=str(item.get("reasoning", "")),
                    result_id=patent.result_id if patent else "",
                    invention_title=patent.invention_title if patent else "",
                )
            )
        assessments.sort(key=lambda a: a.similarity_score, reverse=True)
        self._last_overall = response.get("overall") or {}
        return assessments

    def summarize_risk(
        self, assessments: list[SimilarityAssessment], patents: list[PatentDocument] | None = None
    ) -> PriorArtSummary:
        overall = getattr(self, "_last_overall", {}) or {}
        max_similarity = max((a.similarity_score for a in assessments), default=0.0)

        differentiators = overall.get("key_differentiators") or [
            a.differentiating_points
            for a in assessments[:3]
            if a.differentiating_points and a.differentiating_points != "없음"
        ]

        summary = PriorArtSummary(
            used_queries=list(self.last_used_queries),
            total_found=self.last_total_found,
            assessed_count=len(assessments),
            max_similarity=round(max_similarity, 2),
            overall_risk=str(overall.get("overall_risk") or self._risk_level(max_similarity)).upper(),
            key_differentiators=[str(d) for d in differentiators if str(d).strip()],
            patents=list(patents or []),
            assessments=assessments,
            is_sample=any(p.is_sample for p in (patents or [])),
        )
        if not assessments:
            summary.overall_risk = "LOW"
            summary.message = "유사 선행기술이 검색되지 않았습니다. 검색어를 완화해 재검색해보세요."
        return summary

    def run(
        self,
        invention: InventionStructure,
        queries: SearchQueries | str,
        max_results: int | None = None,
    ) -> PriorArtSummary:
        """검색 → 평가 → 요약을 한 번에. KIPRIS 실패 시에도 파이프라인은 계속된다."""
        try:
            patents = self.search_prior_art(queries, max_results=max_results)
        except KiprisError as exc:
            if exc.error_code == "E6005":
                patents = []
            else:
                raise

        assessments = self.assess_similarity(invention, patents) if patents else []
        summary = self.summarize_risk(assessments, patents)
        summary.invention_id = invention.invention_id
        return summary

    # ─── 내부 ──────────────────────────────────────────
    @staticmethod
    def _dedupe_by_application_no(patents: list[PatentDocument]) -> list[PatentDocument]:
        seen: set[str] = set()
        unique = []
        for patent in patents:
            key = patent.application_number or patent.invention_title
            if key in seen:
                continue
            seen.add(key)
            unique.append(patent)
        return unique

    @staticmethod
    def _build_abstract_context(patents: list[PatentDocument]) -> list[dict]:
        """특허 전문이 아닌 초록만 전달하여 토큰을 억제한다."""
        return [
            {
                "application_number": patent.application_number,
                "invention_title": patent.invention_title,
                "application_date": patent.application_date,
                "abstract": (patent.abstract or "")[:_ABSTRACT_LIMIT],
            }
            for patent in patents
        ]

    @staticmethod
    def _risk_level(score: float) -> str:
        if score >= settings.SIMILARITY_HIGH:
            return "HIGH"
        if score >= settings.SIMILARITY_MEDIUM:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _score(value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
