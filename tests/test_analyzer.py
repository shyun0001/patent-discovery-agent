"""Mock LLM으로 분석 → 발명 → 검색어 → 선행기술 평가 경로를 검증한다."""
import pytest

from core.analyzer import TechChangeAnalyzer
from core.differ import DiffEngine
from core.inventor import InventionExtractor
from core.prior_art import PriorArtAnalyzer
from core.reporter import ReportBuilder
from core.searcher import SearchQueryGenerator
from db.models import InventionPoint
from exceptions import AnalysisError
from patent.schemas import PatentDocument
from tests.conftest import FakeLLM

TECH_RESPONSE = {
    "tech_changes": [
        {
            "change_type": "algorithm",
            "title": "옵티마이저 교체 및 학습률 스케줄링 변경",
            "description": "SGD에서 AdamW + 코사인 어닐링으로 교체",
            "original_summary": "SGD 기반 학습",
            "changed_summary": "AdamW + 코사인 어닐링",
            "significance_score": 0.85,
            "is_patentable_candidate": True,
            "reasoning": "옵티마이저 아키텍처 자체의 변경",
        },
        {
            "change_type": "bug_fix",
            "title": "오타 수정",
            "description": "문구 정리",
            "significance_score": 0.9,
            "is_patentable_candidate": False,
            "reasoning": "단순 수정",
        },
        {
            "change_type": "optimization",
            "title": "사소한 정리",
            "description": "여백 정리",
            "significance_score": 0.2,
            "is_patentable_candidate": False,
            "reasoning": "특허성 없음",
        },
    ]
}

INVENTION_RESPONSE = {
    "invention_points": [
        {
            "title": "도메인 특화 적응형 학습률 스케줄링 방법",
            "summary": "AdamW와 코사인 어닐링을 결합한 학습 방법",
            "source_change_titles": ["옵티마이저 교체 및 학습률 스케줄링 변경"],
            "confidence_score": 0.82,
        }
    ]
}

STRUCTURE_RESPONSE = {
    "technical_field": "인공지능 / 기계학습",
    "background_art": "종래에는 SGD를 사용하였다.",
    "problem": "종래의 학습 방식은 수렴이 느린 문제가 있었다.",
    "solution_means": "본 발명은 AdamW와 코사인 어닐링을 결합한 방법을 제공한다.",
    "effect": "본 발명에 의하면 수렴 속도가 40% 향상된다.",
    "patentability": {
        "novelty": {"level": "HIGH", "reasoning": "선행기술에서 미발견"},
        "inventive_step": {"level": "MEDIUM", "reasoning": "결합에 진보성"},
        "industrial_applicability": {"level": "HIGH", "reasoning": "즉시 적용 가능"},
    },
}

QUERY_RESPONSE = {
    "primary_kr": "모바일 경량모델 적응형 학습률 스케줄링",
    "primary_en": "adaptive learning rate scheduling for mobile lightweight model",
    "secondary_kr": ["AdamW 코사인 어닐링 결합 학습 방법"],
    "secondary_en": ["AdamW cosine annealing training"],
    "boolean_query": "(학습률 OR 스케줄링) AND 경량",
    "ipc_codes": [{"code": "G06N 3/08", "description": "신경망의 학습 방법"}],
}

SIMILARITY_RESPONSE = {
    "assessments": [
        {
            "application_number": "1020210012345",
            "similarity_score": 0.72,
            "risk_level": "MEDIUM",
            "overlapping_points": "학습률 스케줄링 구성이 중첩됨",
            "differentiating_points": "AdamW 결합과 모바일 특화 구성은 없음",
            "reasoning": "적용 도메인이 다름",
        }
    ],
    "overall": {
        "max_similarity": 0.72,
        "overall_risk": "MEDIUM",
        "key_differentiators": ["AdamW + 코사인 어닐링 결합", "모바일 경량 모델 도메인"],
    },
}


