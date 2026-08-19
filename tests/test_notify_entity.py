"""Tests for the MattermostNotifyEntity (custom_components.mattermost.notify)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.mattermost.const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN
from custom_components.mattermost.notify import (
    MattermostNotifyEntity,
    async_setup_entry,
)

CHANNEL_ID = "a" * 26


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.resolve_channel_id = AsyncMock(return_value=CHANNEL_ID)
    client.post_message = AsyncMock(return_value=True)
    return client


async def test_async_setup_entry_adds_one_entity(hass, mock_config_entry, mock_client):
    mock_config_entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][mock_config_entry.entry_id] = {
        DATA_CLIENT: mock_client,
        DATA_COORDINATOR: None,
    }

    added = []

    def _add_entities(entities):
        added.extend(entities)

    await async_setup_entry(hass, mock_config_entry, _add_entities)

    assert len(added) == 1
    assert isinstance(added[0], MattermostNotifyEntity)


async def test_send_message_uses_entry_default_channel(mock_config_entry, mock_client):
    from custom_components.mattermost.services import MattermostMessenger

    messenger = MattermostMessenger(MagicMock(), mock_client, None)
    entity = MattermostNotifyEntity(mock_config_entry, messenger, "general")

    await entity.async_send_message("hello", title="Hi")

    mock_client.resolve_channel_id.assert_awaited_with("general")
    mock_client.post_message.assert_awaited_once()


def test_unique_id_and_device_info(mock_config_entry, mock_client):
    from custom_components.mattermost.services import MattermostMessenger

    messenger = MattermostMessenger(MagicMock(), mock_client, None)
    entity = MattermostNotifyEntity(mock_config_entry, messenger, "general")

    assert entity.unique_id == f"{mock_config_entry.entry_id}_notify"
    assert (DOMAIN, mock_config_entry.entry_id) in entity.device_info["identifiers"]
