"""Page 2 — Diff 뷰어."""
import streamlit as st

from core.differ import DiffEngine
from exceptions import PatentAgentError
from ui_state import init_state, pipeline, reset_from, show_error

st.set_page_config(page_title="Diff", page_icon="🔍", layout="wide")
init_state()

st.title("🔍 Diff 뷰어")

if not st.session_state.get("diff"):
    st.warning("먼저 소스 연동 페이지에서 문서를 가져와주세요.")
    st.page_link("pages/1_🔗_Source.py", label="소스 연동으로 이동", icon="🔗")
    st.stop()

diff = st.session_state.diff
doc_old, doc_new = st.session_state.documents

col1, col2, col3, col4 = st.columns(4)
col1.metric("변경률", f"{diff.change_ratio:.1%}")
col2.metric("변경 섹션", f"{len(diff.changed_sections)} / {diff.total_sections}")
col3.metric("추가 라인", diff.summary.added_lines)
col4.metric("삭제 라인", diff.summary.removed_lines)

with st.expander("📌 비교 대상", expanded=True):
    left, right = st.columns(2)
    for column, doc, label in ((left, doc_old, "이전 버전"), (right, doc_new, "변경 버전")):
        source = doc.source
        column.markdown(f"**{label}** — `{doc.filename}`")
        if source:
            column.caption(f"{source.source_type} · {source.source_ref[:12]}")
            if source.source_url:
                column.markdown(f"[소스 보기]({source.source_url})")
        column.caption(f"{doc.char_count:,}자 · {len(doc.sections)}개 섹션")

st.subheader("변경된 섹션")
for section in diff.changed_sections:
    icon = {"added": "🟢", "removed": "🔴", "modified": "🟡"}.get(section.change_type, "⚪")
    with st.expander(f"{icon} {section.heading or f'섹션 #{section.section_index}'} ({section.change_type})"):
        left, right = st.columns(2)
        left.markdown("**이전**")
        left.text(section.old_content[:2000] or "(없음)")
        right.markdown("**변경**")
        right.text(section.new_content[:2000] or "(없음)")

st.subheader("Unified Diff")
st.markdown(DiffEngine().format_diff_html(diff.diff_text), unsafe_allow_html=True)

st.divider()
if st.button("🧠 기술 변화 분석 실행", type="primary"):
    try:
        with st.spinner("AI가 기술 변화를 분석 중입니다..."):
            changes = pipeline().analyze_changes(diff)
        reset_from("tech_changes")
        st.session_state.tech_changes = changes
        st.success(f"유의미한 기술 변화 {len(changes)}건을 찾았습니다.")
        st.page_link("pages/3_🧠_Analysis.py", label="분석 결과 보기", icon="🧠")
    except PatentAgentError as exc:
        show_error(exc)
