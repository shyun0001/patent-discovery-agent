import pytest

from exceptions import KiprisError
from patent.kipris_client import KiprisClient
from tests.conftest import FIXTURES


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.headers = {}


def _client_with(monkeypatch, fixture_name, service_key="dummy-key"):
    client = KiprisClient(service_key=service_key, offline=False)
    xml = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResponse(xml)

    monkeypatch.setattr(client.session, "get", fake_get)
    return client, calls


def test_search_maps_xml_fields(monkeypatch):
    client, _ = _client_with(monkeypatch, "kipris_search.xml")
    results = client.search("모바일 경량모델 적응형 학습률 스케줄링")

    assert len(results) == 3
    first = results[0]
    assert first.application_number == "1020210012345"
    assert first.invention_title.startswith("학습률 스케줄링")
    assert first.application_date == "2021-01-28"  # YYYYMMDD → YYYY-MM-DD
    assert first.ipc_codes == ["G06N 3/08", "G06N 3/04"]  # 구분자 분해
    assert "1020210012345" in first.kipris_url
    assert client.last_total_found == 37


def test_empty_result_returns_empty_list(monkeypatch):
    client, _ = _client_with(monkeypatch, "kipris_empty.xml")
    assert client.search("존재하지 않는 기술") == []


def test_error_result_code_raises(monkeypatch):
    client, _ = _client_with(monkeypatch, "kipris_error.xml")
    with pytest.raises(KiprisError) as exc:
        client.search("테스트")
    assert exc.value.error_code == "E6002"


def test_second_call_uses_cache(monkeypatch):
    client, calls = _client_with(monkeypatch, "kipris_search.xml")
    client.search("동일 검색어")
    assert len(calls) == 1
    assert client.last_call_cached is False

    client.search("동일 검색어")
    assert len(calls) == 1  # API 재호출 없음
    assert client.last_call_cached is True


def test_offline_mode_without_service_key():
    client = KiprisClient(service_key="")
    assert client.offline is True

    results = client.search("모바일 경량모델")
    assert len(results) == 3
    assert all(item.is_sample for item in results)


def test_missing_fields_do_not_raise(monkeypatch):
    client = KiprisClient(service_key="dummy", offline=False)
    xml = """<?xml version="1.0"?><response><header><resultCode>00</resultCode></header>
    <body><count><totalCount>1</totalCount></count><items><item>
    <applicationNumber>1020200000001</applicationNumber></item></items></body></response>"""
    monkeypatch.setattr(client.session, "get", lambda *a, **k: FakeResponse(xml))

    results = client.search("필드 누락")
    assert results[0].invention_title == ""
    assert results[0].ipc_codes == []


# ─── resultCode 매핑 & 폴백 ────────────────────────────
def _error_xml(code: str, msg: str) -> str:
    return (
        '<?xml version="1.0"?><response><header><successYN>N</successYN>'
        f"<resultCode>{code}</resultCode><resultMsg>{msg}</resultMsg>"
        "</header></response>"
    )


@pytest.mark.parametrize(
    "code,msg,expected",
    [
        ("30", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "E6002"),
        ("31", "DEADLINE_HAS_EXPIRED_ERROR", "E6007"),
        ("32", "SERVICE_ACCESS_DENIED_ERROR", "E6003"),
    ],
)
def test_result_codes_map_to_error_codes(monkeypatch, code, msg, expected):
    client = KiprisClient(service_key="dummy", offline=False)
    monkeypatch.setattr(
        client.session, "get", lambda *a, **k: FakeResponse(_error_xml(code, msg))
    )
    with pytest.raises(KiprisError) as exc:
        client.search("테스트")
    assert exc.value.error_code == expected


def test_expired_key_falls_back_to_sample_data(monkeypatch):
    """키 만료(31) 시 데모가 끊기지 않고 샘플 데이터로 진행되어야 한다."""
    from core.prior_art import PriorArtAnalyzer
    from db.models import InventionStructure
    from tests.conftest import FakeLLM
    from tests.test_analyzer import SIMILARITY_RESPONSE

    client = KiprisClient(service_key="expired-key", offline=False)
    monkeypatch.setattr(
        client.session,
        "get",
        lambda *a, **k: FakeResponse(_error_xml("31", "DEADLINE_HAS_EXPIRED_ERROR")),
    )

    analyzer = PriorArtAnalyzer(
        kipris=client, llm_client=FakeLLM({"선행기술 조사 전문가": SIMILARITY_RESPONSE})
    )
    structure = InventionStructure(
        invention_id="inv_x", title="t", problem="p", solution_means="s", effect="e"
    )
    summary = analyzer.run(structure, "학습률 스케줄링")

    assert summary.is_sample is True
    assert "사용 기간이 만료" in summary.message
    assert summary.patents  # 샘플 fixture 3건으로 진행됨


def test_param_error_retries_with_alternate_paging(monkeypatch):
    """실측 규격(numOfRows/pageNo)이 거부되면 docsStart/docsCount로 1회 재시도한다."""
    client = KiprisClient(service_key="dummy", offline=False)
    ok_xml = (FIXTURES / "kipris_search.xml").read_text(encoding="utf-8")
    seen = []

    def fake_get(url, params=None, timeout=None):
        seen.append(params)
        if "numOfRows" in params:
            return FakeResponse(_error_xml("10", "INVALID_REQUEST_PARAMETER_ERROR"))
        return FakeResponse(ok_xml)

    monkeypatch.setattr(client.session, "get", fake_get)
    results = client.search("학습률")
    assert len(results) == 3
    assert "docsStart" in seen[1] and "numOfRows" not in seen[1]


def test_service_path_and_endpoint_are_pinned():
    """실측으로 확정한 엔드포인트가 유지되는지 고정한다 (경로 오타 재발 방지)."""
    from config import settings

    assert settings.KIPRIS_SERVICE == "patUtiModInfoSearchSevice"
    assert settings.KIPRIS_API_BASE == "https://plus.kipris.or.kr/kipo-api/kipi"
