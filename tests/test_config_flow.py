"""Tests for custom_components.mattermost.config_flow."""

from __future__ import annotations

import pytest
from aioresponses import aioresponses
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.mattermost.const import DOMAIN

from .conftest import TEST_CHANNEL, TEST_TOKEN, TEST_URL

PING_URL = f"{TEST_URL}/api/v4/system/ping"
CONFIG_CLIENT_URL = f"{TEST_URL}/api/v4/config/client"


def _mock_successful_connect(mocked: aioresponses) -> None:
    mocked.get(PING_URL, status=200, payload={})
    mocked.get(CONFIG_CLIENT_URL, status=200, payload={})


async def test_user_flow_creates_entry_with_host_title(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM

    with aioresponses() as mocked:
        _mock_successful_connect(mocked)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "url": TEST_URL,
                "api_key": TEST_TOKEN,
                "default_channel": TEST_CHANNEL,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Mattermost (mattermost.example.com)"


async def test_duplicate_unique_id_aborts(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with aioresponses() as mocked:
        _mock_successful_connect(mocked)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "url": TEST_URL,
                "api_key": TEST_TOKEN,
                "default_channel": TEST_CHANNEL,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_updates_data_and_reloads(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_channel = "alerts"
    with aioresponses() as mocked:
        _mock_successful_connect(mocked)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "url": TEST_URL,
                "api_key": TEST_TOKEN,
                "default_channel": new_channel,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].data["default_channel"] == new_channel


async def test_reconfigure_mismatched_server_aborts(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)

    with aioresponses() as mocked:
        _mock_successful_connect_for(mocked, "https://different.example.com")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "url": "https://different.example.com",
                "api_key": TEST_TOKEN,
                "default_channel": TEST_CHANNEL,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"


@pytest.mark.parametrize("is_reconfigure", [False, True])
async def test_cannot_connect_error(hass, mock_config_entry, is_reconfigure):
    if is_reconfigure:
        mock_config_entry.add_to_hass(hass)
        result = await mock_config_entry.start_reconfigure_flow(hass)
    else:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

    with aioresponses() as mocked:
        mocked.get(PING_URL, status=500, body="down")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "url": TEST_URL,
                "api_key": TEST_TOKEN,
                "default_channel": TEST_CHANNEL,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.parametrize("is_reconfigure", [False, True])
async def test_invalid_auth_error(hass, mock_config_entry, is_reconfigure):
    if is_reconfigure:
        mock_config_entry.add_to_hass(hass)
        result = await mock_config_entry.start_reconfigure_flow(hass)
    else:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

    with aioresponses() as mocked:
        mocked.get(PING_URL, status=200, payload={})
        mocked.get(CONFIG_CLIENT_URL, status=401, body="unauthorized")
        mocked.get(f"{TEST_URL}/api/v4/hooks/incoming", status=401, body="unauthorized")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "url": TEST_URL,
                "api_key": TEST_TOKEN,
                "default_channel": TEST_CHANNEL,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_two_entries_get_distinguishable_titles(hass):
    with aioresponses() as mocked:
        _mock_successful_connect_for(mocked, "https://mm-one.example.com")
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "url": "https://mm-one.example.com",
                "api_key": TEST_TOKEN,
                "default_channel": TEST_CHANNEL,
            },
        )
    assert result["title"] == "Mattermost (mm-one.example.com)"

    with aioresponses() as mocked:
        _mock_successful_connect_for(mocked, "https://mm-two.example.com")
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "url": "https://mm-two.example.com",
                "api_key": TEST_TOKEN,
                "default_channel": TEST_CHANNEL,
            },
        )
    assert result["title"] == "Mattermost (mm-two.example.com)"

    entries = hass.config_entries.async_entries(DOMAIN)
    assert {e.title for e in entries} == {
        "Mattermost (mm-one.example.com)",
        "Mattermost (mm-two.example.com)",
    }


def _mock_successful_connect_for(mocked: aioresponses, base_url: str) -> None:
    mocked.get(f"{base_url}/api/v4/system/ping", status=200, payload={})
    mocked.get(f"{base_url}/api/v4/config/client", status=200, payload={})
