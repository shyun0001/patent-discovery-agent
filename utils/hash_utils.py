"""캐시 키 생성 유틸."""
import hashlib
import json


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_hash(model: str, prompt: str) -> str:
    """LLM 캐시 키: SHA256(model + prompt)."""
    return sha256_text(f"{model}|{prompt}")


def query_hash(operation: str, params: dict) -> str:
    """KIPRIS 캐시 키. Service Key는 해시 대상에서 제외한다."""
    safe = {k: v for k, v in params.items() if k.lower() not in ("servicekey", "accesskey")}
    payload = json.dumps(safe, sort_keys=True, ensure_ascii=False)
    return sha256_text(f"{operation}|{payload}")
