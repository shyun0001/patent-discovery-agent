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
    assert "## 9. 선행기술 조사 결과" in report.report_markdown
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
