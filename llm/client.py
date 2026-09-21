"""LLMClient — OpenAI 호출 + SQLite 캐싱 + 재시도."""
from __future__ import annotations

import json
import re
import time

from config import settings
from db import repository
from exceptions import LLMError
from utils.hash_utils import prompt_hash

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class LLMClient:
    """동일 (model, prompt) 요청은 캐시에서 반환하여 비용을 0으로 만든다."""

    def __init__(self, api_key: str | None = None, default_model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.default_model = default_model or settings.MODEL_SECONDARY
        self._client = None
        self.last_call_cached = False

    # ─── 내부 ──────────────────────────────────────────
    def _ensure_client(self):
        if self._client is None:
            if not self.api_key:
                raise LLMError("OPENAI_API_KEY가 설정되지 않았습니다.", "E3001")
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise LLMError(f"openai 패키지를 불러올 수 없습니다: {exc}", "E3002") from exc
            self._client = OpenAI(api_key=self.api_key, timeout=settings.LLM_TIMEOUT)
        return self._client

    def _call_api_with_retry(self, prompt: str, model: str, json_mode: bool, temperature: float) -> str:
        client = self._ensure_client()
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_error = None
        for attempt in range(settings.LLM_MAX_RETRIES):
            try:
                response = client.chat.completions.create(**kwargs)
                return response.choices[0].message.content or ""
            except Exception as exc:  # openai 예외 타입에 의존하지 않는다
                last_error = exc
                message = str(exc).lower()
                if "rate limit" in message or "429" in message:
                    code = "E3004"
                elif "context length" in message or "maximum context" in message:
                    raise LLMError("입력이 모델 컨텍스트 한도를 초과했습니다.", "E3005") from exc
                else:
                    code = "E3002"
                if attempt < settings.LLM_MAX_RETRIES - 1:
                    time.sleep(2**attempt)
        raise LLMError(f"LLM 호출에 실패했습니다: {last_error}", code)

    # ─── 공개 API ──────────────────────────────────────
    def call(self, prompt: str, model: str | None = None, temperature: float = 0.1) -> str:
        model = model or self.default_model
        key = prompt_hash(model, prompt)

        cached = repository.get_cache(key)
        if cached is not None:
            self.last_call_cached = True
            return cached

        self.last_call_cached = False
        response = self._call_api_with_retry(prompt, model, json_mode=False, temperature=temperature)
        repository.set_cache(key, prompt, response, model)
        return response

    def call_structured(
        self, prompt: str, model: str | None = None, temperature: float = 0.1
    ) -> dict:
        """JSON 응답 강제 호출. 파싱 실패 시 1회 재강조 후 재호출한다."""
        model = model or self.default_model
        key = prompt_hash(model, prompt)

        cached = repository.get_cache(key)
        if cached is not None:
            self.last_call_cached = True
            try:
                return self._parse_json(cached)
            except LLMError:
                repository.clear_cache(key)  # 손상된 캐시는 버린다

        self.last_call_cached = False
        raw = self._call_api_with_retry(prompt, model, json_mode=True, temperature=temperature)
        try:
            parsed = self._parse_json(raw)
        except LLMError:
            retry_prompt = prompt + "\n\n[재강조] 반드시 유효한 JSON 객체만 출력하세요. 설명 문장을 포함하지 마세요."
            raw = self._call_api_with_retry(retry_prompt, model, json_mode=True, temperature=0.0)
            parsed = self._parse_json(raw)

        repository.set_cache(key, prompt, raw, model)
        return parsed

    @staticmethod
    def _parse_json(raw: str) -> dict:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
        match = _JSON_BLOCK.search(raw or "")
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise LLMError("LLM 응답을 JSON으로 파싱하지 못했습니다.", "E3003")
