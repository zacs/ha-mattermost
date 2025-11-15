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
    DATA_HASS_CONFIG,
    DOMAIN,
    MATTERMOST_DATA,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NOTIFY]

# Config entry only - no YAML configuration supported
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


class MattermostHTTPClient:
    """Simple HTTP client for Mattermost API."""

    def __init__(self, base_url: str, token: str):
        """Initialize the client."""
        self.base_url = base_url.rstrip("/")
        self.token = token
        # Use Bearer format as specified in Mattermost API docs
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "HomeAssistant-Mattermost",
        }

    async def test_connection(self) -> bool:
        """Test if the connection and authentication work."""
        async with aiohttp.ClientSession() as session:
            try:
                # First test basic connectivity
                async with session.get(
                    f"{self.base_url}/api/v4/config/client",
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Server connectivity failed: %s - %s",
                            response.status,
                            error_text,
                        )
                        return False
                    _LOGGER.debug("Server connectivity test passed")

                # Test authentication with the bot token
                async with session.get(
                    f"{self.base_url}/api/v4/users/me",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as response:
                    if response.status == 200:
                        user_data = await response.json()
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
                    else:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Bot authentication failed: %s - %s",
                            response.status,
                            error_text,
                        )
                        _LOGGER.error(
                            "Check that your bot token is valid and the bot has proper "
                            "permissions"
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
        self, channel: str, file_path: str, filename: str | None = None
    ) -> bool:
        """Upload a file to a channel."""
        async with aiohttp.ClientSession() as session:
            try:
                # Get channel ID
                channel_id = await self._get_channel_id(session, channel)
                if not channel_id:
                    return False

                with open(file_path, "rb") as f:
                    form = aiohttp.FormData()
                    form.add_field(
                        "files", f, filename=filename or os.path.basename(file_path)
                    )
                    form.add_field("channel_id", channel_id)

                    async with session.post(
                        f"{self.base_url}/api/v4/files",
                        headers=self.headers,
                        data=form,
                        timeout=aiohttp.ClientTimeout(total=60),
                        ssl=False,
                    ) as response:
                        return response.status == 201
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

        # Create and test HTTP client
        client = MattermostHTTPClient(url, config[CONF_API_KEY])
        if not await client.test_connection():
            raise ConfigEntryNotReady("Could not connect to Mattermost server")

    except Exception as err:
        _LOGGER.error("Failed to connect to Mattermost: %s", err)
        raise ConfigEntryNotReady from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_HASS_CONFIG: config,
    }

    # Set up notify platform using discovery
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
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        # Remove data
        hass.data[DOMAIN].pop(entry.entry_id)

    return True
