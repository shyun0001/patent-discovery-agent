"""Patent Discovery Agent — Streamlit 메인 엔트리포인트.

실행: streamlit run app.py
"""
import streamlit as st

from config import settings
from db import repository
from db.models import Project
from ui_state import init_state, pipeline, reset_from

st.set_page_config(page_title="Patent Discovery Agent", page_icon="🔬", layout="wide")

settings.ensure_dirs()
init_state()

st.title("🔬 Patent Discovery Agent")
st.caption(
    "GitHub 커밋 · Google Drive 리비전을 비교해 잠재 발명을 찾아내고, "
    "KIPRIS 선행기술 검색까지 이어 발명신고서 초안을 만듭니다."
)

# ─── 사이드바: 프로젝트 ────────────────────────────────
with st.sidebar:
    st.header("📁 프로젝트")
    projects = repository.get_projects()
    names = [p.name for p in projects]

    if projects:
        current = st.session_state.get("project_name")
        index = names.index(current) if current in names else 0
        selected = st.selectbox("프로젝트 선택", names, index=index)
        chosen = projects[names.index(selected)]
        if st.session_state.get("project_id") != chosen.id:
            st.session_state.project_id = chosen.id
            st.session_state.project_name = chosen.name
            reset_from("source")
    else:
        st.info("아직 프로젝트가 없습니다. 아래에서 생성해주세요.")

    with st.form("new_project"):
        st.subheader("새 프로젝트")
        name = st.text_input("이름", placeholder="AI 모델 경량화 연구")
        description = st.text_area("설명", placeholder="모바일용 경량 추론 모델 개발", height=70)
        if st.form_submit_button("생성", use_container_width=True) and name.strip():
            project = Project(name=name.strip(), description=description.strip())
            repository.save_project(project)
            st.session_state.project_id = project.id
            st.session_state.project_name = project.name
            reset_from("source")
            st.rerun()

    st.divider()
    st.subheader("🔌 연동 상태")
    st.write("GitHub:", "✅ 토큰 설정됨" if settings.GITHUB_TOKEN else "⚠️ 토큰 없음")
    st.write(
        "Google Drive:",
        "✅ 인증 파일 있음" if settings.GDRIVE_CREDENTIALS_PATH.exists() else "⚠️ 인증 파일 없음",
    )
    if settings.KIPRIS_SERVICE_KEY and not settings.KIPRIS_OFFLINE:
        st.write("KIPRIS: ✅ Service Key 설정됨")
    else:
        st.write("KIPRIS: 🟡 오프라인(샘플) 모드")
    st.write("OpenAI:", "✅ 키 설정됨" if settings.OPENAI_API_KEY else "⚠️ 키 없음")

    rate = st.session_state.get("github_rate_limit")
    if rate:
        st.caption(f"GitHub rate limit: {rate['remaining']}/{rate['limit']}")

    st.divider()
    st.subheader("💰 사용량")
    usage = pipeline().llm.usage
    st.caption(f"LLM 실호출 {usage['calls']}회 · 캐시 적중 {usage['cached']}회")
    st.caption(
        f"토큰 입력 {usage['prompt_tokens']:,} / 출력 {usage['completion_tokens']:,}"
    )
    kipris_calls = repository.count_kipris_calls()
    st.caption(f"KIPRIS 실호출 {kipris_calls} / {settings.KIPRIS_CALL_BUDGET}회")
    if kipris_calls > settings.KIPRIS_CALL_BUDGET * 0.8:
        st.warning("KIPRIS 호출 한도의 80%를 넘었습니다.")

# ─── 본문 ──────────────────────────────────────────────
if not st.session_state.get("project_id"):
    st.warning("좌측 사이드바에서 프로젝트를 먼저 생성하거나 선택해주세요.")
    st.stop()

st.success(f"현재 프로젝트: **{st.session_state.project_name}**")

steps = [
    ("🔗 소스 연동", "GitHub 커밋 또는 Drive 리비전 2개를 선택해 문서를 가져옵니다.", "documents"),
    ("🔍 Diff", "이전/변경 버전의 텍스트 차이를 계산합니다.", "diff"),
    ("🧠 기술 변화 분석", "AI가 기술적으로 유의미한 변화를 골라냅니다.", "tech_changes"),
    ("💡 발명 포인트", "과제·수단·효과로 구조화하고 검색어를 만듭니다.", "structure"),
    ("🇰🇷 선행기술 조사", "KIPRIS에서 유사 특허를 찾아 유사도를 평가합니다.", "prior_art"),
    ("📋 발명신고서", "선행기술 조사 결과까지 포함한 초안을 만듭니다.", "report"),
]

st.subheader("진행 상황")
columns = st.columns(len(steps))
for column, (label, help_text, key) in zip(columns, steps):
    done = bool(st.session_state.get(key))
    column.metric(label, "완료" if done else "대기", help=help_text)

st.info("좌측 페이지 목록에서 **1_🔗_Source** 부터 순서대로 진행하세요.")

with st.expander("ℹ️ 이 MVP의 입력 경로"):
    st.markdown(
        """
- 문서는 **GitHub 연동**과 **Google Drive 연동**으로만 가져옵니다. 수동 파일 업로드는 제공하지 않습니다.
- 선행기술 검색 대상은 **KIPRIS(국내 특허/실용신안)** 로 한정합니다. 영문 검색어는 신고서 참고용입니다.
- LLM 응답과 KIPRIS 응답은 SQLite에 캐싱되어, 같은 입력을 재분석할 때 추가 비용이 발생하지 않습니다.
        """
    )

if pipeline() and st.session_state.get("report"):
    st.download_button(
        "📥 발명신고서 다운로드 (.md)",
        data=st.session_state.report.report_markdown.encode("utf-8"),
        file_name=f"disclosure_{st.session_state.report.invention_id}.md",
        mime="text/markdown",
    )
