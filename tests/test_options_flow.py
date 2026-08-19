"""Tests for the Mattermost options flow (the Assist bridge toggle)."""

from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType

from custom_components.mattermost.const import CONF_ENABLE_ASSIST_BRIDGE


async def test_default_is_disabled(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["data_schema"]({})[CONF_ENABLE_ASSIST_BRIDGE] is False


async def test_toggle_persists_to_options(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ENABLE_ASSIST_BRIDGE: True},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_ENABLE_ASSIST_BRIDGE] is True


async def test_toggle_off_persists(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_ENABLE_ASSIST_BRIDGE: True}
    )

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ENABLE_ASSIST_BRIDGE: False},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_ENABLE_ASSIST_BRIDGE] is False
