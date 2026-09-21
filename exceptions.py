"""Patent Agent 예외 계층 — 에러 코드는 implementation_detail.md §6.1 기준."""


class PatentAgentError(Exception):
    """모든 Patent Agent 예외의 기반 클래스."""

    def __init__(self, message: str, error_code: str = ""):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class SourceError(PatentAgentError):
    """소스(GitHub / Google Drive) 연동 실패.

    E0001: 자격 증명 미설정        E0005: 리비전 선택 오류
    E0002: 인증 실패                E0006: 파일 다운로드 실패
    E0003: 대상 없음                E0007: 변환 불가 파일
    E0004: API Rate Limit 초과
    """


class DocumentParseError(PatentAgentError):
    """문서 파싱 실패.

    E1001: 지원하지 않는 파일 형식   E1003: PDF 텍스트 추출 실패
    E1002: 파일 인코딩 오류          E1004: PPTX 파싱 실패
                                     E1005: DOCX 파싱 실패
    """


class DiffError(PatentAgentError):
    """Diff 처리 실패. E2001: 내용 없음 / E2002: 두 문서 동일."""


class LLMError(PatentAgentError):
    """LLM 호출 실패.

    E3001: API 키 미설정   E3003: 응답 JSON 파싱 실패   E3005: 컨텍스트 초과
    E3002: API 호출 실패   E3004: Rate Limit 초과
    """


class AnalysisError(PatentAgentError):
    """분석 처리 실패. E4001~E4003."""


class ReportError(PatentAgentError):
    """보고서 생성 실패. E5001: 템플릿 로드 실패 / E5002: 필수 필드 누락."""


class KiprisError(PatentAgentError):
    """KIPRIS 선행기술 검색 실패.

    E6001: Service Key 미설정   E6004: XML 파싱 실패
    E6002: 인증 실패            E6005: 검색 결과 0건 (정보성)
    E6003: 호출 한도 초과       E6006: 타임아웃
    """
