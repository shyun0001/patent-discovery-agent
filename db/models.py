"""데이터 모델 — implementation_plan.md §4.1 ER 다이어그램 기준 dataclass."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Project:
    name: str
    description: str = ""
    id: str = field(default_factory=_id)
    created_at: str = field(default_factory=_now)


@dataclass
class SourceConnection:
    project_id: str
    source_type: str  # "github" | "gdrive"
    display_name: str = ""
    repo_url: str = ""
    folder_id: str = ""
    credential_ref: str = ""  # 토큰 자체가 아니라 출처만 기록 (예: "env:GITHUB_TOKEN")
    id: str = field(default_factory=_id)
    connected_at: str = field(default_factory=_now)


@dataclass
class SourceRef:
    """문서 하나의 소스 좌표. source_type + source_path + source_ref 가 고유 식별자."""

    source_type: str
    source_path: str
    source_ref: str
    source_url: str = ""
    connection_id: str = ""
    label: str = ""


@dataclass
class Section:
    index: int
    heading: str
    content: str


@dataclass
class Document:
    project_id: str
    filename: str
    file_type: str
    content: str
    version: int = 1
    source: SourceRef | None = None
    sections: list[Section] = field(default_factory=list)
    id: str = field(default_factory=_id)
    fetched_at: str = field(default_factory=_now)

    @property
    def char_count(self) -> int:
        return len(self.content)


@dataclass
class ChangedSection:
    section_index: int
    heading: str
    change_type: str  # added | removed | modified
    old_content: str
    new_content: str
    diff_text: str


@dataclass
class DiffSummary:
    added_lines: int = 0
    removed_lines: int = 0
    modified_lines: int = 0


@dataclass
class DiffResult:
    doc_old_id: str
    doc_new_id: str
    diff_text: str = ""
    change_ratio: float = 0.0
    total_sections: int = 0
    changed_sections: list[ChangedSection] = field(default_factory=list)
    summary: DiffSummary = field(default_factory=DiffSummary)
    id: str = field(default_factory=_id)
    created_at: str = field(default_factory=_now)


@dataclass
class TechChange:
    change_type: str
    title: str
    description: str
    diff_id: str = ""
    original_text: str = ""
    changed_text: str = ""
    significance_score: float = 0.0
    is_patentable_candidate: bool = False
    reasoning: str = ""
    id: str = field(default_factory=_id)


@dataclass
class InventionPoint:
    title: str
    summary: str
    source_change_ids: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    id: str = field(default_factory=_id)
    created_at: str = field(default_factory=_now)


@dataclass
class PatentabilityScore:
    novelty: str = ""
    novelty_reasoning: str = ""
    inventive_step: str = ""
    inventive_step_reasoning: str = ""
    industrial_applicability: str = ""
    industrial_applicability_reasoning: str = ""


@dataclass
class InventionStructure:
    invention_id: str
    technical_field: str = ""
    background_art: str = ""
    problem: str = ""
    solution_means: str = ""
    effect: str = ""
    title: str = ""
    summary: str = ""
    patentability: PatentabilityScore = field(default_factory=PatentabilityScore)
    id: str = field(default_factory=_id)


@dataclass
class IPCCode:
    code: str
    description: str = ""


@dataclass
class SearchQueries:
    invention_id: str
    primary_kr: str = ""
    primary_en: str = ""
    secondary_kr: list[str] = field(default_factory=list)
    secondary_en: list[str] = field(default_factory=list)
    boolean_query: str = ""
    ipc_codes: list[IPCCode] = field(default_factory=list)
    id: str = field(default_factory=_id)


@dataclass
class DisclosureReport:
    invention_id: str
    report_markdown: str = ""
    sections: dict[str, Any] = field(default_factory=dict)
    prior_art_included: bool = False
    id: str = field(default_factory=_id)
    generated_at: str = field(default_factory=_now)
