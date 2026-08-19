"""Tests for custom_components.mattermost.assist_bridge."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.mattermost.assist_bridge import (
    FALLBACK_REPLY,
    MattermostAssistBridge,
)
from custom_components.mattermost.const import (
    CONF_ENABLE_ASSIST_BRIDGE,
    DATA_ASSIST_BRIDGE,
    DOMAIN,
)

BOT_USER_ID = "bot-user-id"
BOT_USERNAME = "habot"


def _post_event(
    *, user_id: str, message: str, channel_id: str = "chan1", channel_type: str = "O"
) -> dict:
    post = {"user_id": user_id, "message": message, "channel_id": channel_id}
    return {
        "event": "posted",
        "data": {"post": json.dumps(post), "channel_type": channel_type},
    }


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.base_url = "https://mattermost.example.com"
    client.token = "tok"
    client.get_me = AsyncMock(
        return_value={"id": BOT_USER_ID, "username": BOT_USERNAME}
    )
    client.post_message = AsyncMock(return_value=True)
    return client


@pytest.fixture
def bridge(hass, mock_config_entry, mock_client):
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.mattermost.assist_bridge.MattermostWebSocketClient"
    ) as ws_cls:
        ws_cls.return_value.async_start = MagicMock()
        b = MattermostAssistBridge(hass, mock_config_entry, mock_client)
        b._ws_client = ws_cls.return_value
    return b


def _mock_converse_result(speech: str | None):
    result = MagicMock()
    result.response.speech = {"plain": {"speech": speech}} if speech else {}
    return result


async def test_setup_fetches_bot_identity_and_starts_ws(bridge, mock_client):
    await bridge.async_setup()
    mock_client.get_me.assert_awaited_once()
    bridge._ws_client.async_start.assert_called_once()
    assert bridge._bot_user_id == BOT_USER_ID


async def test_dm_always_relays(bridge, mock_client):
    await bridge.async_setup()
    event = _post_event(
        user_id="someone-else", message="turn on the lights", channel_type="D"
    )

    with patch(
        "custom_components.mattermost.assist_bridge.conversation.async_converse",
        new=AsyncMock(return_value=_mock_converse_result("Lights on")),
    ) as converse:
        await bridge._async_handle_posted_event(event)

    converse.assert_awaited_once()
    _, kwargs = converse.call_args
    assert kwargs["text"] == "turn on the lights"
    mock_client.post_message.assert_awaited_once_with("chan1", "Lights on")


async def test_mention_in_channel_relays_and_strips_token(bridge, mock_client):
    await bridge.async_setup()
    event = _post_event(
        user_id="someone-else",
        message=f"@{BOT_USERNAME} what's the weather",
        channel_type="O",
    )

    with patch(
        "custom_components.mattermost.assist_bridge.conversation.async_converse",
        new=AsyncMock(return_value=_mock_converse_result("Sunny")),
    ) as converse:
        await bridge._async_handle_posted_event(event)

    converse.assert_awaited_once()
    _, kwargs = converse.call_args
    assert kwargs["text"] == "what's the weather"


async def test_channel_message_without_mention_ignored(bridge, mock_client):
    await bridge.async_setup()
    event = _post_event(
        user_id="someone-else", message="just chatting", channel_type="O"
    )

    with patch(
        "custom_components.mattermost.assist_bridge.conversation.async_converse",
        new=AsyncMock(),
    ) as converse:
        await bridge._async_handle_posted_event(event)

    converse.assert_not_awaited()
    mock_client.post_message.assert_not_awaited()


async def test_self_authored_posts_always_ignored(bridge, mock_client):
    await bridge.async_setup()
    event = _post_event(user_id=BOT_USER_ID, message="hello", channel_type="D")

    with patch(
        "custom_components.mattermost.assist_bridge.conversation.async_converse",
        new=AsyncMock(),
    ) as converse:
        await bridge._async_handle_posted_event(event)

    converse.assert_not_awaited()
    mock_client.post_message.assert_not_awaited()


async def test_reply_goes_to_incoming_channel_id_no_resolve(bridge, mock_client):
    await bridge.async_setup()
    event = _post_event(
        user_id="someone-else", message="hi", channel_type="D", channel_id="chan-xyz"
    )

    with patch(
        "custom_components.mattermost.assist_bridge.conversation.async_converse",
        new=AsyncMock(return_value=_mock_converse_result("hello")),
    ):
        await bridge._async_handle_posted_event(event)

    mock_client.post_message.assert_awaited_once_with("chan-xyz", "hello")
    mock_client.resolve_channel_id.assert_not_awaited()


async def test_converse_error_posts_fallback(bridge, mock_client):
    await bridge.async_setup()
    event = _post_event(user_id="someone-else", message="hi", channel_type="D")

    with patch(
        "custom_components.mattermost.assist_bridge.conversation.async_converse",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await bridge._async_handle_posted_event(event)

    mock_client.post_message.assert_awaited_once_with("chan1", FALLBACK_REPLY)


async def test_empty_speech_posts_fallback(bridge, mock_client):
    await bridge.async_setup()
    event = _post_event(user_id="someone-else", message="hi", channel_type="D")

    with patch(
        "custom_components.mattermost.assist_bridge.conversation.async_converse",
        new=AsyncMock(return_value=_mock_converse_result(None)),
    ):
        await bridge._async_handle_posted_event(event)

    mock_client.post_message.assert_awaited_once_with("chan1", FALLBACK_REPLY)


async def test_bridge_not_constructed_when_option_off(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    from custom_components.mattermost import async_setup_entry

    with (
        patch("custom_components.mattermost.MattermostHTTPClient") as client_cls,
        patch(
            "custom_components.mattermost.MattermostDataUpdateCoordinator"
        ) as coordinator_cls,
        patch(
            "custom_components.mattermost.discovery.async_load_platform",
            new=AsyncMock(),
        ),
    ):
        client_cls.return_value.test_connection = AsyncMock(return_value=True)
        coordinator_cls.return_value.async_config_entry_first_refresh = AsyncMock()
        coordinator_cls.return_value.last_update_success = True

        with patch.object(
            hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
        ):
            await async_setup_entry(hass, mock_config_entry)

    assert hass.data[DOMAIN][mock_config_entry.entry_id][DATA_ASSIST_BRIDGE] is None


async def test_toggling_option_on_reloads_and_activates_bridge(hass, mock_config_entry):
    """Flipping the options-flow toggle reloads the entry and starts the bridge."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch("custom_components.mattermost.MattermostHTTPClient") as client_cls,
        patch(
            "custom_components.mattermost.MattermostDataUpdateCoordinator"
        ) as coordinator_cls,
        patch(
            "custom_components.mattermost.discovery.async_load_platform",
            new=AsyncMock(),
        ),
        patch("custom_components.mattermost.MattermostAssistBridge") as bridge_cls,
        patch.object(
            hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
        ),
    ):
        client_cls.return_value.test_connection = AsyncMock(return_value=True)
        coordinator_cls.return_value.async_config_entry_first_refresh = AsyncMock()
        bridge_cls.return_value.async_setup = AsyncMock()
        bridge_cls.return_value.async_unload = AsyncMock()

        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        assert hass.data[DOMAIN][mock_config_entry.entry_id][DATA_ASSIST_BRIDGE] is None

        hass.config_entries.async_update_entry(
            mock_config_entry, options={CONF_ENABLE_ASSIST_BRIDGE: True}
        )
        await hass.async_block_till_done()

        bridge_cls.return_value.async_setup.assert_awaited()
        assert (
            hass.data[DOMAIN][mock_config_entry.entry_id][DATA_ASSIST_BRIDGE]
            is bridge_cls.return_value
        )
