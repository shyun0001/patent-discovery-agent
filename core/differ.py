"""DiffEngine — difflib 기반 로컬 비교 (LLM 비용 없음)."""
from __future__ import annotations

import difflib
import html

from db.models import ChangedSection, DiffResult, DiffSummary, Document, Section
from exceptions import DiffError

_MATCH_THRESHOLD = 0.6


class DiffEngine:
    def compute_diff(self, doc_old: Document, doc_new: Document) -> DiffResult:
        if not doc_old.content.strip() or not doc_new.content.strip():
            raise DiffError("문서 내용이 비어 있습니다.", "E2001")
        if doc_old.content.strip() == doc_new.content.strip():
            raise DiffError("두 문서에 차이가 없습니다.", "E2002")

        old_lines = doc_old.content.splitlines()
        new_lines = doc_new.content.splitlines()
        diff_text = "\n".join(
            difflib.unified_diff(
                old_lines, new_lines, fromfile="v1", tofile="v2", lineterm="", n=2
            )
        )

        changed = self.get_changed_sections(doc_old.sections, doc_new.sections)
        return DiffResult(
            doc_old_id=doc_old.id,
            doc_new_id=doc_new.id,
            diff_text=diff_text,
            change_ratio=self.calculate_change_ratio(doc_old.content, doc_new.content),
            total_sections=max(len(doc_old.sections), len(doc_new.sections)),
            changed_sections=changed,
            summary=self._summarize(diff_text),
        )

    # ─── 섹션 매칭 ─────────────────────────────────────
    def get_changed_sections(
        self, old_sections: list[Section], new_sections: list[Section]
    ) -> list[ChangedSection]:
        changed: list[ChangedSection] = []
        used: set[int] = set()

        for new_sec in new_sections:
            match = self._match_section(new_sec, old_sections, used)
            if match is None:
                changed.append(
                    ChangedSection(
                        section_index=new_sec.index,
                        heading=new_sec.heading,
                        change_type="added",
                        old_content="",
                        new_content=new_sec.content,
                        diff_text=self._section_diff("", new_sec.content),
                    )
                )
                continue

            used.add(match.index)
            if match.content.strip() != new_sec.content.strip():
                changed.append(
                    ChangedSection(
                        section_index=new_sec.index,
                        heading=new_sec.heading or match.heading,
                        change_type="modified",
                        old_content=match.content,
                        new_content=new_sec.content,
                        diff_text=self._section_diff(match.content, new_sec.content),
                    )
                )

        for old_sec in old_sections:
            if old_sec.index not in used:
                changed.append(
                    ChangedSection(
                        section_index=old_sec.index,
                        heading=old_sec.heading,
                        change_type="removed",
                        old_content=old_sec.content,
                        new_content="",
                        diff_text=self._section_diff(old_sec.content, ""),
                    )
                )

        changed.sort(key=lambda item: item.section_index)
        return changed

    def _match_section(
        self, target: Section, candidates: list[Section], used: set[int]
    ) -> Section | None:
        best, best_score = None, 0.0
        for candidate in candidates:
            if candidate.index in used:
                continue
            score = difflib.SequenceMatcher(
                None, self._norm(target.heading), self._norm(candidate.heading)
            ).ratio()
            if not target.heading and not candidate.heading:
                score = difflib.SequenceMatcher(
                    None, target.content[:200], candidate.content[:200]
                ).ratio()
            if score > best_score:
                best, best_score = candidate, score
        return best if best_score >= _MATCH_THRESHOLD else None

    # ─── 지표 ──────────────────────────────────────────
    def calculate_change_ratio(self, old_text: str, new_text: str) -> float:
        ratio = difflib.SequenceMatcher(None, old_text, new_text).ratio()
        return round(1.0 - ratio, 4)

    @staticmethod
    def _summarize(diff_text: str) -> DiffSummary:
        added = removed = 0
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        return DiffSummary(
            added_lines=added,
            removed_lines=removed,
            modified_lines=min(added, removed),
        )

    # ─── 렌더링 ────────────────────────────────────────
    def format_diff_html(self, diff_text: str) -> str:
        rows = []
        for line in diff_text.splitlines():
            escaped = html.escape(line)
            if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                color, background = "#6b7280", "transparent"
            elif line.startswith("+"):
                color, background = "#166534", "#dcfce7"
            elif line.startswith("-"):
                color, background = "#991b1b", "#fee2e2"
            else:
                color, background = "inherit", "transparent"
            rows.append(
                f"<div style='color:{color};background:{background};"
                f"padding:1px 6px;white-space:pre-wrap'>{escaped}</div>"
            )
        return (
            "<div style='font-family:ui-monospace,Consolas,monospace;font-size:12px;"
            "border:1px solid #e5e7eb;border-radius:6px;overflow:auto;max-height:520px'>"
            + "".join(rows)
            + "</div>"
        )

    @staticmethod
    def _section_diff(old: str, new: str) -> str:
        return "\n".join(
            difflib.unified_diff(
                old.splitlines(), new.splitlines(), lineterm="", n=1
            )
        )

    @staticmethod
    def _norm(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum() or "가" <= ch <= "힣")
