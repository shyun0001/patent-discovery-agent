"""Page 6 — 발명신고서 초안."""
import streamlit as st

from core.reporter import ReportBuilder
from exceptions import PatentAgentError
from ui_state import init_state, show_error

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

if report.prior_art_included:
    st.success("✅ 선행기술 조사 결과가 포함된 초안입니다.")
else:
    st.info("ℹ️ 선행기술 조사 없이 생성된 초안입니다 (9항: 미실시).")

col_name, col_affiliation = st.columns(2)
inventor_name = col_name.text_input("발명자 성명", value=report.sections.get("inventor_name", ""))
inventor_affiliation = col_affiliation.text_input(
    "소속", value=report.sections.get("inventor_affiliation", "")
)

st.subheader("섹션 편집")
edited = {}
editable = [
    ("title", "1. 발명의 명칭", 68),
    ("technical_field", "2. 기술 분야", 68),
    ("background_art", "3. 배경 기술", 120),
    ("problem", "4. 해결하고자 하는 과제", 140),
    ("solution_means", "5. 과제 해결 수단", 180),
    ("effect", "6. 발명의 효과", 140),
    ("summary", "7. 발명의 상세한 설명", 140),
]
for key, label, height in editable:
    edited[key] = st.text_area(label, value=report.sections.get(key, ""), height=height)

if st.button("🔄 편집 내용 반영", type="primary"):
    try:
        if structure:
            structure.title = edited["title"]
            structure.technical_field = edited["technical_field"]
            structure.background_art = edited["background_art"]
            structure.problem = edited["problem"]
            structure.solution_means = edited["solution_means"]
            structure.effect = edited["effect"]
            structure.summary = edited["summary"]
            report = ReportBuilder().build_disclosure(
                structure,
                queries,
                prior_art,
                inventor_name=inventor_name,
                inventor_affiliation=inventor_affiliation,
                detail=st.session_state.get("disclosure_detail"),
                documents=list(st.session_state.get("documents") or []),
            )
            st.session_state.report = report
            st.success("반영되었습니다.")
    except PatentAgentError as exc:
        show_error(exc)

st.divider()
st.subheader("미리보기")
st.markdown(report.report_markdown)

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
