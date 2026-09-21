"""Page 3 — 기술 변화 분석 결과."""
import streamlit as st

from exceptions import PatentAgentError
from ui_state import init_state, pipeline, reset_from, show_error

st.set_page_config(page_title="기술 변화 분석", page_icon="🧠", layout="wide")
init_state()

st.title("🧠 기술 변화 분석")

if not st.session_state.get("tech_changes"):
    st.warning("먼저 Diff 페이지에서 기술 변화 분석을 실행해주세요.")
    st.page_link("pages/2_🔍_Diff.py", label="Diff 뷰어로 이동", icon="🔍")
    st.stop()

changes = st.session_state.tech_changes
st.caption(f"유의미성 점수 {0.5} 이상인 변화 {len(changes)}건 (bug_fix·refactor 제외)")

selected = []
for change in changes:
    with st.container(border=True):
        head, score_col = st.columns([4, 1])
        checked = head.checkbox(
            f"**{change.title}**", value=change.is_patentable_candidate, key=f"chk_{change.id}"
        )
        head.caption(f"유형: `{change.change_type}`")
        score_col.metric("유의미성", f"{change.significance_score:.2f}")
        st.progress(change.significance_score)
        st.write(change.description)
        if change.reasoning:
            with st.expander("판단 근거"):
                st.write(change.reasoning)
                if change.original_text or change.changed_text:
                    st.caption(f"이전: {change.original_text}")
                    st.caption(f"변경: {change.changed_text}")
        if checked:
            selected.append(change)

st.divider()
st.write(f"선택된 발명 후보: **{len(selected)}건**")

if st.button("💡 발명 포인트 도출", type="primary", disabled=not selected):
    try:
        with st.spinner("발명 포인트를 도출하는 중입니다..."):
            points = pipeline().extract_inventions(selected)
        reset_from("inventions")
        st.session_state.selected_changes = selected
        st.session_state.inventions = points
        st.success(f"발명 후보 {len(points)}건을 도출했습니다.")
        st.page_link("pages/4_💡_Invention.py", label="발명 포인트 보기", icon="💡")
    except PatentAgentError as exc:
        show_error(exc)
