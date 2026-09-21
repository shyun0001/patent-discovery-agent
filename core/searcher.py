"""SearchQueryGenerator — 발명 구조에서 KIPRIS 검색어와 IPC 코드를 생성한다 (Stage 3).

query_en은 발명신고서 참고용이며, 실제 API 조회에는 사용하지 않는다 (검색 대상: 국내 KIPRIS).
"""
from __future__ import annotations

from config import settings
from db.models import IPCCode, InventionStructure, SearchQueries
from llm.client import LLMClient
from llm.prompts import PromptManager


class SearchQueryGenerator:
    def __init__(self, llm_client: LLMClient | None = None, prompts: PromptManager | None = None):
        self.llm = llm_client or LLMClient()
        self.prompts = prompts or PromptManager()

    def generate_queries(self, invention: InventionStructure) -> SearchQueries:
        payload = {
            "title": invention.title,
            "technical_field": invention.technical_field,
            "problem": invention.problem,
            "solution_means": invention.solution_means,
            "effect": invention.effect,
        }
        prompt = self.prompts.build_search_query_prompt(payload)
        response = self.llm.call_structured(prompt, model=settings.MODEL_SECONDARY, temperature=0.3)

        queries = SearchQueries(
            invention_id=invention.invention_id,
            primary_kr=str(response.get("primary_kr", "")).strip(),
            primary_en=str(response.get("primary_en", "")).strip(),
            secondary_kr=[str(q).strip() for q in response.get("secondary_kr", []) if str(q).strip()],
            secondary_en=[str(q).strip() for q in response.get("secondary_en", []) if str(q).strip()],
            boolean_query=str(response.get("boolean_query", "")).strip(),
            ipc_codes=self._parse_ipc(response.get("ipc_codes", [])),
        )
        if not queries.primary_kr:
            queries.primary_kr = invention.title or invention.technical_field
        if not queries.boolean_query:
            queries.boolean_query = self._build_boolean_query(queries)
        return queries

    def suggest_ipc_codes(self, invention: InventionStructure) -> list[IPCCode]:
        return self.generate_queries(invention).ipc_codes

    # ─── 내부 ──────────────────────────────────────────
    @staticmethod
    def _parse_ipc(raw) -> list[IPCCode]:
        codes = []
        for item in raw or []:
            if isinstance(item, dict):
                code = str(item.get("code", "")).strip()
                description = str(item.get("description", "")).strip()
            else:
                code, description = str(item).strip(), ""
            if code:
                codes.append(IPCCode(code=code, description=description))
        return codes

    @staticmethod
    def _build_boolean_query(queries: SearchQueries) -> str:
        terms = [queries.primary_kr, *queries.secondary_kr]
        terms = [t for t in terms if t]
        return " OR ".join(f"({t})" for t in terms)
