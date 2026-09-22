"""GDriveConnector — Google Drive API v3로 파일/리비전을 가져온다.

서비스 계정 키가 있으면 우선 사용하고, 없으면 OAuth 클라이언트 시크릿으로 인증한다.
google 패키지는 지연 임포트하여, 미설치 환경에서도 앱 자체는 기동되게 한다.
"""
from __future__ import annotations

import io

from config import settings
from exceptions import SourceError
from sources.base import DriveFile, Revision, SourceConnector

# 네이티브 Google 문서는 그대로 내려받을 수 없어 export가 필요하다.
_EXPORT_MAP = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".txt"),
}


class GDriveConnector(SourceConnector):
    source_type = "gdrive"

    def __init__(self, credentials_path=None, token_path=None, folder_id: str = "", api_key: str | None = None):
        super().__init__()
        self.credentials_path = credentials_path or settings.GDRIVE_CREDENTIALS_PATH
        self.token_path = token_path or settings.GDRIVE_TOKEN_PATH
        self.folder_id = folder_id or settings.GDRIVE_DEFAULT_FOLDER_ID
        self.api_key = settings.GDRIVE_API_KEY if api_key is None else api_key
        self.service = None
        # 자격 증명 없이 API 키만 있는 경우 True — 링크 공개 파일만 다룰 수 있다.
        self.api_key_mode = False
        self._file_meta: dict[str, DriveFile] = {}

    # ─── 인증 ──────────────────────────────────────────
    def authenticate(self) -> bool:
        if self.service is not None:
            return True
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise SourceError(
                "google-api-python-client가 설치되지 않았습니다. requirements.txt를 설치해주세요.",
                "E0001",
            ) from exc

        from pathlib import Path as _Path

        if not _Path(self.credentials_path).exists() and self.api_key:
            # 서비스 계정/OAuth 자격 증명이 없으면 API 키로 동작한다.
            self.api_key_mode = True
            self.service = build(
                "drive", "v3", developerKey=self.api_key, cache_discovery=False
            )
            return True

        credentials = self._load_credentials()
        self.api_key_mode = False
        self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return True

    def _load_credentials(self):
        from pathlib import Path

        cred_path = Path(self.credentials_path)
        token_path = Path(self.token_path)

        if not cred_path.exists():
            raise SourceError(
                "Google Drive 인증 정보를 찾을 수 없습니다. 폴더 탐색과 리비전 비교에는 "
                f"서비스 계정 키(JSON) 또는 OAuth 클라이언트가 필요합니다: {cred_path}",
                "E0001",
            )

        # 1) 서비스 계정 키
        try:
            import json

            with open(cred_path, encoding="utf-8") as fp:
                payload = json.load(fp)
        except (OSError, ValueError) as exc:
            raise SourceError(f"인증 파일을 읽을 수 없습니다: {exc}", "E0001") from exc

        if payload.get("type") == "service_account":
            from google.oauth2 import service_account

            return service_account.Credentials.from_service_account_file(
                str(cred_path), scopes=settings.GDRIVE_SCOPES
            )

        # 2) OAuth 클라이언트 시크릿
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(token_path), settings.GDRIVE_SCOPES
            )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(cred_path), settings.GDRIVE_SCOPES
            )
            creds = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    # ─── 목록 조회 ─────────────────────────────────────
    def list_targets(self, folder_id: str = "") -> list[DriveFile]:
        return self.list_folder(folder_id or self.folder_id)

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        self.authenticate()
        if not folder_id:
            raise SourceError("Drive 폴더 ID가 지정되지 않았습니다.", "E0003")
        if self.api_key_mode:
            raise SourceError(
                "API 키로는 폴더 목록을 조회할 수 없습니다. 서비스 계정 키를 등록하거나, "
                "링크 공개된 파일의 ID를 직접 입력해주세요.",
                "E0002",
            )
        try:
            response = (
                self.service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="files(id,name,mimeType,modifiedTime,webViewLink)",
                    pageSize=100,
                )
                .execute()
            )
        except Exception as exc:
            raise self._to_source_error(exc) from exc

        files = []
        for item in response.get("files", []):
            mime = item.get("mimeType", "")
            name = item.get("name", "")
            export_required = mime in _EXPORT_MAP
            if not export_required and not self.is_supported(name):
                continue
            drive_file = DriveFile(
                file_id=item.get("id", ""),
                name=name,
                mime_type=mime,
                modified_at=item.get("modifiedTime", ""),
                web_view_link=item.get("webViewLink", ""),
                export_required=export_required,
            )
            self._file_meta[drive_file.file_id] = drive_file
            files.append(drive_file)
        return files

    def list_revisions(self, target: str) -> list[Revision]:
        """target = Drive file_id"""
        self.authenticate()
        if self.api_key_mode:
            raise SourceError(
                "API 키로는 리비전 이력을 조회할 수 없습니다(소유자 권한 필요). "
                "서비스 계정 키를 등록하거나, 서로 다른 두 공개 파일을 비교해주세요.",
                "E0002",
            )
        try:
            response = (
                self.service.revisions()
                .list(
                    fileId=target,
                    fields="revisions(id,modifiedTime,lastModifyingUser(displayName))",
                )
                .execute()
            )
        except Exception as exc:
            raise self._to_source_error(exc) from exc

        meta = self._file_meta.get(target)
        revisions = []
        for item in response.get("revisions", []):
            modified = item.get("modifiedTime", "")
            user = (item.get("lastModifyingUser") or {}).get("displayName", "")
            revisions.append(
                Revision(
                    ref=item.get("id", ""),
                    label=f"리비전 ({modified[:10]})",
                    path=target,
                    author=user,
                    modified_at=modified,
                    url=meta.web_view_link if meta else "",
                )
            )
        revisions.reverse()  # 최신순
        return revisions

    # ─── 다운로드 ──────────────────────────────────────
    def fetch_content(self, target: str, ref: str = "") -> bytes:
        cached = self._read_cache(self.filename_for(target), ref or "latest")
        if cached is not None:
            return cached

        self.authenticate()
        meta = self._file_meta.get(target) or self._fetch_meta(target)
        try:
            if meta.export_required:
                data = self._export_native_doc(target, meta.mime_type)
            elif ref:
                request = self.service.revisions().get_media(fileId=target, revisionId=ref)
                data = self._download(request)
            else:
                request = self.service.files().get_media(fileId=target)
                data = self._download(request)
        except SourceError:
            raise
        except Exception as exc:
            raise self._to_source_error(exc) from exc

        self._write_cache(self.filename_for(target), ref or "latest", data)
        return data

    def fetch_file(self, file_id: str, revision_id: str = "") -> bytes:
        return self.fetch_content(file_id, revision_id)

    def _fetch_meta(self, file_id: str) -> DriveFile:
        try:
            item = (
                self.service.files()
                .get(fileId=file_id, fields="id,name,mimeType,modifiedTime,webViewLink")
                .execute()
            )
        except Exception as exc:
            raise self._to_source_error(exc) from exc
        drive_file = DriveFile(
            file_id=item.get("id", ""),
            name=item.get("name", ""),
            mime_type=item.get("mimeType", ""),
            modified_at=item.get("modifiedTime", ""),
            web_view_link=item.get("webViewLink", ""),
            export_required=item.get("mimeType", "") in _EXPORT_MAP,
        )
        self._file_meta[file_id] = drive_file
        return drive_file

    def _export_native_doc(self, file_id: str, mime_type: str) -> bytes:
        export_mime, _ = _EXPORT_MAP.get(mime_type, ("application/pdf", ".pdf"))
        try:
            request = self.service.files().export_media(fileId=file_id, mimeType=export_mime)
            return self._download(request)
        except Exception:
            # 대체 포맷(PDF)으로 1회 재시도
            try:
                request = self.service.files().export_media(
                    fileId=file_id, mimeType="application/pdf"
                )
                return self._download(request)
            except Exception as exc:
                raise SourceError(
                    "이 Google 문서는 텍스트로 변환할 수 없습니다.", "E0007"
                ) from exc

    @staticmethod
    def _download(request) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    # ─── 헬퍼 ──────────────────────────────────────────
    def filename_for(self, file_id: str) -> str:
        meta = self._file_meta.get(file_id)
        if not meta:
            return f"{file_id}.bin"
        if meta.export_required:
            _, ext = _EXPORT_MAP.get(meta.mime_type, ("application/pdf", ".pdf"))
            return f"{meta.name}{ext}"
        return meta.name

    def source_url(self, file_id: str, ref: str = "") -> str:
        meta = self._file_meta.get(file_id)
        return meta.web_view_link if meta else f"https://drive.google.com/file/d/{file_id}/view"

    @staticmethod
    def _to_source_error(exc: Exception) -> SourceError:
        message = str(exc)
        if "404" in message or "notFound" in message:
            return SourceError("해당 파일/폴더를 찾을 수 없습니다.", "E0003")
        if "403" in message:
            if "quota" in message.lower() or "rateLimit" in message:
                return SourceError("Google Drive 호출 한도를 초과했습니다.", "E0004")
            return SourceError("Google Drive 접근 권한이 없습니다.", "E0002")
        if "401" in message:
            return SourceError("Google Drive 인증에 실패했습니다.", "E0002")
        return SourceError(f"Google Drive 호출 실패: {message}", "E0006")
