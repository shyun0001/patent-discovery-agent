"""CRUD — sqlite3 직접 사용 (ORM 불필요)."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime

from config import settings
from db.init_db import init_db
from db.models import (
    DiffResult,
    DisclosureReport,
    Document,
    IPCCode,
    InventionPoint,
    InventionStructure,
    Project,
    SearchQueries,
    SourceConnection,
    SourceRef,
    TechChange,
)
from patent.schemas import PatentDocument, SimilarityAssessment

_initialized = False


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ─── project ───────────────────────────────────────────
def save_project(project: Project) -> str:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO project (id, name, description, created_at) VALUES (?,?,?,?)",
            (project.id, project.name, project.description, project.created_at),
        )
    return project.id


def get_projects() -> list[Project]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM project ORDER BY created_at DESC").fetchall()
    return [
        Project(id=r["id"], name=r["name"], description=r["description"] or "", created_at=r["created_at"])
        for r in rows
    ]


# ─── source_connection ─────────────────────────────────
def save_source_connection(conn_obj: SourceConnection) -> str:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO source_connection
               (id, project_id, source_type, display_name, repo_url, folder_id, credential_ref, connected_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                conn_obj.id,
                conn_obj.project_id,
                conn_obj.source_type,
                conn_obj.display_name,
                conn_obj.repo_url,
                conn_obj.folder_id,
                conn_obj.credential_ref,
                conn_obj.connected_at,
            ),
        )
    return conn_obj.id


def get_source_connections(project_id: str) -> list[SourceConnection]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM source_connection WHERE project_id = ? ORDER BY connected_at DESC",
            (project_id,),
        ).fetchall()
    return [
        SourceConnection(
            id=r["id"],
            project_id=r["project_id"],
            source_type=r["source_type"],
            display_name=r["display_name"] or "",
            repo_url=r["repo_url"] or "",
            folder_id=r["folder_id"] or "",
            credential_ref=r["credential_ref"] or "",
            connected_at=r["connected_at"],
        )
        for r in rows
    ]


# ─── document ──────────────────────────────────────────
def save_document(doc: Document) -> str:
    src = doc.source or SourceRef("", "", "")
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO document
               (id, project_id, source_connection_id, source_type, source_path, source_ref,
                source_url, filename, file_type, content, version, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                doc.id,
                doc.project_id,
                src.connection_id,
                src.source_type,
                src.source_path,
                src.source_ref,
                src.source_url,
                doc.filename,
                doc.file_type,
                doc.content,
                doc.version,
                doc.fetched_at,
            ),
        )
    return doc.id


def _row_to_document(row: sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        project_id=row["project_id"] or "",
        filename=row["filename"] or "",
        file_type=row["file_type"] or "",
        content=row["content"] or "",
        version=row["version"] or 1,
        fetched_at=row["fetched_at"] or "",
        source=SourceRef(
            source_type=row["source_type"] or "",
            source_path=row["source_path"] or "",
            source_ref=row["source_ref"] or "",
            source_url=row["source_url"] or "",
            connection_id=row["source_connection_id"] or "",
        ),
    )


def get_document_by_source(source_type: str, source_path: str, source_ref: str) -> Document | None:
    """동일 리비전 재수집 방지용 조회."""
    with connect() as conn:
        row = conn.execute(
            """SELECT * FROM document
               WHERE source_type = ? AND source_path = ? AND source_ref = ?""",
            (source_type, source_path, source_ref),
        ).fetchone()
    return _row_to_document(row) if row else None


def get_documents_by_project(project_id: str) -> list[Document]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM document WHERE project_id = ? ORDER BY fetched_at DESC",
            (project_id,),
        ).fetchall()
    return [_row_to_document(r) for r in rows]


# ─── diff / analysis ───────────────────────────────────
def save_diff_result(diff: DiffResult) -> str:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO diff_result
               (id, doc_old_id, doc_new_id, diff_text, change_ratio, created_at)
               VALUES (?,?,?,?,?,?)""",
            (diff.id, diff.doc_old_id, diff.doc_new_id, diff.diff_text, diff.change_ratio, diff.created_at),
        )
    return diff.id


def save_tech_change(change: TechChange) -> str:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO tech_change
               (id, diff_id, change_type, title, description, original_text, changed_text,
                significance_score, is_patentable_candidate, reasoning)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                change.id,
                change.diff_id,
                change.change_type,
                change.title,
                change.description,
                change.original_text,
                change.changed_text,
                change.significance_score,
                int(change.is_patentable_candidate),
                change.reasoning,
            ),
        )
    return change.id


def save_invention_point(point: InventionPoint) -> str:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO invention_point
               (id, tech_change_ids, title, summary, confidence_score, created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                point.id,
                json.dumps(point.source_change_ids, ensure_ascii=False),
                point.title,
                point.summary,
                point.confidence_score,
                point.created_at,
            ),
        )
    return point.id


