"""Mattermost REST API client."""

from __future__ import annotations

import logging
import os

import aiohttp
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def normalize_base_url(url: str) -> str:
    """Normalize a user-supplied Mattermost server URL.

    Strips a trailing /api/v4 if present, and infers http:// for local
    IPs/hostnames vs https:// for public domains when no scheme is given.
    """
    clean_url = url
    if "/api/v4" in clean_url:
        clean_url = clean_url.split("/api/v4")[0]

    if not clean_url.startswith(("http://", "https://")):
        if (
            clean_url.startswith("192.168.")
            or clean_url.startswith("10.")
            or clean_url.startswith("127.")
            or "localhost" in clean_url
        ):
            clean_url = f"http://{clean_url}"
        else:
            clean_url = f"https://{clean_url}"

    return clean_url


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

    async def get_me(self) -> dict | None:
        """Fetch the bot's own user record from /api/v4/users/me."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.base_url}/api/v4/users/me",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as response:
                    if response.status != 200:
                        _LOGGER.error(
                            "Could not fetch bot user record: %s", response.status
                        )
                        return None
                    return await response.json()
            except Exception as e:
                _LOGGER.error("Error fetching bot user record: %s", e)
                return None

    async def resolve_channel_id(self, channel: str) -> str | None:
        """Resolve a channel name (or pass through a channel ID) to a channel ID.

        This is the single public entry point for channel resolution -- callers
        outside this client should always use this method rather than opening
        their own session and reaching into _get_channel_id directly.
        """
        async with aiohttp.ClientSession() as session:
            return await self._get_channel_id(session, channel)

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
            # Try to get channel by name across all teams the bot belongs to.
            # Note: /api/v4/teams lists every team on the server and requires
            # the list_all_teams (sysadmin) permission -- an ordinary bot
            # account doesn't have that, so it must be /api/v4/users/me/teams
            # instead, which lists only the teams this account is a member of.
            async with session.get(
                f"{self.base_url}/api/v4/users/me/teams",
                headers=self.headers,
                ssl=False,
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

                    # Second try: search channels by display name, among the
                    # channels the bot has joined on this team.
                    async with session.get(
                        f"{self.base_url}/api/v4/users/me/teams/{team_id}/channels",
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
