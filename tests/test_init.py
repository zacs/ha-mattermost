"""Tests for custom_components.mattermost.__init__ (async_setup_entry)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.helpers import issue_registry as ir

from custom_components.mattermost import async_setup_entry
from custom_components.mattermost.const import DOMAIN, ISSUE_DEPRECATED_NOTIFY_SERVICE


async def test_deprecation_repair_issue_created_on_setup(hass, mock_config_entry):
    """The notify.mattermost deprecation issue must be raised from the event loop.

    HA's legacy notify platform calls notify.py's get_service() from an
    executor thread, so issue_registry calls can't live there -- this is a
    regression test for that: async_setup_entry (which always runs on the
    event loop) is responsible for creating the issue instead.
    """
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
        patch.object(
            hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
        ),
    ):
        client_cls.return_value.test_connection = AsyncMock(return_value=True)
        coordinator_cls.return_value.async_config_entry_first_refresh = AsyncMock()
        coordinator_cls.return_value.last_update_success = True

        await async_setup_entry(hass, mock_config_entry)

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, ISSUE_DEPRECATED_NOTIFY_SERVICE)
    assert issue is not None
