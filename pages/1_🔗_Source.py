"""Page 1 — 소스 연동 (GitHub / Google Drive)."""
import streamlit as st

from config import settings
from db import repository
from db.models import SourceConnection
from exceptions import PatentAgentError, SourceError
from sources.gdrive_connector import GDriveConnector
from sources.github_connector import GitHubConnector
from ui_state import init_state, pipeline, project_id, reset_from, show_error

st.set_page_config(page_title="소스 연동", page_icon="🔗", layout="wide")
init_state()

st.title("🔗 소스 연동")
st.caption("GitHub 커밋 또는 Google Drive 리비전 2개를 골라 비교할 문서를 가져옵니다.")

if not project_id():
    st.warning("먼저 홈에서 프로젝트를 선택해주세요.")
    st.page_link("app.py", label="홈으로 이동", icon="🏠")
    st.stop()


def _save_connection(source_type: str, display_name: str, repo_url: str = "", folder_id: str = "") -> str:
    connection = SourceConnection(
        project_id=project_id(),
        source_type=source_type,
        display_name=display_name,
        repo_url=repo_url,
        folder_id=folder_id,
        credential_ref="env:GITHUB_TOKEN" if source_type == "github" else "file:GDRIVE_CREDENTIALS_PATH",
    )
    repository.save_source_connection(connection)
    st.session_state.connection_id = connection.id
    return connection.id


def _import_and_diff(connector, old: dict, new: dict, filename_old: str, filename_new: str):
    if old["source_path"] == new["source_path"] and old["source_ref"] == new["source_ref"]:
        raise SourceError("이전/변경 리비전이 동일합니다. 서로 다른 항목을 선택해주세요.", "E0005")

    orchestrator = pipeline()
    with st.spinner("소스에서 문서를 가져오는 중입니다..."):
        doc_old = orchestrator.import_document(
            connector, old["source_path"], old["source_ref"], filename_old,
            project_id=project_id(), version=1, connection_id=st.session_state.connection_id,
        )
        doc_new = orchestrator.import_document(
            connector, new["source_path"], new["source_ref"], filename_new,
            project_id=project_id(), version=2, connection_id=st.session_state.connection_id,
        )
    reset_from("documents")
    st.session_state.documents = (doc_old, doc_new)
    st.session_state.source = {"old": old, "new": new}
    st.session_state.connector = connector

    with st.spinner("문서 차이를 계산하는 중입니다..."):
        st.session_state.diff = orchestrator.run_diff(doc_old, doc_new)

    st.success(f"문서 2건을 가져왔습니다 — 변경률 {st.session_state.diff.change_ratio:.1%}")
    st.page_link("pages/2_🔍_Diff.py", label="Diff 뷰어로 이동", icon="🔍")


github_tab, drive_tab = st.tabs(["GitHub", "Google Drive"])

# ─── GitHub ────────────────────────────────────────────
with github_tab:
    col_repo, col_token = st.columns([2, 1])
    repo_input = col_repo.text_input(
        "Repository", value=settings.GITHUB_DEFAULT_REPO, placeholder="owner/repo 또는 GitHub URL"
    )
    token_input = col_token.text_input(
        "Personal Access Token", value=settings.GITHUB_TOKEN, type="password"
    )

    if st.button("연결", key="gh_connect", type="primary"):
        try:
            connector = GitHubConnector(token=token_input)
            info = connector.connect(repo_input)
            st.session_state.connector = connector
            st.session_state.github_files = connector.list_files()
            st.session_state.github_rate_limit = connector.get_rate_limit()
            _save_connection("github", info.slug, repo_url=info.html_url)
            st.success(f"연결됨: {info.slug} (기본 브랜치: {info.default_branch})")
        except PatentAgentError as exc:
            show_error(exc)

    files = st.session_state.get("github_files")
    connector = st.session_state.get("connector")
    if files and isinstance(connector, GitHubConnector):
        path = st.selectbox("분석할 파일", files, key="gh_path")
        if st.button("커밋 목록 불러오기", key="gh_commits"):
            try:
                st.session_state.github_revisions = connector.list_commits(path)
            except PatentAgentError as exc:
                show_error(exc)

        revisions = st.session_state.get("github_revisions")
        if revisions:
            st.dataframe(
                [
                    {
                        "커밋": r.ref[:8],
                        "메시지": r.label,
                        "작성자": r.author,
                        "일시": r.modified_at[:19].replace("T", " "),
                    }
                    for r in revisions
                ],
                use_container_width=True,
                hide_index=True,
            )
            labels = [r.display() for r in revisions]
            col_old, col_new = st.columns(2)
            old_index = col_old.selectbox(
                "이전 커밋", range(len(labels)), format_func=lambda i: labels[i],
                index=min(1, len(labels) - 1), key="gh_old",
            )
            new_index = col_new.selectbox(
                "변경 커밋", range(len(labels)), format_func=lambda i: labels[i],
                index=0, key="gh_new",
            )

            if st.button("가져와서 비교 시작", key="gh_run", type="primary"):
                try:
                    old_rev, new_rev = revisions[old_index], revisions[new_index]
                    filename = path.split("/")[-1]
                    _import_and_diff(
                        connector,
                        {"source_path": path, "source_ref": old_rev.ref},
                        {"source_path": path, "source_ref": new_rev.ref},
                        filename,
                        filename,
                    )
                except PatentAgentError as exc:
                    show_error(exc)
    elif not files:
        st.info("저장소를 먼저 연결해주세요. 분석 가능한 확장자: .md, .txt, .pdf, .pptx, .docx")

