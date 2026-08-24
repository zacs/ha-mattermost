"""The Mattermost integration."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_NAME, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_DEFAULT_CHANNEL,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_HASS_CONFIG,
    DOMAIN,
    MATTERMOST_DATA,
)
from .coordinator import MattermostDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]

# Config entry only - no YAML configuration supported
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


class MattermostHTTPClient:
    """Simple HTTP client for Mattermost API."""

    def __init__(self, hass: HomeAssistant, base_url: str, token: str):
        """Initialize the client."""
        self.hass = hass
        self.base_url = base_url.rstrip("/")
        self.token = token
        # Use Bearer format as specified in Mattermost API docs
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "HomeAssistant-Mattermost",
        }

    async def test_connection(self) -> bool:
        """Test if the connection and authentication work.

        Compatibility notes:
        - Some older Mattermost servers (e.g. 10.x) may not expose certain
          endpoints exactly as newer ones do. We therefore:
          1) Ping the server (/api/v4/system/ping) to ensure reachability.
          2) Probe /api/v4/config/client if available (do not fail on 404).
          3) Attempt token auth with /api/v4/users/me.
          4) Fallback to /api/v4/hooks/incoming (200 or 403 indicates valid token/server).
        """
        async with aiohttp.ClientSession() as session:
            try:
                # 1) Ping server for basic reachability
                ping_url = f"{self.base_url}/api/v4/system/ping"
                try:
                    async with session.get(
                        ping_url,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=10),
                        ssl=False,
                    ) as ping_resp:
                        if ping_resp.status != 200:
                            error_text = await ping_resp.text()
                            _LOGGER.error(
                                "Server ping failed: %s - %s", ping_resp.status, error_text
                            )
                            return False
                        _LOGGER.debug("Server ping passed")
                except Exception as e:
                    _LOGGER.error("Server ping request failed: %s", e)
                    return False

                # 2) Try config/client - helpful on newer servers but may be absent on older ones.
                config_url = f"{self.base_url}/api/v4/config/client"
                try:
                    async with session.get(
                        config_url,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=10),
                        ssl=False,
                    ) as cfg_resp:
                        if cfg_resp.status == 200:
                            _LOGGER.debug("Config endpoint available")
                        else:
                            # Don't treat non-200 as fatal here; continue to auth checks.
                            _LOGGER.debug(
                                "Config endpoint returned status %s, continuing with auth checks",
                                cfg_resp.status,
                            )
                except Exception as e:
                    _LOGGER.debug("Config endpoint check failed (ignoring): %s", e)

                # 3) Primary token/auth check: users/me
                users_url = f"{self.base_url}/api/v4/users/me"
                try:
                    async with session.get(
                        users_url,
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                        ssl=False,
                    ) as user_resp:
                        if user_resp.status == 200:
                            user_data = await user_resp.json()
                            username = user_data.get("username", "unknown")
                            is_bot = user_data.get("is_bot", False)
                            _LOGGER.info(
                                "Successfully authenticated as bot user: %s", username
                            )
                            if not is_bot:
                                _LOGGER.warning(
                                    "User account is not marked as bot. Consider using a bot account."
                                )
                            return True
                        elif user_resp.status == 401:
                            _LOGGER.error("Bot authentication failed: 401 Unauthorized")
                        else:
                            text = await user_resp.text()
                            _LOGGER.debug("users/me returned %s: %s", user_resp.status, text)
                except Exception as e:
                    _LOGGER.debug("users/me request failed: %s", e)

                # 4) Fallback: try incoming webhooks - some tokens/servers respond here (200 or 403 means token/server usable)
                hooks_url = f"{self.base_url}/api/v4/hooks/incoming"
                try:
                    async with session.get(
                        hooks_url,
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                        ssl=False,
                    ) as hooks_resp:
                        if hooks_resp.status in (200, 403):
                            _LOGGER.debug(
                                "Webhooks endpoint indicates server/token valid (status %s)",
                                hooks_resp.status,
                            )
                            return True
                        _LOGGER.debug("Webhooks endpoint returned %s", hooks_resp.status)
                except Exception as e:
                    _LOGGER.debug("Webhooks endpoint check failed (ignoring): %s", e)

                _LOGGER.error(
                    "Authentication checks failed; token or permissions may be invalid"
                )
                return False

            except Exception as e:
                _LOGGER.error("Connection test failed: %s", e)
                return False

    async def post_message(self, channel: str, message: str, **kwargs) -> bool:
        """Post a message to a channel."""
        async with aiohttp.ClientSession() as session:
            try:
                # Get channel ID if needed
                channel_id = await self._get_channel_id(session, channel)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", channel)
                    return False

                post_data = {
                    "channel_id": channel_id,
                    "message": message,
                }

                # Add any additional post properties from kwargs
                if "props" in kwargs:
                    post_data["props"] = kwargs["props"]

                async with session.post(
                    f"{self.base_url}/api/v4/posts",
                    headers=self.headers,
                    json=post_data,
                    timeout=aiohttp.ClientTimeout(total=30),
                    ssl=False,
                ) as response:
                    if response.status != 201:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Failed to post message: %s - %s",
                            response.status,
                            error_text,
                        )
                        return False
                    return True
            except Exception as e:
                _LOGGER.error("Error posting message: %s", e)
                return False

    async def upload_file(
        self,
        channel: str,
        file_path: str,
        message: str = "",
        **kwargs,
    ) -> bool:
        """Upload a file to a channel and create a post with it."""

        # Read file in executor to avoid blocking the event loop
        def _read_file():
            with open(file_path, "rb") as f:
                return f.read()

        try:
            file_content = await self.hass.async_add_executor_job(_read_file)
        except Exception as e:
            _LOGGER.error("Error reading file %s: %s", file_path, e)
            return False

        filename = os.path.basename(file_path)

        async with aiohttp.ClientSession() as session:
            try:
                # Get channel ID
                channel_id = await self._get_channel_id(session, channel)
                if not channel_id:
                    return False

                # Step 1: Upload the file
                form = aiohttp.FormData()
                form.add_field("files", file_content, filename=filename)
                form.add_field("channel_id", channel_id)

                upload_headers = {
                    "Authorization": f"Bearer {self.token}",
                    "User-Agent": "HomeAssistant-Mattermost",
                }

                async with session.post(
                    f"{self.base_url}/api/v4/files",
                    headers=upload_headers,
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=60),
                    ssl=False,
                ) as response:
                    if response.status != 201:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Failed to upload file: %s - %s",
                            response.status,
                            error_text,
                        )
                        return False

                    file_response = await response.json()
                    file_infos = file_response.get("file_infos", [])
                    if not file_infos:
                        _LOGGER.error("File upload returned no file info")
                        return False

                    file_id = file_infos[0]["id"]

                # Step 2: Create a post with the uploaded file
                post_data = {
                    "channel_id": channel_id,
                    "message": message or "",
                    "file_ids": [file_id],
                }

                # Add any additional post properties from kwargs
                if "props" in kwargs:
                    post_data["props"] = kwargs["props"]

                async with session.post(
                    f"{self.base_url}/api/v4/posts",
                    headers=self.headers,
                    json=post_data,
                    timeout=aiohttp.ClientTimeout(total=30),
                    ssl=False,
                ) as response:
                    if response.status != 201:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Failed to create post with file: %s - %s",
                            response.status,
                            error_text,
                        )
                        return False
                    return True
            except Exception as e:
                _LOGGER.error("Error uploading file: %s", e)
                return False

    async def _get_channel_id(
        self, session: aiohttp.ClientSession, channel: str
    ) -> str | None:
        """Get channel ID from channel name or return channel ID if already provided."""
        # Remove # prefix if present
        channel_name = channel.lstrip("#")

        # Check if it's already a channel ID
        # (Mattermost channel IDs are 26 character alphanumeric strings)
        if len(channel_name) == 26 and channel_name.isalnum():
            _LOGGER.debug("Input appears to be a channel ID already: %s", channel_name)
            return channel_name

        try:
            # Try to get channel by name across all teams
            async with session.get(
                f"{self.base_url}/api/v4/teams", headers=self.headers, ssl=False
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error(
                        "Failed to get teams: %s - %s", response.status, error_text
                    )
                    return None

                teams = await response.json()

                for team in teams:
                    team_id = team["id"]
                    team_name = team.get("name", "unknown")

                    # First try: lookup by channel name (API name)
                    async with session.get(
                        f"{self.base_url}/api/v4/teams/{team_id}/channels/name/"
                        f"{channel_name}",
                        headers=self.headers,
                        ssl=False,
                    ) as channel_response:
                        if channel_response.status == 200:
                            channel_data = await channel_response.json()
                            return channel_data["id"]

                    # Second try: search all channels by display name
                    async with session.get(
                        f"{self.base_url}/api/v4/teams/{team_id}/channels",
                        headers=self.headers,
                        ssl=False,
                    ) as channels_response:
                        if channels_response.status == 200:
                            channels = await channels_response.json()
                            target_display_names = [f"#{channel_name}", channel_name]

                            for ch in channels:
                                display_name = ch.get("display_name", "")
                                if display_name in target_display_names:
                                    return ch["id"]

                _LOGGER.error(
                    "Channel '%s' not found in any team",
                    channel_name,
                )
                return None
        except Exception as e:
            _LOGGER.error(
                "Exception while looking up channel '%s': %s", channel_name, e
            )
            return None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Mattermost component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mattermost from a config entry."""
    config = entry.data

    try:
        # Clean up URL if needed
        url = config[CONF_URL]
        if "/api/v4" in url:
            url = url.split("/api/v4")[0]

        # Parse URL for proper format
        if not url.startswith(("http://", "https://")):
            # Default to HTTP for local IPs, HTTPS for domains
            if (
                url.startswith("192.168.")
                or url.startswith("10.")
                or url.startswith("127.")
                or "localhost" in url
            ):
                url = f"http://{url}"
            else:
                url = f"https://{url}"

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

    # Set up the binary_sensor platform via the standard config-entry mechanism.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up notify platform using discovery (legacy notify pattern).
    discovery_data = hass.data[DOMAIN][entry.entry_id].copy()
    discovery_data[CONF_NAME] = "mattermost"

    await discovery.async_load_platform(
        hass,
        Platform.NOTIFY,
        DOMAIN,
        discovery_data,
        config,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
