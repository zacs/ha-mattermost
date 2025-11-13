"""The Mattermost integration."""

from __future__ import annotations

import logging

from mattermostdriver import Driver
from mattermostdriver.exceptions import (
    InvalidOrMissingParameters,
    NotEnoughPermissions,
    ResourceNotFound,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_DEFAULT_CHANNEL,
    DATA_CLIENT,
    DATA_HASS_CONFIG,
    DOMAIN,
    MATTERMOST_DATA,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NOTIFY]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Mattermost component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mattermost from a config entry."""
    config = entry.data

    try:
        # Parse the URL to extract components for the driver
        from urllib.parse import urlparse
        parsed_url = urlparse(config[CONF_URL] if config[CONF_URL].startswith(('http://', 'https://')) else f'https://{config[CONF_URL]}')
        
        client = Driver({
            "url": parsed_url.hostname,
            "scheme": parsed_url.scheme,
            "port": parsed_url.port or (443 if parsed_url.scheme == 'https' else 80),
            "token": config[CONF_API_KEY],
            "timeout": 30,
            "request_timeout": 30,
        })
        
        # Test connection by getting user info (no need to login with token)
        await hass.async_add_executor_job(client.users.get_user, "me")
        
    except (InvalidOrMissingParameters, NotEnoughPermissions, ResourceNotFound) as err:
        _LOGGER.error("Failed to connect to Mattermost: %s", err)
        raise ConfigEntryNotReady from err
    except Exception as err:
        _LOGGER.error("Unexpected error connecting to Mattermost: %s", err)
        raise ConfigEntryNotReady from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_HASS_CONFIG: config,
    }

    # Set up notify platform
    discovery.load_platform(
        hass,
        Platform.NOTIFY,
        DOMAIN,
        {MATTERMOST_DATA: hass.data[DOMAIN][entry.entry_id]},
        {DOMAIN: {}},
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        # Disconnect the client
        client = hass.data[DOMAIN][entry.entry_id].get(DATA_CLIENT)
        if client:
            await hass.async_add_executor_job(client.disconnect)
        
        hass.data[DOMAIN].pop(entry.entry_id)

    return True