"""특허 검색 관련 데이터 모델."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


def _id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class PatentDocument:
    """KIPRIS 검색 결과 1건 (서지정보 + 초록)."""

    application_number: str
    invention_title: str = ""
    applicant_name: str = ""
    application_date: str = ""
    open_date: str = ""
    register_status: str = ""
    abstract: str = ""
    ipc_codes: list[str] = field(default_factory=list)
    kipris_url: str = ""
    rank: int = 0
    is_sample: bool = False
    result_id: str = field(default_factory=_id)


@dataclass
class SimilarityAssessment:
    """선행문헌 1건에 대한 LLM 유사도 평가."""

    application_number: str
    similarity_score: float = 0.0
    risk_level: str = "LOW"  # HIGH | MEDIUM | LOW
    overlapping_points: str = ""
    differentiating_points: str = ""
    reasoning: str = ""
    result_id: str = ""
    invention_title: str = ""
    id: str = field(default_factory=_id)


@dataclass
class PriorArtSummary:
    """선행기술 조사 결과 묶음 — 화면과 신고서가 함께 사용한다."""

    invention_id: str = ""
    used_queries: list[str] = field(default_factory=list)
    total_found: int = 0
    assessed_count: int = 0
    max_similarity: float = 0.0
    overall_risk: str = "LOW"
    key_differentiators: list[str] = field(default_factory=list)
    patents: list[PatentDocument] = field(default_factory=list)
    assessments: list[SimilarityAssessment] = field(default_factory=list)
    is_sample: bool = False
    message: str = ""
    id: str = field(default_factory=_id)

    def assessment_for(self, application_number: str) -> SimilarityAssessment | None:
        for item in self.assessments:
            if item.application_number == application_number:
                return item
        return None