def _fake_llm():
    return FakeLLM(
        {
            "기술 특허 전문 분석가": TECH_RESPONSE,
            "잠재적 발명 포인트를 도출": INVENTION_RESPONSE,
            "핵심 구성요소로 구조화": STRUCTURE_RESPONSE,
            "선행기술 검색 전략": QUERY_RESPONSE,
            "선행기술 조사 전문가": SIMILARITY_RESPONSE,
        }
    )


def test_analyze_maps_and_filters(sample_docs):
    old, new = sample_docs
    diff = DiffEngine().compute_diff(old, new)
    analyzer = TechChangeAnalyzer(_fake_llm())

    changes = analyzer.analyze(diff.changed_sections, diff_id=diff.id)
    assert len(changes) == 3
    assert changes[0].significance_score == 0.9  # 점수 내림차순 정렬

    significant = analyzer.filter_significant(changes)
    titles = [c.title for c in significant]
    assert "옵티마이저 교체 및 학습률 스케줄링 변경" in titles
    assert "오타 수정" not in titles  # bug_fix 제외
    assert "사소한 정리" not in titles  # threshold 미달


def test_analyze_without_sections_raises():
    with pytest.raises(AnalysisError) as exc:
        TechChangeAnalyzer(_fake_llm()).analyze([])
    assert exc.value.error_code == "E4001"


def test_invention_extraction_and_structure():
    llm = _fake_llm()
    analyzer = TechChangeAnalyzer(llm)
    changes = analyzer.analyze(
        [
            type(
                "S",
                (),
                {
                    "heading": "## 3. 학습 알고리즘",
                    "section_index": 2,
                    "change_type": "modified",
                    "diff_text": "- SGD\n+ AdamW",
                },
            )()
        ]
    )
    extractor = InventionExtractor(llm)
    points = extractor.extract_invention_points(changes)
    assert points[0].title.startswith("도메인 특화")
    assert points[0].source_change_ids  # 제목 매칭으로 연결됨

    structure = extractor.structure_invention(points[0])
    assert structure.problem.startswith("종래")
    assert structure.patentability.novelty == "HIGH"
    assert structure.patentability.novelty_reasoning


def test_search_query_generation():
    structure = InventionExtractor(_fake_llm()).structure_invention(
        InventionPoint(title="테스트 발명", summary="요약")
    )
    queries = SearchQueryGenerator(_fake_llm()).generate_queries(structure)
    assert queries.primary_kr
    assert queries.ipc_codes[0].code == "G06N 3/08"
    assert queries.secondary_kr


def test_prior_art_assessment_and_summary():
    structure = InventionExtractor(_fake_llm()).structure_invention(
        InventionPoint(title="테스트 발명", summary="요약")
    )
    patents = [
        PatentDocument(
            application_number="1020210012345",
            invention_title="학습률 스케줄링을 이용한 신경망 학습 방법",
            abstract="학습률을 주기적으로 조절한다.",
        )
    ]
    analyzer = PriorArtAnalyzer(llm_client=_fake_llm())
    assessments = analyzer.assess_similarity(structure, patents)
    assert assessments[0].similarity_score == 0.72
    assert assessments[0].risk_level == "MEDIUM"

    summary = analyzer.summarize_risk(assessments, patents)
    assert summary.overall_risk == "MEDIUM"
    assert summary.max_similarity == 0.72
    assert len(summary.key_differentiators) == 2


def test_summary_with_no_results_is_low_risk():
    analyzer = PriorArtAnalyzer(llm_client=_fake_llm())
    summary = analyzer.summarize_risk([], [])
    assert summary.overall_risk == "LOW"
    assert "검색되지 않았습니다" in summary.message


