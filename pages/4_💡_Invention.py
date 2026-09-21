"""Page 4 — 발명 포인트 구조화 + 검색어 생성."""
import streamlit as st

from exceptions import PatentAgentError
from ui_state import init_state, pipeline, reset_from, show_error

st.set_page_config(page_title="발명 포인트", page_icon="💡", layout="wide")
init_state()

st.title("💡 발명 포인트")

if not st.session_state.get("inventions"):
    st.warning("먼저 기술 변화 분석 페이지에서 발명 포인트를 도출해주세요.")
    st.page_link("pages/3_🧠_Analysis.py", label="분석 페이지로 이동", icon="🧠")
    st.stop()

points = st.session_state.inventions
titles = [p.title or "(제목 없음)" for p in points]
index = st.selectbox("발명 후보 선택", range(len(points)), format_func=lambda i: titles[i])
point = points[index]

st.subheader(point.title)
st.write(point.summary)
st.caption(f"신뢰도: {point.confidence_score:.2f} · 근거 변화 {len(point.source_change_ids)}건")

if st.button("🔧 과제/수단/효과 구조화 + 검색어 생성", type="primary"):
    try:
        orchestrator = pipeline()
        with st.spinner("발명을 특허 명세서 구조로 정리하는 중입니다..."):
            structure = orchestrator.structure_invention(point)
        with st.spinner("KIPRIS 검색어를 생성하는 중입니다..."):
            queries = orchestrator.generate_queries(structure)
        reset_from("structure")
        st.session_state.invention_point = point
        st.session_state.structure = structure
        st.session_state.queries = queries
        st.session_state.prior_art_query = queries.primary_kr
        st.success("구조화가 완료되었습니다.")
    except PatentAgentError as exc:
        show_error(exc)

structure = st.session_state.get("structure")
if structure and structure.invention_id == point.id:
    st.divider()
    st.caption(f"기술 분야: {structure.technical_field}")

    with st.expander("🎯 기술적 과제 (Problem)", expanded=True):
        st.write(structure.problem)
    with st.expander("🔧 해결 수단 (Solution Means)", expanded=True):
        st.write(structure.solution_means)
    with st.expander("✨ 기대 효과 (Effect)", expanded=True):
        st.write(structure.effect)
    with st.expander("📚 배경 기술"):
        st.write(structure.background_art or "-")

    patentability = structure.patentability
    st.subheader("특허성 추정 (사전 지식 기반)")
    cols = st.columns(3)
    for column, label, level, reason in (
        (cols[0], "신규성", patentability.novelty, patentability.novelty_reasoning),
        (cols[1], "진보성", patentability.inventive_step, patentability.inventive_step_reasoning),
        (
            cols[2],
            "산업상 이용가능성",
            patentability.industrial_applicability,
            patentability.industrial_applicability_reasoning,
        ),
    ):
        column.metric(label, level or "-")
        if reason:
            column.caption(reason)
    st.caption("※ 실제 신규성 판단은 다음 단계의 KIPRIS 검색 결과를 우선합니다.")

    queries = st.session_state.get("queries")
    if queries:
        st.subheader("검색어")
        st.write(f"**한국어 (KIPRIS 조회용)**: {queries.primary_kr}")
        st.write(f"**English (참고용)**: {queries.primary_en or '-'}")
        if queries.secondary_kr:
            st.write("**보조 검색어**: " + ", ".join(queries.secondary_kr))
        if queries.boolean_query:
            st.code(queries.boolean_query, language="text")
        if queries.ipc_codes:
            st.write("**IPC 코드**")
            st.table(
                [{"코드": c.code, "설명": c.description} for c in queries.ipc_codes]
            )

        st.page_link("pages/5_🇰🇷_PriorArt.py", label="KIPRIS 선행기술 검색", icon="🇰🇷")
