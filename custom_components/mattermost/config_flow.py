"""Config flow for Mattermost integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_URL

from .const import CONF_DEFAULT_CHANNEL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class MattermostFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mattermost."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors = {}

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
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Mattermost",
                    data=user_input,
                )

        user_input = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL): str,
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(CONF_DEFAULT_CHANNEL): str,
                }
            ),
            errors=errors,
        )

    async def _async_try_connect(
        self, token: str, url: str, channel: str
    ) -> tuple[str, None] | tuple[None, dict[str, str]]:
        """Try connecting to Mattermost."""
        try:
            # Parse the URL to extract components for the driver
            from urllib.parse import urlparse

            _LOGGER.debug("Testing connection with URL: %s", url)

            # Handle various URL formats - clean up if user included API path
            clean_url = url
            if "/api/v4" in clean_url:
                # Remove API path if user included it
                clean_url = clean_url.split("/api/v4")[0]

            # Handle various URL formats
            if not clean_url.startswith(("http://", "https://")):
                # Default to HTTP for local IPs, HTTPS for domains
                if (
                    clean_url.startswith("192.168.")
                    or clean_url.startswith("10.")
                    or clean_url.startswith("127.")
                    or "localhost" in clean_url
                ):
                    test_url = f"http://{clean_url}"
                else:
                    test_url = f"https://{clean_url}"
            else:
                test_url = clean_url

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