def test_report_includes_prior_art_section():
    llm = _fake_llm()
    structure = InventionExtractor(llm).structure_invention(
        InventionPoint(title="테스트 발명", summary="요약")
    )
    queries = SearchQueryGenerator(llm).generate_queries(structure)
    patents = [
        PatentDocument(
            application_number="1020210012345",
            invention_title="학습률 스케줄링을 이용한 신경망 학습 방법",
            applicant_name="주식회사 에이아이테크",
            application_date="2021-01-28",
            abstract="학습률을 주기적으로 조절한다.",
        )
    ]
    analyzer = PriorArtAnalyzer(llm_client=llm)
    assessments = analyzer.assess_similarity(structure, patents)
    summary = analyzer.summarize_risk(assessments, patents)

    report = ReportBuilder().build_disclosure(structure, queries, summary)
    assert "## 10. 선행기술 조사 결과" in report.report_markdown
    assert "1020210012345" in report.report_markdown
    assert "G06N 3/08" in report.report_markdown
    assert report.prior_art_included is True


def test_report_without_prior_art_marks_not_performed():
    llm = _fake_llm()
    structure = InventionExtractor(llm).structure_invention(
        InventionPoint(title="테스트 발명", summary="요약")
    )
    report = ReportBuilder().build_disclosure(structure, None, None)
    assert "선행기술 조사 미실시" in report.report_markdown
    assert report.prior_art_included is False


def test_prior_art_table_escapes_pipe_in_applicant():
    """KIPRIS는 복수 출원인을 '|'로 구분해 주므로 표 셀이 깨지지 않아야 한다."""
    from core.reporter import ReportBuilder
    from patent.schemas import PatentDocument, PriorArtSummary

    summary = PriorArtSummary(
        patents=[
            PatentDocument(
                application_number="1020230171342",
                invention_title="하이브리드 V2X기반 화물운송시스템",
                applicant_name="주식회사 글로벌엔씨|주식회사 아이티텔레콤",
                application_date="2023-11-30",
            )
        ]
    )
    table = ReportBuilder().render_prior_art_table(summary)
    row = [line for line in table.splitlines() if "1020230171342" in line][0]
    assert row.count("|") == 6  # 5개 열 → 경계 파이프 6개
    assert "글로벌엔씨, 주식회사 아이티텔레콤" in row


# ─── 신고서 상세화 (구성요소·동작·실시예·청구항) ───────
DETAIL_RESPONSE = {
    "title_en": "Method and Apparatus for Adaptive Learning Rate Scheduling",
    "purpose": "본 발명의 목적은 수렴 속도를 개선하는 데 있다.",
    "components": [
        {"name": "학습률 결정부", "function": "코사인 어닐링 적용", "detail": "주기 T마다 갱신"},
        {"name": "가중치 감쇠 분리부", "function": "정규화 강화", "detail": "AdamW 방식"},
    ],
    "operation": ["(1) 초기 학습률을 설정한다.", "(2) 주기마다 학습률을 재상승시킨다."],
    "embodiment": "모바일 분류 모델에 적용해 수렴 에폭이 120에서 72로 감소하였다.",
    "claims": {
        "independent": "신경망 학습 방법에 있어서, ... 하는 것을 특징으로 하는 학습 방법.",
        "dependent": [
            "제1항에 있어서, 주기가 가변인 것을 특징으로 하는 학습 방법.",
            "제1항에 있어서, 워밍업 구간을 포함하는 것을 특징으로 하는 학습 방법.",
        ],
    },
    "applications": ["모바일 AI", "임베디드 비전"],
    "open_issues": ["장기 안정성 검증 필요"],
}


def _detail():
    from core.elaborator import DisclosureElaborator

    llm = FakeLLM({"발명신고서 수준으로 상세화": DETAIL_RESPONSE})
    structure = InventionExtractor(_fake_llm()).structure_invention(
        InventionPoint(title="테스트 발명", summary="요약")
    )
    return structure, DisclosureElaborator(llm).elaborate(structure)


