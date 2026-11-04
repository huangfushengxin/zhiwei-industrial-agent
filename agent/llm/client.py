"""Small, injectable HTTP client. Errors never echo credentials or response bodies."""
from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class LLMError(RuntimeError):
    pass


class ChatClient:
    def __init__(self, api_key: str, *, base_url: str = "https://api.agnes-ai.cn/v1",
                 model: str = "agnes-3.0-flash", timeout: float = 30,
                 retries: int = 1, opener=None, sleeper=None):
        if not api_key.strip():
            raise ValueError("Set AGNES_API_KEY before running a live report")
        url = urlsplit(base_url)
        if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("Use an HTTPS API base URL without credentials, query or fragment")
        if timeout <= 0 or retries not in (0, 1, 2):
            raise ValueError("Invalid timeout or retry limit")
        self._key = api_key
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self._open = opener or urlopen
        self._sleep = sleeper or time.sleep

    def complete(self, messages: list[dict[str, str]], *, output_tokens: int) -> str:
        body = json.dumps({"model": self.model, "messages": messages,
                           "max_tokens": output_tokens, "temperature": 0}).encode("utf-8")
        request = Request(self.url, data=body, headers={
            "Authorization": "Bearer " + self._key, "Content-Type": "application/json",
        })
        for attempt in range(self.retries + 1):
            try:
                with self._open(request, timeout=self.timeout) as response:
                    raw = response.read(262145)
                if len(raw) > 262144:
                    raise LLMError("Model response exceeds 256 KiB")
                payload = json.loads(raw)
                choice = payload["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise LLMError("Model output was truncated; increase the output budget")
                content = choice["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise LLMError("Model returned no text report")
                return content
            except HTTPError as exc:
                status = exc.code
                exc.close()
                if status not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise LLMError(f"Model API returned HTTP {status}") from None
            except (URLError, TimeoutError, OSError):
                if attempt == self.retries:
                    raise LLMError("Model API connection failed or timed out") from None
            except (ValueError, KeyError, IndexError, TypeError):
                raise LLMError("Model API returned an invalid response envelope") from None
            self._sleep(min(2 ** attempt, 4))
        raise LLMError("Model request failed")