# ─── Google Drive ──────────────────────────────────────
with drive_tab:
    folder_input = st.text_input(
        "폴더 ID", value=settings.GDRIVE_DEFAULT_FOLDER_ID, placeholder="Drive 폴더 ID"
    )
    st.caption(
        f"인증 파일: {settings.GDRIVE_CREDENTIALS_PATH} "
        f"({'있음' if settings.GDRIVE_CREDENTIALS_PATH.exists() else '없음'})"
    )

    if st.button("인증 후 파일 목록 불러오기", key="gd_connect", type="primary"):
        try:
            connector = GDriveConnector(folder_id=folder_input)
            connector.authenticate()
            st.session_state.connector = connector
            st.session_state.gdrive_files = connector.list_folder(folder_input)
            _save_connection("gdrive", f"Drive 폴더 {folder_input[:8]}", folder_id=folder_input)
            st.success(f"{len(st.session_state.gdrive_files)}개 파일을 찾았습니다.")
        except PatentAgentError as exc:
            show_error(exc)

    drive_files = st.session_state.get("gdrive_files")
    connector = st.session_state.get("connector")
    if drive_files and isinstance(connector, GDriveConnector):
        st.dataframe(
            [
                {
                    "파일명": f.name,
                    "수정일": f.modified_at[:10],
                    "변환필요": "예" if f.export_required else "아니오",
                }
                for f in drive_files
            ],
            use_container_width=True,
            hide_index=True,
        )
        names = [f.name for f in drive_files]
        mode = st.radio(
            "비교 모드", ["동일 파일의 리비전 2개", "서로 다른 파일 2개"], key="gd_mode"
        )

        if mode == "서로 다른 파일 2개":
            col_old, col_new = st.columns(2)
            old_index = col_old.selectbox(
                "이전 버전 파일", range(len(names)), format_func=lambda i: names[i], key="gd_old_file"
            )
            new_index = col_new.selectbox(
                "변경 버전 파일", range(len(names)), format_func=lambda i: names[i],
                index=min(1, len(names) - 1), key="gd_new_file",
            )
            if st.button("가져와서 비교 시작", key="gd_run_files", type="primary"):
                try:
                    old_file, new_file = drive_files[old_index], drive_files[new_index]
                    _import_and_diff(
                        connector,
                        {"source_path": old_file.file_id, "source_ref": ""},
                        {"source_path": new_file.file_id, "source_ref": ""},
                        connector.filename_for(old_file.file_id),
                        connector.filename_for(new_file.file_id),
                    )
                except PatentAgentError as exc:
                    show_error(exc)
        else:
            file_index = st.selectbox(
                "파일", range(len(names)), format_func=lambda i: names[i], key="gd_file"
            )
            if st.button("리비전 목록 불러오기", key="gd_revisions"):
                try:
                    st.session_state.gdrive_revisions = connector.list_revisions(
                        drive_files[file_index].file_id
                    )
                except PatentAgentError as exc:
                    show_error(exc)

            revisions = st.session_state.get("gdrive_revisions")
            if revisions:
                labels = [r.display() for r in revisions]
                col_old, col_new = st.columns(2)
                old_index = col_old.selectbox(
                    "이전 리비전", range(len(labels)), format_func=lambda i: labels[i],
                    index=min(1, len(labels) - 1), key="gd_old_rev",
                )
                new_index = col_new.selectbox(
                    "변경 리비전", range(len(labels)), format_func=lambda i: labels[i],
                    index=0, key="gd_new_rev",
                )
                if st.button("가져와서 비교 시작", key="gd_run_revs", type="primary"):
                    try:
                        drive_file = drive_files[file_index]
                        filename = connector.filename_for(drive_file.file_id)
                        _import_and_diff(
                            connector,
                            {"source_path": drive_file.file_id, "source_ref": revisions[old_index].ref},
                            {"source_path": drive_file.file_id, "source_ref": revisions[new_index].ref},
                            filename,
                            filename,
                        )
                    except PatentAgentError as exc:
                        show_error(exc)
    elif not drive_files:
        st.info("폴더 ID를 입력하고 인증을 진행해주세요.")

rate = st.session_state.get("github_rate_limit")
if rate and rate.get("limit"):
    st.caption(f"GitHub rate limit 잔여: {rate['remaining']}/{rate['limit']}")
