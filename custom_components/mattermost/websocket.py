"""Thin transport layer for Mattermost's WebSocket event API."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

MIN_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 60


def _websocket_url(base_url: str) -> str:
    """Derive the wss://.../api/v4/websocket URL from an http(s) base URL."""
    if base_url.startswith("https://"):
        host = base_url[len("https://") :]
        scheme = "wss://"
    elif base_url.startswith("http://"):
        host = base_url[len("http://") :]
        scheme = "ws://"
    else:
        host = base_url
        scheme = "wss://"
    return f"{scheme}{host}/api/v4/websocket"


class MattermostWebSocketClient:
    """Maintains a persistent connection to Mattermost's WebSocket event API."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        token: str,
        on_message: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Initialize the websocket client."""
        self._hass = hass
        self._base_url = base_url
        self._token = token
        self._on_message = on_message
        self._task: asyncio.Task | None = None
        self._stopping = False

    def async_start(self) -> None:
        """Start the background connection loop."""
        self._stopping = False
        self._task = self._hass.async_create_background_task(
            self._run_forever(), name="mattermost_websocket"
        )

    async def async_stop(self) -> None:
        """Stop the connection loop and wait for it to exit."""
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_forever(self) -> None:
        """Connect, authenticate, and forward posted events, reconnecting on drop."""
        backoff = MIN_BACKOFF_SECONDS
        url = _websocket_url(self._base_url)

        while not self._stopping:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url, ssl=False) as ws:
                        _LOGGER.debug("Connected to Mattermost websocket at %s", url)
                        await ws.send_json(
                            {
                                "seq": 1,
                                "action": "authentication_challenge",
                                "data": {"token": self._token},
                            }
                        )
                        backoff = MIN_BACKOFF_SECONDS

                        async for msg in ws:
                            if self._stopping:
                                break
                            if msg.type != aiohttp.WSMsgType.TEXT:
                                continue
                            try:
                                event = json.loads(msg.data)
                            except ValueError:
                                _LOGGER.debug("Ignoring non-JSON websocket message")
                                continue
                            if event.get("event") != "posted":
                                continue
                            try:
                                await self._on_message(event)
                            except Exception:
                                _LOGGER.exception(
                                    "Error handling Mattermost websocket event"
                                )
            except asyncio.CancelledError:
                raise
            except Exception as err:
                if self._stopping:
                    break
                _LOGGER.warning(
                    "Mattermost websocket connection lost (%s); reconnecting in %ds",
                    err,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
