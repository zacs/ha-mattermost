"""Mattermost platform for notify component."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

from mattermostdriver import Driver
from mattermostdriver.exceptions import (
    InvalidOrMissingParameters,
    NotEnoughPermissions,
    ResourceNotFound,
)
import voluptuous as vol

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_TARGET,
    ATTR_TITLE,
    BaseNotificationService,
)
from homeassistant.const import CONF_PATH
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    ATTR_ATTACHMENTS,
    ATTR_AUTHOR_ICON,
    ATTR_AUTHOR_LINK,
    ATTR_AUTHOR_NAME,
    ATTR_COLOR,
    ATTR_FALLBACK,
    ATTR_FIELDS,
    ATTR_FILE,
    ATTR_FOOTER,
    ATTR_FOOTER_ICON,
    ATTR_IMAGE_URL,
    ATTR_PASSWORD,
    ATTR_PATH,
    ATTR_PRETEXT,
    ATTR_TEXT,
    ATTR_THUMB_URL,
    ATTR_TITLE as CONST_ATTR_TITLE,
    ATTR_TITLE_LINK,
    ATTR_URL,
    ATTR_USERNAME,
    CONF_DEFAULT_CHANNEL,
    DATA_CLIENT,
    MATTERMOST_DATA,
)

_LOGGER = logging.getLogger(__name__)

FILE_PATH_SCHEMA = vol.Schema({vol.Required(CONF_PATH): str})

FILE_URL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_URL): str,
        vol.Inclusive(ATTR_USERNAME, "credentials"): str,
        vol.Inclusive(ATTR_PASSWORD, "credentials"): str,
    }
)

ATTACHMENT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_FALLBACK): str,
        vol.Optional(ATTR_COLOR): str,
        vol.Optional(ATTR_PRETEXT): str,
        vol.Optional(ATTR_AUTHOR_NAME): str,
        vol.Optional(ATTR_AUTHOR_LINK): str,
        vol.Optional(ATTR_AUTHOR_ICON): str,
        vol.Optional(CONST_ATTR_TITLE): str,
        vol.Optional(ATTR_TITLE_LINK): str,
        vol.Optional(ATTR_TEXT): str,
        vol.Optional(ATTR_FIELDS): list,
        vol.Optional(ATTR_IMAGE_URL): str,
        vol.Optional(ATTR_THUMB_URL): str,
        vol.Optional(ATTR_FOOTER): str,
        vol.Optional(ATTR_FOOTER_ICON): str,
    }
)

DATA_FILE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_FILE): vol.Any(FILE_PATH_SCHEMA, FILE_URL_SCHEMA),
    }
)

DATA_TEXT_ONLY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ATTACHMENTS): [ATTACHMENT_SCHEMA],
    }
)

DATA_SCHEMA = vol.All(
    vol.Any(DATA_FILE_SCHEMA, DATA_TEXT_ONLY_SCHEMA, None)
)


async def async_get_service(
    hass: HomeAssistant,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
) -> MattermostNotificationService | None:
    """Set up the Mattermost notification service."""
    if discovery_info:
        return MattermostNotificationService(
            hass,
            discovery_info[MATTERMOST_DATA][DATA_CLIENT],
            discovery_info,
        )
    return None


@callback
def _get_filename_from_url(url: str) -> str:
    """Return the filename of a passed URL."""
    parsed_url = urlparse(url)
    return os.path.basename(parsed_url.path)


@callback
def _sanitize_channel_names(channel_list: list[str]) -> list[str]:
    """Remove any # symbols from a channel list."""
    return [channel.lstrip("#") for channel in channel_list]


