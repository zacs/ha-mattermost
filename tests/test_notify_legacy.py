"""Tests for the legacy notify.mattermost service (custom_components.mattermost.notify)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

import custom_components.mattermost.notify as notify_mod
from custom_components.mattermost.notify import MattermostNotificationService

CHANNEL_ID = "a" * 26


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.resolve_channel_id = AsyncMock(return_value=CHANNEL_ID)
    client.post_message = AsyncMock(return_value=True)
    client.upload_file = AsyncMock(return_value=True)
    return client


@pytest.fixture(autouse=True)
def _reset_deprecation_flag():
    notify_mod._deprecation_warned = False
    yield
    notify_mod._deprecation_warned = False


async def test_send_text_message(hass, mock_client):
    service = MattermostNotificationService(
        hass, mock_client, {"default_channel": "general"}
    )
    await service.async_send_message("hello", title="Hi", target=["general"])
    mock_client.resolve_channel_id.assert_awaited_with("general")
    mock_client.post_message.assert_awaited_once()
    args, _ = mock_client.post_message.call_args
    assert args[0] == CHANNEL_ID
    assert "hello" in args[1]
    assert "Hi" in args[1]


async def test_send_local_file_message(hass, mock_client, tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("data")
    hass.config.allowlist_external_dirs.add(str(tmp_path))

    service = MattermostNotificationService(
        hass, mock_client, {"default_channel": "general"}
    )
    await service.async_send_message(
        "hello",
        target=["general"],
        data={"file": {"path": str(file_path)}},
    )
    mock_client.upload_file.assert_awaited_once()


async def test_multi_target_partial_failure_raises(hass, mock_client):
    async def resolve_side_effect(target):
        return CHANNEL_ID if target == "ok" else None

    mock_client.resolve_channel_id.side_effect = resolve_side_effect

    service = MattermostNotificationService(
        hass, mock_client, {"default_channel": "general"}
    )
    with pytest.raises(HomeAssistantError, match="bad"):
        await service.async_send_message("hello", target=["ok", "bad"])
    mock_client.post_message.assert_awaited_once()


async def test_default_author_injected_into_attachments(hass, mock_client):
    service = MattermostNotificationService(
        hass, mock_client, {"default_channel": "general"}
    )
    await service.async_send_message(
        "hello",
        target=["general"],
        data={"attachments": [{"text": "an attachment"}]},
    )
    _, kwargs = mock_client.post_message.call_args
    attachments = kwargs["props"]["attachments"]
    assert attachments[0]["author_name"] == "Home Assistant"
    assert "author_icon" in attachments[0]


async def test_custom_author_not_overridden(hass, mock_client):
    service = MattermostNotificationService(
        hass, mock_client, {"default_channel": "general"}
    )
    await service.async_send_message(
        "hello",
        target=["general"],
        data={"attachments": [{"text": "x", "author_name": "Custom"}]},
    )
    _, kwargs = mock_client.post_message.call_args
    assert kwargs["props"]["attachments"][0]["author_name"] == "Custom"


async def test_deprecation_warning_logged_once(hass, mock_client, caplog):
    with caplog.at_level("WARNING"):
        MattermostNotificationService(hass, mock_client, {"default_channel": "general"})
        MattermostNotificationService(hass, mock_client, {"default_channel": "general"})

    deprecation_logs = [r for r in caplog.records if "deprecated" in r.message]
    assert len(deprecation_logs) == 1
