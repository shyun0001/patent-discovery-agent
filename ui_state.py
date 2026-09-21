"""Streamlit 세션 상태 헬퍼 — 페이지 간 파이프라인 상태를 공유한다."""
from __future__ import annotations

import streamlit as st

from core.pipeline import PipelineOrchestrator

# 단계 순서 — 앞 단계가 바뀌면 뒤 단계 결과는 무효화한다.
STAGES = [
    "source",
    "documents",
    "diff",
    "tech_changes",
    "selected_changes",
    "inventions",
    "structure",
    "queries",
    "prior_art",
    "report",
]

_DEFAULTS = {
    "project_id": "",
    "project_name": "",
    "connector": None,
    "connection_id": "",
    "source": None,
    "documents": None,
    "diff": None,
    "tech_changes": None,
    "selected_changes": None,
    "inventions": None,
    "invention_point": None,
    "structure": None,
    "queries": None,
    "prior_art": None,
    "report": None,
    "github_rate_limit": None,
    "github_files": None,
    "github_revisions": None,
    "gdrive_files": None,
    "gdrive_revisions": None,
    "prior_art_query": "",
}


def init_state() -> None:
    for key, value in _DEFAULTS.items():
        st.session_state.setdefault(key, value)


def pipeline() -> PipelineOrchestrator:
    """PipelineOrchestrator는 세션당 1개만 만든다."""
    if "pipeline" not in st.session_state or st.session_state.pipeline is None:
        st.session_state.pipeline = PipelineOrchestrator()
    return st.session_state.pipeline


def reset_from(stage: str) -> None:
    """해당 단계 이후의 결과를 모두 비운다."""
    if stage not in STAGES:
        return
    for key in STAGES[STAGES.index(stage) :]:
        st.session_state[key] = None
    st.session_state.invention_point = None
    st.session_state.report = None


def require(stage: str, message: str) -> bool:
    """선행 단계가 없으면 안내 후 False를 돌려준다."""
    if not st.session_state.get(stage):
        st.warning(message)
        st.page_link("app.py", label="홈으로 이동", icon="🏠")
        return False
    return True


def project_id() -> str:
    return st.session_state.get("project_id") or ""


def show_error(exc: Exception) -> None:
    """예외 코드별 안내 — implementation_detail.md §6.4 패턴."""
    from exceptions import (
        AnalysisError,
        DiffError,
        DocumentParseError,
        KiprisError,
        LLMError,
        PatentAgentError,
        SourceError,
    )

    if isinstance(exc, SourceError):
        if exc.error_code in ("E0001", "E0002"):
            st.error(f"🔑 {exc.message}")
        elif exc.error_code == "E0004":
            st.warning(f"🚦 {exc.message}")
        else:
            st.error(f"🔗 {exc.message}")
    elif isinstance(exc, KiprisError):
        if exc.error_code == "E6005":
            st.info(f"🔍 {exc.message}")
        elif exc.error_code in ("E6001", "E6003"):
            st.warning(f"🇰🇷 {exc.message}")
        else:
            st.error(f"🇰🇷 {exc.message}")
    elif isinstance(exc, DocumentParseError):
        st.error(f"📄 {exc.message}")
    elif isinstance(exc, DiffError):
        st.warning(f"🔍 {exc.message}")
    elif isinstance(exc, LLMError):
        if exc.error_code == "E3001":
            st.error("🤖 OPENAI_API_KEY가 설정되지 않았습니다. .env를 확인해주세요.")
        elif exc.error_code == "E3004":
            st.warning("⏳ Rate Limit — 잠시 후 다시 시도해주세요.")
        else:
            st.error(f"🤖 {exc.message}")
    elif isinstance(exc, AnalysisError):
        st.warning(f"💡 {exc.message}")
    elif isinstance(exc, PatentAgentError):
        st.error(f"⚠️ 오류가 발생했습니다: {exc.message}")
    else:
        st.error(f"⚠️ 예기치 못한 오류: {exc}")