def test_elaborator_maps_all_detail_fields():
    _, detail = _detail()
    assert detail.title_en.startswith("Method and Apparatus")
    assert len(detail.components) == 2
    assert detail.components[0].name == "학습률 결정부"
    assert len(detail.operation) == 2
    assert detail.claim_independent.endswith("학습 방법.")
    assert len(detail.claims_dependent) == 2
    assert detail.is_empty is False


def test_report_renders_expanded_sections():
    structure, detail = _detail()
    report = ReportBuilder().build_disclosure(structure, None, None, detail=detail)
    markdown = report.report_markdown

    for heading in (
        "## 1. 발명의 명칭",
        "### 6-1. 주요 구성요소",
        "### 7-1. 실시예",
        "## 9. 청구항 초안",
        "## 11. 특허성 자가평가",
        "## 13. 근거 자료 (추적성)",
    ):
        assert heading in markdown, heading
    assert "| 1 | 학습률 결정부 |" in markdown
    assert "**청구항 2**" in markdown
    assert "Method and Apparatus" in markdown
    # 특허성 자가평가 표가 구조화 결과를 그대로 인용하는지
    assert "HIGH" in markdown and "선행기술에서 미발견" in markdown


def test_report_degrades_without_detail():
    """상세화가 실패해도 신고서는 생성되어야 한다."""
    structure = InventionExtractor(_fake_llm()).structure_invention(
        InventionPoint(title="테스트 발명", summary="요약")
    )
    report = ReportBuilder().build_disclosure(structure, None, None, detail=None)
    assert "## 9. 청구항 초안" in report.report_markdown
    assert "_청구항 초안이 생성되지 않았습니다._" in report.report_markdown


def test_evidence_section_links_source_revisions():
    from db.models import Document, SourceRef

    structure, detail = _detail()
    documents = [
        Document(
            project_id="p", filename="report.md", file_type="md", content="x", version=1,
            source=SourceRef("github", "docs/report.md", "abc123def456", "https://github.com/x/y/blob/abc/report.md"),
        ),
        Document(
            project_id="p", filename="report.md", file_type="md", content="y", version=2,
            source=SourceRef("github", "docs/report.md", "def456abc789", "https://github.com/x/y/blob/def/report.md"),
        ),
    ]
    report = ReportBuilder().build_disclosure(structure, None, None, detail=detail, documents=documents)
    assert "**이전 버전**: `docs/report.md` @ `abc123def456`" in report.report_markdown
    assert "**변경 버전**" in report.report_markdown
    assert "소스 보기" in report.report_markdown


# ─── LLM 작성 신고서 (사용자 제공 프롬프트) ────────────
DRAFT_MARKDOWN = """# 1. 발명의 명칭

정책 버전 검증과 서비스 타입별 무선접속기술 매핑을 이용한 메시지 전송 방법

# 2. 발명의 핵심 요약

- 기술적 문제: 단일 RAT 고정 정책에서 지연과 전송 실패가 증가한다.
- 핵심 기술적 구성: 정책 버전 검증부, 서비스 타입 분류부, RAT 후보 평가부

# 6. 핵심 기술적 구성

| 번호 | 기술적 구성 | 필수/선택 | 기능 및 동작 | 다른 구성과의 관계 | 입력 근거 |
|---|---|---|---|---|---|
| 1 | 정책 수신부 | 필수 | 정책 수신 | 분류부에 전달 | `technical_report.md` 설계 구간 |

# 11. 검토용 청구항 초안

독립항: ... 하는 것을 특징으로 하는 방법. (근거: `technical_report.md`)

# 13. 작성 신뢰도 및 한계

직접 확인된 범위는 설계 구간이며, 정량 효과는 [확인 필요]다.
"""


