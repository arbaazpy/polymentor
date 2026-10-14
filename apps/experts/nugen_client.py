"""Thin, dependency-light client for the Nugen API.

Wraps the endpoints PolyMentor needs:
  - inference:   POST /api/v3/inference/chat/completions   (stream + non-stream)
  - documents:   POST /api/v3/documents/create, GET status
  - alignment:   POST /api/v3/alignment-projects/create, GET status
  - models:      GET  /api/v3/models/base, /api/v3/models/aligned
  - deployment:  POST /api/v3/models/{id}/deployment, GET status

Only `requests` is required. The API key is read from Django settings (which
loads it from the local .env) and is never logged.

Endpoint paths are centralised here so the one place to fix drift (seen in
exercise 1 where docs/cookbook disagreed) is this module.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger("polymentor.nugen")

DEFAULT_TIMEOUT = (10, 120)  # (connect, read) seconds


class NugenError(RuntimeError):
    """Raised when the Nugen API returns an error or is unreachable."""

    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body

    @property
    def hint(self) -> str:
        if self.status == 401:
            return "Unauthorized (401): check NUGEN_API_KEY."
        if self.status == 404:
            return "Not found (404): model id may be wrong or undeployed."
        if self.status == 409:
            return "Conflict (409): model may still be training."
        if self.status == 429:
            return "Rate limited (429): back off and retry."
        if self.status == 504:
            return "Gateway timeout (504): retry or confirm deployment."
        return self.args[0] if self.args else "Nugen request failed."


@dataclass
class ChatMessage:
    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class NugenClient:
    """Stateless wrapper around the Nugen REST API."""

    # Endpoint registry — single source of truth for paths.
    EP_CHAT = "/api/v3/inference/chat/completions"
    EP_DOCS_CREATE = "/api/v3/documents/create"
    EP_DOCS_STATUS = "/api/v3/documents/{document_id}/status"
    EP_MODELS_BASE = "/api/v3/models/base"
    EP_MODELS_ALIGNED = "/api/v3/models/aligned"
    EP_ALIGN_CREATE = "/api/v3/alignment-projects/create"
    EP_ALIGN_STATUS = "/api/v3/alignment-projects/{alignment_id}/status"
    EP_DEPLOY = "/api/v3/models/{model_id}/deployment"
    EP_DEPLOY_STATUS = "/api/v3/models/{model_id}/deployment/status"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.NUGEN_API_KEY
        self.base_url = (base_url or settings.NUGEN_BASE_URL).rstrip("/")
        self._session = session or requests.Session()
        if not self.api_key:
            logger.warning("NugenClient created without an API key set.")

    # -- internals ---------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: tuple[int, int] = DEFAULT_TIMEOUT,
    ) -> requests.Response:
        url = self._url(path)
        try:
            resp = self._session.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
                stream=stream,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise NugenError(f"Network error calling Nugen: {exc}") from exc

        if resp.status_code >= 400:
            body = _safe_body(resp)
            raise NugenError(
                f"Nugen {method} {path} failed: {resp.status_code}",
                status=resp.status_code,
                body=body,
            )
        return resp

    # -- inference ---------------------------------------------------------
    def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage] | list[dict[str, str]],
        temperature: float = 0.25,
        max_tokens: int = 512,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat completion. Returns the parsed JSON response."""
        payload = self._chat_payload(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            extra=extra,
        )
        resp = self._request("POST", self.EP_CHAT, json_body=payload)
        return resp.json()

    def chat_stream(
        self,
        *,
        model: str,
        messages: list[ChatMessage] | list[dict[str, str]],
        temperature: float = 0.25,
        max_tokens: int = 512,
        extra: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """Streaming chat completion.

        Yields incremental text deltas (already extracted from the SSE
        `data:` lines). Prefer this for longer answers to avoid 504s.
        """
        payload = self._chat_payload(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            extra=extra,
        )
        resp = self._request("POST", self.EP_CHAT, json_body=payload, stream=True)
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data:"):
                line = line[len("data:") :].strip()
            if line == "[DONE]":
                break
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Nugen returns errors (e.g. "Model not deployed") as HTTP 200 SSE
            # frames with an `error` key. Surface them instead of yielding "".
            err = chunk.get("error") if isinstance(chunk, dict) else None
            if err:
                message = err.get("message") if isinstance(err, dict) else str(err)
                code = err.get("code") if isinstance(err, dict) else None
                raise NugenError(
                    f"Nugen streaming error: {message}",
                    status=code,
                    body=json.dumps(err)[:2000],
                )
            delta = _extract_delta(chunk)
            if delta:
                yield delta

    @staticmethod
    def _chat_payload(
        *,
        model: str,
        messages: list[ChatMessage] | list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool,
        extra: dict[str, Any] | None,
    ) -> dict[str, Any]:
        norm_messages = [
            m.as_dict() if isinstance(m, ChatMessage) else m for m in messages
        ]
        payload: dict[str, Any] = {
            "model": model,
            "messages": norm_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if extra:
            payload.update(extra)
        return payload

    # -- documents ---------------------------------------------------------
    def create_document(self, *, files: list[tuple[str, bytes]], categories: list[str] | None = None) -> dict[str, Any]:
        """Upload one or more documents (multipart). Returns the parsed response.

        `files` is a list of (filename, content_bytes). Uses multipart, so we
        bypass the JSON helper and build the request directly.
        """
        url = self._url(self.EP_DOCS_CREATE)
        multipart = [("files", (name, content)) for name, content in files]
        data = {}
        if categories:
            data["categories"] = ",".join(categories)
        try:
            resp = self._session.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=multipart,
                data=data,
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise NugenError(f"Network error uploading document: {exc}") from exc
        if resp.status_code >= 400:
            raise NugenError(
                f"Document upload failed: {resp.status_code}",
                status=resp.status_code,
                body=_safe_body(resp),
            )
        return resp.json()

    def document_status(self, document_id: str) -> dict[str, Any]:
        resp = self._request("GET", self.EP_DOCS_STATUS.format(document_id=document_id))
        return resp.json()

    # -- models ------------------------------------------------------------
    def list_base_models(self) -> dict[str, Any]:
        return self._request("GET", self.EP_MODELS_BASE).json()

    def list_aligned_models(self) -> dict[str, Any]:
        return self._request("GET", self.EP_MODELS_ALIGNED).json()

    # -- alignment ---------------------------------------------------------
    def create_alignment(
        self,
        *,
        name: str,
        base_model: str,
        document_ids: list[str],
        benchmark_id: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "base_model": base_model,
            "document_ids": document_ids,
            "description": description,
        }
        if benchmark_id:
            payload["benchmark_id"] = benchmark_id
        return self._request("POST", self.EP_ALIGN_CREATE, json_body=payload).json()

    def alignment_status(self, alignment_id: str) -> dict[str, Any]:
        return self._request("GET", self.EP_ALIGN_STATUS.format(alignment_id=alignment_id)).json()

    # -- deployment --------------------------------------------------------
    def deploy_model(self, model_id: str, *, early: bool = False) -> dict[str, Any]:
        path = self.EP_DEPLOY.format(model_id=model_id)
        if early:
            path += "?early=true"
        return self._request("POST", path).json()

    def deployment_status(self, model_id: str) -> dict[str, Any]:
        return self._request("GET", self.EP_DEPLOY_STATUS.format(model_id=model_id)).json()


def _safe_body(resp: requests.Response) -> str:
    try:
        return resp.text[:2000]
    except Exception:  # pragma: no cover - defensive
        return "<unreadable body>"


def _extract_delta(chunk: dict[str, Any]) -> str:
    """Pull the incremental text from an OpenAI-style streaming chunk."""
    try:
        choices = chunk.get("choices") or []
        if not choices:
            return ""
        choice = choices[0]
        # streaming: {"choices":[{"delta":{"content":"..."}}]}
        delta = choice.get("delta") or {}
        if "content" in delta and delta["content"]:
            return delta["content"]
        # some servers send full message objects
        message = choice.get("message") or {}
        if "content" in message and message["content"]:
            return message["content"]
    except (AttributeError, IndexError, TypeError):
        return ""
    return ""


def extract_full_text(response: dict[str, Any]) -> str:
    """Pull the complete assistant text from a non-streaming chat response."""
    try:
        choices = response.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content", "") or ""
    except (AttributeError, IndexError, TypeError):
        return ""
