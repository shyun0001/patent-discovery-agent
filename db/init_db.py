"""SQLite 스키마 생성 — 실행: python -m db.init_db"""
import sqlite3

from config import settings

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS source_connection (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id),
    source_type TEXT NOT NULL,
    display_name TEXT,
    repo_url TEXT,
    folder_id TEXT,
    credential_ref TEXT,
    connected_at TEXT
);

CREATE TABLE IF NOT EXISTS document (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES project(id),
    source_connection_id TEXT,
    source_type TEXT,
    source_path TEXT,
    source_ref TEXT,
    source_url TEXT,
    filename TEXT,
    file_type TEXT,
    content TEXT,
    version INTEGER,
    fetched_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_source
    ON document(source_type, source_path, source_ref);

CREATE TABLE IF NOT EXISTS diff_result (
    id TEXT PRIMARY KEY,
    doc_old_id TEXT REFERENCES document(id),
    doc_new_id TEXT REFERENCES document(id),
    diff_text TEXT,
    change_ratio REAL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS tech_change (
    id TEXT PRIMARY KEY,
    diff_id TEXT REFERENCES diff_result(id),
    change_type TEXT,
    title TEXT,
    description TEXT,
    original_text TEXT,
    changed_text TEXT,
    significance_score REAL,
    is_patentable_candidate INTEGER,
    reasoning TEXT
);

CREATE TABLE IF NOT EXISTS invention_point (
    id TEXT PRIMARY KEY,
    tech_change_ids TEXT,
    title TEXT,
    summary TEXT,
    confidence_score REAL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS invention_structure (
    id TEXT PRIMARY KEY,
    invention_point_id TEXT REFERENCES invention_point(id),
    technical_field TEXT,
    background_art TEXT,
    problem TEXT,
    solution_means TEXT,
    effect TEXT,
    patentability_json TEXT
);

CREATE TABLE IF NOT EXISTS search_query (
    id TEXT PRIMARY KEY,
    invention_point_id TEXT REFERENCES invention_point(id),
    primary_kr TEXT,
    primary_en TEXT,
    secondary_kr TEXT,
    secondary_en TEXT,
    boolean_query TEXT,
    ipc_codes TEXT
);

CREATE TABLE IF NOT EXISTS prior_art_result (
    id TEXT PRIMARY KEY,
    search_query_id TEXT,
    invention_point_id TEXT,
    application_number TEXT,
    invention_title TEXT,
    applicant_name TEXT,
    application_date TEXT,
    open_date TEXT,
    register_status TEXT,
    abstract TEXT,
    ipc_codes TEXT,
    kipris_url TEXT,
    rank INTEGER,
    searched_at TEXT
);

CREATE TABLE IF NOT EXISTS similarity_assessment (
    id TEXT PRIMARY KEY,
    prior_art_result_id TEXT,
    invention_point_id TEXT,
    application_number TEXT,
    similarity_score REAL,
    risk_level TEXT,
    overlapping_points TEXT,
    differentiating_points TEXT,
    reasoning TEXT
);

CREATE TABLE IF NOT EXISTS disclosure_report (
    id TEXT PRIMARY KEY,
    invention_point_id TEXT REFERENCES invention_point(id),
    report_markdown TEXT,
    report_docx BLOB,
    prior_art_included INTEGER,
    generated_at TEXT
);

CREATE TABLE IF NOT EXISTS llm_cache (
    prompt_hash TEXT PRIMARY KEY,
    prompt TEXT,
    response TEXT,
    model TEXT,
    cached_at TEXT
);

CREATE TABLE IF NOT EXISTS kipris_cache (
    query_hash TEXT PRIMARY KEY,
    query TEXT,
    response_json TEXT,
    result_count INTEGER,
    cached_at TEXT
);
"""


def init_db(db_path=None) -> None:
    settings.ensure_dirs()
    path = str(db_path or settings.DB_PATH)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
    print(f"[init_db] schema ready: {path}")


if __name__ == "__main__":
    init_db()