class MattermostNotificationService(BaseNotificationService):
    """Define the Mattermost notification logic."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: Driver,
        config: dict[str, str],
    ) -> None:
        """Initialize."""
        self._hass = hass
        self._client = client
        self._config = config

    async def async_send_message(self, message: str, **kwargs: Any) -> None:
        """Send a message to Mattermost."""
        data = kwargs.get(ATTR_DATA) or {}

        try:
            DATA_SCHEMA(data)
        except vol.Invalid as err:
            _LOGGER.error("Invalid message data: %s", err)
            data = {}

        title = kwargs.get(ATTR_TITLE)
        targets = _sanitize_channel_names(
            kwargs.get(ATTR_TARGET, [self._config[CONF_DEFAULT_CHANNEL]])
        )

        # Message Type 1: A text-only message (possibly with attachments)
        if ATTR_FILE not in data:
            return await self._async_send_text_message(
                targets, message, title, data.get(ATTR_ATTACHMENTS)
            )

        # Message Type 2: A file message
        file_data = data[ATTR_FILE]
        if CONF_PATH in file_data:
            return await self._async_send_local_file_message(
                file_data[CONF_PATH], targets, message, title
            )
        
        return await self._async_send_remote_file_message(
            file_data[ATTR_URL],
            targets,
            message,
            title,
            username=file_data.get(ATTR_USERNAME),
            password=file_data.get(ATTR_PASSWORD),
        )

    async def _async_send_text_message(
        self,
        targets: list[str],
        message: str,
        title: str | None,
        attachments: list[dict] | None = None,
    ) -> None:
        """Send a text-only message to Mattermost."""
        full_message = f"**{title}**\n\n{message}" if title else message
        
        # Prepare post data
        post_data = {
            "message": full_message,
            "props": {
                "from_webhook": "true",
            }
        }
        
        # Add default author info to attachments if not provided
        if attachments:
            for attachment in attachments:
                if ATTR_AUTHOR_NAME not in attachment:
                    attachment[ATTR_AUTHOR_NAME] = "Home Assistant"
                if ATTR_AUTHOR_ICON not in attachment:
                    attachment[ATTR_AUTHOR_ICON] = "https://www.home-assistant.io/images/favicon-192x192-full.png"
            post_data["props"]["attachments"] = attachments

        for target in targets:
            try:
                # Get channel ID
                channel_id = await self._async_get_channel_id(target)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", target)
                    continue

                post_data["channel_id"] = channel_id
                
                # Send the message
                await self._hass.async_add_executor_job(
                    self._client.posts.create_post, options=post_data
                )
                
            except Exception as err:
                _LOGGER.error("Failed to send message to %s: %s", target, err)

    async def _async_send_local_file_message(
        self,
        file_path: str,
        targets: list[str],
        message: str,
        title: str | None,
    ) -> None:
        """Upload a local file (with message) to Mattermost."""
        if not self._hass.config.is_allowed_path(file_path):
            _LOGGER.error("Path does not exist or is not allowed: %s", file_path)
            return

        if not os.path.isfile(file_path):
            _LOGGER.error("File does not exist: %s", file_path)
            return

        filename = os.path.basename(file_path)
        
        for target in targets:
            try:
                # Get channel ID
                channel_id = await self._async_get_channel_id(target)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", target)
                    continue

                # Upload the file
                with open(file_path, "rb") as file_obj:
                    file_upload = await self._hass.async_add_executor_job(
                        self._client.files.upload_file,
                        channel_id,
                        {"files": (filename, file_obj)}
                    )
                
                file_id = file_upload["file_infos"][0]["id"]
                
                # Create post with file attachment
                full_message = f"**{title}**\n\n{message}" if title else message
                post_data = {
                    "channel_id": channel_id,
                    "message": full_message,
                    "file_ids": [file_id],
                    "props": {
                        "from_webhook": "true",
                        "attachments": [{
                            "author_name": "Home Assistant",
                            "author_icon": "https://www.home-assistant.io/images/favicon-192x192-full.png"
                        }]
                    }
                }
                
                await self._hass.async_add_executor_job(
                    self._client.posts.create_post, options=post_data
                )
                
            except Exception as err:
                _LOGGER.error("Failed to send file to %s: %s", target, err)

    async def _async_send_remote_file_message(
        self,
        url: str,
        targets: list[str],
        message: str,
        title: str | None,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Upload a remote file (with message) to Mattermost."""
        if not self._hass.config.is_allowed_external_url(url):
            _LOGGER.error("URL is not allowed: %s", url)
            return

        filename = _get_filename_from_url(url)
        
        # Import aiohttp here to avoid issues if not available
        try:
            import aiohttp
            from homeassistant.helpers import aiohttp_client
        except ImportError:
            _LOGGER.error("aiohttp not available for remote file downloads")
            return

        session = aiohttp_client.async_get_clientsession(self._hass)
        
        # Fetch the remote file
        auth = aiohttp.BasicAuth(username, password) if username and password else None

        try:
            async with session.get(url, auth=auth) as resp:
                resp.raise_for_status()
                file_content = await resp.read()
        except Exception as err:
            _LOGGER.error("Failed to download file from %s: %s", url, err)
            return

        for target in targets:
            try:
                # Get channel ID
                channel_id = await self._async_get_channel_id(target)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", target)
                    continue

                # Upload the file from memory
                import io
                file_obj = io.BytesIO(file_content)
                file_upload = await self._hass.async_add_executor_job(
                    self._client.files.upload_file,
                    channel_id,
                    {"files": (filename, file_obj)}
                )
                
                file_id = file_upload["file_infos"][0]["id"]
                
                # Create post with file attachment
                full_message = f"**{title}**\n\n{message}" if title else message
                post_data = {
                    "channel_id": channel_id,
                    "message": full_message,
                    "file_ids": [file_id],
                    "props": {
                        "from_webhook": "true",
                        "attachments": [{
                            "author_name": "Home Assistant",
                            "author_icon": "https://www.home-assistant.io/images/favicon-192x192-full.png"
                        }]
                    }
                }
                
                await self._hass.async_add_executor_job(
                    self._client.posts.create_post, options=post_data
                )
                
            except Exception as err:
                _LOGGER.error("Failed to send remote file to %s: %s", target, err)

    async def _async_get_channel_id(self, channel_name: str) -> str | None:
        """Get channel ID from channel name."""
        try:
            # First, try to get channel by name (assuming it's in the user's team)
            channel = await self._hass.async_add_executor_job(
                self._client.channels.get_channel_by_name, channel_name
            )
            return channel["id"]
        except (ResourceNotFound, InvalidOrMissingParameters):
            try:
                # If that fails, try to search for the channel
                channels = await self._hass.async_add_executor_job(
                    self._client.channels.search_channels, options={"term": channel_name}
                )
                for channel in channels:
                    if channel["name"] == channel_name or channel["display_name"] == channel_name:
                        return channel["id"]
            except Exception as err:
                _LOGGER.warning("Could not search for channel %s: %s", channel_name, err)
        
        _LOGGER.error("Could not find channel: %s", channel_name)
        return None