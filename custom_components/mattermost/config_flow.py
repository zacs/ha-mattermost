"""Config flow for Mattermost integration."""

from __future__ import annotations

import logging
from typing import Any

from mattermostdriver import Driver
from mattermostdriver.exceptions import (
    InvalidOrMissingParameters,
    NotEnoughPermissions,
    ResourceNotFound,
)
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_NAME, CONF_URL
from homeassistant.core import HomeAssistant

from .const import CONF_DEFAULT_CHANNEL, DOMAIN

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_DEFAULT_CHANNEL): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.
    
    Data has the keys from CONFIG_SCHEMA with values provided by the user.
    """
    # Parse the URL to extract components for the driver
    from urllib.parse import urlparse
    parsed_url = urlparse(data[CONF_URL] if data[CONF_URL].startswith(('http://', 'https://')) else f'https://{data[CONF_URL]}')
    
    client = Driver({
        "url": parsed_url.hostname,
        "scheme": parsed_url.scheme,
        "port": parsed_url.port or (443 if parsed_url.scheme == 'https' else 80),
        "token": data[CONF_API_KEY],
        "timeout": 30,
        "request_timeout": 30,
    })

    try:
        # Test connection by getting user info (no need to login with token)
        user_info = await hass.async_add_executor_job(client.users.get_user, "me")
        username = user_info.get("username", "Mattermost")
        
        # Test if we can access the specified channel
        try:
            # Try to get channel by name (without # prefix if present)
            channel_name = data[CONF_DEFAULT_CHANNEL].lstrip("#")
            await hass.async_add_executor_job(
                client.channels.get_channel_by_name_and_team_name, 
                None, 
                channel_name
            )
        except (ResourceNotFound, InvalidOrMissingParameters):
            _LOGGER.warning(
                "Could not verify access to channel %s, but connection is working", 
                data[CONF_DEFAULT_CHANNEL]
            )
        
        return {"title": f"{username}@{data[CONF_URL]}"}
    
    except (InvalidOrMissingParameters, NotEnoughPermissions) as err:
        raise vol.Invalid("invalid_auth") from err
    except ResourceNotFound as err:
        raise vol.Invalid("cannot_connect") from err
    except Exception as err:
        _LOGGER.exception("Unexpected exception")
        raise vol.Invalid("unknown") from err
    finally:
        try:
            await hass.async_add_executor_job(client.disconnect)
        except Exception:
            pass


class MattermostConfigFlow(ConfigFlow):
    """Handle a config flow for Mattermost."""
    
    VERSION = 1
    DOMAIN = DOMAIN

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except vol.Invalid as err:
                errors["base"] = str(err)
            else:
                # Check if already configured
                await self.async_set_unique_id(f"{user_input[CONF_URL]}_{user_input[CONF_API_KEY][:8]}")
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=CONFIG_SCHEMA,
            errors=errors,
        )