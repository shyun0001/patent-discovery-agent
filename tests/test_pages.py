"""Streamlit 페이지 스모크 테스트.

AppTest로 app.py에 진입한 뒤 각 페이지로 전환한다 (실제 멀티페이지 구조와 동일한 경로).
페이지를 단독 실행하면 내비게이션 레지스트리가 없어 st.page_link가 실패하므로 이 방식을 쓴다.
"""
import pytest
from streamlit.testing.v1 import AppTest

from core.differ import DiffEngine
from tests.conftest import ROOT

PAGES = [
    "pages/1_🔗_Source.py",
    "pages/2_🔍_Diff.py",
    "pages/3_🧠_Analysis.py",
    "pages/4_💡_Invention.py",
    "pages/5_🇰🇷_PriorArt.py",
    "pages/6_📋_Report.py",
]


def _app(**state) -> AppTest:
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    for key, value in state.items():
        app.session_state[key] = value
    return app


def _run_page(page: str, **state) -> AppTest:
    app = _app(**state)
    app.run()
    app.switch_page(page)
    return app.run()


def test_home_runs_without_exception():
    app = _app().run()
    assert not app.exception
    assert app.warning  # 프로젝트 미선택 안내


@pytest.mark.parametrize("page", PAGES)
def test_page_runs_without_exception(page):
    """선행 단계가 없어도 예외 없이 안내를 띄우고 멈춰야 한다 (page_link 해석 포함)."""
    app = _run_page(page)
    assert not app.exception, f"{page}: {[e.message for e in app.exception]}"
    assert app.warning, f"{page}: 선행 단계 안내가 표시되지 않았습니다"


def test_diff_page_renders_metrics(sample_docs):
    old, new = sample_docs
    diff = DiffEngine().compute_diff(old, new)

    app = _run_page("pages/2_🔍_Diff.py", diff=diff, documents=(old, new))
    assert not app.exception
    labels = [m.label for m in app.metric]
    assert "변경률" in labels and "변경 섹션" in labels


def test_report_page_marks_prior_art_not_performed():
    from core.reporter import ReportBuilder
    from db.models import InventionStructure

    structure = InventionStructure(
        invention_id="inv_test",
        title="테스트 발명",
        problem="종래에는 문제가 있었다.",
        solution_means="본 발명은 해결책을 제공한다.",
        effect="효과가 있다.",
    )
    report = ReportBuilder().build_disclosure(structure)

    app = _run_page("pages/6_📋_Report.py", report=report, structure=structure)
    assert not app.exception
    assert any("선행기술 조사 없이" in str(item.value) for item in app.info)
    assert app.download_button  # .md 다운로드 버튼 노출


def test_prior_art_page_shows_results(sample_docs):
    from core.prior_art import PriorArtAnalyzer
    from db.models import InventionStructure, SearchQueries
    from patent.kipris_client import KiprisClient
    from tests.conftest import FakeLLM
    from tests.test_analyzer import SIMILARITY_RESPONSE

    structure = InventionStructure(
        invention_id="inv_test",
        title="테스트 발명",
        problem="문제",
        solution_means="수단",
        effect="효과",
    )
    queries = SearchQueries(invention_id="inv_test", primary_kr="모바일 경량모델 학습률")

    analyzer = PriorArtAnalyzer(
        kipris=KiprisClient(service_key="", offline=True),
        llm_client=FakeLLM({"선행기술 조사 전문가": SIMILARITY_RESPONSE}),
    )
    summary = analyzer.run(structure, queries)

    app = _run_page(
        "pages/5_🇰🇷_PriorArt.py", structure=structure, queries=queries, prior_art=summary
    )
    assert not app.exception
    assert any("샘플 데이터" in str(c.value) for c in app.caption)
    assert app.dataframe  # 검색 결과 테이블
