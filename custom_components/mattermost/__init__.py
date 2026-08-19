"""The Mattermost integration."""

from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_NAME, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import discovery
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .api import MattermostHTTPClient, normalize_base_url
from .assist_bridge import MattermostAssistBridge
from .const import (
    CONF_ENABLE_ASSIST_BRIDGE,
    DATA_ASSIST_BRIDGE,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_HASS_CONFIG,
    DEFAULT_ENABLE_ASSIST_BRIDGE,
    DOMAIN,
    ISSUE_DEPRECATED_NOTIFY_SERVICE,
)
from .coordinator import MattermostDataUpdateCoordinator
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NOTIFY]

# Config entry only - no YAML configuration supported
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Mattermost component."""
    await async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mattermost from a config entry."""
    config = entry.data

    try:
        url = normalize_base_url(config[CONF_URL])

        # Create HTTP client
        client = MattermostHTTPClient(hass, url, config[CONF_API_KEY])

        # Set up the coordinator and perform the initial connectivity check.
        # async_config_entry_first_refresh raises ConfigEntryNotReady on failure.
        coordinator = MattermostDataUpdateCoordinator(hass, entry, client)
        await coordinator.async_config_entry_first_refresh()

    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.error("Failed to connect to Mattermost: %s", err)
        raise ConfigEntryNotReady from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
        DATA_HASS_CONFIG: config,
    }

    # Set up the binary_sensor and notify-entity platforms via the standard
    # config-entry mechanism.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Also set up the legacy notify.mattermost service via discovery (soft-deprecated).
    discovery_data = hass.data[DOMAIN][entry.entry_id].copy()
    discovery_data[CONF_NAME] = "mattermost"

    await discovery.async_load_platform(
        hass,
        Platform.NOTIFY,
        DOMAIN,
        discovery_data,
        config,
    )

    # notify.mattermost (registered above) is soft-deprecated. This must run
    # here rather than from notify.py's get_service(), which HA's legacy
    # notify platform calls from an executor thread -- issue_registry calls
    # require the event loop.
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_DEPRECATED_NOTIFY_SERVICE,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_DEPRECATED_NOTIFY_SERVICE,
    )

    # Optionally start the Mattermost -> Assist chat bridge.
    bridge = None
    if entry.options.get(CONF_ENABLE_ASSIST_BRIDGE, DEFAULT_ENABLE_ASSIST_BRIDGE):
        bridge = MattermostAssistBridge(hass, entry, client)
        await bridge.async_setup()
    hass.data[DOMAIN][entry.entry_id][DATA_ASSIST_BRIDGE] = bridge

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change (e.g. the Assist bridge toggle)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        entry_data = hass.data[DOMAIN][entry.entry_id]
        bridge = entry_data.get(DATA_ASSIST_BRIDGE)
        if bridge is not None:
            await bridge.async_unload()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