def _structure_with_prior_art():
    llm = _fake_llm()
    structure = InventionExtractor(llm).structure_invention(
        InventionPoint(title="테스트 발명", summary="요약")
    )
    queries = SearchQueryGenerator(llm).generate_queries(structure)
    patents = [
        PatentDocument(
            application_number="1020210012345",
            invention_title="학습률 스케줄링을 이용한 신경망 학습 방법",
            applicant_name="주식회사 에이아이테크",
            application_date="2021-01-28",
            abstract="학습률을 주기적으로 조절한다.",
        )
    ]
    analyzer = PriorArtAnalyzer(llm_client=llm)
    assessments = analyzer.assess_similarity(structure, patents)
    return structure, queries, analyzer.summarize_risk(assessments, patents)


def test_writer_prompt_includes_real_inputs(sample_docs):
    """프롬프트의 [입력자료]가 실제 수집 기록으로 채워지는지 확인한다."""
    from core.differ import DiffEngine
    from core.writer import DisclosureWriter
    from db.models import SourceRef

    old, new = sample_docs
    old.source = SourceRef("github", "docs/report.md", "abc123def456789", "https://github.com/x/y")
    old.version = 1
    new.source = SourceRef("github", "docs/report.md", "def456abc789012", "https://github.com/x/z")
    new.version = 2
    diff = DiffEngine().compute_diff(old, new)
    structure, queries, prior_art = _structure_with_prior_art()

    llm = FakeLLM({})
    llm.text_response = DRAFT_MARKDOWN
    writer = DisclosureWriter(llm)
    draft = writer.write(structure, queries, prior_art, [old, new], diff, "청구항은 방법항만")

    prompt = llm.calls[-1]
    # 근거로 인용 가능한 식별정보가 프롬프트에 들어갔는가
    assert "docs/report.md" in prompt
    assert "abc123def456" in prompt and "def456abc789" in prompt
    # 실제 연구자료 변경 원문과 선행기술 데이터가 들어갔는가
    assert "AdamW" in prompt
    assert "1020210012345" in prompt and "주식회사 에이아이테크" in prompt
    # 사용자 추가 지시가 전달됐는가
    assert "청구항은 방법항만" in prompt
    # 근거 위조 방지 지시가 포함됐는가
    assert "근거 위치 미확인" in prompt
    assert draft.markdown.startswith("# 1. 발명의 명칭")


def test_writer_marks_prior_art_absent():
    from core.writer import DisclosureWriter

    structure, queries, _ = _structure_with_prior_art()
    llm = FakeLLM({})
    llm.text_response = DRAFT_MARKDOWN
    DisclosureWriter(llm).write(structure, queries, None, None, None)
    assert "선행기술 조사 미실시" in llm.calls[-1]


def test_build_from_draft_keeps_body_and_adds_evidence():
    from db.models import Document, SourceRef

    structure, queries, prior_art = _structure_with_prior_art()
    documents = [
        Document(
            project_id="p", filename="report.md", file_type="md", content="x", version=1,
            source=SourceRef("github", "docs/report.md", "abc123def456", "https://github.com/x/y"),
        )
    ]
    report = ReportBuilder().build_from_draft(
        structure, DRAFT_MARKDOWN, queries, prior_art, documents
    )
    markdown = report.report_markdown

    # LLM 본문은 그대로 유지
    assert "# 6. 핵심 기술적 구성" in markdown
    assert "# 13. 작성 신뢰도 및 한계" in markdown
    # 시스템이 보증하는 머리말·부록
    assert markdown.startswith("# 발명신고서 (Invention Disclosure)")
    assert "IDF-" in markdown
    assert "## 부록 A. 분석 근거" in markdown
    assert "`docs/report.md` @ `abc123def456`" in markdown
    assert "1020210012345" in markdown
    assert report.sections["body"] == DRAFT_MARKDOWN.strip()


def test_build_from_draft_rejects_empty_body():
    from exceptions import ReportError

    structure, _, _ = _structure_with_prior_art()
    with pytest.raises(ReportError):
        ReportBuilder().build_from_draft(structure, "   ")
