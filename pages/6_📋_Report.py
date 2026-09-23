"""Page 6 — 발명신고서 초안."""
import streamlit as st

from core.reporter import ReportBuilder
from exceptions import PatentAgentError
from ui_state import init_state, pipeline, show_error

st.set_page_config(page_title="발명신고서", page_icon="📋", layout="wide")
init_state()

st.title("📋 발명신고서 초안")

if not st.session_state.get("report"):
    st.warning("먼저 선행기술 조사 페이지에서 신고서를 생성해주세요.")
    st.page_link("pages/5_🇰🇷_PriorArt.py", label="선행기술 조사로 이동", icon="🇰🇷")
    st.stop()

report = st.session_state.report
structure = st.session_state.get("structure")
queries = st.session_state.get("queries")
prior_art = st.session_state.get("prior_art")

col_a, col_b, col_c = st.columns(3)
col_a.metric("문서 분량", f"{len(report.report_markdown):,}자")
col_b.metric("선행기술 포함", "예" if report.prior_art_included else "아니오")
col_c.metric("섹션 수", sum(1 for line in report.report_markdown.splitlines() if line.startswith("# ")))

if not report.prior_art_included:
    st.info("ℹ️ 선행기술 조사 없이 생성된 초안입니다 (8항 선행기술 비교는 생략됩니다).")

tab_view, tab_edit = st.tabs(["미리보기", "본문 편집"])

with tab_view:
    st.markdown(report.report_markdown)

with tab_edit:
    st.caption(
        "LLM이 작성한 본문을 직접 수정할 수 있습니다. 머리말과 부록(근거 기록)은 "
        "시스템이 자동 생성하므로 편집 대상이 아닙니다."
    )
    body = st.text_area(
        "본문 (마크다운)",
        value=report.sections.get("body", report.report_markdown),
        height=520,
        label_visibility="collapsed",
    )

    col_apply, col_regen = st.columns(2)
    if col_apply.button("✏️ 편집 내용 반영", type="primary", use_container_width=True):
        try:
            if structure:
                st.session_state.report = ReportBuilder().build_from_draft(
                    structure,
                    body,
                    queries,
                    prior_art,
                    list(st.session_state.get("documents") or []),
                )
                st.success("반영되었습니다.")
                st.rerun()
        except PatentAgentError as exc:
            show_error(exc)

    if col_regen.button("🔄 다시 작성 (LLM 재호출)", use_container_width=True):
        try:
            with st.spinner("발명신고서를 다시 작성하는 중입니다..."):
                st.session_state.report = pipeline().write_disclosure(
                    structure,
                    queries=queries,
                    prior_art=prior_art,
                    documents=list(st.session_state.get("documents") or []),
                    diff=st.session_state.get("diff"),
                    extra_instruction=st.session_state.get("report_instruction", ""),
                )
            st.success("다시 작성했습니다.")
            st.rerun()
        except PatentAgentError as exc:
            show_error(exc)

st.divider()
col_md, col_docx = st.columns(2)
col_md.download_button(
    "📥 마크다운 다운로드 (.md)",
    data=report.report_markdown.encode("utf-8"),
    file_name=f"disclosure_{report.invention_id}.md",
    mime="text/markdown",
    use_container_width=True,
)

try:
    docx_bytes = ReportBuilder().export_docx(report)
    col_docx.download_button(
        "📥 Word 다운로드 (.docx)",
        data=docx_bytes,
        file_name=f"disclosure_{report.invention_id}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
except PatentAgentError:
    col_docx.caption("python-docx 미설치 — DOCX 내보내기를 사용할 수 없습니다.")
