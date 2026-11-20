"""외부 서비스 연결: LLM(OpenAI 호환 API, 기본 Groq)과 웹 검색(Tavily).

키는 서버 쪽(st.secrets 또는 환경변수)에서만 읽고, 화면·대화·내보내기 파일에 절대 넣지 않는다.
키가 없으면 None을 돌려주고, 앱은 규칙 기반 모드로 계속 동작한다.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlsplit

import requests

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"


def secret(name: str, default: str = "") -> str:
    value = os.environ.get(name, "")
    if not value:
        try:
            import streamlit as st

            value = str(st.secrets.get(name, "") or "")
        except Exception:  # secrets.toml이 없을 때
            value = ""
    return value.strip() or default


class LLMError(RuntimeError):
    """LLM 호출 또는 응답 해석 실패."""


class LLM:
    def __init__(self, api_key: str, model: str, base_url: str):
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")

    def chat(self, messages: list[dict], *, temperature: float = 0.2, max_tokens: int = 1800,
             json_mode: bool = False) -> str:
        body = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body, timeout=60,
            )
            if response.status_code >= 400:
                raise LLMError(f"LLM 응답 오류 (HTTP {response.status_code})")
            return response.json()["choices"][0]["message"]["content"] or ""
        except LLMError:
            raise
        except Exception as error:  # 네트워크·형식 오류. 키가 섞일 수 있는 원문은 싣지 않는다.
            raise LLMError(f"LLM 호출 실패 ({type(error).__name__})") from None

    def json(self, messages: list[dict], **kwargs) -> dict:
        text = self.chat(messages, json_mode=True, **kwargs)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                raise LLMError("LLM이 JSON을 반환하지 않았어요") from None
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                raise LLMError("LLM JSON 해석 실패") from None
        if not isinstance(data, dict):
            raise LLMError("LLM JSON 형식 오류")
        return data


class SearchError(RuntimeError):
    """검색 API 호출 실패."""


def safe_url(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2000:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and "." in parsed.hostname


def host_matches(url: str, domain: str) -> bool:
    if not domain:
        return False
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    domain = domain.lower()
    return host == domain or host.endswith("." + domain)


class Search:
    def __init__(self, api_key: str):
        from tavily import TavilyClient

        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, *, domains: list[str] | None = None, max_results: int = 5,
               deep: bool = False) -> list[dict]:
        try:
            result = self._client.search(
                query, max_results=max_results, include_domains=domains or None,
                search_depth="advanced" if deep else "basic",
            )
        except Exception as error:
            raise SearchError(f"검색 실패 ({type(error).__name__})") from None
        hits = []
        for item in (result.get("results") or []) if isinstance(result, dict) else []:
            url = item.get("url") if isinstance(item, dict) else None
            if not safe_url(url):
                continue
            hits.append({
                "title": str(item.get("title") or url)[:200],
                "url": url,
                "content": str(item.get("content") or "")[:3000],
            })
        return hits


def build_services() -> tuple[LLM | None, Search | None]:
    llm_key = secret("LLM_API_KEY") or secret("GROQ_API_KEY")
    llm = None
    if llm_key:
        llm = LLM(llm_key, secret("LLM_MODEL") or secret("GROQ_MODEL", DEFAULT_MODEL),
                  secret("LLM_BASE_URL", DEFAULT_BASE_URL))
    search = None
    tavily_key = secret("TAVILY_API_KEY")
    if tavily_key:
        try:
            search = Search(tavily_key)
        except Exception:
            search = None
    return llm, search
