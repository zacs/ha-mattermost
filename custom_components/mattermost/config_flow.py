"""Config flow for Mattermost integration."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import callback

from .api import normalize_base_url
from .const import (
    CONF_ASSIST_AGENT_ID,
    CONF_DEFAULT_CHANNEL,
    CONF_ENABLE_ASSIST_BRIDGE,
    DEFAULT_ENABLE_ASSIST_BRIDGE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _title_for(url: str) -> str:
    """Derive a UI-distinguishing title for a config entry from its server URL."""
    hostname = urlparse(normalize_base_url(url)).hostname or url
    return f"Mattermost ({hostname})"


class MattermostFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mattermost."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        return await self._async_step_connect(user_input, is_reconfigure=False)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        return await self._async_step_connect(user_input, is_reconfigure=True)

    async def _async_step_connect(
        self, user_input: dict[str, Any] | None, is_reconfigure: bool
    ) -> ConfigFlowResult:
        """Shared logic for the user and reconfigure steps."""
        errors = {}
        step_id = "reconfigure" if is_reconfigure else "user"

        if user_input is not None:
            error, info = await self._async_try_connect(
                user_input[CONF_API_KEY],
                user_input[CONF_URL],
                user_input[CONF_DEFAULT_CHANNEL],
            )
            if error is not None:
                errors["base"] = error
            elif info is not None:
                await self.async_set_unique_id(
                    f"{user_input[CONF_URL]}_{user_input[CONF_API_KEY][:8]}"
                )
                if is_reconfigure:
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(),
                        data_updates=user_input,
                    )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_title_for(user_input[CONF_URL]),
                    data=user_input,
                )

        defaults = self._get_reconfigure_entry().data if is_reconfigure else {}
        schema = vol.Schema(
            {
                vol.Required(CONF_URL): str,
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_DEFAULT_CHANNEL): str,
            }
        )
        if defaults:
            schema = self.add_suggested_values_to_schema(schema, defaults)

        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> MattermostOptionsFlowHandler:
        """Create the options flow."""
        return MattermostOptionsFlowHandler()

    async def _async_try_connect(
        self, token: str, url: str, channel: str
    ) -> tuple[str, None] | tuple[None, dict[str, str]]:
        """Try connecting to Mattermost."""
        try:
            _LOGGER.debug("Testing connection with URL: %s", url)

            test_url = normalize_base_url(url)
            parsed_url = urlparse(test_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.hostname}"
            if parsed_url.port:
                base_url += f":{parsed_url.port}"

            # Test basic server connectivity
            async with aiohttp.ClientSession() as session:
                ping_url = f"{base_url}/api/v4/system/ping"
                try:
                    async with session.get(
                        ping_url, timeout=aiohttp.ClientTimeout(total=10), ssl=False
                    ) as ping_response:
                        if ping_response.status != 200:
                            return "cannot_connect", None
                except Exception:
                    return "cannot_connect", None

                # Test bot token authentication
                headers = {"Authorization": f"Bearer {token}"}
                config_url = f"{base_url}/api/v4/config/client"

                async with session.get(
                    config_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as response:
                    if response.status == 200:
                        server_name = f"Bot@{parsed_url.hostname}"
                        return None, {"server": server_name}
                    elif response.status == 401:
                        return "invalid_auth", None

                # If config endpoint fails, try webhooks (bots often have webhook permissions)
                webhooks_url = f"{base_url}/api/v4/hooks/incoming"
                async with session.get(
                    webhooks_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as response:
                    if response.status in (200, 403):
                        # 403 means authenticated but no permission - token is valid!
                        server_name = f"Bot@{parsed_url.hostname}"
                        return None, {"server": server_name}

                return "invalid_auth", None

        except aiohttp.ClientError:
            return "cannot_connect", None
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return "unknown", None


class MattermostOptionsFlowHandler(OptionsFlow):
    """Handle Mattermost options (the Assist chat bridge toggle)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENABLE_ASSIST_BRIDGE,
                    default=current.get(
                        CONF_ENABLE_ASSIST_BRIDGE, DEFAULT_ENABLE_ASSIST_BRIDGE
                    ),
                ): bool,
                vol.Optional(
                    CONF_ASSIST_AGENT_ID,
                    description={"suggested_value": current.get(CONF_ASSIST_AGENT_ID)},
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
