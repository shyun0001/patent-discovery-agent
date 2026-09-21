"""KiprisClient — KIPRIS Plus OpenAPI로 국내 특허/실용신안을 검색한다.

검색 대상은 KIPRIS(국내)로 한정한다. USPTO/Google Patents 등 해외 DB는 사용하지 않는다.
응답 필드 매핑은 _normalize_item() 한 곳에만 두어, 명세서와 다를 때 여기만 고치면 되게 한다.
"""
from __future__ import annotations

import time
from dataclasses import asdict

import requests
import xmltodict

from config import settings
from db import repository
from exceptions import KiprisError
from patent.schemas import PatentDocument
from utils.hash_utils import query_hash


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value) -> str:
    """xmltodict가 dict(#text)나 None을 줄 수 있으므로 안전하게 문자열화한다."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("#text", "")).strip()
    return str(value).strip()


def _format_date(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return raw


def _split_ipc(raw: str) -> list[str]:
    if not raw:
        return []
    for sep in ("|", ",", ";"):
        raw = raw.replace(sep, "\n")
    return [code.strip() for code in raw.split("\n") if code.strip()]


class KiprisClient:
    def __init__(self, service_key: str | None = None, offline: bool | None = None):
        self.service_key = service_key if service_key is not None else settings.KIPRIS_SERVICE_KEY
        self.offline = settings.KIPRIS_OFFLINE if offline is None else offline
        if not self.service_key:
            # 키가 없으면 데모가 멈추지 않도록 오프라인(샘플) 모드로 동작한다.
            self.offline = True
        self.session = requests.Session()
        self.last_call_cached = False
        self.last_total_found = 0

    # ─── 공개 API ──────────────────────────────────────
    def search(self, query: str, rows: int | None = None, page: int = 1) -> list[PatentDocument]:
        """자유 키워드 검색 (getWordSearch)."""
        query = (query or "").strip()
        if not query:
            return []
        rows = rows or settings.KIPRIS_MAX_RESULTS
        params = {
            "word": query,
            "numOfRows": rows,
            "pageNo": page,
            "patent": "true",
            "utility": "true",
        }
        return self._search("getWordSearch", params, query)

    def search_advanced(
        self, title: str = "", abstract: str = "", ipc: str = "", rows: int | None = None
    ) -> list[PatentDocument]:
        """필드 지정 검색 (getAdvancedSearch)."""
        rows = rows or settings.KIPRIS_MAX_RESULTS
        params = {
            "inventionTitle": title,
            "astrtCont": abstract,
            "ipcNumber": ipc,
            "numOfRows": rows,
            "pageNo": 1,
            "patent": "true",
            "utility": "true",
        }
        params = {k: v for k, v in params.items() if v not in ("", None)}
        label = title or abstract or ipc
        return self._search("getAdvancedSearch", params, label)

    # ─── 내부 ──────────────────────────────────────────
    def _search(self, operation: str, params: dict, query_label: str) -> list[PatentDocument]:
        key = query_hash(operation, params)

        cached = repository.get_kipris_cache(key)
        if cached is not None:
            self.last_call_cached = True
            self.last_total_found = cached.get("result_count", 0)
            return [PatentDocument(**item) for item in cached["results"]]

        self.last_call_cached = False
        xml_text = self._load_sample_response() if self.offline else self._call_api(operation, params)
        items = self._parse_xml(xml_text)
        documents = []
        for index, item in enumerate(items, start=1):
            doc = self._normalize_item(item)
            doc.rank = index
            doc.is_sample = self.offline
            documents.append(doc)

        repository.set_kipris_cache(
            key, query_label, [asdict(d) for d in documents], self.last_total_found
        )
        return documents

    def _call_api(self, operation: str, params: dict) -> str:
        if not self.service_key:
            raise KiprisError("KIPRIS Service Key가 설정되지 않았습니다.", "E6001")

        url = f"{settings.KIPRIS_API_BASE}/{settings.KIPRIS_SERVICE}/{operation}"
        payload = dict(params)
        payload["ServiceKey"] = self.service_key

        last_error = None
        for attempt in range(settings.KIPRIS_MAX_RETRIES):
            try:
                response = self.session.get(url, params=payload, timeout=settings.KIPRIS_TIMEOUT)
            except requests.Timeout as exc:
                last_error = exc
                if attempt < settings.KIPRIS_MAX_RETRIES - 1:
                    time.sleep(2**attempt)
                    continue
                raise KiprisError("KIPRIS 응답이 지연되고 있습니다.", "E6006") from exc
            except requests.RequestException as exc:
                last_error = exc
                if attempt < settings.KIPRIS_MAX_RETRIES - 1:
                    time.sleep(2**attempt)
                    continue
                break

            if response.status_code == 200:
                return response.text
            if 500 <= response.status_code < 600:
                last_error = f"HTTP {response.status_code}"
                if attempt < settings.KIPRIS_MAX_RETRIES - 1:
                    time.sleep(2**attempt)
                    continue
            raise KiprisError(f"KIPRIS 호출 실패 (HTTP {response.status_code})", "E6002")

        raise KiprisError(f"KIPRIS 호출에 실패했습니다: {last_error}", "E6006")

    def _parse_xml(self, xml_text: str) -> list[dict]:
        try:
            parsed = xmltodict.parse(xml_text)
        except Exception as exc:
            raise KiprisError("KIPRIS 응답 XML을 파싱하지 못했습니다.", "E6004") from exc

        root = parsed.get("response") or next(iter(parsed.values()), {}) or {}
        header = root.get("header") or {}
        result_code = _text(header.get("resultCode"))
        if result_code and result_code not in ("00", "0"):
            message = _text(header.get("resultMsg")) or "알 수 없는 오류"
            code = "E6003" if "한도" in message or "LIMIT" in message.upper() else "E6002"
            raise KiprisError(f"KIPRIS 오류: {message} (resultCode={result_code})", code)

        body = root.get("body") or {}
        count = body.get("count") or {}
        self.last_total_found = int(_text(count.get("totalCount")) or 0)

        items = body.get("items") or {}
        if isinstance(items, str):
            return []
        raw_items = _as_list(items.get("item"))
        if not raw_items and not self.last_total_found:
            self.last_total_found = 0
        if self.last_total_found == 0:
            self.last_total_found = len(raw_items)
        return [item for item in raw_items if isinstance(item, dict)]

    @staticmethod
    def _normalize_item(item: dict) -> PatentDocument:
        """KIPRIS XML 필드 → 내부 모델 매핑 (필드명 변경 시 이 함수만 수정)."""
        app_no = _text(item.get("applicationNumber")).replace("-", "")
        open_date = _text(item.get("openDate")) or _text(item.get("registerDate"))
        return PatentDocument(
            application_number=app_no,
            invention_title=_text(item.get("inventionTitle")),
            applicant_name=_text(item.get("applicantName")),
            application_date=_format_date(_text(item.get("applicationDate"))),
            open_date=_format_date(open_date),
            register_status=_text(item.get("registerStatus")),
            abstract=_text(item.get("astrtCont")),
            ipc_codes=_split_ipc(_text(item.get("ipcNumber"))),
            kipris_url=settings.KIPRIS_DETAIL_URL.format(app_no=app_no),
        )

    @staticmethod
    def _load_sample_response() -> str:
        path = settings.FIXTURES_DIR / "kipris_search.xml"
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise KiprisError(
                "KIPRIS Service Key가 없고 샘플 응답도 찾을 수 없습니다.", "E6001"
            ) from exc
