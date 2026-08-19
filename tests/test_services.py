"""Tests for the mattermost.send_message service (custom_components.mattermost.services)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.mattermost.const import (
    CONF_DEFAULT_CHANNEL,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_HASS_CONFIG,
    DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from custom_components.mattermost.services import async_register_services

CHANNEL_ID = "a" * 26


def _make_client():
    client = AsyncMock()
    client.resolve_channel_id = AsyncMock(return_value=CHANNEL_ID)
    client.post_message = AsyncMock(return_value=True)
    client.upload_file = AsyncMock(return_value=True)
    return client


async def test_service_registered_once_across_entries(hass, mock_config_entry):
    await async_register_services(hass)
    await async_register_services(hass)  # simulate a second config entry's setup

    assert hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE)


async def test_routes_to_targeted_entry(hass):
    await async_register_services(hass)

    client_a = _make_client()
    client_b = _make_client()
    hass.data[DOMAIN] = {
        "entry_a": {DATA_CLIENT: client_a, DATA_COORDINATOR: None},
        "entry_b": {DATA_CLIENT: client_b, DATA_COORDINATOR: None},
    }

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {
            "config_entry_id": "entry_a",
            "message": "hello",
            "target": ["general"],
        },
        blocking=True,
    )

    client_a.post_message.assert_awaited_once()
    client_b.post_message.assert_not_awaited()


async def test_missing_target_with_multiple_entries_raises(hass):
    await async_register_services(hass)

    hass.data[DOMAIN] = {
        "entry_a": {DATA_CLIENT: _make_client(), DATA_COORDINATOR: None},
        "entry_b": {DATA_CLIENT: _make_client(), DATA_COORDINATOR: None},
    }

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {"message": "hello", "target": ["general"]},
            blocking=True,
        )


async def test_single_loaded_entry_implicit_target(hass):
    await async_register_services(hass)

    client = _make_client()
    hass.data[DOMAIN] = {"only_entry": {DATA_CLIENT: client, DATA_COORDINATOR: None}}

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {"message": "hello", "target": ["general"]},
        blocking=True,
    )

    client.post_message.assert_awaited_once()


async def test_attachments_and_multi_target_partial_failure(hass):
    await async_register_services(hass)

    client = _make_client()

    async def resolve_side_effect(target):
        return CHANNEL_ID if target == "ok" else None

    client.resolve_channel_id.side_effect = resolve_side_effect
    hass.data[DOMAIN] = {"only_entry": {DATA_CLIENT: client, DATA_COORDINATOR: None}}

    from homeassistant.exceptions import HomeAssistantError

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            {
                "message": "hello",
                "target": ["ok", "bad"],
                "attachments": [{"text": "attach"}],
            },
            blocking=True,
        )

    client.post_message.assert_awaited_once()
    _, kwargs = client.post_message.call_args
    assert kwargs["props"]["attachments"][0]["author_name"] == "Home Assistant"


async def test_omitted_target_defaults_to_entry_default_channel(hass):
    await async_register_services(hass)

    client = _make_client()
    hass.data[DOMAIN] = {
        "only_entry": {
            DATA_CLIENT: client,
            DATA_COORDINATOR: None,
            DATA_HASS_CONFIG: {CONF_DEFAULT_CHANNEL: "general"},
        }
    }

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {"message": "hello"},
        blocking=True,
    )

    client.resolve_channel_id.assert_awaited_with("general")
    client.post_message.assert_awaited_once()


async def test_local_file_routes_through_upload(hass, tmp_path):
    await async_register_services(hass)

    client = _make_client()
    hass.data[DOMAIN] = {"only_entry": {DATA_CLIENT: client, DATA_COORDINATOR: None}}
    hass.config.allowlist_external_dirs.add(str(tmp_path))

    file_path = tmp_path / "test.txt"
    file_path.write_text("data")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        {
            "message": "hello",
            "target": ["general"],
            "file": {"path": str(file_path)},
        },
        blocking=True,
    )

    client.upload_file.assert_awaited_once()
