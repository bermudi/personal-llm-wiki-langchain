"""Minimal Telegram Bot API client for long polling and replies."""

from __future__ import annotations

import json
from pathlib import Path
from urllib import error, request

_MAX_TELEGRAM_MESSAGE_LEN = 4000


class TelegramApiError(RuntimeError):
    """Raised when the Telegram Bot API returns an error."""


def split_telegram_text(text: str, *, limit: int = _MAX_TELEGRAM_MESSAGE_LEN) -> list[str]:
    """Split a long response into Telegram-safe message chunks."""
    cleaned = text.strip() or "(empty response)"
    chunks: list[str] = []

    while len(cleaned) > limit:
        split_at = cleaned.rfind("\n\n", 0, limit + 1)
        if split_at < limit // 2:
            split_at = cleaned.rfind("\n", 0, limit + 1)
        if split_at < limit // 2:
            split_at = cleaned.rfind(" ", 0, limit + 1)
        if split_at < limit // 2:
            split_at = limit

        chunk = cleaned[:split_at].rstrip()
        if not chunk:
            chunk = cleaned[:limit]
            split_at = limit

        chunks.append(chunk)
        cleaned = cleaned[split_at:].lstrip()

    chunks.append(cleaned)
    return chunks


class TelegramClient:
    """Tiny Telegram Bot API wrapper using the stdlib only."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

    def _request(self, method: str, payload: dict | None = None, *, timeout: int = 60) -> object:
        data = json.dumps(payload or {}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TelegramApiError(f"HTTP {exc.code} calling {method}: {detail}") from exc
        except error.URLError as exc:
            raise TelegramApiError(f"Network error calling {method}: {exc.reason}") from exc

        if not body.get("ok"):
            raise TelegramApiError(f"Telegram {method} failed: {body.get('description', 'unknown error')}")
        return body.get("result")

    def delete_webhook(self, *, drop_pending_updates: bool = False) -> None:
        self._request("deleteWebhook", {"drop_pending_updates": drop_pending_updates}, timeout=15)

    def get_updates(
        self,
        *,
        offset: int | None,
        timeout: int = 30,
        allowed_updates: list[str] | None = None,
    ) -> list[dict]:
        payload: dict[str, object] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        result = self._request("getUpdates", payload, timeout=timeout + 15)
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: int, text: str) -> None:
        self._request("sendMessage", {"chat_id": chat_id, "text": text}, timeout=30)

    def download_file(self, file_id: str, dest: Path, *, timeout: int = 60) -> Path:
        """Download a file by its file_id to *dest*. Returns the written path."""
        # 1. getFilePath
        result = self._request("getFile", {"file_id": file_id}, timeout=15)
        file_path = result["file_path"]  # type: ignore[index]
        download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"

        dest.parent.mkdir(parents=True, exist_ok=True)
        req = request.Request(download_url)
        with request.urlopen(req, timeout=timeout) as resp:
            dest.write_bytes(resp.read())
        return dest

    def send_messages(self, chat_id: int, text: str) -> None:
        for chunk in split_telegram_text(text):
            self.send_message(chat_id, chunk)