def save_invention_structure(structure: InventionStructure) -> str:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO invention_structure
               (id, invention_point_id, technical_field, background_art, problem,
                solution_means, effect, patentability_json)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                structure.id,
                structure.invention_id,
                structure.technical_field,
                structure.background_art,
                structure.problem,
                structure.solution_means,
                structure.effect,
                json.dumps(asdict(structure.patentability), ensure_ascii=False),
            ),
        )
    return structure.id


def save_search_query(query: SearchQueries) -> str:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO search_query
               (id, invention_point_id, primary_kr, primary_en, secondary_kr,
                secondary_en, boolean_query, ipc_codes)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                query.id,
                query.invention_id,
                query.primary_kr,
                query.primary_en,
                json.dumps(query.secondary_kr, ensure_ascii=False),
                json.dumps(query.secondary_en, ensure_ascii=False),
                query.boolean_query,
                json.dumps([asdict(c) for c in query.ipc_codes], ensure_ascii=False),
            ),
        )
    return query.id


# ─── prior art ─────────────────────────────────────────
def save_prior_art_results(
    query_id: str, invention_id: str, results: list[PatentDocument]
) -> list[str]:
    saved = []
    with connect() as conn:
        for item in results:
            conn.execute(
                """INSERT OR REPLACE INTO prior_art_result
                   (id, search_query_id, invention_point_id, application_number, invention_title,
                    applicant_name, application_date, open_date, register_status, abstract,
                    ipc_codes, kipris_url, rank, searched_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.result_id,
                    query_id,
                    invention_id,
                    item.application_number,
                    item.invention_title,
                    item.applicant_name,
                    item.application_date,
                    item.open_date,
                    item.register_status,
                    item.abstract,
                    json.dumps(item.ipc_codes, ensure_ascii=False),
                    item.kipris_url,
                    item.rank,
                    _now(),
                ),
            )
            saved.append(item.result_id)
    return saved


def get_prior_art_results(query_id: str) -> list[PatentDocument]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM prior_art_result WHERE search_query_id = ? ORDER BY rank",
            (query_id,),
        ).fetchall()
    return [
        PatentDocument(
            result_id=r["id"],
            application_number=r["application_number"] or "",
            invention_title=r["invention_title"] or "",
            applicant_name=r["applicant_name"] or "",
            application_date=r["application_date"] or "",
            open_date=r["open_date"] or "",
            register_status=r["register_status"] or "",
            abstract=r["abstract"] or "",
            ipc_codes=json.loads(r["ipc_codes"] or "[]"),
            kipris_url=r["kipris_url"] or "",
            rank=r["rank"] or 0,
        )
        for r in rows
    ]


def save_similarity_assessment(assessment: SimilarityAssessment, invention_id: str = "") -> str:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO similarity_assessment
               (id, prior_art_result_id, invention_point_id, application_number, similarity_score,
                risk_level, overlapping_points, differentiating_points, reasoning)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                assessment.id,
                assessment.result_id,
                invention_id,
                assessment.application_number,
                assessment.similarity_score,
                assessment.risk_level,
                assessment.overlapping_points,
                assessment.differentiating_points,
                assessment.reasoning,
            ),
        )
    return assessment.id


# ─── report ────────────────────────────────────────────
def save_disclosure_report(report: DisclosureReport) -> str:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO disclosure_report
               (id, invention_point_id, report_markdown, report_docx, prior_art_included, generated_at)
               VALUES (?,?,?,?,?,?)""",
            (
                report.id,
                report.invention_id,
                report.report_markdown,
                None,
                int(report.prior_art_included),
                report.generated_at,
            ),
        )
    return report.id


# ─── caches ────────────────────────────────────────────
def get_cache(prompt_hash: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT response FROM llm_cache WHERE prompt_hash = ?", (prompt_hash,)
        ).fetchone()
    return row["response"] if row else None


def set_cache(prompt_hash: str, prompt: str, response: str, model: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO llm_cache (prompt_hash, prompt, response, model, cached_at)
               VALUES (?,?,?,?,?)""",
            (prompt_hash, prompt, response, model, _now()),
        )


def clear_cache(prompt_hash: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM llm_cache WHERE prompt_hash = ?", (prompt_hash,))


def get_kipris_cache(query_hash: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM kipris_cache WHERE query_hash = ?", (query_hash,)
        ).fetchone()
    if not row:
        return None
    return {
        "query": row["query"],
        "results": json.loads(row["response_json"] or "[]"),
        "result_count": row["result_count"] or 0,
    }


def set_kipris_cache(query_hash: str, query: str, results: list[dict], result_count: int) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO kipris_cache
               (query_hash, query, response_json, result_count, cached_at)
               VALUES (?,?,?,?,?)""",
            (query_hash, query, json.dumps(results, ensure_ascii=False), result_count, _now()),
        )


def clear_kipris_cache(query_hash: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM kipris_cache WHERE query_hash = ?", (query_hash,))


def ipc_codes_from_json(raw: str) -> list[IPCCode]:
    return [IPCCode(**item) for item in json.loads(raw or "[]")]
