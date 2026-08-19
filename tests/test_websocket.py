"""Tests for custom_components.mattermost.websocket."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from custom_components.mattermost.websocket import (
    MattermostWebSocketClient,
    _websocket_url,
)


def _text_msg(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.TEXT
    msg.data = json.dumps(payload)
    return msg


class FakeWebSocket:
    """Fake ClientWebSocketResponse: async context manager + async iterator.

    Stops the owning client's reconnect loop on exit, so a test only has to
    reason about a single connection pass instead of an infinite retry loop.
    """

    def __init__(
        self, messages: list[MagicMock], client: MattermostWebSocketClient
    ) -> None:
        self._messages = list(messages)
        self._client = client
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._client._stopping = True
        return False


def _patched_session(fake_ws: FakeWebSocket) -> MagicMock:
    session = MagicMock()
    session.ws_connect = MagicMock(return_value=fake_ws)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


class TestWebSocketUrl:
    def test_https_to_wss(self) -> None:
        assert (
            _websocket_url("https://mm.example.com")
            == "wss://mm.example.com/api/v4/websocket"
        )

    def test_http_to_ws(self) -> None:
        assert (
            _websocket_url("http://localhost:8065")
            == "ws://localhost:8065/api/v4/websocket"
        )


async def test_sends_auth_challenge_first(hass) -> None:
    on_message = AsyncMock()
    client = MattermostWebSocketClient(
        hass, "https://mm.example.com", "tok", on_message
    )
    fake_ws = FakeWebSocket([], client)

    with patch("aiohttp.ClientSession", return_value=_patched_session(fake_ws)):
        await client._run_forever()

    assert fake_ws.sent == [
        {"seq": 1, "action": "authentication_challenge", "data": {"token": "tok"}}
    ]
    on_message.assert_not_awaited()


async def test_posted_events_forwarded(hass) -> None:
    event = {"event": "posted", "data": {"post": "{}"}}
    on_message = AsyncMock()
    client = MattermostWebSocketClient(
        hass, "https://mm.example.com", "tok", on_message
    )
    fake_ws = FakeWebSocket([_text_msg(event)], client)

    with patch("aiohttp.ClientSession", return_value=_patched_session(fake_ws)):
        await client._run_forever()

    on_message.assert_awaited_once_with(event)


async def test_non_posted_events_ignored(hass) -> None:
    event = {"event": "typing", "data": {}}
    on_message = AsyncMock()
    client = MattermostWebSocketClient(
        hass, "https://mm.example.com", "tok", on_message
    )
    fake_ws = FakeWebSocket([_text_msg(event)], client)

    with patch("aiohttp.ClientSession", return_value=_patched_session(fake_ws)):
        await client._run_forever()

    on_message.assert_not_awaited()


async def test_reconnects_with_backoff_on_drop(hass) -> None:
    on_message = AsyncMock()
    client = MattermostWebSocketClient(
        hass, "https://mm.example.com", "tok", on_message
    )

    call_count = 0

    class BrokenSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def ws_connect(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise aiohttp.ClientConnectionError("boom")

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            client._stopping = True

    with (
        patch("aiohttp.ClientSession", return_value=BrokenSession()),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        await client._run_forever()

    assert call_count == 2
    assert sleep_calls == [5, 10]


async def test_stop_prevents_further_reconnects(hass) -> None:
    on_message = AsyncMock()
    client = MattermostWebSocketClient(
        hass, "https://mm.example.com", "tok", on_message
    )
    client._stopping = True

    call_count = 0

    class BrokenSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def ws_connect(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise aiohttp.ClientConnectionError("boom")

    with patch("aiohttp.ClientSession", return_value=BrokenSession()):
        await client._run_forever()

    assert call_count == 0


async def test_async_stop_cancels_background_task(hass) -> None:
    on_message = AsyncMock()
    client = MattermostWebSocketClient(
        hass, "https://mm.example.com", "tok", on_message
    )
    fake_ws = FakeWebSocket([], client)

    with patch("aiohttp.ClientSession", return_value=_patched_session(fake_ws)):
        client.async_start()
        await client.async_stop()

    assert client._task is None
