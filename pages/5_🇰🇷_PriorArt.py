"""Page 5 — KIPRIS 선행기술 조사."""
import streamlit as st

from config import settings
from exceptions import PatentAgentError
from ui_state import init_state, pipeline, reset_from, show_error
from utils.hash_utils import query_hash
from db import repository

st.set_page_config(page_title="선행기술 조사", page_icon="🇰🇷", layout="wide")
init_state()

st.title("🇰🇷 선행기술 조사 (KIPRIS)")
st.caption("검색 대상: 국내 특허/실용신안. 해외 DB(USPTO·Google Patents)는 조회하지 않습니다.")

if not st.session_state.get("queries") or not st.session_state.get("structure"):
    st.warning("먼저 발명 포인트 페이지에서 검색어를 생성해주세요.")
    st.page_link("pages/4_💡_Invention.py", label="발명 포인트로 이동", icon="💡")
    st.stop()

structure = st.session_state.structure
queries = st.session_state.queries

col_query, col_rows = st.columns([3, 1])
query_text = col_query.text_input(
    "검색어 (수정 후 재검색 가능)", value=st.session_state.get("prior_art_query") or queries.primary_kr
)
max_results = col_rows.number_input(
    "상위 N건", min_value=3, max_value=30, value=settings.KIPRIS_MAX_RESULTS
)

col_search, col_refresh = st.columns([1, 1])
run_search = col_search.button("🔎 KIPRIS 검색", type="primary")
force_refresh = col_refresh.button("♻️ 캐시 무시하고 재검색")

if run_search or force_refresh:
    try:
        st.session_state.prior_art_query = query_text
        if force_refresh:
            params = {
                "word": query_text,
                "numOfRows": int(max_results),
                "pageNo": 1,
                "patent": "true",
                "utility": "true",
            }
            repository.clear_kipris_cache(query_hash("getWordSearch", params))

        orchestrator = pipeline()
        with st.spinner("KIPRIS에서 선행기술을 검색 중입니다..."):
            summary = orchestrator.search_prior_art(
                structure,
                query_text if query_text != queries.primary_kr else queries,
                max_results=int(max_results),
                query_id=queries.id,
            )
        reset_from("prior_art")
        st.session_state.prior_art = summary
    except PatentAgentError as exc:
        show_error(exc)

summary = st.session_state.get("prior_art")
if summary:
    if summary.is_sample:
        st.caption("⚠️ 샘플 데이터 — KIPRIS Service Key가 없어 오프라인 모드로 동작 중입니다.")

    if not summary.patents:
        st.info(
            summary.message
            or "유사 선행기술이 발견되지 않았습니다 — 신규성 확보 가능성이 있습니다."
        )
        st.caption("검색어를 더 넓은 범위로 바꿔 다시 시도해볼 수 있습니다.")
    else:
        banner = {
            "HIGH": st.error,
            "MEDIUM": st.warning,
        }.get(summary.overall_risk, st.success)
        banner(
            f"종합 위험도 {summary.overall_risk} · 최고 유사도 {summary.max_similarity:.2f} "
            f"· 검색 {summary.total_found}건 중 상위 {summary.assessed_count}건 분석"
        )
        st.caption("사용 검색어: " + ", ".join(summary.used_queries))

        rows = []
        for patent in summary.patents:
            assessment = summary.assessment_for(patent.application_number)
            rows.append(
                {
                    "출원번호": patent.application_number,
                    "발명의 명칭": patent.invention_title,
                    "출원인": patent.applicant_name,
                    "출원일": patent.application_date,
                    "상태": patent.register_status,
                    "유사도": round(assessment.similarity_score, 2) if assessment else None,
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

        st.subheader("문헌별 상세")
        for patent in summary.patents:
            assessment = summary.assessment_for(patent.application_number)
            icon = {"HIGH": "🔴", "MEDIUM": "🟡"}.get(
                assessment.risk_level if assessment else "LOW", "🟢"
            )
            score = f"{assessment.similarity_score:.2f}" if assessment else "-"
            with st.expander(f"{icon} [{score}] {patent.invention_title} ({patent.application_number})"):
                st.markdown(f"[KIPRIS에서 보기]({patent.kipris_url})")
                st.caption(
                    f"출원인: {patent.applicant_name} · 출원일: {patent.application_date} "
                    f"· IPC: {', '.join(patent.ipc_codes) or '-'}"
                )
                st.markdown("**📄 초록**")
                st.write(patent.abstract or "-")
                if assessment:
                    st.markdown("**🔴 중복 우려 포인트**")
                    st.write(assessment.overlapping_points or "-")
                    st.markdown("**🟢 차별점**")
                    st.write(assessment.differentiating_points or "-")
                    if assessment.reasoning:
                        st.caption(f"판단 근거: {assessment.reasoning}")

        if summary.key_differentiators:
            st.subheader("본 발명의 핵심 차별점")
            for item in summary.key_differentiators:
                st.write(f"- {item}")

st.divider()
col_go, col_skip = st.columns(2)
if col_go.button("📋 발명신고서 생성", type="primary"):
    try:
        orchestrator = pipeline()
        with st.spinner("구성요소·실시예·청구항 초안을 작성하는 중입니다..."):
            detail = orchestrator.elaborate_disclosure(structure, st.session_state.get("prior_art"))
        with st.spinner("발명신고서를 조립하는 중입니다..."):
            report = orchestrator.build_report(
                structure,
                queries,
                st.session_state.get("prior_art"),
                detail=detail,
                documents=list(st.session_state.get("documents") or []),
            )
        st.session_state.disclosure_detail = detail
        st.session_state.report = report
        st.success("발명신고서 초안이 생성되었습니다.")
        st.page_link("pages/6_📋_Report.py", label="신고서 보기", icon="📋")
    except PatentAgentError as exc:
        show_error(exc)

if col_skip.button("건너뛰고 신고서 생성"):
    try:
        report = pipeline().build_report(
            structure, queries, None, documents=list(st.session_state.get("documents") or [])
        )
        st.session_state.report = report
        st.info("선행기술 조사 없이 신고서를 생성했습니다 (9항은 '미실시'로 표기).")
        st.page_link("pages/6_📋_Report.py", label="신고서 보기", icon="📋")
    except PatentAgentError as exc:
        show_error(exc)
